"""Small, idempotent owner for a PostgreSQL session advisory lock."""


class SubmissionAdvisoryLock:
    def __init__(self, cursor, lock_key, *, close_cursor=False):
        self.cursor = cursor
        self.lock_key = lock_key
        self.close_cursor = close_cursor
        self.released = False

    def release(self):
        if self.released or self.cursor.closed:
            return
        try:
            self.cursor.execute(
                "SELECT pg_advisory_unlock(hashtextextended(%s, 0))",
                [self.lock_key],
            )
        finally:
            self.released = True
            if self.close_cursor:
                self.cursor.close()
