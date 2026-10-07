from facodi_api.core.submission_lock import SubmissionAdvisoryLock


class FakeCursor:
    def __init__(self):
        self.closed = False
        self.calls = []

    def execute(self, query, params):
        self.calls.append((query, params))

    def close(self):
        self.closed = True


class FailsOnceCursor(FakeCursor):
    def execute(self, query, params):
        super().execute(query, params)
        if len(self.calls) == 1:
            raise RuntimeError("transaction is aborted")


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


def test_failed_unlock_is_retried_after_transaction_rollback():
    cursor = FailsOnceCursor()
    lock = SubmissionAdvisoryLock(cursor, "scope:key")

    with __import__('pytest').raises(RuntimeError, match='aborted'):
        lock.release()
    assert not lock.released

    lock.release()
    assert lock.released
    assert len(cursor.calls) == 2
