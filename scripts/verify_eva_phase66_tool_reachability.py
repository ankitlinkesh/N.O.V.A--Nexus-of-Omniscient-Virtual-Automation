"""Standalone verifier for Phase 66: no registered tool may be stranded.

Five times now a capability shipped registered, gated, and documented -- and
wired to NOTHING, so it could never actually run in production. Concretely:
``voice.listen_once`` existed since Phase 49b and nothing called it until
Phase 61 wired it up. ``app.focus`` was registered and gated and reachable
from nowhere until Phase 64. Both shipped "green" many phases apart, because
every test that exercised them called the function directly -- the gap was
that no PRODUCTION path did. Tests proved the tool WORKS; nothing proved
anything could ever REACH it.

WHAT "REACHABLE" ACTUALLY MEANS -- READ THIS BEFORE TOUCHING THE METHOD

This verifier is deliberately NOT about whether a tool is *callable*.
``/api/tools/{tool_name}`` calls ``tools.run(tool_name, **body)`` for ANY
registered tool, so every one of the 100 tools this file examines is already
callable in principle through that generic, header-guarded endpoint. That is
exactly the shape of the ``listen_once``/``app.focus`` bug: both were
callable in principle the whole time; nothing in the product ever chose to
call them. So the question this file answers is narrower and harder: does
something in the FIXED, shipped product -- a console command handler, a
capability router, a form filler, a default action tag on the tool's own
observation record -- actually ROUTE to this tool for some real situation?
A tool being technically reachable through a generic pass-through (the HTTP
endpoint, or a user-authored "skill" that can name any tool at all) does not
answer that question, because nothing in FIXED code decided to call that
*specific* tool -- the name came from outside, the same way it would for any
other tool. Keep that distinction in mind before treating a new kind of
"mention" as evidence.

THE INVARIANT

Every tool in ``ToolRegistry._tools`` must be reachable by at least one of:

  (a) planner-visible -- its name appears in ``reg.planner_specs()`` under
      the UNION of flag states we check here (default env, and
      ``EVA_V2_PLAYWRIGHT_ENABLED=true``), or
  (b) referenced by production source -- its name appears as an exact
      string-literal constant in a non-test, non-verifier Python module
      other than ``registry.py`` or ``roadmap/catalog.py`` (see EXCLUSIONS
      below for why those two specifically are disqualified), e.g. the
      console handlers in ``eva/core/fast_commands.py``.

"Production source" here means every ``.py`` file under ``backend/eva/``
except the two exclusions. Tests (``backend/tests/``) and verifiers
(``scripts/verify_*.py``) are excluded on purpose: a test calling a tool
proves the tool WORKS, not that anything in the shipped product can ever
reach it -- that conflation is exactly how the five prior bugs shipped
green.

EXCLUSIONS, AND WHY EACH ONE EXISTS

  * ``eva/tools/registry.py`` -- every tool's own ``ToolSpec`` entry lives
    here, so its name necessarily appears here regardless of whether
    anything else in the product ever calls it. Counting it would make
    every tool trivially "reachable".

  * ``eva/roadmap/catalog.py`` -- added after this verifier's first
    real-world use caught the same laundering pattern in a new costume.
    The first version of this file counted a catalog.py entry as a valid
    production reference, and it looked plausible: ``app.open`` and
    ``screen.click`` both have ``ExecutionBoundary`` entries there, so both
    looked "referenced". But ``get_execution_boundary_catalog()`` is
    declarative metadata read by the ``eva execution boundaries`` report --
    it does not route a call, any more than a comment does. Two genuinely
    stranded tools (``app.open`` and ``file.patch_text``, see below) were
    masked behind exactly this: an ``ExecutionBoundary`` entry that made the
    scan count them as referenced while nothing in the product actually
    called them. Counting a catalog OF tools as a caller of those tools is
    circular by construction -- it always mentions every tool it documents,
    whether or not anything routes to it -- so it is excluded here the same
    way ``registry.py`` is, and for the same reason: a file whose entire
    purpose is to enumerate tool names is not evidence that any of them are
    used.

  Other files that classify or describe tools without calling them were
  spot-checked while investigating the catalog.py masking (a security
  audit's classification sets in ``eva/security/action_audit.py``; the
  "agents" framework's capability-to-agent-class discovery metadata in
  ``eva/agents/*.py``, which is explicitly documented elsewhere in that
  package as "discovery metadata only" and not yet real execution). None of
  those turned out to be any tool's *only* production reference -- every
  tool touched by them also has a real caller elsewhere -- so excluding them
  did not change the computed set. That was checked, not assumed, but it is
  also not a closed question: a file structured like ``catalog.py`` (mentions
  many tool names, calls none of them) is a standing risk for this scan
  method in general, and a future one could mask a new stranded tool the
  same way until someone excludes it too. This verifier's method is a proxy
  for "something routes to it", not a proof; treat any new exclusion the way
  ``catalog.py`` was added here -- with a specific, checked reason, not a
  standing allowance for "descriptive-looking" files in general.

HOW THIS DIFFERS FROM test_planner_reachability.py

``backend/tests/test_planner_reachability.py`` already exists and asserts
the OPPOSITE, security-facing direction: that ``screen.*``/``web.*``/``mcp.*``
tools are *not* planner-visible by default (some of that invisibility is
permanent and deliberate -- ``screen.*`` must never be planner-reachable
regardless of flags, because giving an LLM planner direct mouse/keyboard
control is a standing safety decision, not a gap). This verifier asserts the
complementary invariant: every tool REGISTERED in ``ToolRegistry._tools``
is reachable by *some* production path, planner or otherwise. A tool can
correctly satisfy ``test_planner_reachability.py`` (permanently hidden from
the planner) while still needing to pass THIS verifier via a production
caller -- e.g. ``screen.click`` is planner-invisible by design, but reachable
through ``eva/screen/form_filler.py``'s ``run("screen.click", ...)`` call.
Both files must keep passing; neither subsumes the other.

METHOD, AND ITS LIMITATIONS

The scan is AST-based, not a text grep: for every production file (outside
the two exclusions above) we parse the module and collect every
``ast.Constant`` string node's exact value. A tool name counts as referenced
only if some string literal in the file is EXACTLY EQUAL to it -- not merely
containing it as a substring. Two consequences fall out of that for free,
both confirmed against real instances found while writing this verifier:

  * Comments are invisible. The tokenizer strips them before the parser
    ever builds a node, so a comment like
    ``# *** NOT registry.run("screen.click", ...) ***`` (a real comment in
    ``eva/screen/screen_tools.py``) contributes nothing -- correctly, since
    a comment is not a reachable code path. (screen.click has other, real,
    non-comment references, so this particular case was never a false
    negative; it is called out here because it is the concrete case that
    proved the exact-match approach was necessary rather than a plain grep.)
  * A docstring merely MENTIONING a tool name in prose (e.g. "...call
    screen.click to press the button...") does not count, because the full
    string constant does not equal the tool name. A docstring or string
    constant whose ENTIRE value happens to equal a tool name verbatim WOULD
    still count as a reference -- this is a known, accepted imprecision:
    manually auditing all 104 tools while building this verifier found no
    such case, but the exact-match approach cannot structurally rule it out
    for future tools.

Dynamically-built tool names (an f-string, string concatenation, or a name
assembled in a loop) are invisible to this scan by construction -- there is
no string constant equal to the assembled name for the AST walk to find.
The only such case among the tools registered in a default environment is
``mcp.*``: ``eva/mcp/registration.py`` builds MCP tool names as
``f"mcp.{server.name}.{tool_name}"``. This is handled honestly, not papered
over: MCP tool specs are merged into ``self._tools`` only when the MCP
subsystem has actually loaded them (enabled + configured), so in the default
environment this verifier runs in, ``mcp.*`` names are simply ABSENT from
``ToolRegistry._tools`` -- there is nothing to classify as reachable or
unreachable, honestly mirroring what ``test_planner_reachability.py``
already documents about the same cache. ``web.*`` tools are NOT built
dynamically (each is a literal ``ToolSpec`` entry in ``registry.py``) and
are covered by planner-visibility under the Playwright-enabled flag state,
not by this source-scan at all.

THE PIN

``EXPECTED_UNREACHABLE`` is the reviewed set: tool name -> written
justification for why it is intentionally exempt. It is compared to the
computed unreachable set by EXACT MATCH, both directions -- a newly
stranded tool fails the build (it is not yet in the reviewed set), and a
tool that became reachable but is still listed also fails (the list cannot
silently rot into over-broad cover).

As first shipped, the reviewed set had FOUR entries -- a genuine finding, not
a scanner artifact. The first pass at this verifier excluded only
``registry.py`` and treated a ``roadmap/catalog.py`` entry as a valid
reference; under that method only ``app.close_request`` and ``file.read_text``
looked stranded, and both were "fixed" by giving them a catalog entry. That
fix was wrong -- it satisfied the scan without making either tool any more
callable-from-the-product than before (see the EXCLUSIONS section above).
Once ``catalog.py`` was correctly excluded, TWO MORE tools that had been
masked behind their own catalog entry surfaced: ``app.open`` and
``file.patch_text``. All four turned out to be a shadow family of dotted
tools duplicating a working, actually-routed alternative:

  * ``app.close_request`` -> superseded by ``close_app`` (what the console
    "close app"/"close" commands in ``eva/core/fast_commands.py`` route to).
  * ``app.open`` -> superseded by ``open_app`` (planner-visible, and what
    the console "open" commands route to). ``app.open`` itself was not
    broken: Phase 64 gave it a correct ``app_window_open`` postcondition and
    it was live-verified working (``reg.run("app.open", app="notepad")``
    really opened Notepad and correctly reported success) -- it simply had
    no caller.
  * ``file.patch_text`` -> superseded by ``file.write_text`` (its own
    implementation, ``safe_file_tools.file_patch_text``, delegated to
    ``file_write_text`` for the actual write; it was ``file.write_text``, not
    ``file.patch_text``, that other production code actually referenced).
  * ``file.read_text`` -> superseded by ``workspace_read_file``
    (planner-visible, allowlist-bounded, what workspace reads route
    through).

Each was retained deliberately rather than deleted at the time, in case a
future phase wired it up on purpose. Phase 70 revisited that call: no phase
ever did wire any of the four up, each still had a confirmed working
counterpart, and letting a reviewed-but-permanent exemption list stand in
for deletion just gives duplication a paper trail instead of removing it.
Before deleting ``app.open``, its one genuinely load-bearing property -- the
accurate, independently-checked ``app_window_open`` postcondition Phase 64
gave it -- was moved onto ``open_app`` (the tool actually being routed to),
so the routed path gained real verification instead of losing it. All four
tools, their registry entries, and their remaining code paths were deleted;
``EXPECTED_UNREACHABLE`` is now empty and ``EXPECTED_TOOL_COUNT`` dropped
from 104 to 100. ``app.close_request`` was ``SYSTEM_CHANGE`` while its
survivor ``close_app`` stays the less-gated ``SAFE_LOCAL_UI`` -- that
asymmetry was noted, not resolved; risk (re)classification is a separate
decision from reachability and out of scope here.
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BACKEND_EVA = ROOT / "backend" / "eva"
REGISTRY_FILE = (BACKEND_EVA / "tools" / "registry.py").resolve()
CATALOG_FILE = (BACKEND_EVA / "roadmap" / "catalog.py").resolve()
# Files structurally incapable of proving reachability: registry.py binds
# every tool's own ToolSpec (so it always "mentions" every tool), and
# catalog.py is a declarative report catalog OF tools that documents a tool
# name without ever calling it (see the EXCLUSIONS section in the module
# docstring for the concrete masking this caused and how it was found).
EXCLUDED_FILES = (REGISTRY_FILE, CATALOG_FILE)

# Ground truth measured directly against the registry. A drift in either
# number means tools were added/removed or the planner surface changed --
# either is fine, but it must be a deliberate, reviewed edit to this file.
# Phase 91 added `system_time` (101 -> 102); it is planner-reachable.
EXPECTED_TOOL_COUNT = 102
# Phase 91 made `system_time` planner-visible (72 -> 73 default, 79 -> 80 with
# Playwright). It had to be: registered + audited + referenced from production
# source satisfied the reachability check above while the model still could not
# call it, so a time question kept being answered from nothing. These two pins
# are the ones that would have caught it -- reachable-by-grep is not
# reachable-by-planner.
# Phase 118 made file.list_dir, system_status, file.write_text, file.copy,
# and file.move planner-visible (73 -> 78 default, 80 -> 85 with Playwright).
# file.delete stays console-only and is NOT in this count. app.focus was
# tried and then deliberately reverted (round 2 of the same phase): it is
# pinned OUT of planner_specs() by verify_eva_phase64_honest_effects.py
# (console/internal-only), the planner already has window_focus for the same
# job, and the runner only tracks a verified typing target for
# {"open_app", "window_focus"} (agent/runner.py::_run_step) -- a
# planner-chosen app.focus would never set typing_target.
EXPECTED_DEFAULT_PLANNER_VISIBLE_COUNT = 78
EXPECTED_PLAYWRIGHT_PLANNER_VISIBLE_COUNT = 85

# The reviewed set of intentionally-exempt tools: name -> justification.
# Growing this list is a deliberate act with a real reason, not a place to
# launder a tool nobody got around to wiring up -- if you are tempted to add
# an entry, first ask whether wiring the tool to a caller or exposing it to
# the planner is the actually-correct fix (see the failure message below for
# the three options and the trade-off between them).
#
# Empty as of Phase 70. The four entries that lived here (app.close_request,
# app.open, file.patch_text, file.read_text) were deleted outright rather
# than kept as documented duplicates -- see the module docstring's "THE PIN"
# section for why deletion, not continued exemption, was the right fix once
# each one's working, actually-routed counterpart was confirmed. An empty
# dict here is a claim, not an absence of one: every one of the 100
# registered tools left is reachable by a real production path. See
# test_mutation_c_an_empty_expected_unreachable_still_catches_a_stranded_tool
# in backend/tests/test_tool_reachability.py, which strands a tool on
# purpose and proves the empty dict still fails the build -- an empty
# EXPECTED_UNREACHABLE must never be mistaken for "nothing is checked".
EXPECTED_UNREACHABLE: dict[str, str] = {}


def check(value: object, message: str) -> None:
    if not value:
        raise AssertionError(message)


def _iter_production_files():
    for path in sorted(BACKEND_EVA.rglob("*.py")):
        if path.resolve() in EXCLUDED_FILES:
            continue
        yield path


def _string_constants(path: Path) -> set[str]:
    """Exact string-literal constants appearing in `path`'s AST.

    See the module docstring's METHOD section for why this is AST-based
    (exact match) rather than a text grep (substring match): it makes
    comments structurally invisible and prose mentions non-matching, at the
    cost of being unable to rule out a docstring whose entire text happens
    to equal a tool name verbatim.
    """
    try:
        source = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        # A file that cannot be parsed contributes no evidence either way;
        # it cannot make a tool falsely "reachable". If this ever fires for
        # a real production file, the missing coverage is at least silent
        # in the safe direction (more likely to flag a false unreachable,
        # never to hide a real one).
        return set()
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.add(node.value)
    return found


def _production_referenced_names() -> set[str]:
    referenced: set[str] = set()
    for path in _iter_production_files():
        referenced |= _string_constants(path)
    return referenced


def _planner_visible_union(registry_cls) -> tuple[set[str], set[str]]:
    """Return (default_visible, playwright_visible) planner name sets.

    Both are computed against FRESH registries so nothing from one flag
    state leaks into the other via shared mutable state.
    """
    default_registry = registry_cls()
    default_visible = {spec["name"] for spec in default_registry.planner_specs()}

    prior = os.environ.get("EVA_V2_PLAYWRIGHT_ENABLED")
    os.environ["EVA_V2_PLAYWRIGHT_ENABLED"] = "true"
    try:
        pw_registry = registry_cls()
        pw_visible = {spec["name"] for spec in pw_registry.planner_specs()}
    finally:
        if prior is None:
            os.environ.pop("EVA_V2_PLAYWRIGHT_ENABLED", None)
        else:
            os.environ["EVA_V2_PLAYWRIGHT_ENABLED"] = prior

    return default_visible, pw_visible


def compute_unreachable(registry) -> dict[str, str]:
    """The reusable core: given a live ToolRegistry, return {name: reason}
    for every registered tool reachable by neither the planner union nor a
    production-source string-literal reference (registry.py and catalog.py
    excluded -- see EXCLUDED_FILES and the module docstring). Shared with
    the pytest suite so the two test surfaces cannot silently diverge in
    method."""
    from backend.eva.tools.registry import ToolRegistry

    default_visible, pw_visible = _planner_visible_union(ToolRegistry)
    planner_union = default_visible | pw_visible
    referenced = _production_referenced_names()

    unreachable: dict[str, str] = {}
    for name in sorted(registry._tools):
        if name in planner_union:
            continue
        if name in referenced:
            continue
        unreachable[name] = (
            "not planner-visible under the default-or-Playwright-enabled union, and its name is "
            "not an exact string-literal constant in any backend/eva/**/*.py file other than "
            "registry.py or roadmap/catalog.py"
        )
    return unreachable


def _format_unreachable_failure(extra: dict[str, str], stale: set[str]) -> str:
    lines = ["Phase 66 tool-reachability audit failed."]
    if extra:
        lines.append("")
        lines.append("Newly stranded (registered but reachable from nowhere):")
        for name, reason in sorted(extra.items()):
            lines.append(f"  - {name}: {reason}")
        lines.append("")
        lines.append(
            "Fix ONE of the following for each tool named above:\n"
            "  1. Wire it to a real caller -- a console handler in eva/core/fast_commands.py, a\n"
            "     capability router in eva/core/capabilities.py, a form filler, or similar FIXED\n"
            "     product code that chooses to call this tool for some real situation. A generic\n"
            "     pass-through that can call ANY tool by a caller-supplied name (the /api/tools/\n"
            "     {name} endpoint, a user-authored skill step) does NOT count -- it proves the\n"
            "     tool is callable, not that anything routes to it. A roadmap/catalog.py entry\n"
            "     does NOT count either -- it is a declarative report, not a caller (see the\n"
            "     module docstring's EXCLUSIONS section for why this specific one is called out).\n"
            "  2. Expose it to the planner -- add it to the `visible` list in\n"
            "     ToolRegistry.planner_specs() (or, for web.*, it is already covered once\n"
            "     Playwright is enabled).\n"
            "  3. If it is deliberately not meant to be reachable yet, add it to\n"
            "     EXPECTED_UNREACHABLE in this file with a written reason -- this is the right\n"
            "     home for a TRUE positive (a genuinely unrouted, deliberately-retained tool,\n"
            "     e.g. a superseded duplicate), never a place to paper over a scanner false\n"
            "     positive or a tool nobody has decided about yet."
        )
    if stale:
        lines.append("")
        lines.append(
            "Stale EXPECTED_UNREACHABLE entries (now genuinely reachable, but still listed "
            "as exempt -- remove them so the allowlist cannot rot):"
        )
        for name in sorted(stale):
            lines.append(f"  - {name}")
    return "\n".join(lines)


def main() -> int:
    from backend.eva.tools.registry import ToolRegistry
    from scripts import verify_eva_all

    registry = ToolRegistry()
    all_tools = set(registry._tools)
    check(
        len(all_tools) == EXPECTED_TOOL_COUNT,
        f"registered tool count drifted: expected {EXPECTED_TOOL_COUNT}, got {len(all_tools)}. "
        "If this was a deliberate tool addition/removal, update EXPECTED_TOOL_COUNT here "
        "and make sure the new/removed tool is reachable (or exempted) below.",
    )

    default_visible, pw_visible = _planner_visible_union(ToolRegistry)
    check(
        len(default_visible) == EXPECTED_DEFAULT_PLANNER_VISIBLE_COUNT,
        f"default-env planner-visible count drifted: expected {EXPECTED_DEFAULT_PLANNER_VISIBLE_COUNT}, "
        f"got {len(default_visible)}.",
    )
    check(
        len(pw_visible) == EXPECTED_PLAYWRIGHT_PLANNER_VISIBLE_COUNT,
        f"Playwright-enabled planner-visible count drifted: expected "
        f"{EXPECTED_PLAYWRIGHT_PLANNER_VISIBLE_COUNT}, got {len(pw_visible)}.",
    )

    computed = compute_unreachable(registry)
    computed_names = set(computed)
    expected_names = set(EXPECTED_UNREACHABLE)

    extra = {name: computed[name] for name in computed_names - expected_names}
    stale = expected_names - computed_names

    if extra or stale:
        raise AssertionError(_format_unreachable_failure(extra, stale))

    # Registration.
    verifier_name = "verify_eva_phase66_tool_reachability.py"
    check(verifier_name in verify_eva_all.FULL_VERIFIERS, "full profile missing the Phase 66 verifier")
    check(verifier_name in verify_eva_all.QUICK_VERIFIERS, "quick profile missing the Phase 66 verifier")
    check(verifier_name in getattr(verify_eva_all, "VERIFIER_DESCRIPTORS"), "master verifier descriptor missing the Phase 66 verifier")

    print(
        "PASS: Phase 66 tool reachability -- all 100 registered tools are reachable by at least "
        "one production path (planner-visible under the default-or-Playwright union, or an exact "
        "string-literal reference in backend/eva/**/*.py outside registry.py AND roadmap/catalog.py "
        "-- a declarative catalog of tools is not evidence anything calls them). "
        f"{len(default_visible)} tools are planner-visible by default, {len(pw_visible)} once "
        "EVA_V2_PLAYWRIGHT_ENABLED is set, and the remainder are reached only through production "
        "callers such as eva/core/fast_commands.py. EXPECTED_UNREACHABLE is empty as of Phase 70: "
        "the four dotted duplicates this verifier originally found and pinned here "
        "(app.close_request, app.open, file.patch_text, file.read_text) were deleted outright "
        "rather than kept as a documented exemption, once each one's working, actually-routed "
        "counterpart (close_app, open_app, file.write_text, workspace_read_file respectively) was "
        "confirmed -- app.open's one load-bearing property, its accurate app_window_open "
        "postcondition, was moved onto open_app first so the routed path did not lose "
        "verification. EXPECTED_UNREACHABLE is still compared by EXACT MATCH even though it is "
        "empty: a newly stranded tool fails the build by name, and a stale exemption for a tool "
        "that becomes reachable also fails, so the allowlist cannot silently rot into 'nothing is "
        "checked' in either direction. This is the complementary check to "
        "backend/tests/test_planner_reachability.py, which asserts the opposite, security-facing "
        "direction -- that screen.*/web.*/mcp.* stay OUT of the planner by default."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
