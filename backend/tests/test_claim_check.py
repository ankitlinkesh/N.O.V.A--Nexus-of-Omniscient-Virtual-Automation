"""A run must not report a whole goal as finished when nothing it did matches part of the goal."""

from backend.eva.agent import runner
from backend.eva.agent.claim_check import unsupported_note, unsupported_parts
from backend.eva.agent.task import AgentStep, AgentTask


def step(tool, status="done"):
    return AgentStep(index=0, thought_summary="", planned_action="", tool_name=tool, status=status)


def test_opening_the_app_is_not_clicking_in_it():
    goal = 'open calculator and click "Seven", "Plus", "Two", "Equals"'
    assert "click" in unsupported_parts(goal, [step("open_app")])[0]
    assert unsupported_parts(goal, [step("open_app")] + [step("screen.click")] * 4) == []


def test_fewer_clicks_than_named_labels_is_reported():
    goal = 'click "Seven", "Plus", "Two"'
    assert unsupported_parts(goal, [step("screen.click")]) == ["2 of the 3 clicks you named"]


def test_a_failed_step_does_not_count():
    assert unsupported_parts("click the OK button", [step("screen.click", status="failed")])


def test_typing_press_scroll_and_send_need_their_own_steps():
    assert unsupported_parts("open notepad and type hello", [step("open_app")]) == ["typing the text"]
    assert unsupported_parts("open notepad and type hello", [step("open_app"), step("screen.type_text")]) == []
    assert unsupported_parts("press enter", [step("open_app")]) == ["the key press"]
    assert unsupported_parts("scroll down", []) == ["the scrolling"]
    assert unsupported_parts("write an email to rahul and send it", [step("email.draft_gmail")]) == ["sending it (nothing was sent)"]
    assert unsupported_parts("write an email to rahul and send it", [step("email.draft_gmail"), step("email.send_drafted")]) == []


def test_ordinary_goals_are_left_alone():
    for goal in ("what type of music do I like", "play pavazhamalli on spotify", "how much free space is on C", "open calculator",
                 "write an email to my professor", "press play", "search the web for python"):
        assert unsupported_parts(goal, [step("open_app")]) == [], goal
    assert unsupported_note("open calculator", []) == ""


def test_finalizer_appends_the_note_and_marks_the_task_attempted():
    task = AgentTask(user_goal='open calculator and click "Seven"')
    task.steps.append(step("open_app"))
    task.final_response = "I finished the task. open_app returned Opening calculator. (verified)"
    result = runner._finalize_success(task, runner.AgentRunState(), None, {}, events=[], safety_stops=[], memory=None, session_id="s")
    assert "I have no record of the click(s)" in task.final_response
    assert task.status == "attempted" and "unsupported_claim" in result["safety_stops"]


def test_finalizer_leaves_a_complete_run_alone():
    task = AgentTask(user_goal='open calculator and click "Seven"')
    task.steps.extend([step("open_app"), step("screen.click")])
    task.final_response = "Done."
    runner._finalize_success(task, runner.AgentRunState(), None, {}, events=[], safety_stops=[], memory=None, session_id="s")
    assert task.final_response == "Done." and task.status != "attempted"


def test_writing_an_email_is_supported_but_reading_mail_is_still_refused():
    from backend.eva.agent.policies import is_unsupported_capability

    for ok in ("write an email to test@example.com saying hi", "draft an email to my professor", "compose a mail and send it to rahul", "send an email to sam"):
        assert not is_unsupported_capability(ok), ok
    for refused in ("read my emails", "check my inbox", "reply to the last email", "book a meeting on my calendar", "call mom on the phone"):
        assert is_unsupported_capability(refused), refused


def test_a_stop_message_shows_the_tools_sentence_not_dict_text():
    from backend.eva.agent.task import readable_observation

    raw = "chrome_open_web_app_and_verify returned {'ok': True, 'opened': True, 'message': 'Done, YouTube is open in Chrome.', 'verified': False} (self-reported)"
    assert readable_observation(raw)[0] == "Done, YouTube is open in Chrome. (not independently verified)"
    plain = "workspace search found 3 files"
    assert readable_observation(plain)[0] == plain
    odd = "tool returned {'ok': True, 'rows': [1, 2]}"
    assert readable_observation(odd)[0] == odd
