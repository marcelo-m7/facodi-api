"""DTOs and Contracts for FACODI API Pipeline v2."""

from __future__ import annotations

import math
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def compute_sha256(content: str | bytes) -> str:
    """Compute SHA-256 hash of string or bytes."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


class SourceType(str, Enum):
    YOUTUBE = "youtube"
    DOCUMENT = "document"
    MANUAL = "manual"
    MARKDOWN = "markdown"


class ContentCategory(str, Enum):
    VIDEO = "video"
    ARTICLE = "article"
    DOCUMENT = "document"
    INFOGRAPHIC = "infographic"
    QUIZ = "quiz"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class RunStatus(str, Enum):
    RECEIVED = "received"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    WAITING_REVIEW = "waiting_review"
    WAITING_INPUT = "waiting_input"
    PUBLISHED = "published"


@dataclass(frozen=True)
class TranscriptSegment:
    """A single timestamped transcript segment."""
    start: float
    duration: float
    text: str

    def __post_init__(self):
        for value in (self.start, self.duration):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError("Transcript timing must be finite and nonnegative")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TranscriptSegment:
        return cls(
            start=float(data["start"]),
            duration=float(data["duration"]),
            text=str(data["text"]).strip(),
        )


@dataclass(frozen=True)
class ContentSource:
    """Identification and payload of the raw source."""
    source_type: SourceType
    url: Optional[str] = None
    title: Optional[str] = None
    language: str = "pt"
    raw_content: Optional[str] = None
    raw_file_name: Optional[str] = None
    raw_file_bytes: Optional[bytes] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    schema_version: str = "2.0.0"

    def compute_hash(self) -> str:
        payload = {"source_type": self.source_type.value, "url": self.url,
                   "raw_content": self.raw_content, "filename": self.raw_file_name,
                   "file_hash": compute_sha256(self.raw_file_bytes) if self.raw_file_bytes else None,
                   "title": self.title, "language": self.language,
                   "metadata": self.metadata, "schema_version": self.schema_version}
        return compute_sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False))

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "source_type": self.source_type.value,
            "url": self.url,
            "title": self.title,
            "language": self.language,
            "raw_content": self.raw_content,
            "raw_file_name": self.raw_file_name,
            "metadata": self.metadata,
            "schema_version": self.schema_version,
            "input_hash": self.compute_hash(),
        }
        return d


@dataclass(frozen=True)
class ContentChunk:
    """Chunk of content suitable for enrichment and semantic retrieval."""
    index: int
    title: str
    text: str
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    token_count_estimate: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ContentChunk:
        return cls(
            index=int(data["index"]),
            title=str(data["title"]),
            text=str(data["text"]),
            start_time=float(data["start_time"]) if data.get("start_time") is not None else None,
            end_time=float(data["end_time"]) if data.get("end_time") is not None else None,
            token_count_estimate=int(data.get("token_count_estimate") or len(data["text"].split())),
        )


@dataclass(frozen=True)
class ContentDocument:
    """Normalized content document extracted from a ContentSource."""
    id: str
    source_type: SourceType
    title: str
    text_content: str
    markdown_content: str
    language: str
    source_url: Optional[str] = None
    duration_seconds: Optional[float] = None
    segments: List[TranscriptSegment] = field(default_factory=list)
    chunks: List[ContentChunk] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    input_hash: str = ""
    acquired_at: str = field(default_factory=utc_now_iso)
    schema_version: str = "2.0.0"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source_type": self.source_type.value,
            "title": self.title,
            "text_content": self.text_content,
            "markdown_content": self.markdown_content,
            "language": self.language,
            "source_url": self.source_url,
            "duration_seconds": self.duration_seconds,
            "segments": [s.to_dict() for s in self.segments],
            "chunks": [c.to_dict() for c in self.chunks],
            "metadata": self.metadata,
            "warnings": self.warnings,
            "input_hash": self.input_hash,
            "acquired_at": self.acquired_at,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ContentDocument:
        return cls(
            id=data.get("id") or str(uuid.uuid4()),
            source_type=SourceType(data["source_type"]),
            title=data.get("title") or "Untitled Document",
            text_content=data.get("text_content") or "",
            markdown_content=data.get("markdown_content") or "",
            language=data.get("language") or "pt",
            source_url=data.get("source_url"),
            duration_seconds=data.get("duration_seconds"),
            segments=[TranscriptSegment.from_dict(s) for s in data.get("segments", [])],
            chunks=[ContentChunk.from_dict(c) for c in data.get("chunks", [])],
            metadata=data.get("metadata", {}),
            warnings=data.get("warnings", []),
            input_hash=data.get("input_hash", ""),
            acquired_at=data.get("acquired_at") or utc_now_iso(),
            schema_version=data.get("schema_version", "2.0.0"),
        )


@dataclass(frozen=True)
class ConceptExtraction:
    """Individual concept extracted with evidence references."""
    name: str
    relevance: float
    category: str
    evidence_snippet: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    chunk_indices: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EnrichedDocument:
    """Document enriched with summary, key concepts, topics and pedagogical taxonomy."""
    id: str
    document_id: str
    summary: str
    topics: List[str]
    concepts: List[ConceptExtraction]
    keywords: List[str]
    suggested_category: ContentCategory
    target_audience_level: str
    prerequisites: List[str]
    provider_name: str
    model_name: Optional[str] = None
    prompt_hash: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    schema_version: str = "2.0.0"
    created_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def from_dict(cls, data):
        values = dict(data)
        values['concepts'] = [ConceptExtraction(**item) for item in values.get('concepts', [])]
        values['suggested_category'] = ContentCategory(values['suggested_category'])
        return cls(**values)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "document_id": self.document_id,
            "summary": self.summary,
            "topics": self.topics,
            "concepts": [c.to_dict() for c in self.concepts],
            "keywords": self.keywords,
            "suggested_category": self.suggested_category.value,
            "target_audience_level": self.target_audience_level,
            "prerequisites": self.prerequisites,
            "provider_name": self.provider_name,
            "model_name": self.model_name,
            "prompt_hash": self.prompt_hash,
            "warnings": self.warnings,
            "schema_version": self.schema_version,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class TargetEntity:
    """Entity in a target catalog snapshot (Course, Roadmap, Curricular Unit)."""
    id: str
    name: str
    type: str  # "course", "curricular_unit", "roadmap"
    code: Optional[str] = None
    description: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    topics: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TargetEntity:
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            type=str(data.get("type", "course")),
            code=data.get("code"),
            description=data.get("description"),
            tags=list(data.get("tags", [])),
            topics=list(data.get("topics", [])),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass(frozen=True)
class CatalogSnapshot:
    """Immutable snapshot of the course / curricular catalog."""
    snapshot_id: str
    created_at: str
    targets: List[TargetEntity]
    metadata: Dict[str, Any] = field(default_factory=dict)
    schema_version: str = "2.0.0"

    def compute_hash(self) -> str:
        dump = json.dumps([t.to_dict() for t in self.targets], sort_keys=True)
        return compute_sha256(dump)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "created_at": self.created_at,
            "targets": [t.to_dict() for t in self.targets],
            "metadata": self.metadata,
            "snapshot_hash": self.compute_hash(),
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CatalogSnapshot:
        return cls(
            snapshot_id=data.get("snapshot_id") or str(uuid.uuid4()),
            created_at=data.get("created_at") or utc_now_iso(),
            targets=[TargetEntity.from_dict(t) for t in data.get("targets", [])],
            metadata=data.get("metadata", {}),
            schema_version=data.get("schema_version", "2.0.0"),
        )


@dataclass(frozen=True)
class MappingCandidate:
    """Proposed mapping match with score and justification."""
    target_id: str
    target_name: str
    target_type: str
    relation: str  # "matches_course", "matches_curricular_unit", "suggests_prerequisite"
    score: float  # Deterministic / ranking score (0.0 to 1.0)
    confidence: float
    justification: str
    evidence: List[str]
    matched_concepts: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MappingResult:
    """Complete result of curriculum mapping against a CatalogSnapshot."""
    id: str
    enriched_document_id: str
    snapshot_id: str
    snapshot_hash: str
    candidates: List[MappingCandidate]
    unmatched_concepts: List[str]
    ranking_algorithm_version: str
    created_at: str = field(default_factory=utc_now_iso)
    schema_version: str = "2.0.0"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "enriched_document_id": self.enriched_document_id,
            "snapshot_id": self.snapshot_id,
            "snapshot_hash": self.snapshot_hash,
            "candidates": [c.to_dict() for c in self.candidates],
            "unmatched_concepts": self.unmatched_concepts,
            "ranking_algorithm_version": self.ranking_algorithm_version,
            "created_at": self.created_at,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True)
class PipelineStep:
    """Individual step execution record within a PipelineRun."""
    step_key: str  # "ingest", "enrich", "map", "publish"
    name: str
    status: StepStatus
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    artifact_id: Optional[str] = None
    execution_time_seconds: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_key": self.step_key,
            "name": self.name,
            "status": self.status.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error_message": self.error_message,
            "artifact_id": self.artifact_id,
            "execution_time_seconds": self.execution_time_seconds,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PipelineStep:
        return cls(
            step_key=data["step_key"],
            name=data["name"],
            status=StepStatus(data["status"]),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            error_message=data.get("error_message"),
            artifact_id=data.get("artifact_id"),
            execution_time_seconds=data.get("execution_time_seconds"),
        )


@dataclass(frozen=True)
class PipelineRun:
    """Immutable state and history of an entire pipeline run."""
    run_id: str
    idempotency_key: str
    status: RunStatus
    source_type: SourceType
    source_url: Optional[str]
    created_at: str
    updated_at: str
    steps: List[PipelineStep] = field(default_factory=list)
    artifacts: Dict[str, str] = field(default_factory=dict)  # artifact_key -> artifact_id
    error: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    schema_version: str = "2.0.0"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "idempotency_key": self.idempotency_key,
            "status": self.status.value,
            "source_type": self.source_type.value,
            "source_url": self.source_url,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "steps": [s.to_dict() for s in self.steps],
            "artifacts": self.artifacts,
            "error": self.error,
            "metadata": self.metadata,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PipelineRun:
        return cls(
            run_id=data["run_id"],
            idempotency_key=data.get("idempotency_key") or data["run_id"],
            status=RunStatus(data["status"]),
            source_type=SourceType(data["source_type"]),
            source_url=data.get("source_url"),
            created_at=data.get("created_at") or utc_now_iso(),
            updated_at=data.get("updated_at") or utc_now_iso(),
            steps=[PipelineStep.from_dict(s) for s in data.get("steps", [])],
            artifacts=data.get("artifacts", {}),
            error=data.get("error"),
            metadata=data.get("metadata", {}),
            schema_version=data.get("schema_version", "2.0.0"),
        )


@dataclass(frozen=True)
class ApiError:
    """Structured standard API error."""
    code: str
    message: str
    request_id: str
    retryable: bool = False
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        res = {
            "error": {
                "code": self.code,
                "message": self.message,
                "request_id": self.request_id,
                "retryable": self.retryable,
            }
        }
        if self.details:
            res["error"]["details"] = self.details
        return res
