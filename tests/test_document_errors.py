import pytest

from facodi_api.core.ingestion import document


def test_invalid_document_exposes_only_a_typed_safe_code():
    with pytest.raises(ValueError) as caught:
        document.extract_document(b'not a PDF', '.pdf')
    assert getattr(caught.value, 'code', None) == 'DOCUMENT_INVALID_FORMAT'


def test_child_error_cannot_become_an_arbitrary_public_message(tmp_path, monkeypatch):
    script = tmp_path / 'untrusted.py'
    script.write_text('print(\'{"error":"secret-provider-body"}\')')
    monkeypatch.setattr(document, '_WORKER_SCRIPT', script)
    with pytest.raises(ValueError) as caught:
        document.extract_document(b'input', '.txt')
    assert getattr(caught.value, 'code', None) == 'DOCUMENT_EXTRACTION_FAILED'
    assert 'secret-provider-body' not in str(caught.value)
