"""Bounded body validation without Odoo; not an HTTP integration test."""
import io
import pytest

def parser():
    from facodi_api.core.contracts.http_input import read_json_object
    return read_json_object


def test_stream_without_content_length_is_bounded():
    stream = io.BytesIO(b' ' * 17)
    with pytest.raises(ValueError, match='Payload too large'):
        parser()(stream, limit=16)
    assert stream.tell() == 17


@pytest.mark.parametrize('body', [b'{', b'[]', b'{"x":NaN}', b'\xff'])
def test_invalid_json_never_becomes_empty_submission(body):
    with pytest.raises(ValueError, match='Invalid JSON'):
        parser()(io.BytesIO(body), limit=128)


def test_valid_body_is_read_at_boundary():
    assert parser()(io.BytesIO(b'{"a":1}'), limit=7) == {'a': 1}
