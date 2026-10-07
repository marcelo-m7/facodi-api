"""Bounded body validation without Odoo; not an HTTP integration test."""
import io
import hashlib
import hmac
import time
import pytest

from facodi_api.core.contracts.webhook_auth import (
    WebhookAuthenticationError,
    WebhookConfigurationError,
    verify_stripe,
    verify_supabase,
)

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


@pytest.mark.parametrize('verify', [verify_supabase, verify_stripe])
def test_webhooks_require_server_secret_and_signature(verify):
    with pytest.raises(WebhookConfigurationError):
        verify(b'{}', None, '')
    with pytest.raises(WebhookAuthenticationError):
        verify(b'{}', None, 'fixture-secret')
    with pytest.raises(WebhookAuthenticationError):
        verify(b'{}', 'invalid-signature', 'fixture-secret')


def test_supabase_signature_binds_exact_body():
    body = b'{"id":"fixture-event"}'
    signature = hmac.new(b'fixture-secret', body, hashlib.sha256).hexdigest()
    verify_supabase(body, signature, 'fixture-secret')
    with pytest.raises(WebhookAuthenticationError):
        verify_supabase(body + b' ', signature, 'fixture-secret')


@pytest.mark.parametrize('expired', [False, True])
def test_stripe_signature_binds_body_and_timestamp(expired):
    body = b'{"id":"evt_fixture","object":"event","type":"fixture.created"}'
    timestamp = int(time.time()) - (600 if expired else 0)
    signed = str(timestamp).encode() + b'.' + body
    digest = hmac.new(b'fixture-secret', signed, hashlib.sha256).hexdigest()
    signature = f't={timestamp},v1={digest}'
    if expired:
        with pytest.raises(WebhookAuthenticationError):
            verify_stripe(body, signature, 'fixture-secret')
    else:
        verify_stripe(body, signature, 'fixture-secret')
        with pytest.raises(WebhookAuthenticationError):
            verify_stripe(body + b' ', signature, 'fixture-secret')
