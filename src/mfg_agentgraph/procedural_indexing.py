"""Pure deterministic procedural index-plan builder for Issue #29 Milestone A1."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Final, TypeAlias, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

_CONTRACT_VERSION: Final = "mfg-agentgraph-procedural-index-v1"
_DISTANCE: Final = "Cosine"
_VECTOR_SOURCE: Final = "caller_supplied"
_COLLECTION_NAME = re.compile(r"[A-Za-z0-9_-]+\Z")
_WINDOWS_ABSOLUTE = re.compile(r"[A-Za-z]:/")
_LOWER_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MAX_INPUT_BYTES: Final = 1_000_000
_MAX_ARTIFACT_BYTES: Final = 10_000_000
_MAX_JSON_NESTING: Final = 128
_MAX_CHUNKS: Final = 10_000
_MAX_CHUNK_CHARS: Final = 1_000_000
_MAX_IDENTIFIER_BYTES: Final = 1_024
_MAX_EVIDENCE_ID_BYTES: Final = 8_192
_MAX_RESPONSE_BYTES: Final = 1_000_000
_CONFIG_KEYS: Final = frozenset(
    {
        "contract_version",
        "document_id",
        "source_path",
        "applicable_asset_id",
        "applicable_asset_type",
        "related_procedure",
        "evidence_id_prefix",
        "first_chunk_index",
        "max_chunk_chars",
        "collection_name",
        "vector_size",
        "distance",
        "payload_indexes",
        "vector_source",
        "vector_producer_id",
        "embedding_generated_by_indexer",
    }
)
_PAYLOAD_INDEXES: Final = (
    ("applicable_asset_id", "keyword"),
    ("applicable_asset_type", "keyword"),
    ("related_procedure", "keyword"),
)
_PAYLOAD_KEYS: Final = frozenset(
    {
        "evidence_id",
        "document",
        "chunk_index",
        "related_procedure",
        "text",
        "applicable_asset_id",
        "applicable_asset_type",
        "source_path",
        "start_line",
        "end_line",
        "source_sha256",
        "index_contract_version",
        "vector_source",
        "vector_producer_id",
        "embedding_generated_by_indexer",
    }
)

JsonScalar: TypeAlias = str | int | float | bool | None
FrozenJson: TypeAlias = JsonScalar | tuple["FrozenJson", ...] | Mapping[str, "FrozenJson"]


class ProceduralIndexBuildError(Exception):
    """Sanitized deterministic failure raised for caller-supplied build defects."""

    code: str
    field: str
    sanitized_detail: str

    def __init__(self, code: str, field: str, sanitized_detail: str) -> None:
        recorded_code = _record_identifier(code, "code")
        recorded_field = _record_identifier(field, "field")
        recorded_detail = _record_identifier(sanitized_detail, "sanitized_detail")
        self.code = recorded_code
        self.field = recorded_field
        self.sanitized_detail = recorded_detail
        super().__init__(f"{recorded_code}:{recorded_field}:{recorded_detail}")


class IndexingTerminalStatus(StrEnum):
    """Terminal outcome of a Qdrant index execution."""

    PASSED = "passed"
    FAILED = "failed"


class IndexingPhase(StrEnum):
    """Last attempted external operation."""

    COLLECTION_LOOKUP = "collection_lookup"
    COLLECTION_CREATE = "collection_create"
    COLLECTION_READBACK = "collection_readback"
    PAYLOAD_INDEX_CREATE = "payload_index_create"
    PAYLOAD_INDEX_READBACK = "payload_index_readback"
    POINT_UPSERT = "point_upsert"


class CollectionState(StrEnum):
    """Conservative knowledge about the target collection."""

    UNKNOWN = "unknown"
    NOT_CREATED = "not_created"
    CREATE_COMPLETED_UNVERIFIED = "create_completed_unverified"
    CREATED = "created"
    VERIFIED_EXISTING = "verified_existing"
    WRITE_OUTCOME_UNKNOWN = "write_outcome_unknown"


class PayloadIndexState(StrEnum):
    """Conservative knowledge about one required payload index."""

    UNKNOWN = "unknown"
    MISSING = "missing"
    PREEXISTING_VERIFIED = "preexisting_verified"
    CREATE_COMPLETED_UNVERIFIED = "create_completed_unverified"
    CREATED_VERIFIED = "created_verified"
    WRITE_OUTCOME_UNKNOWN = "write_outcome_unknown"


@dataclass(frozen=True, slots=True)
class QdrantIndexServiceConfig:
    """Trusted Qdrant service endpoint for executing an immutable plan."""

    base_url: str
    timeout_seconds: float = 5.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_url", _record_base_url(self.base_url))
        timeout = _record_timeout(self.timeout_seconds)
        object.__setattr__(self, "timeout_seconds", timeout)


@dataclass(frozen=True, slots=True)
class ProceduralIndexingResult:
    """Sanitized immutable result of the bounded Qdrant write protocol."""

    status: IndexingTerminalStatus
    phase: IndexingPhase
    collection_state: CollectionState
    payload_indexes: tuple[tuple[str, PayloadIndexState], ...]
    external_side_effect_may_have_occurred: bool
    intended_point_count: int
    completed_point_count: int | None
    intended_point_ids: tuple[str, ...]
    retry_count: int = 0
    error_code: str | None = None
    error_field: str | None = None
    error_detail: str | None = None

    def __post_init__(self) -> None:
        if type(self.status) is not IndexingTerminalStatus:
            raise TypeError("status must be an IndexingTerminalStatus")
        if type(self.phase) is not IndexingPhase:
            raise TypeError("phase must be an IndexingPhase")
        if type(self.collection_state) is not CollectionState:
            raise TypeError("collection_state must be a CollectionState")
        if type(self.external_side_effect_may_have_occurred) is not bool:
            raise TypeError("external_side_effect_may_have_occurred must be a bool")
        _record_nonnegative_int(self.intended_point_count, "intended_point_count")
        if self.completed_point_count is not None:
            _record_nonnegative_int(self.completed_point_count, "completed_point_count")
            if self.completed_point_count > self.intended_point_count:
                raise ValueError("completed_point_count must not exceed intended_point_count")
        if self.retry_count != 0 or type(self.retry_count) is not int:
            raise ValueError("retry_count must be zero")
        indexes = _record_index_states(self.payload_indexes)
        point_ids = _record_result_point_ids(self.intended_point_ids)
        if self.intended_point_count != len(point_ids):
            raise ValueError("intended_point_count must match intended_point_ids")
        errors = (self.error_code, self.error_field, self.error_detail)
        if self.status is IndexingTerminalStatus.PASSED:
            if any(value is not None for value in errors):
                raise ValueError("passed results must not contain an error")
            if self.phase is not IndexingPhase.POINT_UPSERT:
                raise ValueError("passed results must finish at point_upsert")
            if self.completed_point_count != self.intended_point_count:
                raise ValueError("passed results must complete every intended point")
            if self.collection_state not in {
                CollectionState.CREATED,
                CollectionState.VERIFIED_EXISTING,
            }:
                raise ValueError("passed result collection_state must be verified")
            if not self.external_side_effect_may_have_occurred:
                raise ValueError("passed results must record the upsert side effect")
            if any(
                state
                not in {PayloadIndexState.PREEXISTING_VERIFIED, PayloadIndexState.CREATED_VERIFIED}
                for _, state in indexes
            ):
                raise ValueError("passed results require verified payload indexes")
        else:
            if any(type(value) is not str for value in errors):
                raise ValueError("failed results must contain one sanitized error")
            if self.phase is IndexingPhase.POINT_UPSERT:
                if self.completed_point_count is not None:
                    raise ValueError(
                        "failed point_upsert results must have unknown completed count"
                    )
            elif self.completed_point_count != 0:
                raise ValueError(
                    "failed results before point_upsert must have zero completed points"
                )
            for field_name, value in zip(
                ("error_code", "error_field", "error_detail"),
                errors,
                strict=True,
            ):
                _record_identifier(value, field_name)
        object.__setattr__(self, "payload_indexes", indexes)
        object.__setattr__(self, "intended_point_ids", point_ids)


@dataclass(frozen=True, slots=True)
class ProceduralIndexConfig:
    """Normalized, versioned configuration retained by an index plan."""

    contract_version: str
    document_id: str
    source_path: str
    applicable_asset_id: str
    applicable_asset_type: str
    related_procedure: str
    evidence_id_prefix: str
    first_chunk_index: int
    max_chunk_chars: int
    collection_name: str
    vector_size: int
    distance: str
    payload_indexes: tuple[Mapping[str, FrozenJson], ...]
    vector_source: str
    vector_producer_id: str
    embedding_generated_by_indexer: bool

    def __post_init__(self) -> None:
        for field_name in (
            "contract_version",
            "document_id",
            "applicable_asset_id",
            "applicable_asset_type",
            "related_procedure",
            "evidence_id_prefix",
            "distance",
            "vector_source",
            "vector_producer_id",
        ):
            _record_identifier(getattr(self, field_name), field_name)
        _record_source_path(self.source_path)
        _record_collection_name(self.collection_name)
        for field_name in ("first_chunk_index", "max_chunk_chars", "vector_size"):
            _record_positive_int(getattr(self, field_name), field_name)
        if self.max_chunk_chars > _MAX_CHUNK_CHARS:
            raise ValueError("max_chunk_chars exceeds the contract")
        if self.contract_version != _CONTRACT_VERSION:
            raise ValueError("contract_version must match the contract")
        if self.distance != _DISTANCE:
            raise ValueError("distance must match the contract")
        if self.vector_source != _VECTOR_SOURCE:
            raise ValueError("vector_source must match the contract")
        if self.embedding_generated_by_indexer is not False:
            raise ValueError("embedding_generated_by_indexer must be false")
        values = _record_members(self.payload_indexes, Mapping, "payload_indexes")
        indexes = tuple(_record_mapping(item, "payload_indexes") for item in values)
        expected = _payload_index_documents()
        if list(indexes) != expected:
            raise ValueError("payload_indexes must match the contract")
        object.__setattr__(
            self,
            "payload_indexes",
            tuple(cast(Mapping[str, FrozenJson], _freeze(item)) for item in indexes),
        )


@dataclass(frozen=True, slots=True)
class ProceduralSourceSnapshot:
    """Canonical source content and identity retained for audit and validation."""

    document_id: str
    source_path: str
    canonical_text: str
    source_sha256: str

    def __post_init__(self) -> None:
        _record_identifier(self.document_id, "document_id")
        _record_source_path(self.source_path)
        if type(self.canonical_text) is not str:
            raise TypeError("canonical_text must be a string")
        if self.canonical_text.startswith("\ufeff") or "\x00" in self.canonical_text:
            raise ValueError("canonical_text contains a forbidden character")
        if "\r" in self.canonical_text or not self.canonical_text.endswith("\n"):
            raise ValueError("canonical_text must use canonical LF newlines")
        if self.canonical_text.endswith("\n\n") or not self.canonical_text.strip():
            raise ValueError("canonical_text must have exactly one final LF and be nonblank")
        try:
            canonical_bytes = self.canonical_text.encode("utf-8")
        except UnicodeEncodeError:
            raise ValueError("canonical_text must contain only Unicode scalar values") from None
        if len(canonical_bytes) > _MAX_INPUT_BYTES:
            raise ValueError("canonical_text exceeds the input byte limit")
        digest = hashlib.sha256(canonical_bytes).hexdigest()
        _record_digest(self.source_sha256)
        if digest != self.source_sha256:
            raise ValueError("source_sha256 must match canonical_text")


@dataclass(frozen=True, slots=True)
class ProceduralVectorMap:
    """Exact immutable caller-supplied vectors retained by an index plan."""

    vectors: Mapping[str, Sequence[float]]
    vector_size: int

    def __post_init__(self) -> None:
        _record_positive_int(self.vector_size, "vector_size")
        if not isinstance(self.vectors, Mapping):
            raise TypeError("vectors must be a mapping")
        if not self.vectors:
            raise ValueError("vectors must be nonempty")
        normalized: dict[str, tuple[float, ...]] = {}
        for evidence_id, vector in self.vectors.items():
            _record_identifier(evidence_id, "vectors.evidence_id")
            recorded = _record_vector(vector)
            if len(recorded) != self.vector_size:
                raise ValueError("vector must have the configured dimension")
            normalized[evidence_id] = recorded
        object.__setattr__(self, "vectors", MappingProxyType(normalized))


@dataclass(frozen=True, slots=True)
class ProceduralChunk:
    """One stable, source-located paragraph chunk."""

    evidence_id: str
    document: str
    chunk_index: int
    related_procedure: str
    text: str
    applicable_asset_id: str
    applicable_asset_type: str
    source_path: str
    start_line: int
    end_line: int
    source_sha256: str
    index_contract_version: str
    vector_source: str
    vector_producer_id: str
    embedding_generated_by_indexer: bool

    def __post_init__(self) -> None:
        for field_name in (
            "evidence_id",
            "document",
            "related_procedure",
            "applicable_asset_id",
            "applicable_asset_type",
            "index_contract_version",
            "vector_source",
            "vector_producer_id",
        ):
            _record_identifier(getattr(self, field_name), field_name)
        _record_source_path(self.source_path)
        _record_text(self.text)
        _record_positive_int(self.chunk_index, "chunk_index")
        _record_positive_int(self.start_line, "start_line")
        _record_positive_int(self.end_line, "end_line")
        if self.start_line > self.end_line:
            raise ValueError("start_line must not exceed end_line")
        _record_digest(self.source_sha256)
        if self.index_contract_version != _CONTRACT_VERSION:
            raise ValueError("index_contract_version must match the contract")
        if self.vector_source != _VECTOR_SOURCE:
            raise ValueError("vector_source must match the contract")
        if self.embedding_generated_by_indexer is not False:
            raise ValueError("embedding_generated_by_indexer must be false")


@dataclass(frozen=True, slots=True)
class ProceduralIndexPoint:
    """Immutable Qdrant point snapshot."""

    point_id: str
    vector: tuple[float, ...]
    payload: Mapping[str, FrozenJson]

    def __post_init__(self) -> None:
        payload = _record_payload(self.payload)
        vector = _record_vector(self.vector)
        if type(self.point_id) is not str:
            raise TypeError("point_id must be a string")
        try:
            parsed_id = uuid.UUID(self.point_id)
        except (ValueError, AttributeError):
            raise ValueError("point_id must be a canonical UUID") from None
        if str(parsed_id) != self.point_id:
            raise ValueError("point_id must be a canonical UUID")
        expected_id = _point_uuid(
            cast(str, payload["index_contract_version"]),
            cast(str, payload["document"]),
            cast(str, payload["evidence_id"]),
        )
        if self.point_id != expected_id:
            raise ValueError("point_id must be derived from payload identity")
        object.__setattr__(self, "vector", vector)
        object.__setattr__(self, "payload", cast(Mapping[str, FrozenJson], _freeze(payload)))


@dataclass(frozen=True, slots=True)
class ProceduralIndexPlan:
    """Deeply immutable artifact and Qdrant request snapshots."""

    artifact_bytes: bytes
    create_collection_request: Mapping[str, FrozenJson]
    payload_index_requests: tuple[Mapping[str, FrozenJson], ...]
    upsert_request: Mapping[str, FrozenJson]
    chunks: tuple[ProceduralChunk, ...]
    points: tuple[ProceduralIndexPoint, ...]
    config: ProceduralIndexConfig
    source: ProceduralSourceSnapshot
    vectors: ProceduralVectorMap

    def __post_init__(self) -> None:
        if type(self.artifact_bytes) is not bytes:
            raise TypeError("artifact_bytes must be exact bytes")
        if type(self.config) is not ProceduralIndexConfig:
            raise TypeError("config must be a ProceduralIndexConfig")
        if type(self.source) is not ProceduralSourceSnapshot:
            raise TypeError("source must be a ProceduralSourceSnapshot")
        if type(self.vectors) is not ProceduralVectorMap:
            raise TypeError("vectors must be a ProceduralVectorMap")
        config = self.config
        source = self.source
        vectors = self.vectors
        if source.document_id != config.document_id or source.source_path != config.source_path:
            raise ValueError("source identity must match config")
        if vectors.vector_size != config.vector_size:
            raise ValueError("vector dimension must match config")
        chunks = _record_members(self.chunks, ProceduralChunk, "chunks")
        points = _record_members(self.points, ProceduralIndexPoint, "points")
        if not chunks or len(chunks) != len(points):
            raise ValueError("chunks and points must have equal nonzero length")
        evidence_ids = tuple(chunk.evidence_id for chunk in chunks)
        point_ids = tuple(point.point_id for point in points)
        if len(set(evidence_ids)) != len(evidence_ids) or len(set(point_ids)) != len(point_ids):
            raise ValueError("evidence and point IDs must be unique")
        for previous, current in zip(chunks, chunks[1:], strict=False):
            if current.start_line <= previous.end_line:
                raise ValueError("chunks must be strictly ordered by source location")
            if current.chunk_index != previous.chunk_index + 1:
                raise ValueError("chunk indices must be consecutive")
        if chunks[0].chunk_index != config.first_chunk_index:
            raise ValueError("chunk indices must start at the configured index")
        if set(vectors.vectors) != set(evidence_ids):
            raise ValueError("vector IDs must exactly match chunk evidence IDs")

        try:
            source_chunks = _chunk_source(source.canonical_text, config.max_chunk_chars)
        except ProceduralIndexBuildError:
            raise ValueError("source snapshot violates configured chunking") from None
        expected_chunks = tuple(
            ProceduralChunk(
                evidence_id=f"{config.evidence_id_prefix}{config.first_chunk_index + offset}",
                document=config.document_id,
                chunk_index=config.first_chunk_index + offset,
                related_procedure=config.related_procedure,
                text=item.text,
                applicable_asset_id=config.applicable_asset_id,
                applicable_asset_type=config.applicable_asset_type,
                source_path=config.source_path,
                start_line=item.start_line,
                end_line=item.end_line,
                source_sha256=source.source_sha256,
                index_contract_version=config.contract_version,
                vector_source=config.vector_source,
                vector_producer_id=config.vector_producer_id,
                embedding_generated_by_indexer=config.embedding_generated_by_indexer,
            )
            for offset, item in enumerate(source_chunks)
        )
        if chunks != expected_chunks:
            raise ValueError("chunks must exactly match config and source snapshot")

        create_request = _record_mapping(
            self.create_collection_request, "create_collection_request"
        )
        payload_request_values = _record_members(
            self.payload_index_requests, Mapping, "payload_index_requests"
        )
        payload_requests = tuple(
            _record_mapping(item, "payload_index_requests") for item in payload_request_values
        )
        upsert_request = _record_mapping(self.upsert_request, "upsert_request")
        expected_indexes = _payload_index_documents()
        if list(payload_requests) != expected_indexes:
            raise ValueError("payload_index_requests must match the contract")

        if list(config.payload_indexes) != expected_indexes:
            raise ValueError("payload index requests must match config")
        vector_size = config.vector_size
        if create_request != {"vectors": {"size": vector_size, "distance": config.distance}}:
            raise ValueError("create_collection_request must match config")
        point_documents = [_point_document(point) for point in points]
        if upsert_request != {"points": point_documents}:
            raise ValueError("upsert_request must match points")
        for chunk, point in zip(chunks, points, strict=True):
            if dict(point.payload) != _chunk_payload(chunk):
                raise ValueError("point payloads must match chunks")
            if point.vector != vectors.vectors[chunk.evidence_id]:
                raise ValueError("points must match retained vectors and chunk order")

        artifact = _record_artifact(self.artifact_bytes)
        if artifact["contract_version"] != config.contract_version:
            raise ValueError("artifact contract_version must match the contract")
        collection = artifact["collection"]
        if type(collection) is not dict or set(collection) != {"name", "vector_size", "distance"}:
            raise ValueError("artifact collection schema is invalid")
        _record_collection_name(collection["name"])
        if collection != {
            "name": config.collection_name,
            "vector_size": vector_size,
            "distance": config.distance,
        }:
            raise ValueError("artifact collection must match config")
        if artifact["payload_indexes"] != expected_indexes or artifact["points"] != point_documents:
            raise ValueError("artifact requests and points must match the plan")
        if artifact["source"] != {
            "document_id": source.document_id,
            "source_path": source.source_path,
            "source_sha256": source.source_sha256,
        }:
            raise ValueError("artifact source must match source snapshot")

        object.__setattr__(self, "chunks", chunks)
        object.__setattr__(self, "points", points)
        object.__setattr__(
            self,
            "create_collection_request",
            cast(Mapping[str, FrozenJson], _freeze(create_request)),
        )
        object.__setattr__(
            self,
            "payload_index_requests",
            tuple(cast(Mapping[str, FrozenJson], _freeze(item)) for item in payload_requests),
        )
        object.__setattr__(
            self,
            "upsert_request",
            cast(Mapping[str, FrozenJson], _freeze(upsert_request)),
        )


_Config = ProceduralIndexConfig


@dataclass(frozen=True, slots=True)
class _SourceChunk:
    text: str
    start_line: int
    end_line: int


def build_procedural_index(
    config_bytes: bytes, source_bytes: bytes, vector_bytes: bytes
) -> ProceduralIndexPlan:
    """Build a deterministic procedural index plan without I/O or inference."""

    failure_fields: tuple[str, str, str] | None = None
    result: ProceduralIndexPlan | None = None
    try:
        _require_exact_bytes(config_bytes, "config_bytes")
        _require_exact_bytes(source_bytes, "source_bytes")
        _require_exact_bytes(vector_bytes, "vector_bytes")
        _require_input_bound(config_bytes, "config_bytes")
        _require_input_bound(source_bytes, "source_bytes")
        _require_input_bound(vector_bytes, "vector_bytes")
        result = _build(config_bytes, source_bytes, vector_bytes)
    except ProceduralIndexBuildError as error:
        failure_fields = (error.code, error.field, error.sanitized_detail)
    except Exception:
        failure_fields = ("build_invalid", "inputs", "input violates the build contract")
    finally:
        del config_bytes, source_bytes, vector_bytes
    if failure_fields is not None:
        code, field, detail = failure_fields
        del failure_fields
        raise ProceduralIndexBuildError(code, field, detail) from None
    assert result is not None
    return result


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        del req, fp, code, msg, headers, newurl
        return None


class _ExecutionFailure(Exception):
    def __init__(self, code: str, field: str, detail: str, *, not_found: bool = False) -> None:
        self.code = code
        self.field = field
        self.detail = detail
        self.not_found = not_found
        super().__init__(detail)


def execute_procedural_index(
    plan: ProceduralIndexPlan,
    service: QdrantIndexServiceConfig,
) -> ProceduralIndexingResult:
    """Execute the fixed Qdrant 1.19.2 protocol with sanitized failures."""

    if type(plan) is not ProceduralIndexPlan:
        raise TypeError("plan must be a ProceduralIndexPlan")
    if type(service) is not QdrantIndexServiceConfig:
        raise TypeError("service must be a QdrantIndexServiceConfig")
    try:
        return _execute_procedural_index(plan, service)
    except Exception:
        point_ids = tuple(point.point_id for point in plan.points)
        return _indexing_result(
            status=IndexingTerminalStatus.FAILED,
            phase=IndexingPhase.COLLECTION_LOOKUP,
            collection_state=CollectionState.UNKNOWN,
            index_states={field: PayloadIndexState.UNKNOWN for field, _ in _PAYLOAD_INDEXES},
            side_effect=False,
            intended_count=len(point_ids),
            completed_count=0,
            point_ids=point_ids,
            error=_ExecutionFailure(
                "unexpected_execution_failure",
                "qdrant_service",
                "unexpected Qdrant indexing failure",
            ),
        )


def _execute_procedural_index(
    plan: ProceduralIndexPlan,
    service: QdrantIndexServiceConfig,
) -> ProceduralIndexingResult:
    """Execute the protocol after public-boundary validation."""

    point_ids = tuple(point.point_id for point in plan.points)
    intended_count = len(point_ids)
    collection_state = CollectionState.UNKNOWN
    index_states = {field: PayloadIndexState.UNKNOWN for field, _ in _PAYLOAD_INDEXES}
    side_effect = False
    completed_count: int | None = 0
    phase = IndexingPhase.COLLECTION_LOOKUP
    opener = build_opener(ProxyHandler({}), _NoRedirectHandler())
    collection_path = f"/collections/{plan.config.collection_name}"

    def failure(error: _ExecutionFailure) -> ProceduralIndexingResult:
        return _indexing_result(
            status=IndexingTerminalStatus.FAILED,
            phase=phase,
            collection_state=collection_state,
            index_states=index_states,
            side_effect=side_effect,
            intended_count=intended_count,
            completed_count=completed_count,
            point_ids=point_ids,
            error=error,
        )

    try:
        document = _qdrant_request(opener, service, "GET", collection_path)
    except _ExecutionFailure as error:
        if not error.not_found:
            return failure(error)
        collection_state = CollectionState.NOT_CREATED
        phase = IndexingPhase.COLLECTION_CREATE
        side_effect = True
        collection_state = CollectionState.WRITE_OUTCOME_UNKNOWN
        try:
            created = _qdrant_request(
                opener,
                service,
                "PUT",
                collection_path,
                plan.create_collection_request,
            )
            _require_create_response(created)
        except _ExecutionFailure as create_error:
            return failure(create_error)
        except Exception:
            return failure(_unexpected_execution("collection", "collection creation failed"))
        collection_state = CollectionState.CREATE_COMPLETED_UNVERIFIED
        phase = IndexingPhase.COLLECTION_READBACK
        try:
            document = _qdrant_request(opener, service, "GET", collection_path)
            existing, missing = _collection_contract(document, plan)
        except _ExecutionFailure as readback_error:
            return failure(readback_error)
        except Exception:
            return failure(_unexpected_execution("collection", "collection readback failed"))
        collection_state = CollectionState.CREATED
    else:
        try:
            existing, missing = _collection_contract(document, plan)
        except _ExecutionFailure as compatibility_error:
            return failure(compatibility_error)
        except Exception:
            return failure(_unexpected_execution("collection", "collection validation failed"))
        collection_state = CollectionState.VERIFIED_EXISTING

    for field in existing:
        index_states[field] = PayloadIndexState.PREEXISTING_VERIFIED
    for field in missing:
        index_states[field] = PayloadIndexState.MISSING

    for request_body in plan.payload_index_requests:
        field = cast(str, request_body["field_name"])
        if index_states[field] is not PayloadIndexState.MISSING:
            continue
        phase = IndexingPhase.PAYLOAD_INDEX_CREATE
        side_effect = True
        index_states[field] = PayloadIndexState.WRITE_OUTCOME_UNKNOWN
        try:
            response = _qdrant_request(
                opener,
                service,
                "PUT",
                f"{collection_path}/index?wait=true",
                request_body,
            )
            _require_update_response(response, field)
        except _ExecutionFailure as index_error:
            index_error = _ExecutionFailure(
                index_error.code,
                field,
                index_error.detail,
            )
            return failure(index_error)
        except Exception:
            return failure(_unexpected_execution(field, "payload index creation failed"))
        index_states[field] = PayloadIndexState.CREATE_COMPLETED_UNVERIFIED

    phase = IndexingPhase.PAYLOAD_INDEX_READBACK
    try:
        readback = _qdrant_request(opener, service, "GET", collection_path)
        verified, still_missing = _collection_contract(readback, plan)
        if still_missing:
            raise _ExecutionFailure(
                "payload_index_unverified",
                still_missing[0],
                "required payload index was not verified",
            )
    except _ExecutionFailure as readback_error:
        return failure(readback_error)
    except Exception:
        return failure(_unexpected_execution("payload_indexes", "payload index readback failed"))
    for field in verified:
        if index_states[field] is PayloadIndexState.CREATE_COMPLETED_UNVERIFIED:
            index_states[field] = PayloadIndexState.CREATED_VERIFIED
        elif index_states[field] is PayloadIndexState.MISSING:
            index_states[field] = PayloadIndexState.PREEXISTING_VERIFIED

    phase = IndexingPhase.POINT_UPSERT
    side_effect = True
    completed_count = None
    try:
        response = _qdrant_request(
            opener,
            service,
            "PUT",
            f"{collection_path}/points?wait=true",
            plan.upsert_request,
        )
        _require_update_response(response, "points")
    except _ExecutionFailure as upsert_error:
        return failure(upsert_error)
    except Exception:
        return failure(_unexpected_execution("points", "point upsert failed"))
    completed_count = intended_count
    return _indexing_result(
        status=IndexingTerminalStatus.PASSED,
        phase=phase,
        collection_state=collection_state,
        index_states=index_states,
        side_effect=side_effect,
        intended_count=intended_count,
        completed_count=completed_count,
        point_ids=point_ids,
    )


def _qdrant_request(
    opener: Any,
    service: QdrantIndexServiceConfig,
    method: str,
    path: str,
    body: Mapping[str, FrozenJson] | None = None,
) -> dict[str, Any]:
    data = (
        None
        if body is None
        else json.dumps(
            _mutable_json(body, "request"),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = Request(f"{service.base_url}{path}", data=data, method=method, headers=headers)
    try:
        with opener.open(request, timeout=service.timeout_seconds) as response:
            if getattr(response, "status", None) != 200:
                raise _ExecutionFailure(
                    "qdrant_response_invalid",
                    "qdrant_service",
                    "Qdrant returned a non-200 response",
                )
            media_type = response.headers.get("Content-Type", "").partition(";")[0].strip().lower()
            if media_type != "application/json":
                raise _ExecutionFailure(
                    "qdrant_response_invalid",
                    "qdrant_service",
                    "Qdrant response media type is not JSON",
                )
            payload: bytes = response.read(_MAX_RESPONSE_BYTES + 1)
    except _ExecutionFailure:
        raise
    except HTTPError as error:
        if method == "GET" and error.code == 404:
            raise _ExecutionFailure(
                "collection_not_found",
                "collection",
                "Qdrant collection was not found",
                not_found=True,
            ) from None
        raise _ExecutionFailure(
            "qdrant_request_failed", _request_field(path), _request_failure_detail(path)
        ) from None
    except (URLError, TimeoutError, OSError):
        raise _ExecutionFailure(
            "qdrant_request_failed", _request_field(path), _request_failure_detail(path)
        ) from None
    except Exception:
        raise _ExecutionFailure(
            "qdrant_request_failed", _request_field(path), _request_failure_detail(path)
        ) from None
    if len(payload) > _MAX_RESPONSE_BYTES:
        raise _ExecutionFailure(
            "qdrant_response_invalid",
            _request_field(path),
            "Qdrant response exceeds the size limit",
        )
    try:
        text = payload.decode("utf-8")
        _validate_json_nesting(text, "qdrant_response")
        document = json.loads(
            text,
            object_pairs_hook=_execution_unique_object,
            parse_constant=_execution_reject_constant,
        )
    except Exception:
        raise _ExecutionFailure(
            "qdrant_response_invalid", _request_field(path), "Qdrant returned malformed JSON"
        ) from None
    if (
        type(document) is not dict
        or type(document.get("status")) is not str
        or document["status"] != "ok"
    ):
        raise _ExecutionFailure(
            "qdrant_response_invalid", _request_field(path), "Qdrant response envelope is invalid"
        )
    return cast(dict[str, Any], document)


def _collection_contract(
    document: Mapping[str, Any], plan: ProceduralIndexPlan
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    try:
        result = document["result"]
        vectors = result["config"]["params"]["vectors"]
        payload_schema = result["payload_schema"]
    except (KeyError, TypeError):
        raise _ExecutionFailure(
            "collection_incompatible", "collection", "collection configuration is incompatible"
        ) from None
    if (
        type(vectors) is not dict
        or type(vectors.get("size")) is not int
        or type(vectors.get("distance")) is not str
        or vectors["size"] != plan.config.vector_size
        or vectors["distance"] != plan.config.distance
        or type(payload_schema) is not dict
    ):
        raise _ExecutionFailure(
            "collection_incompatible", "collection", "collection configuration is incompatible"
        )
    existing: list[str] = []
    missing: list[str] = []
    for field, _ in _PAYLOAD_INDEXES:
        schema = payload_schema.get(field)
        if schema is None:
            missing.append(field)
        elif (
            type(schema) is dict
            and type(schema.get("data_type")) is str
            and schema["data_type"] == "keyword"
        ):
            existing.append(field)
        else:
            raise _ExecutionFailure(
                "collection_incompatible", field, "required payload index is incompatible"
            )
    return tuple(existing), tuple(missing)


def _require_create_response(document: Mapping[str, Any]) -> None:
    if type(document.get("result")) is not bool or document["result"] is not True:
        raise _ExecutionFailure(
            "qdrant_response_invalid", "collection", "collection creation was not completed"
        )


def _require_update_response(document: Mapping[str, Any], field: str) -> None:
    result = document.get("result")
    if (
        type(result) is not dict
        or type(result.get("status")) is not str
        or result["status"] != "completed"
    ):
        raise _ExecutionFailure("qdrant_response_invalid", field, "Qdrant write was not completed")


def _indexing_result(
    *,
    status: IndexingTerminalStatus,
    phase: IndexingPhase,
    collection_state: CollectionState,
    index_states: Mapping[str, PayloadIndexState],
    side_effect: bool,
    intended_count: int,
    completed_count: int | None,
    point_ids: tuple[str, ...],
    error: _ExecutionFailure | None = None,
) -> ProceduralIndexingResult:
    return ProceduralIndexingResult(
        status=status,
        phase=phase,
        collection_state=collection_state,
        payload_indexes=tuple((field, index_states[field]) for field, _ in _PAYLOAD_INDEXES),
        external_side_effect_may_have_occurred=side_effect,
        intended_point_count=intended_count,
        completed_point_count=completed_count,
        intended_point_ids=point_ids,
        error_code=None if error is None else error.code,
        error_field=None if error is None else error.field,
        error_detail=None if error is None else error.detail,
    )


def _execution_unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _execution_reject_constant(value: str) -> None:
    del value
    raise ValueError("nonfinite number")


def _unexpected_execution(field: str, detail: str) -> _ExecutionFailure:
    return _ExecutionFailure("unexpected_execution_failure", field, detail)


def _request_field(path: str) -> str:
    if path.endswith("/points?wait=true"):
        return "points"
    if path.endswith("/index?wait=true"):
        return "payload_index"
    return "collection"


def _request_failure_detail(path: str) -> str:
    if path.endswith("/points?wait=true"):
        return "point upsert request failed"
    if path.endswith("/index?wait=true"):
        return "payload index request failed"
    return "collection request failed"


def _build(config_bytes: bytes, source_bytes: bytes, vector_bytes: bytes) -> ProceduralIndexPlan:
    config = _parse_config(config_bytes)
    canonical_source, source_sha256 = _canonical_source(source_bytes)
    source = ProceduralSourceSnapshot(
        document_id=config.document_id,
        source_path=config.source_path,
        canonical_text=canonical_source,
        source_sha256=source_sha256,
    )
    source_chunks = _chunk_source(canonical_source, config.max_chunk_chars)
    if not source_chunks:
        raise _error("source_blank", "source_bytes", "source must produce at least one chunk")

    chunks: list[ProceduralChunk] = []
    evidence_ids: list[str] = []
    seen_evidence_ids: set[str] = set()
    for offset, source_chunk in enumerate(source_chunks):
        chunk_index = config.first_chunk_index + offset
        evidence_id = f"{config.evidence_id_prefix}{chunk_index}"
        if evidence_id in seen_evidence_ids:
            raise _error("evidence_id_duplicate", "evidence_id_prefix", "generated ID is duplicate")
        evidence_ids.append(evidence_id)
        seen_evidence_ids.add(evidence_id)
        chunks.append(
            ProceduralChunk(
                evidence_id=evidence_id,
                document=config.document_id,
                chunk_index=chunk_index,
                related_procedure=config.related_procedure,
                text=source_chunk.text,
                applicable_asset_id=config.applicable_asset_id,
                applicable_asset_type=config.applicable_asset_type,
                source_path=config.source_path,
                start_line=source_chunk.start_line,
                end_line=source_chunk.end_line,
                source_sha256=source_sha256,
                index_contract_version=config.contract_version,
                vector_source=config.vector_source,
                vector_producer_id=config.vector_producer_id,
                embedding_generated_by_indexer=config.embedding_generated_by_indexer,
            )
        )

    vectors = ProceduralVectorMap(
        vectors=_parse_vectors(vector_bytes, tuple(evidence_ids), config.vector_size),
        vector_size=config.vector_size,
    )
    point_documents: list[dict[str, Any]] = []
    points: list[ProceduralIndexPoint] = []
    for chunk in chunks:
        point_id = _point_uuid(config.contract_version, config.document_id, chunk.evidence_id)
        payload = _chunk_payload(chunk)
        vector = cast(tuple[float, ...], vectors.vectors[chunk.evidence_id])
        point_document: dict[str, Any] = {
            "id": point_id,
            "vector": list(vector),
            "payload": payload,
        }
        point_documents.append(point_document)
        points.append(
            ProceduralIndexPoint(
                point_id=point_id,
                vector=vector,
                payload=cast(Mapping[str, FrozenJson], _freeze(payload)),
            )
        )

    payload_indexes = [
        {"field_name": field_name, "field_schema": field_schema}
        for field_name, field_schema in _PAYLOAD_INDEXES
    ]
    artifact: dict[str, Any] = {
        "contract_version": config.contract_version,
        "collection": {
            "name": config.collection_name,
            "vector_size": config.vector_size,
            "distance": config.distance,
        },
        "payload_indexes": payload_indexes,
        "source": {
            "document_id": config.document_id,
            "source_path": config.source_path,
            "source_sha256": source_sha256,
        },
        "points": point_documents,
    }
    artifact_bytes = (
        json.dumps(
            artifact,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )
    create_request = {"vectors": {"size": config.vector_size, "distance": config.distance}}
    upsert_request = {"points": point_documents}
    return ProceduralIndexPlan(
        artifact_bytes=artifact_bytes,
        create_collection_request=cast(Mapping[str, FrozenJson], _freeze(create_request)),
        payload_index_requests=tuple(
            cast(Mapping[str, FrozenJson], _freeze(item)) for item in payload_indexes
        ),
        upsert_request=cast(Mapping[str, FrozenJson], _freeze(upsert_request)),
        chunks=tuple(chunks),
        points=tuple(points),
        config=config,
        source=source,
        vectors=vectors,
    )


def _parse_config(payload: bytes) -> _Config:
    document = _strict_json(payload, "config_bytes")
    if type(document) is not dict:
        raise _error("config_type", "config_bytes", "config must be a JSON object")
    values = cast(dict[str, Any], document)
    if set(values) != _CONFIG_KEYS:
        raise _error("config_keys", "config_bytes", "config keys must match the contract")

    contract_version = _strict_string(values["contract_version"], "contract_version")
    document_id = _strict_string(values["document_id"], "document_id")
    source_path = _source_path(values["source_path"])
    applicable_asset_id = _strict_string(values["applicable_asset_id"], "applicable_asset_id")
    applicable_asset_type = _strict_string(values["applicable_asset_type"], "applicable_asset_type")
    related_procedure = _strict_string(values["related_procedure"], "related_procedure")
    evidence_id_prefix = _strict_string(values["evidence_id_prefix"], "evidence_id_prefix")
    collection_name = _strict_string(values["collection_name"], "collection_name")
    vector_source = _strict_string(values["vector_source"], "vector_source")
    vector_producer_id = _strict_string(values["vector_producer_id"], "vector_producer_id")
    first_chunk_index = _positive_int(values["first_chunk_index"], "first_chunk_index")
    max_chunk_chars = _positive_int(values["max_chunk_chars"], "max_chunk_chars")
    vector_size = _positive_int(values["vector_size"], "vector_size")

    if max_chunk_chars > _MAX_CHUNK_CHARS:
        raise _error("config_value", "max_chunk_chars", "chunk limit exceeds the contract")

    if contract_version != _CONTRACT_VERSION:
        raise _error("config_value", "contract_version", "unsupported contract version")
    if not _COLLECTION_NAME.fullmatch(collection_name):
        raise _error("config_value", "collection_name", "collection name is unsafe")
    if values["distance"] != _DISTANCE or type(values["distance"]) is not str:
        raise _error("config_value", "distance", "distance must match the contract")
    if vector_source != _VECTOR_SOURCE:
        raise _error("config_value", "vector_source", "vector source must match the contract")
    if values["embedding_generated_by_indexer"] is not False:
        raise _error(
            "config_value",
            "embedding_generated_by_indexer",
            "embedding flag must match the contract",
        )
    if not _valid_payload_indexes(values["payload_indexes"]):
        raise _error("config_value", "payload_indexes", "payload indexes must match the contract")

    return _Config(
        contract_version=contract_version,
        document_id=document_id,
        source_path=source_path,
        applicable_asset_id=applicable_asset_id,
        applicable_asset_type=applicable_asset_type,
        related_procedure=related_procedure,
        evidence_id_prefix=evidence_id_prefix,
        first_chunk_index=first_chunk_index,
        max_chunk_chars=max_chunk_chars,
        collection_name=collection_name,
        vector_size=vector_size,
        distance=_DISTANCE,
        payload_indexes=tuple(
            cast(Mapping[str, FrozenJson], _freeze(item)) for item in _payload_index_documents()
        ),
        vector_source=vector_source,
        vector_producer_id=vector_producer_id,
        embedding_generated_by_indexer=False,
    )


def _valid_payload_indexes(value: object) -> bool:
    if type(value) is not list or len(value) != len(_PAYLOAD_INDEXES):
        return False
    return value == _payload_index_documents()


def _payload_index_documents() -> list[dict[str, str]]:
    return [
        {"field_name": field_name, "field_schema": field_schema}
        for field_name, field_schema in _PAYLOAD_INDEXES
    ]


def _strict_json(payload: bytes, field: str) -> object:
    try:
        text = payload.decode("utf-8")
        _validate_json_nesting(text, field)
        return json.loads(
            text,
            object_pairs_hook=lambda pairs: _unique_object(pairs, field),
            parse_constant=lambda value: _reject_constant(value, field),
        )
    except ProceduralIndexBuildError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, OverflowError, RecursionError):
        raise _error("json_invalid", field, "input must be strict UTF-8 JSON") from None


def _validate_json_nesting(text: str, field: str) -> None:
    """Bound parser recursion with a small deterministic pre-scan of JSON delimiters."""

    depth = 0
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > _MAX_JSON_NESTING:
                raise _error("json_invalid", field, "JSON nesting exceeds the depth limit")
        elif character in "]}":
            depth -= 1


def _unique_object(pairs: list[tuple[str, Any]], field: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _error("json_duplicate_key", field, "JSON object contains a duplicate key")
        result[key] = value
    return result


def _reject_constant(value: str, field: str) -> None:
    del value
    raise _error("json_nonfinite", field, "JSON contains a nonfinite number")


def _strict_string(value: object, field: str) -> str:
    if type(value) is not str:
        raise _error("config_value", field, "value must be a string")
    text = value
    if not text.strip() or text != text.strip():
        raise _error("config_value", field, "string must be strict and nonblank")
    if any(unicodedata.category(character) == "Cc" for character in text):
        raise _error("config_value", field, "string must not contain control characters")
    if any(unicodedata.category(character) == "Cs" for character in text):
        raise _error("config_value", field, "string must contain only Unicode scalar values")
    if len(text.encode("utf-8")) > _MAX_IDENTIFIER_BYTES:
        raise _error("config_value", field, "identifier exceeds the byte limit")
    return text


def _source_path(value: object) -> str:
    path = _strict_string(value, "source_path")
    segments = path.split("/")
    if (
        path.startswith("/")
        or _WINDOWS_ABSOLUTE.match(path)
        or "\\" in path
        or any(segment in {"", ".", ".."} for segment in segments)
    ):
        raise _error("config_value", "source_path", "source path must be repository-relative POSIX")
    return path


def _positive_int(value: object, field: str) -> int:
    if type(value) is not int or value <= 0:
        raise _error("config_value", field, "value must be a positive integer")
    return value


def _canonical_source(payload: bytes) -> tuple[str, str]:
    if payload.startswith(b"\xef\xbb\xbf"):
        raise _error("source_bom", "source_bytes", "source must not contain a UTF-8 BOM")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        raise _error("source_utf8", "source_bytes", "source must be strict UTF-8") from None
    if "\x00" in text:
        raise _error("source_nul", "source_bytes", "source must not contain NUL")
    canonical = text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n") + "\n"
    if not canonical.strip():
        raise _error("source_blank", "source_bytes", "source must be nonblank")
    canonical_bytes = canonical.encode("utf-8")
    return canonical, hashlib.sha256(canonical_bytes).hexdigest()


def _chunk_source(canonical_source: str, max_chunk_chars: int) -> tuple[_SourceChunk, ...]:
    lines = canonical_source.split("\n")[:-1]
    chunks: list[_SourceChunk] = []
    current_lines: list[str] = []
    start_line = 0
    for line_number, line in enumerate(lines, start=1):
        if line.strip() == "":
            _append_chunk(chunks, current_lines, start_line, line_number - 1, max_chunk_chars)
            current_lines = []
            start_line = 0
        else:
            if not current_lines:
                start_line = line_number
            current_lines.append(line)
    _append_chunk(chunks, current_lines, start_line, len(lines), max_chunk_chars)
    return tuple(chunks)


def _append_chunk(
    chunks: list[_SourceChunk],
    lines: list[str],
    start_line: int,
    end_line: int,
    max_chunk_chars: int,
) -> None:
    if not lines:
        return
    text = "\n".join(lines)
    if len(text) > max_chunk_chars:
        raise _error("chunk_too_large", "source_bytes", "paragraph exceeds maximum characters")
    chunks.append(_SourceChunk(text=text, start_line=start_line, end_line=end_line))
    if len(chunks) > _MAX_CHUNKS:
        raise _error("chunk_limit", "source_bytes", "source produces too many chunks")


def _parse_vectors(
    payload: bytes, evidence_ids: tuple[str, ...], vector_size: int
) -> dict[str, tuple[float, ...]]:
    document = _strict_json(payload, "vector_bytes")
    if type(document) is not dict:
        raise _error("vector_type", "vector_bytes", "vectors must be a JSON object")
    values = cast(dict[str, Any], document)
    if not evidence_ids or set(values) != set(evidence_ids):
        raise _error("vector_ids", "vector_bytes", "vector keys must equal generated evidence IDs")
    vectors: dict[str, tuple[float, ...]] = {}
    for evidence_id in evidence_ids:
        value = values[evidence_id]
        if type(value) is not list or len(value) != vector_size:
            raise _error(
                "vector_value", "vectors.items", "vector must have the configured dimension"
            )
        normalized: list[float] = []
        for item in cast(list[object], value):
            if type(item) not in {int, float}:
                raise _error("vector_value", "vectors.items", "vector items must be finite numbers")
            try:
                number = float(cast(int | float, item))
            except OverflowError:
                raise _error(
                    "vector_value", "vectors.items", "vector items must be finite numbers"
                ) from None
            if not math.isfinite(number):
                raise _error("vector_value", "vectors.items", "vector items must be finite numbers")
            normalized.append(number)
        vectors[evidence_id] = tuple(normalized)
    return vectors


def _point_uuid(contract_version: str, document_id: str, evidence_id: str) -> str:
    name = json.dumps(
        [contract_version, document_id, evidence_id],
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    return str(uuid.uuid5(uuid.NAMESPACE_URL, name))


def _chunk_payload(chunk: ProceduralChunk) -> dict[str, JsonScalar]:
    return {
        "evidence_id": chunk.evidence_id,
        "document": chunk.document,
        "chunk_index": chunk.chunk_index,
        "related_procedure": chunk.related_procedure,
        "text": chunk.text,
        "applicable_asset_id": chunk.applicable_asset_id,
        "applicable_asset_type": chunk.applicable_asset_type,
        "source_path": chunk.source_path,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
        "source_sha256": chunk.source_sha256,
        "index_contract_version": chunk.index_contract_version,
        "vector_source": chunk.vector_source,
        "vector_producer_id": chunk.vector_producer_id,
        "embedding_generated_by_indexer": chunk.embedding_generated_by_indexer,
    }


def _record_identifier(value: object, field: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field} must be a string")
    if not value.strip():
        raise ValueError(f"{field} must be nonblank")
    if value != value.strip():
        raise ValueError(f"{field} must not contain surrounding whitespace")
    if any(unicodedata.category(character) == "Cc" for character in value):
        raise ValueError(f"{field} must not contain control characters")
    if any(unicodedata.category(character) == "Cs" for character in value):
        raise ValueError(f"{field} must contain only Unicode scalar values")
    byte_limit = (
        _MAX_EVIDENCE_ID_BYTES
        if field == "evidence_id" or field.endswith(".evidence_id")
        else _MAX_IDENTIFIER_BYTES
    )
    if len(value.encode("utf-8")) > byte_limit:
        raise ValueError(f"{field} exceeds the identifier byte limit")
    return value


def _record_source_path(value: object) -> str:
    path = _record_identifier(value, "source_path")
    segments = path.split("/")
    if (
        path.startswith("/")
        or _WINDOWS_ABSOLUTE.match(path)
        or "\\" in path
        or any(segment in {"", ".", ".."} for segment in segments)
    ):
        raise ValueError("source_path must be repository-relative POSIX")
    return path


def _record_text(value: object) -> str:
    if type(value) is not str:
        raise TypeError("text must be a string")
    if "\x00" in value:
        raise ValueError("text must not contain NUL")
    if not value.strip():
        raise ValueError("text must be nonblank")
    if len(value) > _MAX_CHUNK_CHARS:
        raise ValueError("text exceeds the chunk character limit")
    return value


def _record_positive_int(value: object, field: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field} must be an int")
    if value <= 0:
        raise ValueError(f"{field} must be positive")
    return value


def _record_nonnegative_int(value: object, field: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field} must be an integer")
    if value < 0:
        raise ValueError(f"{field} must be nonnegative")
    return value


def _record_base_url(value: object) -> str:
    if type(value) is not str:
        raise TypeError("base_url must be a string")
    if not value or value != value.strip():
        raise ValueError("base_url must be nonblank without surrounding whitespace")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("base_url must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("base_url must not contain credentials")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("base_url must not contain a path, query, or fragment")
    try:
        _ = parsed.port
    except ValueError:
        raise ValueError("base_url contains an invalid port") from None
    return value.rstrip("/")


def _record_timeout(value: object) -> float:
    if type(value) not in {int, float}:
        raise TypeError("timeout_seconds must be numeric")
    normalized = float(cast(int | float, value))
    if not math.isfinite(normalized) or not 0 < normalized <= 60:
        raise ValueError("timeout_seconds must be finite and in (0, 60]")
    return normalized


def _record_index_states(
    value: object,
) -> tuple[tuple[str, PayloadIndexState], ...]:
    if not isinstance(value, tuple) or len(value) != len(_PAYLOAD_INDEXES):
        raise TypeError("payload_indexes must be the exact state tuple")
    normalized: list[tuple[str, PayloadIndexState]] = []
    for item, (expected_field, _) in zip(value, _PAYLOAD_INDEXES, strict=True):
        if not isinstance(item, tuple) or len(item) != 2:
            raise TypeError("payload index state entries must be pairs")
        field, state = item
        if field != expected_field or type(field) is not str:
            raise ValueError("payload index state fields must match the contract")
        if type(state) is not PayloadIndexState:
            raise TypeError("payload index state must be a PayloadIndexState")
        normalized.append((field, state))
    return tuple(normalized)


def _record_result_point_ids(value: object) -> tuple[str, ...]:
    if not isinstance(value, tuple) or not value:
        raise TypeError("intended_point_ids must be a nonempty tuple")
    for point_id in value:
        if type(point_id) is not str:
            raise TypeError("intended_point_ids must contain strings")
        try:
            parsed = uuid.UUID(point_id)
        except (ValueError, AttributeError):
            raise ValueError("intended_point_ids must contain canonical UUIDs") from None
        if str(parsed) != point_id:
            raise ValueError("intended_point_ids must contain canonical UUIDs")
    if len(set(value)) != len(value):
        raise ValueError("intended_point_ids must be unique")
    return value


def _record_digest(value: object) -> str:
    if type(value) is not str:
        raise TypeError("source_sha256 must be a string")
    if not _LOWER_SHA256.fullmatch(value):
        raise ValueError("source_sha256 must be lowercase 64-hex")
    return value


def _record_vector(value: object) -> tuple[float, ...]:
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        raise TypeError("vector must be a sequence")
    if not value:
        raise ValueError("vector must be nonempty")
    normalized: list[float] = []
    for item in value:
        if type(item) not in {int, float}:
            raise TypeError("vector items must be numbers")
        try:
            number = float(cast(int | float, item))
        except OverflowError:
            raise ValueError("vector items must be finite") from None
        if not math.isfinite(number):
            raise ValueError("vector items must be finite")
        normalized.append(number)
    return tuple(normalized)


def _record_payload(value: object) -> dict[str, JsonScalar]:
    if not isinstance(value, Mapping):
        raise TypeError("payload must be a mapping")
    if set(value) != _PAYLOAD_KEYS or any(type(key) is not str for key in value):
        raise ValueError("payload keys must match the contract")
    payload = dict(value)
    chunk = ProceduralChunk(**cast(Any, payload))
    return _chunk_payload(chunk)


def _record_members(value: object, expected_type: type[Any], field: str) -> tuple[Any, ...]:
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        raise TypeError(f"{field} must be a sequence")
    members = tuple(value)
    if any(not isinstance(item, expected_type) for item in members):
        raise TypeError(f"{field} contains an invalid member")
    return members


def _record_mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field} must be a mapping")
    return cast(dict[str, Any], _mutable_json(value, field))


def _mutable_json(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise TypeError(f"{field} mapping keys must be strings")
        return {key: _mutable_json(item, field) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_mutable_json(item, field) for item in value]
    if value is None or type(value) in {str, int, float, bool}:
        if type(value) is float and not math.isfinite(value):
            raise ValueError(f"{field} must not contain nonfinite numbers")
        return value
    raise TypeError(f"{field} contains a non-JSON value")


def _point_document(point: ProceduralIndexPoint) -> dict[str, Any]:
    return {
        "id": point.point_id,
        "vector": list(point.vector),
        "payload": _record_mapping(point.payload, "point.payload"),
    }


def _record_collection_name(value: object) -> str:
    text = _record_identifier(value, "collection.name")
    if not _COLLECTION_NAME.fullmatch(text):
        raise ValueError("collection.name is unsafe")
    return text


def _record_artifact(payload: bytes) -> dict[str, Any]:
    if len(payload) > _MAX_ARTIFACT_BYTES:
        raise ValueError("artifact_bytes exceeds the artifact byte limit")
    try:
        document = json.loads(
            payload,
            object_pairs_hook=lambda pairs: _record_unique_object(pairs),
            parse_constant=lambda value: _record_reject_constant(value),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
        raise ValueError("artifact_bytes must contain strict JSON") from None
    if type(document) is not dict or set(document) != {
        "contract_version",
        "collection",
        "payload_indexes",
        "source",
        "points",
    }:
        raise ValueError("artifact schema is invalid")
    try:
        canonical = (
            json.dumps(
                document,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )
    except (UnicodeEncodeError, RecursionError, ValueError):
        raise ValueError("artifact_bytes must contain strict JSON") from None
    if canonical != payload:
        raise ValueError("artifact_bytes must be canonical JSON")
    return cast(dict[str, Any], document)


def _record_unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("artifact contains a duplicate key")
        result[key] = value
    return result


def _record_reject_constant(value: str) -> None:
    del value
    raise ValueError("artifact contains a nonfinite number")


def _freeze(value: Any) -> FrozenJson:
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise TypeError("internal JSON mapping keys must be strings")
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    if value is None or type(value) in {str, int, float, bool}:
        return cast(JsonScalar, value)
    raise TypeError("unsupported internal JSON value")


def _require_exact_bytes(value: object, field: str) -> None:
    if type(value) is not bytes:
        raise _error("input_type", field, "input must be exact bytes")


def _require_input_bound(value: bytes, field: str) -> None:
    if len(value) > _MAX_INPUT_BYTES:
        raise _error("input_too_large", field, "input exceeds the size limit")


def _error(code: str, field: str, detail: str) -> ProceduralIndexBuildError:
    return ProceduralIndexBuildError(code, field, detail)
