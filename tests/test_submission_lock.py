from facodi_api.core.submission_lock import SubmissionAdvisoryLock


class FakeCursor:
    def __init__(self):
        self.closed = False
        self.calls = []

    def execute(self, query, params):
        self.calls.append((query, params))

    def close(self):
        self.closed = True


def test_advisory_lock_release_is_immediate_and_idempotent():
    cursor = FakeCursor()
    lock = SubmissionAdvisoryLock(cursor, "scope:key", close_cursor=True)

    lock.release()
    lock.release()

    assert cursor.closed
    assert len(cursor.calls) == 1
    assert "pg_advisory_unlock" in cursor.calls[0][0]
    assert cursor.calls[0][1] == ["scope:key"]


def test_transaction_cursor_is_not_closed_when_lock_is_released():
    cursor = FakeCursor()
    lock = SubmissionAdvisoryLock(cursor, "scope:key")

    lock.release()

    assert not cursor.closed
    assert lock.released
