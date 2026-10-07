"""Pure command policy shared by HTTP, ORM and editorial adapters."""


class InvalidTransition(ValueError):
    pass


class RevisionConflict(InvalidTransition):
    pass


INPUT_REQUIRED_ERRORS = frozenset({
    "YOUTUBE_IP_BLOCKED", "YOUTUBE_TRANSCRIPTS_DISABLED",
    "YOUTUBE_LANGUAGE_UNAVAILABLE", "YOUTUBE_VIDEO_UNAVAILABLE",
    "ATTACHMENT_CHANGED", "CANONICAL_INPUT_CHANGED",
})


def failure_status(code: str) -> str:
    return "waiting_input" if code in INPUT_REQUIRED_ERRORS else "failed"


def command_transition(status: str, command: str, revision: int, expected_revision: int) -> str:
    if type(expected_revision) is not int or expected_revision < 0:
        raise InvalidTransition("A nonnegative expected_revision is required.")
    if revision != expected_revision:
        raise RevisionConflict("Run changed; read its current revision before issuing a command.")
    allowed = {
        "retry": ({"failed", "waiting_input"}, "received"),
        "cancel": ({"received", "failed", "waiting_input", "waiting_review"}, "cancelled"),
    }
    if command not in allowed or status not in allowed[command][0]:
        raise InvalidTransition("Command is unavailable in the current state.")
    return allowed[command][1]
