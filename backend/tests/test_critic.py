"""Executable spec for the Phase 41 critic (backend/eva/agent/critic.py).

Pure, deterministic, offline unit tests for:

  * ``DelegationContract.of`` -- building a contract from None, a dict (with
    ``success_criteria`` as a list or a single string), an existing
    ``DelegationContract`` (returned as-is), and malformed input (fails safe);
  * ``DelegationContract.enforcing`` -- True with either success criteria or
    ``require_verified``, False when neither is set;
  * ``review_completion`` -- advisory acceptance with no contract, met vs.
    unmet criteria, REVISE vs. REPORT_HONESTLY by revision budget,
    ``require_verified`` gating, and the fail-safe accept-on-error path; and
  * ``honest_caveat`` -- empty string when satisfied, a non-empty note
    otherwise.

No network, no live LLM, no filesystem I/O.
"""

from __future__ import annotations

from backend.eva.agent.critic import (
    ACCEPT,
    REPORT_HONESTLY,
    REVISE,
    CriticVerdict,
    DelegationContract,
    honest_caveat,
    review_completion,
)


# ---------------------------------------------------------------------------
# DelegationContract.of
# ---------------------------------------------------------------------------


def test_of_none_returns_none():
    assert DelegationContract.of(None) is None


def test_of_dict_with_list_criteria():
    contract = DelegationContract.of({"success_criteria": ["report saved", "email sent"]})
    assert contract is not None
    assert contract.success_criteria == ("report saved", "email sent")


def test_of_dict_with_single_string_criteria():
    contract = DelegationContract.of({"success_criteria": "report saved"})
    assert contract is not None
    assert contract.success_criteria == ("report saved",)


def test_of_existing_contract_returned_as_is():
    original = DelegationContract(success_criteria=("x",))
    assert DelegationContract.of(original) is original


def test_of_bad_dict_returns_none_or_safe():
    # max_revisions cannot be parsed as an int -> the classmethod's own
    # try/except must catch it and fail safe rather than raise.
    result = DelegationContract.of({"max_revisions": "not-a-number"})
    assert result is None


def test_of_unrecognized_type_returns_none():
    assert DelegationContract.of(12345) is None
    assert DelegationContract.of("just a string") is None


# ---------------------------------------------------------------------------
# DelegationContract.enforcing
# ---------------------------------------------------------------------------


def test_enforcing_true_with_success_criteria():
    contract = DelegationContract(success_criteria=("done",))
    assert contract.enforcing is True


def test_enforcing_true_with_require_verified():
    contract = DelegationContract(require_verified=True)
    assert contract.enforcing is True


def test_enforcing_false_when_empty():
    contract = DelegationContract()
    assert contract.enforcing is False


# ---------------------------------------------------------------------------
# review_completion
# ---------------------------------------------------------------------------


def test_no_contract_is_advisory_and_satisfied():
    verdict = review_completion(
        goal="do a thing",
        final_response="All done.",
        observations=[],
        verified_successes=0,
        failures=0,
        contract=None,
    )
    assert verdict.satisfied is True
    assert verdict.recommendation == ACCEPT


def test_non_enforcing_contract_is_advisory_and_satisfied():
    contract = DelegationContract()  # no criteria, require_verified False
    verdict = review_completion(
        goal="do a thing",
        final_response="All done.",
        observations=[],
        verified_successes=0,
        failures=0,
        contract=contract,
    )
    assert verdict.satisfied is True
    assert verdict.recommendation == ACCEPT


def test_criterion_present_in_final_response_is_satisfied():
    contract = DelegationContract(success_criteria=("report saved",))
    verdict = review_completion(
        goal="save the report",
        final_response="I saved the report saved to disk.",
        observations=[],
        verified_successes=0,
        failures=0,
        contract=contract,
    )
    assert verdict.satisfied is True
    assert verdict.recommendation == ACCEPT
    assert verdict.unmet_criteria == ()


def test_criterion_present_in_observations_is_satisfied():
    contract = DelegationContract(success_criteria=("email sent",))
    verdict = review_completion(
        goal="notify the team",
        final_response="Finished.",
        observations=["email sent to the team distribution list"],
        verified_successes=0,
        failures=0,
        contract=contract,
    )
    assert verdict.satisfied is True


def test_criterion_absent_is_unsatisfied_and_listed():
    contract = DelegationContract(success_criteria=("report saved",), max_revisions=1)
    verdict = review_completion(
        goal="save the report",
        final_response="trust me it's done",
        observations=[],
        verified_successes=0,
        failures=0,
        contract=contract,
        revisions_used=0,
    )
    assert verdict.satisfied is False
    assert "report saved" in verdict.unmet_criteria


def test_recommendation_revise_when_budget_remains():
    contract = DelegationContract(success_criteria=("report saved",), max_revisions=1)
    verdict = review_completion(
        goal="save the report",
        final_response="not yet",
        observations=[],
        verified_successes=0,
        failures=0,
        contract=contract,
        revisions_used=0,
    )
    assert verdict.satisfied is False
    assert verdict.recommendation == REVISE


def test_recommendation_report_honestly_when_budget_exhausted():
    contract = DelegationContract(success_criteria=("report saved",), max_revisions=0)
    verdict = review_completion(
        goal="save the report",
        final_response="trust me it's done",
        observations=[],
        verified_successes=0,
        failures=0,
        contract=contract,
        revisions_used=0,
    )
    assert verdict.satisfied is False
    assert verdict.recommendation == REPORT_HONESTLY


def test_require_verified_with_zero_verified_successes_unsatisfied():
    contract = DelegationContract(success_criteria=("report saved",), require_verified=True, max_revisions=1)
    verdict = review_completion(
        goal="save the report",
        final_response="report saved",
        observations=[],
        verified_successes=0,
        failures=0,
        contract=contract,
    )
    assert verdict.satisfied is False


def test_require_verified_with_one_verified_success_and_met_criteria_satisfied():
    contract = DelegationContract(success_criteria=("report saved",), require_verified=True, max_revisions=1)
    verdict = review_completion(
        goal="save the report",
        final_response="report saved",
        observations=[],
        verified_successes=1,
        failures=0,
        contract=contract,
    )
    assert verdict.satisfied is True
    assert verdict.recommendation == ACCEPT


def test_fail_safe_returns_satisfied_true_on_garbage_input():
    contract = DelegationContract(success_criteria=("report saved",), max_revisions=0)
    # observations=None would break `for o in (observations or [])` iteration
    # patterns elsewhere, but review_completion must fail open regardless.
    verdict = review_completion(
        goal="save the report",
        final_response="report saved",
        observations=None,  # type: ignore[arg-type]
        verified_successes=0,
        failures=0,
        contract=contract,
    )
    assert isinstance(verdict, CriticVerdict)
    assert verdict.satisfied is True


# ---------------------------------------------------------------------------
# honest_caveat
# ---------------------------------------------------------------------------


def test_honest_caveat_empty_when_satisfied():
    verdict = CriticVerdict(satisfied=True, confidence=0.9, recommendation=ACCEPT, reasons=(), unmet_criteria=())
    assert honest_caveat(verdict) == ""


def test_honest_caveat_non_empty_when_not_satisfied():
    verdict = CriticVerdict(
        satisfied=False,
        confidence=0.8,
        recommendation=REPORT_HONESTLY,
        reasons=("Unmet success criteria: report saved.",),
        unmet_criteria=("report saved",),
    )
    note = honest_caveat(verdict)
    assert note != ""
    assert "could not confirm" in note
    assert "report saved" in note
