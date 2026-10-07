import pytest

from facodi_api.core.contracts import lifecycle


def test_blocked_acquisition_waits_for_input_without_claiming_completion():
    assert lifecycle.failure_status("YOUTUBE_IP_BLOCKED") == "waiting_input"
    assert lifecycle.failure_status("YOUTUBE_TRANSCRIPTS_DISABLED") == "waiting_input"
    assert lifecycle.failure_status("PIPELINE_FAILED") == "failed"


@pytest.mark.parametrize("status", ["failed", "waiting_input"])
def test_retry_accepts_only_current_revision(status):
    assert lifecycle.command_transition(status, "retry", 3, 3) == "received"
    with pytest.raises(lifecycle.RevisionConflict):
        lifecycle.command_transition(status, "retry", 3, 2)


@pytest.mark.parametrize("expected", [True, -1, 2.0, "2", None])
def test_commands_require_nonnegative_integer_revision(expected):
    with pytest.raises(lifecycle.InvalidTransition):
        lifecycle.command_transition("received", "cancel", 2, expected)


@pytest.mark.parametrize("status", ["running", "waiting_review", "published", "cancelled", "received"])
def test_retry_does_not_reprocess_accepted_or_reviewed_content(status):
    with pytest.raises(lifecycle.InvalidTransition):
        lifecycle.command_transition(status, "retry", 3, 3)


@pytest.mark.parametrize("status", ["received", "failed", "waiting_input", "waiting_review"])
def test_cancel_can_preserve_unpublished_history(status):
    assert lifecycle.command_transition(status, "cancel", 0, 0) == "cancelled"


@pytest.mark.parametrize("status", ["published", "running", "cancelled"])
def test_cancel_cannot_undo_publication_or_running_worker(status):
    with pytest.raises(lifecycle.InvalidTransition):
        lifecycle.command_transition(status, "cancel", 0, 0)
