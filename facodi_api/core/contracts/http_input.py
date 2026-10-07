"""Bounded, strict JSON parsing shared by the HTTP adapter and standalone tests."""
import json

class PayloadTooLarge(ValueError):
    pass

class InvalidPayload(ValueError):
    pass


def _reject_constant(value):
    raise InvalidPayload('Invalid JSON: nonfinite number')


def read_json_object(stream, limit=262144):
    """Read at most limit+1 bytes, including when Content-Length is absent."""
    raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise PayloadTooLarge('Payload too large')
    try:
        value = json.loads(raw.decode('utf-8'), parse_constant=_reject_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise InvalidPayload('Invalid JSON body') from exc
    if not isinstance(value, dict):
        raise InvalidPayload('Invalid JSON: expected an object')
    return value
