"""GUI grounding — turning a screen into things you can actually click (Phase 56).

For the whole project NOVA has been blind to GUIs: it could grab a screenshot but
extracted nothing from it, ``ui_locator.locate_by_text_hint`` was a ``return
None`` stub, and ``screen.click`` refuses raw coordinates and demands a verified
``UiTarget`` that nothing could produce. So "click Submit" / "fill the email
field" had no path. This is the bridge that was missing: text label -> a specific
on-screen target with coordinates and a confidence.

Two design commitments:

  * **The tree is injectable.** The real backend walks the Windows UIAutomation
    accessibility tree (``uiautomation``), which gives exact element rectangles,
    labels and roles — deterministic, no vision model, no tokens. But every
    function takes an optional ``provider``/element list, so the ranking logic is
    tested against fabricated trees with no real desktop, and the whole thing
    degrades to "no targets" (exactly today's behaviour) when the library is
    absent or the flag is off. Install ``uiautomation`` and set
    ``EVA_GUI_GROUNDING_ENABLED=1`` to give NOVA real eyes.

  * **Clicking the WRONG thing is the harm to design against.** The matcher is
    conservative: it strips role words from the query, scores the label, applies
    a role-affinity factor, and zeroes out anything disabled or off-screen. The
    caller still enforces a confidence floor (``screen.click`` wants >= 0.75), so
    a weak match yields *no* click rather than a wrong one.

Pure and fail-safe throughout: any error anywhere yields "no targets", never a
guess, and never raises into the gate.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

from .ui_locator import UiTarget

_FALSY = {"", "0", "false", "no", "off"}

# Bounds on the real tree walk: a foreground window can have thousands of nodes,
# and UIAutomation calls cross a COM boundary. Cap both so grounding cannot hang.
_MAX_NODES = 600
_MAX_DEPTH = 14

# Default confidence a caller must clear to act. Mirrors screen.click's floor.
_DEFAULT_MIN_CONFIDENCE = 0.75

# When the top two matches are within this confidence margin of each other (and
# both clear the floor), the query is AMBIGUOUS — there are two controls it could
# mean, so grounding refuses to pick one rather than risk clicking the wrong one.
_AMBIGUITY_MARGIN = 0.08

# Phase 63: roles that are actual click targets. Used only as a TIE-BREAK
# inside resolve()'s ambiguity margin (see there) -- never to exclude a role
# from matching or scoring in the first place. Some apps legitimately expose
# clickable things as "Text", so this is deliberately not a filter.
_INTERACTIVE_ROLES = frozenset({
    "button", "splitbutton", "hyperlink", "link", "menuitem", "menu",
    "checkbox", "radiobutton", "togglebutton", "tabitem", "tab",
    "listitem", "edit", "combobox", "slider", "spinner",
})


def _is_interactive_role(role: str) -> bool:
    return str(role or "").strip().lower() in _INTERACTIVE_ROLES


# Query words that name a control ROLE rather than its label. They are removed
# from the label match and used instead to prefer the right kind of control.
_ROLE_SYNONYMS: dict[str, frozenset[str]] = {
    "button": frozenset({"button", "splitbutton"}),
    "field": frozenset({"edit", "text", "document"}),
    "input": frozenset({"edit", "text"}),
    "textbox": frozenset({"edit", "text"}),
    "textfield": frozenset({"edit", "text"}),
    "checkbox": frozenset({"checkbox"}),
    "check": frozenset({"checkbox"}),
    "radio": frozenset({"radiobutton"}),
    "link": frozenset({"hyperlink", "link"}),
    "dropdown": frozenset({"combobox"}),
    "combo": frozenset({"combobox"}),
    "combobox": frozenset({"combobox"}),
    "menu": frozenset({"menuitem", "menu"}),
    "menuitem": frozenset({"menuitem"}),
    "tab": frozenset({"tabitem", "tab"}),
    "toggle": frozenset({"togglebutton", "checkbox"}),
    "switch": frozenset({"togglebutton"}),
}


@dataclass(frozen=True)
class RawElement:
    """One control from an accessibility tree — provider-agnostic."""

    name: str
    role: str
    left: int
    top: int
    width: int
    height: int
    enabled: bool = True
    on_screen: bool = True

    @property
    def center(self) -> tuple[int, int]:
        return (self.left + self.width // 2, self.top + self.height // 2)


def grounding_enabled(environ: dict[str, str] | None = None) -> bool:
    """Whether GUI grounding is active. Default OFF (fail safe)."""
    env = environ if environ is not None else os.environ
    return env.get("EVA_GUI_GROUNDING_ENABLED", "").strip().lower() not in _FALSY


# -- the matcher (pure) -----------------------------------------------------

def _normalize(text: object) -> str:
    return " ".join(str(text or "").split()).strip().lower()


def _tokens(text: str) -> list[str]:
    return [t for t in text.replace("&", " ").replace("_", " ").split() if t]


def _split_query(query: str) -> tuple[str, frozenset[str]]:
    """Return (core label text, role synonym set) for a query.

    Role words ("button", "field", ...) are removed from the label text so
    "email field" matches a control literally named "Email", and are turned into
    the set of control roles that satisfy the query.
    """
    role_roles: set[str] = set()
    core: list[str] = []
    for token in _tokens(_normalize(query)):
        if token in _ROLE_SYNONYMS:
            role_roles |= set(_ROLE_SYNONYMS[token])
        else:
            core.append(token)
    core_text = " ".join(core) if core else _normalize(query)
    return core_text, frozenset(role_roles)


def _label_score(core_query: str, name: str) -> float:
    """How well a control's label matches the (role-stripped) query. 0..1."""
    if not core_query or not name:
        return 0.0
    if core_query == name:
        return 1.0
    if core_query in name:
        return 0.9
    if name in core_query:
        return 0.85
    q_set, n_set = set(_tokens(core_query)), set(_tokens(name))
    if not q_set or not n_set:
        return 0.0
    overlap = len(q_set & n_set) / len(q_set | n_set)
    return round(0.8 * overlap, 4)


def score_element(query: str, element: RawElement) -> float:
    """Confidence that ``element`` is what ``query`` refers to. Pure, 0..1.

    Zero for anything that cannot be clicked (off-screen or zero-size). Disabled
    controls are heavily penalised, not zeroed, so "the greyed-out Save button"
    can still be *reported* as the best match to explain why nothing happened.
    """
    if element.width <= 0 or element.height <= 0 or not element.on_screen:
        return 0.0

    core_query, wanted_roles = _split_query(query)
    label = _label_score(core_query, _normalize(element.name))
    if label <= 0.0:
        return 0.0

    role = _normalize(element.role)
    if wanted_roles:
        if role in wanted_roles:
            label = min(1.0, label + 0.05)      # right kind of control: small boost
        else:
            label *= 0.6                          # wrong kind: strong penalty

    if not element.enabled:
        label *= 0.4

    return round(max(0.0, min(1.0, label)), 4)


def rank_targets(query: str, elements: list[RawElement], *, floor: float = 0.0) -> list[UiTarget]:
    """All elements scoring above ``floor``, best first, as clickable UiTargets."""
    scored: list[tuple[float, RawElement]] = []
    for element in elements:
        try:
            confidence = score_element(query, element)
        except Exception:
            confidence = 0.0
        if confidence > floor:
            scored.append((confidence, element))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    targets: list[UiTarget] = []
    for confidence, element in scored:
        cx, cy = element.center
        targets.append(
            UiTarget.from_dict(
                {
                    "label": element.name,
                    "role": element.role,
                    "x": cx,
                    "y": cy,
                    "width": element.width,
                    "height": element.height,
                    "confidence": confidence,
                    "method": "uiautomation",
                }
            )
        )
    return targets


# -- the tree provider (real backend, injectable) ---------------------------

def _uiautomation_elements() -> list[RawElement]:
    """Walk the foreground window's UIAutomation tree into RawElements.

    Bounded in depth and node count so it cannot hang. Returns ``[]`` if the
    library is unavailable or anything goes wrong — grounding then yields no
    targets, which is exactly the pre-Phase-56 behaviour (a safe no-op)."""
    try:
        import uiautomation as auto  # type: ignore
    except Exception:
        return []
    try:
        root = auto.GetForegroundControl()
    except Exception:
        return []
    if root is None:
        return []

    collected: list[RawElement] = []
    stack: list[tuple[object, int]] = [(root, 0)]
    while stack and len(collected) < _MAX_NODES:
        control, depth = stack.pop()
        try:
            name = str(getattr(control, "Name", "") or "")
            rect = getattr(control, "BoundingRectangle", None)
            role = str(getattr(control, "ControlTypeName", "") or "")
            if role.endswith("Control"):
                role = role[: -len("Control")]
            if name and rect is not None:
                left, top = int(rect.left), int(rect.top)
                width, height = int(rect.right - rect.left), int(rect.bottom - rect.top)
                collected.append(
                    RawElement(
                        name=name,
                        role=role,
                        left=left,
                        top=top,
                        width=width,
                        height=height,
                        enabled=bool(getattr(control, "IsEnabled", True)),
                        on_screen=not bool(getattr(control, "IsOffscreen", False)),
                    )
                )
            if depth < _MAX_DEPTH:
                for child in control.GetChildren() or []:
                    stack.append((child, depth + 1))
        except Exception:
            continue
    return collected


# Module-level provider hook. Reassign in tests to feed a fabricated tree; the
# default reads the live UIAutomation tree (or yields [] when unavailable).
_default_provider: Callable[[], list[RawElement]] = _uiautomation_elements


def enumerate_elements(provider: Callable[[], list[RawElement]] | None = None) -> list[RawElement]:
    """Every clickable control on screen right now, or ``[]`` if unavailable."""
    if not grounding_enabled():
        return []
    source = provider or _default_provider
    # Read coordinates in the same DPI space the click path acts in, so a scaled
    # display does not shift every target (see dpi.py). Only matters for the real
    # UIAutomation reader; harmless (idempotent) for injected providers.
    if source is _default_provider:
        try:
            from .dpi import ensure_dpi_aware

            ensure_dpi_aware()
        except Exception:
            pass
    try:
        return list(source() or [])
    except Exception:
        return []


@dataclass(frozen=True)
class Resolution:
    """The result of resolving a query to a target — found, none, or ambiguous."""

    status: str                       # "found" | "none" | "ambiguous"
    target: UiTarget | None
    candidates: tuple[UiTarget, ...]
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "target": self.target.as_dict() if self.target else None,
            "candidates": [c.as_dict() for c in self.candidates],
            "reason": self.reason,
        }


def resolve(
    query: str,
    *,
    provider: Callable[[], list[RawElement]] | None = None,
    min_confidence: float = _DEFAULT_MIN_CONFIDENCE,
    margin: float = _AMBIGUITY_MARGIN,
) -> Resolution:
    """Resolve ``query`` to a single target, or explain why it can't.

    "found" only when there is ONE clear best above the floor. When the top two
    matches are within ``margin`` of each other (both above the floor), the
    result is "ambiguous" and lists the tied candidates — grounding declines to
    guess which the user meant. "none" when nothing clears the floor."""
    if not str(query or "").strip():
        return Resolution("none", None, (), "empty query")
    ranked = rank_targets(query, enumerate_elements(provider), floor=0.0)
    if not ranked:
        return Resolution("none", None, (), "no controls matched")
    best = ranked[0]
    if best.confidence < float(min_confidence):
        return Resolution("none", None, tuple(ranked[:5]), f"best match {best.confidence:.2f} is below the {float(min_confidence):.2f} floor")
    tied = [t for t in ranked if t.confidence >= float(min_confidence) and (best.confidence - t.confidence) < float(margin)]
    if len(tied) >= 2:
        # Phase 63 tie-break: a login page whose <h1> heading reads "Sign in"
        # right next to a "Sign in" BUTTON is an extremely common pattern, and
        # it used to make every such page's submit button unreachable by
        # label -- resolve() saw three equally-scored "Sign in" candidates
        # (the button and two static text nodes for the heading) and refused,
        # exactly as Phase 59 designed it to when it truly cannot tell which
        # control is meant. But a static text node is never a click target a
        # user meant when an interactive control with the same label exists
        # in the same tie -- a heading is not a button -- so when EXACTLY ONE
        # tied candidate is interactive, that is the answer, not an ambiguity.
        #
        # This is intentionally narrow, so it cannot become a general
        # "prefer buttons" rule that overrides real scoring:
        #   * It only ever looks inside the tied set that already exists
        #     above -- a clearly better STATIC match (outside the margin) is
        #     never reached here at all, because `tied` would have length 1.
        #   * Two tied INTERACTIVE candidates (two "OK" buttons) still refuse
        #     exactly as before: interactive_tied below has length 2, not 1.
        #   * Roles are never excluded from matching or scoring (some apps
        #     legitimately expose clickable things as "Text") -- this is a
        #     tie-break, not a filter.
        interactive_tied = [t for t in tied if _is_interactive_role(t.role)]
        if len(interactive_tied) == 1:
            winner = interactive_tied[0]
            return Resolution(
                "found",
                winner,
                tuple(ranked[:5]),
                f"'{query}' tied between {len(tied)} controls; picked the one interactive candidate over the static ones",
            )
        return Resolution("ambiguous", None, tuple(tied[:5]), f"{len(tied)} controls match '{query}' about equally; be more specific")
    return Resolution("found", best, tuple(ranked[:5]), "one clear match")


def locate(
    query: str,
    *,
    provider: Callable[[], list[RawElement]] | None = None,
    min_confidence: float = _DEFAULT_MIN_CONFIDENCE,
) -> UiTarget | None:
    """The single best on-screen target for ``query``, or ``None``.

    ``None`` (not a low-confidence guess) whenever grounding is off, the tree is
    empty, nothing clears ``min_confidence``, OR the match is ambiguous — so a
    caller acts only on a target it can trust, and otherwise does nothing. Use
    :func:`resolve` when you want to tell "not found" from "ambiguous"."""
    return resolve(query, provider=provider, min_confidence=min_confidence).target


def locate_candidates(
    query: str,
    *,
    provider: Callable[[], list[RawElement]] | None = None,
    limit: int = 5,
) -> list[UiTarget]:
    """Ranked candidate targets for a query — for diagnostics/observation."""
    return rank_targets(query, enumerate_elements(provider), floor=0.0)[: max(1, int(limit))]


# -- describing the whole screen (Phase 57) ---------------------------------

def _target_dict(element: RawElement) -> dict[str, object]:
    cx, cy = element.center
    return {
        "label": element.name,
        "role": element.role,
        "x": cx,
        "y": cy,
        "width": element.width,
        "height": element.height,
        "enabled": element.enabled,
        # Existence, not a query match — observation lists what IS on screen;
        # actually clicking still resolves a specific label via locate().
        "confidence": 1.0,
        "method": "uiautomation",
    }


def describe_visible(
    *,
    provider: Callable[[], list[RawElement]] | None = None,
    limit: int = 20,
) -> dict[str, object]:
    """Enumerate the clickable controls on screen into a plain, readable report.

    This is what makes ``screen.observe`` actually useful: instead of just the
    window title it can now say what is on screen and where. Pure and injectable,
    flag-gated, fail-safe — returns an empty report (not an error) when grounding
    is off, the library is absent, or anything goes wrong.
    """
    try:
        elements = enumerate_elements(provider)
    except Exception:
        elements = []
    targets: list[dict[str, object]] = []
    for element in elements:
        if element.width <= 0 or element.height <= 0 or not element.on_screen or not element.name.strip():
            continue
        targets.append(_target_dict(element))
        if len(targets) >= max(1, int(limit)):
            break
    return {"ui_targets": targets, "count": len(targets), "summary": _summarize_targets(targets)}


def _summarize_targets(targets: list[dict[str, object]]) -> str:
    if not targets:
        return ""
    shown = targets[:8]
    parts = [f"{t['label']} ({t['role'] or 'control'})" for t in shown]
    more = f", +{len(targets) - len(shown)} more" if len(targets) > len(shown) else ""
    return f"Visible controls ({len(targets)}): " + "; ".join(parts) + more + "."


__all__ = [
    "RawElement",
    "UiTarget",
    "grounding_enabled",
    "score_element",
    "rank_targets",
    "enumerate_elements",
    "locate",
    "resolve",
    "Resolution",
    "locate_candidates",
    "describe_visible",
]
