"""Bounded text input and isolated PDF/DOCX conversion; no URL fetching."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

from ..contracts.dtos import ContentDocument, SourceType

_WORKER_SCRIPT = Path(__file__).with_name('document_transport.py')


class DocumentAcquisitionError(ValueError):
    SAFE_CODES = {
        'DOCUMENT_TIMEOUT', 'DOCUMENT_TRANSPORT_UNAVAILABLE',
        'DOCUMENT_EXTRACTION_FAILED', 'DOCUMENT_INVALID_OUTPUT',
        'DOCUMENT_INVALID_FORMAT', 'DOCUMENT_TOO_LARGE', 'DOCUMENT_NO_CONTENT',
        'DOCUMENT_TEXT_TOO_LARGE', 'DOCUMENT_LIMIT_EXCEEDED',
        'DOCUMENT_EXPANSION_TOO_LARGE', 'DOCUMENT_NO_TEXT',
    }

    def __init__(self, code):
        self.code = code if isinstance(code, str) and code in self.SAFE_CODES else 'DOCUMENT_EXTRACTION_FAILED'
        super().__init__(self.code)


def extract_document(content, extension, *, budget_seconds=30):
    try:
        result = subprocess.run(
            [sys.executable, str(_WORKER_SCRIPT)],
            input=json.dumps({'content': base64.b64encode(content).decode('ascii'), 'extension': extension}),
            capture_output=True, text=True, timeout=budget_seconds, check=False,
        )
    except subprocess.TimeoutExpired:
        raise DocumentAcquisitionError('DOCUMENT_TIMEOUT') from None
    except OSError:
        raise DocumentAcquisitionError('DOCUMENT_TRANSPORT_UNAVAILABLE') from None
    if result.returncode or len(result.stdout.encode('utf-8')) > 2 * 1024 * 1024:
        raise DocumentAcquisitionError('DOCUMENT_EXTRACTION_FAILED')
    try:
        payload = json.loads(result.stdout)
        if payload.get('error'):
            raise DocumentAcquisitionError(payload['error'])
        text = payload['text']
        if not isinstance(text, str) or not text.strip() or len(text.encode('utf-8')) > 262144:
            raise DocumentAcquisitionError('DOCUMENT_INVALID_OUTPUT')
        return text
    except (KeyError, TypeError, json.JSONDecodeError):
        raise DocumentAcquisitionError('DOCUMENT_INVALID_OUTPUT') from None


class DocumentIngestionAdapter:
    MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024
    MAX_TEXT_BYTES = 262144

    def ingest(self, source):
        if source.source_type in {SourceType.MANUAL, SourceType.MARKDOWN}:
            if not isinstance(source.raw_content, str) or not source.raw_content.strip():
                raise DocumentAcquisitionError('DOCUMENT_NO_CONTENT')
            text, metadata = source.raw_content, dict(source.metadata)
        else:
            content = source.raw_file_bytes or (source.raw_content or '').encode('utf-8')
            filename = os.path.basename(source.raw_file_name or 'document.txt')
            extension = os.path.splitext(filename)[1].lower()
            if extension not in {'.pdf', '.docx', '.txt', '.md'}:
                raise DocumentAcquisitionError('DOCUMENT_INVALID_FORMAT')
            if not content or len(content) > self.MAX_FILE_SIZE_BYTES:
                raise DocumentAcquisitionError('DOCUMENT_TOO_LARGE' if content else 'DOCUMENT_NO_CONTENT')
            text = extract_document(content, extension)
            metadata = {**source.metadata, 'filename': filename, 'filesize': len(content),
                        'parser_boundary': 'isolated_child'}
        if len(text.encode('utf-8')) > self.MAX_TEXT_BYTES:
            raise DocumentAcquisitionError('DOCUMENT_TEXT_TOO_LARGE')
        first_line = next((line.strip('# ').strip() for line in text.splitlines() if line.strip()), 'Document')
        return ContentDocument(
            id=str(uuid.uuid4()), source_type=source.source_type,
            title=source.title or first_line[:120], text_content=text, markdown_content=text,
            language=source.language or 'pt', source_url=source.url, metadata=metadata,
            input_hash=source.compute_hash(),
        )
