"""Pytest coverage for Phase 66: no registered tool may be stranded.

This is the pytest-visible companion to
``scripts/verify_eva_phase66_tool_reachability.py`` -- see that module's
docstring for the full invariant, method, and its documented limitations.
In short: every tool in ``ToolRegistry._tools`` must be reachable either
through ``planner_specs()`` (under the union of default and
``EVA_V2_PLAYWRIGHT_ENABLED=true``), or through an exact string-literal
reference in a production ``backend/eva/**/*.py`` module other than
``registry.py`` or ``roadmap/catalog.py`` (both excluded -- see below and
the verifier's docstring for why a declarative catalog OF tools cannot
prove anything routes to them).

REACHABLE MEANS ROUTED, NOT MERELY CALLABLE. Every registered tool is
already callable in principle through ``/api/tools/{tool_name}``, which
calls ``tools.run(tool_name, **body)`` for any name at all. That is exactly
how ``voice.listen_once`` and ``app.focus`` shipped stranded for phases --
both were callable in principle the whole time. This suite checks whether
something FIXED in the product chooses to call a tool for a real situation,
not whether a generic pass-through could reach it if asked.

HOW THIS DIFFERS FROM test_planner_reachability.py in this same directory:
that file asserts the opposite, security-facing direction -- that
``screen.*``/``web.*``/``mcp.*`` tools stay OUT of the planner by default
(and ``screen.*`` permanently, regardless of flags). This file asserts that
nothing REGISTERED is stranded from every production path -- a tool can
correctly stay planner-invisible forever (like ``screen.click``) while still
needing a production caller to pass here. Both are true at once and neither
subsumes the other; ``test_known_planner_only_and_source_only_tools_are_both_covered``
below exercises exactly that complementary relationship using
``screen.click`` as the concrete example.

THE PINNED FOUR, THEN DELETED: this verifier's first version excluded only
``registry.py`` and counted a ``roadmap/catalog.py`` entry as a valid
reference. That masked two genuinely stranded tools (``app.open``,
``file.patch_text``) behind their own catalog entry, on top of the two it
did catch (``app.close_request``, ``file.read_text``) -- the exact
laundering pattern this phase exists to catch, in a new costume. All four
were pinned in ``EXPECTED_UNREACHABLE`` rather than deleted at the time, in
case a future phase wired one up on purpose. Phase 70 revisited that call:
none ever was wired up, each still had a confirmed working counterpart
(``close_app``, ``open_app``, ``file.write_text``, ``workspace_read_file``
respectively), and ``app.open``'s one load-bearing property -- Phase 64's
accurate ``app_window_open`` postcondition -- was moved onto ``open_app``
before all four were deleted outright, registry entries and all.
``EXPECTED_UNREACHABLE`` is empty as of Phase 70 and ``EXPECTED_TOOL_COUNT``
dropped from 104 to 100. The mutation tests further down are the ones that
matter most: they prove the detector still actually fires on an *empty*
exemption dict (not just that it happens to be quiet today), which is
exactly the failure mode an empty allowlist invites -- being silently
mistaken for "nothing is checked".
"""

from __future__ import annotations

import pytest

from backend.eva.tools.registry import _MCP_TOOL_SPECS
from scripts import verify_eva_phase66_tool_reachability as phase66


@pytest.fixture(autouse=True)
def _clear_mcp_tool_specs_cache():
    """Same precaution as test_planner_reachability.py: don't let this
    file's registry constructions leak mcp.* specs into other test modules
    via the shared module-level cache, and don't inherit any left behind."""
    _MCP_TOOL_SPECS.clear()
    try:
        yield
    finally:
        _MCP_TOOL_SPECS.clear()


def _dummy_spec(name: str):
    from backend.eva.tools.registry import ToolSpec

    return ToolSpec(
        name=name,
        description="Test-only dummy tool: not planner-visible, not referenced anywhere in production source.",
        args_schema={"type": "object", "properties": {}, "required": []},
        safety_level="safe",
        handler=lambda **_kwargs: {"ok": True},
        action_type="SAFE_LOCAL_READ",
        risk_categories=("SAFE_LOCAL_READ",),
    )


# --- Ground truth: the four duplicates are GONE, not merely exempted. -------

# Phase 128 re-registered the NAME `file.read_text`, but not the tool Phase 70 deleted: that one was an
# arbitrary-path PRIVACY_FILE_READ nobody called. This one is path-bounded (`_safe_path`), allow-class,
# taint-tracked and planner-visible, so it is no longer in the deleted set.
_DELETED_DUPLICATE_TOOLS = {"app.close_request", "app.open", "file.patch_text"}
_DELETED_DUPLICATE_COUNTERPARTS = {"close_app", "open_app", "file.write_text", "workspace_read_file"}


def test_expected_unreachable_is_empty_as_of_phase_70():
    """The four dotted duplicates Phase 66 found and pinned here were
    deleted outright in Phase 70 rather than kept as a permanent documented
    exemption. If a future phase ever needs a new entry, it must be added
    deliberately with a written reason -- this must never silently grow
    back to "launder a tool nobody got around to wiring up"."""
    assert phase66.EXPECTED_UNREACHABLE == {}


def test_deleted_duplicate_tools_are_gone_not_merely_unreachable():
    """The distinction that matters: these four are not in EXPECTED_UNREACHABLE
    because they no longer exist at all, not because someone forgot to keep
    exempting them. Their counterparts must still be present and reachable."""
    from backend.eva.tools.registry import ToolRegistry

    registry = ToolRegistry()
    for name in _DELETED_DUPLICATE_TOOLS:
        assert name not in registry._tools, f"{name} should have been deleted in Phase 70, not merely exempted"

    unreachable = phase66.compute_unreachable(registry)
    for counterpart in _DELETED_DUPLICATE_COUNTERPARTS:
        assert counterpart in registry._tools, f"counterpart {counterpart!r} must still be registered"
        assert counterpart not in unreachable, f"counterpart {counterpart!r} must still be reachable"


def test_open_app_carries_the_postcondition_moved_from_the_deleted_app_open():
    """The one piece of real behavior that had to survive the deletion:
    app.open's accurate, independent app_window_open postcondition (Phase
    64) was moved onto open_app -- the tool the console/planner actually
    route to -- before app.open was deleted, so the routed path did not
    regress to a bare self-report."""
    from backend.eva.tools.registry import ToolRegistry

    spec = ToolRegistry().get("open_app")
    assert spec is not None
    assert spec.verification_method == "app_window_open", (
        f"open_app must carry the real independent postcondition moved from the deleted app.open, "
        f"got {spec.verification_method!r}"
    )


def test_default_registry_unreachable_set_is_empty():
    from backend.eva.tools.registry import ToolRegistry

    registry = ToolRegistry()
    unreachable = phase66.compute_unreachable(registry)
    assert unreachable == {}, f"computed unreachable set drifted from the pin (now empty): {sorted(unreachable)}"


def test_verifier_main_passes_against_the_real_registry():
    assert phase66.main() == 0


def test_catalog_py_exclusion_is_load_bearing(monkeypatch):
    """Regression test for the exact defect the coordinator's review caught:
    counting roadmap/catalog.py as a production reference masks real
    stranded tools behind a purely declarative catalog entry.

    Phase 66 found this concretely via app.open and file.patch_text -- both
    had catalog.py as their ONLY non-registry reference. Phase 70 deleted
    both tools (and their catalog.py entries) once each was confirmed
    superseded, so that specific historical repro no longer exists to point
    at -- and, checked directly rather than assumed
    (test_no_registered_tool_is_currently_catalog_only below), no other
    currently-registered tool is catalog-only either. This test keeps the
    general mechanism honestly covered with a synthetic case instead of a
    stale hardcoded one: a dummy name is made to appear in catalog.py's own
    string constants (by wrapping ``_string_constants`` for that one path),
    then the test proves (a) the current, correct method -- which never even
    reads catalog.py, because CATALOG_FILE is in EXCLUDED_FILES and
    ``_iter_production_files()`` skips it entirely -- does not count the
    dummy as referenced, while (b) a pre-fix, only-registry.py-excluded scan
    WOULD have wrongly counted it, reproducing exactly how
    app.open/file.patch_text were masked."""
    from backend.eva.tools.registry import ToolRegistry

    dummy_name = "zzz_test_catalog_only_dummy_tool"
    real_string_constants = phase66._string_constants

    def fake_string_constants(path):
        if path.resolve() == phase66.CATALOG_FILE:
            return real_string_constants(path) | {dummy_name}
        return real_string_constants(path)

    monkeypatch.setattr(phase66, "_string_constants", fake_string_constants)

    # Current, correct method: _iter_production_files() skips CATALOG_FILE
    # entirely, so _string_constants is never even called on it here -- the
    # dummy's "mention" is structurally invisible.
    referenced_with_catalog_excluded = phase66._production_referenced_names()
    assert dummy_name not in referenced_with_catalog_excluded

    # Pre-fix method: only registry.py excluded. Reproduces the exact
    # masking bug -- the dummy now looks referenced purely because
    # catalog.py (wrongly counted) mentions it.
    referenced_without_catalog_exclusion: set[str] = set()
    for path in sorted(phase66.BACKEND_EVA.rglob("*.py")):
        if path.resolve() == phase66.REGISTRY_FILE:
            continue
        referenced_without_catalog_exclusion |= phase66._string_constants(path)
    assert dummy_name in referenced_without_catalog_exclusion, (
        "premise broken: the dummy should look referenced when only registry.py is excluded"
    )

    # And the live effect against a real registry with the dummy registered:
    # correctly excluding catalog.py leaves it unreachable.
    registry = ToolRegistry()
    registry._tools[dummy_name] = _dummy_spec(dummy_name)
    try:
        unreachable = phase66.compute_unreachable(registry)
        assert dummy_name in unreachable
    finally:
        del registry._tools[dummy_name]


def test_no_registered_tool_is_currently_catalog_only():
    """Empirical companion to the synthetic test above: confirms, computed
    fresh against the real registry and real catalog.py rather than assumed,
    that no currently-registered tool relies on catalog.py's exclusion to be
    correctly classified unreachable today. This can legitimately change in
    the future (a new tool could get catalog-only'd the same way app.open
    did); if it does, that is real signal, not a reason to weaken this
    check."""
    from backend.eva.tools.registry import ToolRegistry

    registry = ToolRegistry()
    all_tools = set(registry._tools)

    referenced_without_catalog_exclusion: set[str] = set()
    for path in sorted(phase66.BACKEND_EVA.rglob("*.py")):
        if path.resolve() == phase66.REGISTRY_FILE:
            continue
        referenced_without_catalog_exclusion |= phase66._string_constants(path)

    referenced_with_catalog_excluded = phase66._production_referenced_names()
    catalog_only = (referenced_without_catalog_exclusion - referenced_with_catalog_excluded) & all_tools
    assert catalog_only == set(), (
        f"these registered tools are currently reachable only through roadmap/catalog.py's declarative "
        f"entries -- that is exactly the masking pattern Phase 66/70 fixed, they need a real caller: {catalog_only}"
    )


# --- Complementary relationship with test_planner_reachability.py. ---------


def test_known_planner_only_and_source_only_tools_are_both_covered():
    from backend.eva.tools.registry import ToolRegistry

    registry = ToolRegistry()
    unreachable = phase66.compute_unreachable(registry)
    planner_names = {spec["name"] for spec in registry.planner_specs()}

    # "status" is reachable because it is directly planner-visible.
    assert "status" in planner_names
    assert "status" not in unreachable

    # "screen.click" must STAY planner-invisible (a permanent safety
    # boundary asserted by test_planner_reachability.py) yet still be
    # reachable here -- through eva/screen/form_filler.py's
    # run("screen.click", ...) and other production callers. This is the
    # concrete proof the two files are complementary, not duplicates.
    assert "screen.click" not in planner_names
    assert "screen.click" not in unreachable


def test_mcp_tools_absent_by_default_are_handled_honestly():
    """mcp.* tool names are built dynamically (f"mcp.{server.name}.{tool}")
    in eva/mcp/registration.py and are invisible to an exact-string scan by
    construction -- but they are also simply ABSENT from a default registry
    with no MCP server configured, so there is nothing to misclassify."""
    from backend.eva.tools.registry import ToolRegistry

    registry = ToolRegistry()
    assert not any(name.startswith("mcp.") for name in registry._tools)

    unreachable = phase66.compute_unreachable(registry)
    assert not any(name.startswith("mcp.") for name in unreachable)


# --- Mutation tests: the ones that prove the detector actually fires. ------


def test_mutation_a_an_unwired_registered_tool_is_caught_and_named():
    """Register a dummy tool that is neither planner-visible nor referenced
    by any production source. compute_unreachable() must report it, by
    name -- this is the exact shape of bug this phase exists to catch
    (voice.listen_once / app.focus, both shipped stranded for phases)."""
    from backend.eva.tools.registry import ToolRegistry

    registry = ToolRegistry()
    dummy_name = "zzz_test_stranded_dummy_tool"
    assert dummy_name not in registry._tools

    registry._tools[dummy_name] = _dummy_spec(dummy_name)
    try:
        unreachable = phase66.compute_unreachable(registry)
        assert dummy_name in unreachable, (
            f"a tool with no planner visibility and no production reference must be reported "
            f"unreachable; got {sorted(unreachable)}"
        )
    finally:
        del registry._tools[dummy_name]

    # Removing it restores exactly the pinned baseline -- empty as of Phase
    # 70 -- proving this is live detection against the current registry
    # state, not a stale fixture.
    clean = phase66.compute_unreachable(registry)
    assert dummy_name not in clean
    assert clean == {} == phase66.EXPECTED_UNREACHABLE


def test_mutation_c_an_empty_expected_unreachable_still_catches_a_stranded_tool(monkeypatch):
    """The mutation that matters most now that EXPECTED_UNREACHABLE is
    empty: an empty exemption dict must never be mistaken for "nothing is
    checked". Patch ToolRegistry so main() itself sees a stranded dummy
    tool, and confirm the verifier -- running against the REAL, empty
    EXPECTED_UNREACHABLE, no monkeypatching of that dict needed -- still
    raises and names it. EXPECTED_TOOL_COUNT is bumped alongside the
    mutation so this test isolates the unreachable-set check specifically --
    the separately pinned tool-count check is not the mechanism under test
    here, and letting it fire first would make this test pass for the wrong
    reason."""
    from backend.eva.tools import registry as registry_module

    assert phase66.EXPECTED_UNREACHABLE == {}, "this test's premise is an empty exemption dict"

    dummy_name = "zzz_test_stranded_dummy_tool"
    real_init = registry_module.ToolRegistry.__init__

    def patched_init(self, *args, **kwargs):
        real_init(self, *args, **kwargs)
        self._tools[dummy_name] = _dummy_spec(dummy_name)

    monkeypatch.setattr(registry_module.ToolRegistry, "__init__", patched_init)
    monkeypatch.setattr(phase66, "EXPECTED_TOOL_COUNT", phase66.EXPECTED_TOOL_COUNT + 1)

    with pytest.raises(AssertionError) as excinfo:
        phase66.main()
    message = str(excinfo.value)
    assert dummy_name in message
    # The failure must be actionable: it should point at the three fixes.
    assert "wire it to a caller" in message.lower() or "wire it" in message.lower()


def test_mutation_b_a_wrongly_allowlisted_reachable_tool_fails_exact_match(monkeypatch):
    """Mutate EXPECTED_UNREACHABLE (now empty) to falsely claim a genuinely
    reachable tool ("screen.click") is exempt. The exact-match comparison --
    not a superset/subset check -- must catch this: an allowlist entry for a
    tool that is actually reachable is exactly how the list would rot into
    over-broad cover over time, and an empty dict is not immune to that --
    it just means there is currently nothing wrongly listed."""
    monkeypatch.setitem(
        phase66.EXPECTED_UNREACHABLE,
        "screen.click",
        "bogus entry injected by this test -- screen.click is genuinely reachable",
    )

    with pytest.raises(AssertionError) as excinfo:
        phase66.main()
    message = str(excinfo.value)
    assert "screen.click" in message
    assert "stale" in message.lower()
