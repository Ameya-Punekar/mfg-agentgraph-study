"""Behavior contract for the Issue #29 Milestone B Qdrant index writer."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from email.message import Message
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

import mfg_agentgraph.procedural_indexing as indexing_module
from mfg_agentgraph.procedural_indexing import (
    CollectionState,
    IndexingPhase,
    IndexingTerminalStatus,
    PayloadIndexState,
    QdrantIndexServiceConfig,
    build_procedural_index,
    execute_procedural_index,
)

_FIXTURES = Path(__file__).parent / "fixtures"
_CONFIG = (_FIXTURES / "qdrant" / "pump12-index-config.json").read_bytes()
_SOURCE = (_FIXTURES / "sop" / "pump12-sop.txt").read_bytes()
_VECTORS = (_FIXTURES / "qdrant" / "pump12-vectors.json").read_bytes()
_COLLECTION = "pump12-procedures"
_FIELDS = ("applicable_asset_id", "applicable_asset_type", "related_procedure")


def _json(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode()


def _collection(
    *, indexes: tuple[str, ...] = _FIELDS, size: int = 4, distance: str = "Cosine"
) -> bytes:
    return _json(
        {
            "status": "ok",
            "result": {
                "config": {"params": {"vectors": {"size": size, "distance": distance}}},
                "payload_schema": {field: {"data_type": "keyword"} for field in indexes},
            },
        }
    )


_CREATE_OK = _json({"status": "ok", "result": True})
_UPDATE_OK = _json({"status": "ok", "result": {"status": "completed"}})


class _Response:
    def __init__(
        self,
        body: bytes,
        *,
        status: int = 200,
        content_type: str = "application/json; charset=utf-8",
    ) -> None:
        self.body = body
        self.status = status
        self.headers = {"Content-Type": content_type}

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def read(self, limit: int = -1) -> bytes:
        return self.body if limit < 0 else self.body[:limit]


class _Opener:
    def __init__(self, outcomes: list[bytes | Exception | _Response]) -> None:
        self.outcomes = iter(outcomes)
        self.requests: list[Request] = []
        self.timeouts: list[float] = []

    def open(self, request: Request, *, timeout: float) -> _Response:
        self.requests.append(request)
        self.timeouts.append(timeout)
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        if isinstance(outcome, _Response):
            return outcome
        return _Response(outcome)


def _not_found() -> HTTPError:
    return HTTPError(
        f"http://safe.example/collections/{_COLLECTION}",
        404,
        "not found",
        Message(),
        None,
    )


def _install(
    monkeypatch: pytest.MonkeyPatch, outcomes: list[bytes | Exception | _Response]
) -> _Opener:
    opener = _Opener(outcomes)
    monkeypatch.setattr(indexing_module, "build_opener", lambda *handlers: opener)
    return opener


def _plan() -> Any:
    return build_procedural_index(_CONFIG, _SOURCE, _VECTORS)


def _request_body(request: Request) -> object:
    return json.loads(cast(bytes, request.data) if request.data is not None else b"null")


def test_service_config_is_strict_immutable_and_bounded() -> None:
    config = QdrantIndexServiceConfig("https://qdrant.example/", 60)
    assert config.base_url == "https://qdrant.example"
    assert config.timeout_seconds == 60.0
    with pytest.raises(FrozenInstanceError):
        config.base_url = "http://other.example"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("base_url", "timeout", "error"),
    (
        (None, 5.0, TypeError),
        ("", 5.0, ValueError),
        (" http://safe.example", 5.0, ValueError),
        ("ftp://safe.example", 5.0, ValueError),
        ("http://user:secret@safe.example", 5.0, ValueError),
        ("http://safe.example/path", 5.0, ValueError),
        ("http://safe.example?query=1", 5.0, ValueError),
        ("http://safe.example#fragment", 5.0, ValueError),
        ("http://safe.example:invalid", 5.0, ValueError),
        ("http://safe.example", True, TypeError),
        ("http://safe.example", 0.0, ValueError),
        ("http://safe.example", 60.1, ValueError),
        ("http://safe.example", float("inf"), ValueError),
    ),
)
def test_service_config_rejects_invalid_values_before_network(
    base_url: object,
    timeout: object,
    error: type[Exception],
) -> None:
    with pytest.raises(error):
        QdrantIndexServiceConfig(base_url, timeout)  # type: ignore[arg-type]


def test_missing_collection_is_created_verified_indexed_and_upserted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opener = _install(
        monkeypatch,
        [
            _not_found(),
            _CREATE_OK,
            _collection(indexes=()),
            _UPDATE_OK,
            _UPDATE_OK,
            _UPDATE_OK,
            _collection(),
            _UPDATE_OK,
        ],
    )
    plan = _plan()

    result = execute_procedural_index(
        plan,
        QdrantIndexServiceConfig("http://safe.example", 2.0),
    )

    assert result.status is IndexingTerminalStatus.PASSED
    assert result.phase is IndexingPhase.POINT_UPSERT
    assert result.collection_state is CollectionState.CREATED
    assert result.payload_indexes == tuple(
        (field, PayloadIndexState.CREATED_VERIFIED) for field in _FIELDS
    )
    assert result.external_side_effect_may_have_occurred is True
    assert result.intended_point_count == 1
    assert result.completed_point_count == 1
    assert result.intended_point_ids == (plan.points[0].point_id,)
    assert result.retry_count == 0
    assert result.error_code is None
    assert result.error_field is None
    assert result.error_detail is None
    assert opener.timeouts == [2.0] * 8
    assert [(request.get_method(), request.selector) for request in opener.requests] == [
        ("GET", f"/collections/{_COLLECTION}"),
        ("PUT", f"/collections/{_COLLECTION}"),
        ("GET", f"/collections/{_COLLECTION}"),
        ("PUT", f"/collections/{_COLLECTION}/index?wait=true"),
        ("PUT", f"/collections/{_COLLECTION}/index?wait=true"),
        ("PUT", f"/collections/{_COLLECTION}/index?wait=true"),
        ("GET", f"/collections/{_COLLECTION}"),
        ("PUT", f"/collections/{_COLLECTION}/points?wait=true"),
    ]
    assert _request_body(opener.requests[1]) == {"vectors": {"size": 4, "distance": "Cosine"}}
    assert [_request_body(request) for request in opener.requests[3:6]] == [
        {"field_name": field, "field_schema": "keyword"} for field in _FIELDS
    ]
    assert _request_body(opener.requests[-1]) == json.loads(
        json.dumps({"points": json.loads(plan.artifact_bytes)["points"]})
    )
    assert all(
        request.headers["Content-type"] == "application/json"
        for request in opener.requests
        if request.get_method() == "PUT"
    )
    assert all(request.headers["Accept"] == "application/json" for request in opener.requests)


def test_unchanged_existing_collection_skips_index_writes_and_reuses_point_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opener = _install(monkeypatch, [_collection(), _collection(), _UPDATE_OK])
    plan = _plan()

    result = execute_procedural_index(plan, QdrantIndexServiceConfig("http://safe.example"))

    assert result.status is IndexingTerminalStatus.PASSED
    assert result.collection_state is CollectionState.VERIFIED_EXISTING
    assert result.payload_indexes == tuple(
        (field, PayloadIndexState.PREEXISTING_VERIFIED) for field in _FIELDS
    )
    assert result.intended_point_ids == (plan.points[0].point_id,)
    assert [(request.get_method(), request.selector) for request in opener.requests] == [
        ("GET", f"/collections/{_COLLECTION}"),
        ("GET", f"/collections/{_COLLECTION}"),
        ("PUT", f"/collections/{_COLLECTION}/points?wait=true"),
    ]


@pytest.mark.parametrize(
    "response",
    (
        _collection(size=8),
        _collection(distance="Dot"),
        _json(
            {
                "status": "ok",
                "result": {
                    "config": {"params": {"vectors": {"named": {"size": 4, "distance": "Cosine"}}}},
                    "payload_schema": {},
                },
            }
        ),
        _json(
            {
                "status": "ok",
                "result": {
                    "config": {"params": {"vectors": {"size": 4, "distance": "Cosine"}}},
                    "payload_schema": {"applicable_asset_id": {"data_type": "integer"}},
                },
            }
        ),
    ),
)
def test_incompatible_collection_fails_before_mutation(
    monkeypatch: pytest.MonkeyPatch,
    response: bytes,
) -> None:
    opener = _install(monkeypatch, [response])

    result = execute_procedural_index(_plan(), QdrantIndexServiceConfig("http://safe.example"))

    assert result.status is IndexingTerminalStatus.FAILED
    assert result.phase is IndexingPhase.COLLECTION_LOOKUP
    assert result.external_side_effect_may_have_occurred is False
    assert result.completed_point_count == 0
    assert result.error_code == "collection_incompatible"
    assert len(opener.requests) == 1


def test_upsert_transport_failure_reports_unknown_outcome_without_leakage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = "SECRET-MARKER"
    _install(monkeypatch, [_collection(), _collection(), URLError(marker)])

    result = execute_procedural_index(_plan(), QdrantIndexServiceConfig("http://safe.example"))

    assert result.status is IndexingTerminalStatus.FAILED
    assert result.phase is IndexingPhase.POINT_UPSERT
    assert result.collection_state is CollectionState.VERIFIED_EXISTING
    assert result.payload_indexes == tuple(
        (field, PayloadIndexState.PREEXISTING_VERIFIED) for field in _FIELDS
    )
    assert result.external_side_effect_may_have_occurred is True
    assert result.completed_point_count is None
    assert result.error_code == "qdrant_request_failed"
    assert result.error_field == "points"
    assert result.error_detail == "point upsert request failed"
    assert marker not in repr(result)


def test_only_exact_404_creates_collection(monkeypatch: pytest.MonkeyPatch) -> None:
    error = HTTPError("http://safe.example", 401, "SECRET-MARKER", Message(), None)
    opener = _install(monkeypatch, [error])

    result = execute_procedural_index(_plan(), QdrantIndexServiceConfig("http://safe.example"))

    assert result.status is IndexingTerminalStatus.FAILED
    assert result.collection_state is CollectionState.UNKNOWN
    assert result.external_side_effect_may_have_occurred is False
    assert len(opener.requests) == 1
    assert "SECRET-MARKER" not in repr(result)


def test_collection_create_transport_failure_reports_unknown_collection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, [_not_found(), URLError("SECRET-MARKER")])

    result = execute_procedural_index(_plan(), QdrantIndexServiceConfig("http://safe.example"))

    assert result.phase is IndexingPhase.COLLECTION_CREATE
    assert result.collection_state is CollectionState.WRITE_OUTCOME_UNKNOWN
    assert result.payload_indexes == tuple((field, PayloadIndexState.UNKNOWN) for field in _FIELDS)
    assert result.external_side_effect_may_have_occurred is True
    assert result.completed_point_count == 0
    assert "SECRET-MARKER" not in repr(result)


def test_collection_create_readback_failure_remains_completed_unverified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, [_not_found(), _CREATE_OK, URLError("SECRET-MARKER")])

    result = execute_procedural_index(_plan(), QdrantIndexServiceConfig("http://safe.example"))

    assert result.phase is IndexingPhase.COLLECTION_READBACK
    assert result.collection_state is CollectionState.CREATE_COMPLETED_UNVERIFIED
    assert result.payload_indexes == tuple((field, PayloadIndexState.UNKNOWN) for field in _FIELDS)
    assert result.completed_point_count == 0


def test_payload_index_write_failure_identifies_exact_field_and_preserves_known_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(
        monkeypatch,
        [
            _collection(indexes=("applicable_asset_id",)),
            URLError("SECRET-MARKER"),
        ],
    )

    result = execute_procedural_index(_plan(), QdrantIndexServiceConfig("http://safe.example"))

    assert result.phase is IndexingPhase.PAYLOAD_INDEX_CREATE
    assert result.collection_state is CollectionState.VERIFIED_EXISTING
    assert result.payload_indexes == (
        ("applicable_asset_id", PayloadIndexState.PREEXISTING_VERIFIED),
        ("applicable_asset_type", PayloadIndexState.WRITE_OUTCOME_UNKNOWN),
        ("related_procedure", PayloadIndexState.MISSING),
    )
    assert result.error_field == "applicable_asset_type"
    assert result.completed_point_count == 0


def test_successful_payload_write_then_readback_failure_remains_unverified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(
        monkeypatch,
        [
            _collection(indexes=("applicable_asset_id", "applicable_asset_type")),
            _UPDATE_OK,
            URLError("SECRET-MARKER"),
        ],
    )

    result = execute_procedural_index(_plan(), QdrantIndexServiceConfig("http://safe.example"))

    assert result.phase is IndexingPhase.PAYLOAD_INDEX_READBACK
    assert result.payload_indexes[-1] == (
        "related_procedure",
        PayloadIndexState.CREATE_COMPLETED_UNVERIFIED,
    )
    assert result.completed_point_count == 0


@pytest.mark.parametrize(
    "bad_response",
    (
        _Response(_collection(), content_type="text/plain"),
        _Response(b"{"),
        _Response(b'{"status":"ok","status":"ok","result":{}}'),
        _Response(b'{"status":"ok","result":NaN}'),
        _Response(b"x" * 1_000_001),
        _Response(_collection(), status=201),
        _Response(_json({"status": True, "result": {}})),
    ),
)
def test_malformed_or_unbounded_lookup_response_fails_before_mutation(
    monkeypatch: pytest.MonkeyPatch,
    bad_response: _Response,
) -> None:
    opener = _install(monkeypatch, [bad_response])

    result = execute_procedural_index(_plan(), QdrantIndexServiceConfig("http://safe.example"))

    assert result.status is IndexingTerminalStatus.FAILED
    assert result.phase is IndexingPhase.COLLECTION_LOOKUP
    assert result.external_side_effect_may_have_occurred is False
    assert len(opener.requests) == 1


def test_waited_update_requires_exact_completed_status(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(
        monkeypatch,
        [
            _collection(indexes=("applicable_asset_id", "applicable_asset_type")),
            _json({"status": "ok", "result": {"status": "acknowledged"}}),
        ],
    )

    result = execute_procedural_index(_plan(), QdrantIndexServiceConfig("http://safe.example"))

    assert result.phase is IndexingPhase.PAYLOAD_INDEX_CREATE
    assert result.payload_indexes[-1] == (
        "related_procedure",
        PayloadIndexState.WRITE_OUTCOME_UNKNOWN,
    )
    assert result.error_field == "related_procedure"


def test_unexpected_opener_failure_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_opener(*handlers: object) -> object:
        del handlers
        raise RuntimeError("SECRET-MARKER")

    monkeypatch.setattr(indexing_module, "build_opener", fail_opener)

    result = execute_procedural_index(_plan(), QdrantIndexServiceConfig("http://safe.example"))

    assert result.status is IndexingTerminalStatus.FAILED
    assert result.phase is IndexingPhase.COLLECTION_LOOKUP
    assert result.collection_state is CollectionState.UNKNOWN
    assert result.external_side_effect_may_have_occurred is False
    assert result.error_code == "unexpected_execution_failure"
    assert "SECRET-MARKER" not in repr(result)


def test_public_result_rejects_unbounded_or_incoherent_direct_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, [_collection(), _collection(), _UPDATE_OK])
    result = execute_procedural_index(_plan(), QdrantIndexServiceConfig("http://safe.example"))

    with pytest.raises(ValueError, match="error_detail exceeds"):
        replace(
            result,
            status=IndexingTerminalStatus.FAILED,
            completed_point_count=None,
            error_code="failure",
            error_field="field",
            error_detail="x" * 1_025,
        )
    with pytest.raises(ValueError, match="intended_point_count"):
        replace(result, intended_point_count=2)
    with pytest.raises(ValueError, match="collection_state"):
        replace(result, collection_state=CollectionState.UNKNOWN)
    with pytest.raises(ValueError, match="completed_point_count"):
        replace(
            result,
            status=IndexingTerminalStatus.FAILED,
            completed_point_count=2,
            error_code="failure",
            error_field="points",
            error_detail="write failed",
        )
    with pytest.raises(ValueError, match="point_upsert"):
        replace(
            result,
            status=IndexingTerminalStatus.FAILED,
            completed_point_count=0,
            error_code="failure",
            error_field="points",
            error_detail="write failed",
        )
    with pytest.raises(ValueError, match="before point_upsert"):
        replace(
            result,
            status=IndexingTerminalStatus.FAILED,
            phase=IndexingPhase.PAYLOAD_INDEX_READBACK,
            completed_point_count=None,
            error_code="failure",
            error_field="payload_indexes",
            error_detail="readback failed",
        )


def test_unexpected_failure_after_upsert_dispatch_preserves_unknown_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, [_collection(), _collection(), _UPDATE_OK])

    def fail_validation(document: object, field: str) -> None:
        del document, field
        raise RuntimeError("SECRET-MARKER")

    monkeypatch.setattr(indexing_module, "_require_update_response", fail_validation)

    result = execute_procedural_index(_plan(), QdrantIndexServiceConfig("http://safe.example"))

    assert result.status is IndexingTerminalStatus.FAILED
    assert result.phase is IndexingPhase.POINT_UPSERT
    assert result.external_side_effect_may_have_occurred is True
    assert result.completed_point_count is None
    assert result.error_code == "unexpected_execution_failure"
    assert "SECRET-MARKER" not in repr(result)
