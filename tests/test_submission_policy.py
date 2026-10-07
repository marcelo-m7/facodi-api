import io
import socket

import pytest

from facodi_api.core.contracts import http_input
from facodi_api.core.contracts.dtos import ContentSource, SourceType
from facodi_api.core.ingestion.document import DocumentIngestionAdapter


@pytest.mark.parametrize('kind', [SourceType.MANUAL, SourceType.MARKDOWN])
def test_blank_text_never_becomes_reviewable_content(kind):
    with pytest.raises(ValueError):
        DocumentIngestionAdapter().ingest(ContentSource(kind, raw_content=' \n\t '))


def test_known_length_does_not_wait_for_socket_eof():
    reader, writer = socket.socketpair()
    reader.settimeout(0.2)
    body = b'{"title":"small request"}'
    try:
        writer.sendall(body)
        with reader.makefile('rb') as stream:
            assert http_input.read_request_object(stream, len(body)) == {'title': 'small request'}
    finally:
        reader.close()
        writer.close()


def test_terminated_stream_remains_bounded():
    with pytest.raises(http_input.PayloadTooLarge):
        http_input.read_request_object(io.BytesIO(b'x' * 262145), None, terminated=True)


def test_unterminated_body_without_length_is_rejected():
    with pytest.raises(http_input.InvalidPayload):
        http_input.read_request_object(io.BytesIO(b'{}'), None)
