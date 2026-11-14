"""Qdrant-backed procedural retrieval preserving the Pump_12 result contract."""

from __future__ import annotations

import json
import math
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from time import perf_counter_ns
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from mfg_agentgraph.entity_resolution import KnownAsset
from mfg_agentgraph.evidence_reference import (
    EvidenceCatalog,
    EvidenceKind,
    EvidenceReference,
    EvidenceValidationStatus,
    RetrievalMetadata,
)
from mfg_agentgraph.procedural_retrieval import (
    QDRANT_PROCEDURAL_RETRIEVER_NAME as _QDRANT_PROCEDURAL_RETRIEVER_NAME,
)
from mfg_agentgraph.procedural_retrieval import (
    ProceduralRetrievalResult,
    ProceduralSupportRecord,
)
from mfg_agentgraph.stage_instrumentation import (
    StageError,
    StageErrorCode,
    StageEvent,
    StageName,
    TerminalStatus,
)

QDRANT_PROCEDURAL_RETRIEVER_NAME = _QDRANT_PROCEDURAL_RETRIEVER_NAME
_EXPECTED_ASSET_ID = "ex:Pump_12"
_EXPECTED_ASSET_TYPE = "centrifugal_pump"
_EXPECTED_EVIDENCE_ID = "ex:SOP_Chunk_7"
_EXPECTED_DOCUMENT = "SOP-PUMP-OPS-2026"
_EXPECTED_CHUNK_INDEX = 7
_EXPECTED_PROCEDURE_ID = "ex:Procedure_InspectInletCavitation_Pump12"
_EXPECTED_TEXT = (
    "For anomalous sound at Pump_12, inspect the pump inlet for cavitation before "
    "recommending corrective action."
)
_EXPECTED_SOURCE_PATH = "tests/fixtures/sop/pump12-sop.txt"
_EXPECTED_START_LINE = 1
_EXPECTED_END_LINE = 1
_EXPECTED_SOURCE_SHA256 = "3e538364b4d6a61f92e3bfd0976134865130063bdbcadd607cb203862957eecf"
_EXPECTED_INDEX_CONTRACT_VERSION = "mfg-agentgraph-procedural-index-v1"
_EXPECTED_VECTOR_SOURCE = "caller_supplied"
_EXPECTED_VECTOR_PRODUCER_ID = "pump12-test-vector-v1"
_EXPECTED_POINT_ID = str(
    uuid.uuid5(
        uuid.NAMESPACE_URL,
        json.dumps(
            [_EXPECTED_INDEX_CONTRACT_VERSION, _EXPECTED_DOCUMENT, _EXPECTED_EVIDENCE_ID],
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ),
    )
)
_EXPECTED_PAYLOAD_KEYS = {
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
_COLLECTION_NAME = re.compile(r"[A-Za-z0-9_-]+\Z")
_MAX_RESPONSE_BYTES = 1_000_000
_MAX_IDENTIFIER_BYTES = 1_024
_MAX_QUERY_VECTOR_ITEMS = 100_000


@dataclass(frozen=True, slots=True)
class QdrantProceduralRetrieverConfig:
    """Trusted connection and collection configuration for Qdrant retrieval."""

    base_url: str
    collection_name: str
    score_threshold: float
    timeout_seconds: float = 5.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_url", _validate_base_url(self.base_url))
        object.__setattr__(self, "collection_name", _validate_collection_name(self.collection_name))
        object.__setattr__(
            self,
            "score_threshold",
            _validate_finite_number(self.score_threshold, "score_threshold"),
        )
        timeout = _validate_finite_number(self.timeout_seconds, "timeout_seconds")
        if timeout <= 0:
            raise ValueError("timeout_seconds must be positive")
        object.__setattr__(self, "timeout_seconds", timeout)


@dataclass(frozen=True, slots=True)
class QdrantProceduralRetriever:
    """Retrieve canonical Pump_12 procedural support from Qdrant."""

    config: QdrantProceduralRetrieverConfig

    def __post_init__(self) -> None:
        if not isinstance(self.config, QdrantProceduralRetrieverConfig):
            raise TypeError("config must be a QdrantProceduralRetrieverConfig")

    def retrieve(
        self,
        *,
        resolved_asset: KnownAsset,
        query_vector: Sequence[float],
        retrieval_run_id: str,
        query_id: str,
    ) -> ProceduralRetrievalResult:
        """Query Qdrant and fail closed on any service or semantic defect."""

        if not isinstance(resolved_asset, KnownAsset):
            raise TypeError("resolved_asset must be a KnownAsset")
        vector = _validate_query_vector(query_vector)
        run_id = _require_strict_nonblank(retrieval_run_id, "retrieval_run_id")
        normalized_query_id = _require_strict_nonblank(query_id, "query_id")
        input_ids = (resolved_asset.asset_id, normalized_query_id)
        if resolved_asset.asset_id != _EXPECTED_ASSET_ID:
            return _failure(
                resolved_asset,
                run_id,
                input_ids,
                0,
                "resolved_asset.asset_id",
                "resolved asset is not supported by the Pump_12 service contract",
            )

        started = perf_counter_ns()
        try:
            response = _post_query(self.config, resolved_asset.asset_id, vector)
            support, score = _parse_response(
                response,
                score_threshold=self.config.score_threshold,
                asset_id=resolved_asset.asset_id,
            )
        except _RetrievalFailure as exc:
            return _failure(
                resolved_asset,
                run_id,
                input_ids,
                _duration_ms(started),
                exc.field,
                exc.detail,
            )
        except Exception:
            return _failure(
                resolved_asset,
                run_id,
                input_ids,
                _duration_ms(started),
                "qdrant_service",
                "unexpected Qdrant retrieval failure",
            )

        reference = EvidenceReference(
            kind=EvidenceKind.DOCUMENT_CHUNK,
            source=f"qdrant:{self.config.collection_name}",
            stable_id=support.evidence_id,
            retrieval=RetrievalMetadata(
                retrieval_run_id=run_id,
                query_id=normalized_query_id,
                retriever_name=QDRANT_PROCEDURAL_RETRIEVER_NAME,
                rank=1,
                score=score,
            ),
            validation_status=EvidenceValidationStatus.VALIDATED,
        )
        references = (reference,)
        event = StageEvent(
            stage=StageName.PROCEDURAL_RETRIEVAL,
            run_id=run_id,
            status=TerminalStatus.PASSED,
            duration_ms=_duration_ms(started),
            input_ids=input_ids,
            output_ids=(support.evidence_id,),
        )
        return ProceduralRetrievalResult(
            status=TerminalStatus.PASSED,
            asset=resolved_asset,
            support_records=(support,),
            evidence_references=references,
            evidence_catalog=EvidenceCatalog(references),
            event=event,
        )


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


class _RetrievalFailure(Exception):
    def __init__(self, field: str, detail: str) -> None:
        super().__init__(detail)
        self.field = field
        self.detail = detail


def _post_query(
    config: QdrantProceduralRetrieverConfig,
    asset_id: str,
    query_vector: tuple[float, ...],
) -> bytes:
    body = json.dumps(
        {
            "query": list(query_vector),
            "filter": {
                "must": [
                    {"key": "applicable_asset_id", "match": {"value": asset_id}},
                    {"key": "applicable_asset_type", "match": {"value": _EXPECTED_ASSET_TYPE}},
                    {"key": "related_procedure", "match": {"value": _EXPECTED_PROCEDURE_ID}},
                ]
            },
            "score_threshold": config.score_threshold,
            "limit": 2,
            "with_payload": True,
            "with_vector": False,
        },
        separators=(",", ":"),
    ).encode()
    endpoint = f"{config.base_url}/collections/{config.collection_name}/points/query"
    request = Request(
        endpoint,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    opener = build_opener(ProxyHandler({}), _NoRedirectHandler())
    try:
        with opener.open(request, timeout=config.timeout_seconds) as response:
            media_type = response.headers.get("Content-Type", "").partition(";")[0].strip().lower()
            if media_type != "application/json":
                raise _RetrievalFailure("qdrant_results", "Qdrant response media type is not JSON")
            response_body: bytes = response.read(_MAX_RESPONSE_BYTES + 1)
    except _RetrievalFailure:
        raise
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise _RetrievalFailure("qdrant_service", "Qdrant query request failed") from exc
    if len(response_body) > _MAX_RESPONSE_BYTES:
        raise _RetrievalFailure("qdrant_results", "Qdrant response exceeds the size limit")
    return response_body


def _parse_response(
    payload: bytes,
    *,
    score_threshold: float,
    asset_id: str,
) -> tuple[ProceduralSupportRecord, float]:
    try:
        document = json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_nonfinite_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _RetrievalFailure("qdrant_results", "Qdrant returned malformed JSON") from exc
    if not isinstance(document, dict) or document.get("status") != "ok":
        raise _RetrievalFailure("qdrant_results", "Qdrant result envelope is invalid")
    result = document.get("result")
    if not isinstance(result, dict):
        raise _RetrievalFailure("qdrant_results", "Qdrant result envelope is invalid")
    points = result.get("points")
    if not isinstance(points, list) or len(points) != 1:
        raise _RetrievalFailure(
            "qdrant_results", "Qdrant query must return exactly one support point"
        )
    point = points[0]
    if not isinstance(point, dict):
        raise _RetrievalFailure("qdrant_results", "Qdrant support point is invalid")
    _expect(point.get("id"), _EXPECTED_POINT_ID, "point.id")
    score_value = point.get("score")
    if not isinstance(score_value, int | float) or isinstance(score_value, bool):
        raise _RetrievalFailure("qdrant_results", "Qdrant support score is invalid")
    score = float(score_value)
    if not math.isfinite(score) or score < score_threshold:
        raise _RetrievalFailure("qdrant_results", "Qdrant support score is below threshold")
    point_payload = point.get("payload")
    if not isinstance(point_payload, dict) or set(point_payload) != _EXPECTED_PAYLOAD_KEYS:
        raise _RetrievalFailure("qdrant_results", "Qdrant support payload is invalid")

    _expect(point_payload["evidence_id"], _EXPECTED_EVIDENCE_ID, "payload.evidence_id")
    _expect(point_payload["document"], _EXPECTED_DOCUMENT, "payload.document")
    _expect(point_payload["chunk_index"], _EXPECTED_CHUNK_INDEX, "payload.chunk_index")
    _expect(point_payload["related_procedure"], _EXPECTED_PROCEDURE_ID, "payload.related_procedure")
    _expect(point_payload["text"], _EXPECTED_TEXT, "payload.text")
    _expect(point_payload["applicable_asset_id"], asset_id, "payload.applicable_asset_id")
    _expect(
        point_payload["applicable_asset_type"],
        _EXPECTED_ASSET_TYPE,
        "payload.applicable_asset_type",
    )
    _expect(point_payload["source_path"], _EXPECTED_SOURCE_PATH, "payload.source_path")
    _expect(point_payload["start_line"], _EXPECTED_START_LINE, "payload.start_line")
    _expect(point_payload["end_line"], _EXPECTED_END_LINE, "payload.end_line")
    _expect(point_payload["source_sha256"], _EXPECTED_SOURCE_SHA256, "payload.source_sha256")
    _expect(
        point_payload["index_contract_version"],
        _EXPECTED_INDEX_CONTRACT_VERSION,
        "payload.index_contract_version",
    )
    _expect(point_payload["vector_source"], _EXPECTED_VECTOR_SOURCE, "payload.vector_source")
    _expect(
        point_payload["vector_producer_id"],
        _EXPECTED_VECTOR_PRODUCER_ID,
        "payload.vector_producer_id",
    )
    _expect(
        point_payload["embedding_generated_by_indexer"],
        False,
        "payload.embedding_generated_by_indexer",
    )

    return (
        ProceduralSupportRecord(
            evidence_id=_EXPECTED_EVIDENCE_ID,
            document=_EXPECTED_DOCUMENT,
            chunk_index=_EXPECTED_CHUNK_INDEX,
            related_procedure=_EXPECTED_PROCEDURE_ID,
            text=_EXPECTED_TEXT,
            applicable_asset_id=asset_id,
            applicable_asset_type=_EXPECTED_ASSET_TYPE,
            source_path=_EXPECTED_SOURCE_PATH,
            start_line=_EXPECTED_START_LINE,
            end_line=_EXPECTED_END_LINE,
            source_sha256=_EXPECTED_SOURCE_SHA256,
            index_contract_version=_EXPECTED_INDEX_CONTRACT_VERSION,
        ),
        score,
    )


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _RetrievalFailure("qdrant_results", "Qdrant result contains a duplicate key")
        result[key] = value
    return result


def _reject_nonfinite_json_constant(value: str) -> None:
    del value
    raise _RetrievalFailure("qdrant_results", "Qdrant result contains a nonfinite number")


def _expect(actual: object, expected: object, field: str) -> None:
    if actual != expected or type(actual) is not type(expected):
        raise _RetrievalFailure(field, f"{field} does not match the Pump_12 contract")


def _failure(
    asset: KnownAsset,
    run_id: str,
    input_ids: tuple[str, str],
    duration_ms: int,
    field: str,
    detail: str,
) -> ProceduralRetrievalResult:
    error = StageError(StageErrorCode.UNSUPPORTED_LOWER_RANK, field=field, detail=detail)
    event = StageEvent(
        stage=StageName.PROCEDURAL_RETRIEVAL,
        run_id=run_id,
        status=TerminalStatus.UNSUPPORTED_LOWER_RANK,
        duration_ms=duration_ms,
        input_ids=input_ids,
        errors=(error,),
    )
    return ProceduralRetrievalResult(
        status=TerminalStatus.UNSUPPORTED_LOWER_RANK,
        asset=asset,
        event=event,
    )


def _validate_base_url(value: object) -> str:
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
    except ValueError as exc:
        raise ValueError("base_url contains an invalid port") from exc
    return value.rstrip("/")


def _validate_collection_name(value: object) -> str:
    if type(value) is not str:
        raise TypeError("collection_name must be a string")
    if not _COLLECTION_NAME.fullmatch(value):
        raise ValueError("collection_name contains unsafe characters")
    if len(value.encode("utf-8")) > _MAX_IDENTIFIER_BYTES:
        raise ValueError("collection_name exceeds the identifier byte limit")
    return value


def _validate_finite_number(value: object, field_name: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be numeric")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    return normalized


def _validate_query_vector(value: object) -> tuple[float, ...]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise TypeError("query_vector must be a sequence of finite numbers")
    if not value:
        raise ValueError("query_vector must be nonempty")
    if len(value) > _MAX_QUERY_VECTOR_ITEMS:
        raise ValueError("query_vector exceeds the item limit")
    return tuple(_validate_finite_number(item, "query_vector") for item in value)


def _require_strict_nonblank(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must be nonblank")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")
    if len(value.encode("utf-8")) > _MAX_IDENTIFIER_BYTES:
        raise ValueError(f"{field_name} exceeds the identifier byte limit")
    return value


def _duration_ms(started_ns: int) -> int:
    return max(0, (perf_counter_ns() - started_ns) // 1_000_000)
