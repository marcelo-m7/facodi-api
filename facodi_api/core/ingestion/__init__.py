"""Unified Ingestion Service."""

from __future__ import annotations

from typing import Union

from ..contracts.dtos import ContentDocument, ContentSource, SourceType
from .document import DocumentIngestionAdapter
from .youtube import YouTubeIngestionAdapter


class IngestionService:
    """Dispatches sources to the correct ingestion adapter."""

    def __init__(self):
        self.doc_adapter = DocumentIngestionAdapter()
        self.youtube_adapter = YouTubeIngestionAdapter()

    def ingest(self, source: ContentSource) -> ContentDocument:
        """Route source to adapter and return normalized ContentDocument."""
        if source.source_type == SourceType.YOUTUBE:
            return self.youtube_adapter.ingest(source)
        else:
            return self.doc_adapter.ingest(source)
