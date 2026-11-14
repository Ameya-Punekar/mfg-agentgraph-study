"""Contract tests for the Issue #28 Qdrant procedural retriever."""

from __future__ import annotations

import json
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from copy import deepcopy
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast

import pytest

import mfg_agentgraph.procedural_retrieval as fixture_module
import mfg_agentgraph.qdrant_procedural_retriever as qdrant_module
from mfg_agentgraph.entity_resolution import KnownAsset
from mfg_agentgraph.procedural_retrieval import (
    ProceduralRetrievalResult,
    retrieve_procedural_support,
)
from mfg_agentgraph.qdrant_procedural_retriever import (
    QDRANT_PROCEDURAL_RETRIEVER_NAME,
    QdrantProceduralRetriever,
    QdrantProceduralRetrieverConfig,
)
from mfg_agentgraph.stage_instrumentation import StageErrorCode, StageName, TerminalStatus

_ASSET = KnownAsset("ex:Pump_12", "Pump 12", ("Pump_12",))
_RUN_ID = "run-issue-28"
_QUERY_ID = "query-pump-12-sop-cavitation"
_SCENARIO_PATH = Path(__file__).parent / "fixtures" / "pump_12" / "scenario.json"
_SERVICE_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "qdrant" / "pump12.json"


def _artifact() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(_SERVICE_FIXTURE_PATH.read_bytes()))


_ARTIFACT = _artifact()
_COLLECTION = cast(str, _ARTIFACT["collection"]["name"])
_QUERY_VECTOR = tuple(cast(list[float], _ARTIFACT["points"][0]["vector"]))


def _valid_point() -> dict[str, object]:
    point = cast(dict[str, object], deepcopy(_ARTIFACT["points"][0]))
    point.pop("vector")
    point["score"] = 0.97
    return point


def _query_response() -> bytes:
    return json.dumps(
        {"status": "ok", "result": {"points": [_valid_point()]}},
        separators=(",", ":"),
    ).encode()


@dataclass
class _Response:
    status: int = 200
    content_type: str = "application/json; charset=utf-8"
    body: bytes = _query_response()
    delay_seconds: float = 0.0
    location: str | None = None


@dataclass
class _CapturedRequest:
    path: str
    content_type: str | None
    accept: str | None
    body: bytes


@contextmanager
def _service(response: _Response | None = None) -> Iterator[tuple[str, list[_CapturedRequest]]]:
    configured_response = response or _Response()
    requests: list[_CapturedRequest] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            requests.append(
                _CapturedRequest(
                    path=self.path,
                    content_type=self.headers.get("Content-Type"),
                    accept=self.headers.get("Accept"),
                    body=b"",
                )
            )
            body = configured_response.body
            self.send_response(configured_response.status)
            self.send_header("Content-Type", configured_response.content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            with suppress(BrokenPipeError):
                self.wfile.write(body)

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            requests.append(
                _CapturedRequest(
                    path=self.path,
                    content_type=self.headers.get("Content-Type"),
                    accept=self.headers.get("Accept"),
                    body=self.rfile.read(length),
                )
            )
            if configured_response.delay_seconds:
                time.sleep(configured_response.delay_seconds)
            body = configured_response.body
            self.send_response(configured_response.status)
            self.send_header("Content-Type", configured_response.content_type)
            if configured_response.location is not None:
                self.send_header("Location", configured_response.location)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            with suppress(BrokenPipeError):
                self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = cast(tuple[str, int], server.server_address)
        yield f"http://{host}:{port}", requests
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def _retrieve(base_url: str, *, timeout_seconds: float = 1.0) -> ProceduralRetrievalResult:
    return QdrantProceduralRetriever(
        QdrantProceduralRetrieverConfig(base_url, _COLLECTION, 0.8, timeout_seconds)
    ).retrieve(
        resolved_asset=_ASSET,
        query_vector=_QUERY_VECTOR,
        retrieval_run_id=_RUN_ID,
        query_id=_QUERY_ID,
    )


def _assert_unsupported(result: object, *, field: str) -> None:
    typed = cast(Any, result)
    assert typed.status is TerminalStatus.UNSUPPORTED_LOWER_RANK
    assert typed.support_records == ()
    assert typed.evidence_references == ()
    assert typed.evidence_catalog.references == ()
    assert typed.event.stage is StageName.PROCEDURAL_RETRIEVAL
    assert typed.event.status is TerminalStatus.UNSUPPORTED_LOWER_RANK
    assert typed.event.output_ids == ()
    assert typed.event.retry_count == 0
    assert len(typed.event.errors) == 1
    assert typed.event.errors[0].code is StageErrorCode.UNSUPPORTED_LOWER_RANK
    assert typed.event.errors[0].field == field


def test_qdrant_result_matches_fixture_domain_contract_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = cast(dict[str, Any], json.loads(_SCENARIO_PATH.read_text(encoding="utf-8")))
    fixture = retrieve_procedural_support(
        resolved_asset=_ASSET,
        scenario=scenario,
        retrieval_run_id=_RUN_ID,
        query_id=_QUERY_ID,
    )

    def forbidden_fixture_call(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("Qdrant adapter silently called fixture retriever")

    monkeypatch.setattr(fixture_module, "retrieve_procedural_support", forbidden_fixture_call)

    with _service() as (base_url, requests):
        result = QdrantProceduralRetriever(
            QdrantProceduralRetrieverConfig(
                base_url=base_url,
                collection_name=_COLLECTION,
                score_threshold=0.8,
                timeout_seconds=1.0,
            )
        ).retrieve(
            resolved_asset=_ASSET,
            query_vector=_QUERY_VECTOR,
            retrieval_run_id=_RUN_ID,
            query_id=_QUERY_ID,
        )

    assert result.status is TerminalStatus.PASSED
    assert result.asset == fixture.asset
    assert result.support_records == fixture.support_records
    assert tuple(item.stable_id for item in result.evidence_references) == tuple(
        item.stable_id for item in fixture.evidence_references
    )
    assert result.evidence_catalog.references == result.evidence_references
    reference = result.evidence_references[0]
    assert reference.source == f"qdrant:{_COLLECTION}"
    assert reference.retrieval.retriever_name == QDRANT_PROCEDURAL_RETRIEVER_NAME
    assert reference.retrieval.rank == 1
    assert reference.retrieval.score == 0.97
    assert result.event.stage is StageName.PROCEDURAL_RETRIEVAL
    assert result.event.input_ids == fixture.event.input_ids
    assert result.event.output_ids == fixture.event.output_ids
    assert result.event.errors == ()
    support = result.support_records[0]
    expected_payload = cast(dict[str, Any], _ARTIFACT["points"][0]["payload"])
    assert support.source_path == expected_payload["source_path"]
    assert support.start_line == expected_payload["start_line"]
    assert support.end_line == expected_payload["end_line"]
    assert support.source_sha256 == expected_payload["source_sha256"]
    assert support.index_contract_version == expected_payload["index_contract_version"]

    assert len(requests) == 1
    request = requests[0]
    assert request.path == f"/collections/{_COLLECTION}/points/query"
    assert request.content_type == "application/json"
    assert request.accept == "application/json"
    assert json.loads(request.body) == {
        "query": list(_QUERY_VECTOR),
        "filter": {
            "must": [
                {"key": "applicable_asset_id", "match": {"value": _ASSET.asset_id}},
                {"key": "applicable_asset_type", "match": {"value": "centrifugal_pump"}},
                {
                    "key": "related_procedure",
                    "match": {"value": "ex:Procedure_InspectInletCavitation_Pump12"},
                },
            ]
        },
        "score_threshold": 0.8,
        "limit": 2,
        "with_payload": True,
        "with_vector": False,
    }


@pytest.mark.parametrize(
    ("field_name", "bad_value", "expected_error"),
    (
        ("base_url", "", ValueError),
        ("base_url", None, TypeError),
        ("base_url", "ftp://qdrant.example", ValueError),
        ("base_url", "http://user:secret@qdrant.example", ValueError),
        ("base_url", "http://qdrant.example/api", ValueError),
        ("base_url", "http://qdrant.example?query=1", ValueError),
        ("base_url", "http://qdrant.example#fragment", ValueError),
        ("base_url", "http://qdrant.example:invalid", ValueError),
        ("collection_name", "", ValueError),
        ("collection_name", None, TypeError),
        ("collection_name", "unsafe/name", ValueError),
        ("collection_name", ".", ValueError),
        ("score_threshold", float("nan"), ValueError),
        ("score_threshold", float("inf"), ValueError),
        ("score_threshold", True, TypeError),
        ("timeout_seconds", 0.0, ValueError),
        ("timeout_seconds", -1.0, ValueError),
        ("timeout_seconds", float("inf"), ValueError),
        ("timeout_seconds", True, TypeError),
    ),
)
def test_invalid_config_is_rejected_before_retrieval(
    field_name: str,
    bad_value: object,
    expected_error: type[Exception],
) -> None:
    values: dict[str, object] = {
        "base_url": "http://127.0.0.1:6333",
        "collection_name": _COLLECTION,
        "score_threshold": 0.8,
        "timeout_seconds": 1.0,
    }
    values[field_name] = bad_value

    with pytest.raises(expected_error):
        QdrantProceduralRetrieverConfig(
            base_url=cast(Any, values["base_url"]),
            collection_name=cast(Any, values["collection_name"]),
            score_threshold=cast(Any, values["score_threshold"]),
            timeout_seconds=cast(Any, values["timeout_seconds"]),
        )


def test_config_rejects_hostile_string_subclasses_before_retention() -> None:
    class HostileString(str):
        def rstrip(self, chars: str | None = None) -> str:
            del chars
            return "http://safe.example/evil/path?x=1"

        def __format__(self, format_spec: str) -> str:
            del format_spec
            return "unsafe/path"

    with pytest.raises(TypeError, match="base_url"):
        QdrantProceduralRetrieverConfig(HostileString("http://safe.example"), _COLLECTION, 0.8)
    with pytest.raises(TypeError, match="collection_name"):
        QdrantProceduralRetrieverConfig("http://safe.example", HostileString(_COLLECTION), 0.8)


def test_collection_and_request_ids_enforce_utf8_byte_limit() -> None:
    exact = "x" * 1_024
    config = QdrantProceduralRetrieverConfig("http://safe.example", exact, 0.8)
    assert config.collection_name == exact

    with pytest.raises(ValueError, match="collection_name exceeds"):
        QdrantProceduralRetrieverConfig("http://safe.example", exact + "x", 0.8)

    retriever = QdrantProceduralRetriever(
        QdrantProceduralRetrieverConfig("http://safe.example", _COLLECTION, 0.8)
    )
    for field_name in ("retrieval_run_id", "query_id"):
        kwargs = {
            "resolved_asset": _ASSET,
            "query_vector": _QUERY_VECTOR,
            "retrieval_run_id": _RUN_ID,
            "query_id": _QUERY_ID,
        }
        kwargs[field_name] = "é" * 513
        with pytest.raises(ValueError, match=f"{field_name} exceeds"):
            cast(Any, retriever.retrieve)(**kwargs)


def test_query_vector_enforces_item_limit_before_network(monkeypatch: pytest.MonkeyPatch) -> None:
    opened = False

    def fail_if_opened(*args: object, **kwargs: object) -> object:
        nonlocal opened
        opened = True
        raise AssertionError("network must not be contacted")

    monkeypatch.setattr("urllib.request.OpenerDirector.open", fail_if_opened)
    retriever = QdrantProceduralRetriever(
        QdrantProceduralRetrieverConfig("http://safe.example", _COLLECTION, 0.8)
    )
    result = retriever.retrieve(
        resolved_asset=_ASSET,
        query_vector=(0.0,) * 100_000,
        retrieval_run_id=_RUN_ID,
        query_id=_QUERY_ID,
    )
    assert result.status is TerminalStatus.UNSUPPORTED_LOWER_RANK
    assert opened is True

    opened = False
    with pytest.raises(ValueError, match="query_vector exceeds"):
        retriever.retrieve(
            resolved_asset=_ASSET,
            query_vector=(0.0,) * 100_001,
            retrieval_run_id=_RUN_ID,
            query_id=_QUERY_ID,
        )
    assert opened is False


@pytest.mark.parametrize(
    ("query_vector", "expected_error"),
    (
        ((), ValueError),
        ("not-a-vector", TypeError),
        ((True,), TypeError),
        ((float("nan"),), ValueError),
        ((float("inf"),), ValueError),
        ((object(),), TypeError),
    ),
)
def test_invalid_query_vector_fails_before_network_io(
    query_vector: object,
    expected_error: type[Exception],
) -> None:
    with _service() as (base_url, requests):
        retriever = QdrantProceduralRetriever(
            QdrantProceduralRetrieverConfig(base_url, _COLLECTION, 0.8, 1.0)
        )
        with pytest.raises(expected_error):
            retriever.retrieve(
                resolved_asset=_ASSET,
                query_vector=cast(Any, query_vector),
                retrieval_run_id=_RUN_ID,
                query_id=_QUERY_ID,
            )

    assert requests == []


@pytest.mark.parametrize("field_name", ("retrieval_run_id", "query_id"))
@pytest.mark.parametrize("bad_value", ("", " ", " leading", "trailing "))
def test_invalid_trace_ids_fail_before_network_io(field_name: str, bad_value: str) -> None:
    with _service() as (base_url, requests):
        retriever = QdrantProceduralRetriever(
            QdrantProceduralRetrieverConfig(base_url, _COLLECTION, 0.8, 1.0)
        )
        values = {"retrieval_run_id": _RUN_ID, "query_id": _QUERY_ID}
        values[field_name] = bad_value
        with pytest.raises(ValueError):
            retriever.retrieve(
                resolved_asset=_ASSET,
                query_vector=_QUERY_VECTOR,
                retrieval_run_id=values["retrieval_run_id"],
                query_id=values["query_id"],
            )

    assert requests == []


@pytest.mark.parametrize("field_name", ("retrieval_run_id", "query_id"))
def test_non_string_trace_ids_fail_before_network_io(field_name: str) -> None:
    with _service() as (base_url, requests):
        retriever = QdrantProceduralRetriever(
            QdrantProceduralRetrieverConfig(base_url, _COLLECTION, 0.8, 1.0)
        )
        values: dict[str, object] = {"retrieval_run_id": _RUN_ID, "query_id": _QUERY_ID}
        values[field_name] = None
        with pytest.raises(TypeError):
            retriever.retrieve(
                resolved_asset=_ASSET,
                query_vector=_QUERY_VECTOR,
                retrieval_run_id=cast(Any, values["retrieval_run_id"]),
                query_id=cast(Any, values["query_id"]),
            )

    assert requests == []


@pytest.mark.parametrize(
    ("response", "field"),
    (
        (_Response(status=500), "qdrant_service"),
        (_Response(content_type="text/html"), "qdrant_results"),
        (_Response(body=b"not-json"), "qdrant_results"),
        (
            _Response(
                body=_query_response().replace(b'"result":', b'"result":{"points":[]},"result":', 1)
            ),
            "qdrant_results",
        ),
        (_Response(body=b"[]"), "qdrant_results"),
        (
            _Response(body=json.dumps({"status": "ok", "result": {"points": [None]}}).encode()),
            "qdrant_results",
        ),
        (
            _Response(body=json.dumps({"status": "error", "result": {"points": []}}).encode()),
            "qdrant_results",
        ),
        (_Response(body=json.dumps({"status": "ok"}).encode()), "qdrant_results"),
        (
            _Response(body=json.dumps({"status": "ok", "result": {}}).encode()),
            "qdrant_results",
        ),
        (
            _Response(body=json.dumps({"status": "ok", "result": {"points": []}}).encode()),
            "qdrant_results",
        ),
        (
            _Response(
                body=json.dumps(
                    {"status": "ok", "result": {"points": [_valid_point(), _valid_point()]}}
                ).encode()
            ),
            "qdrant_results",
        ),
        (_Response(body=b"{" + b" " * 1_000_000 + b"}"), "qdrant_results"),
    ),
)
def test_service_and_response_failures_are_sanitized_and_fail_closed(
    response: _Response, field: str
) -> None:
    with _service(response) as (base_url, _):
        result = _retrieve(base_url)

    _assert_unsupported(result, field=field)
    detail = result.event.errors[0].detail
    assert detail is not None
    assert base_url not in detail
    assert "not-json" not in detail


def test_redirect_is_rejected_without_contacting_its_target() -> None:
    with _service() as (target_base_url, target_requests):
        redirect = _Response(
            status=302,
            content_type="text/plain",
            body=b"redirect",
            location=f"{target_base_url}/elsewhere",
        )
        with _service(redirect) as (base_url, source_requests):
            result = _retrieve(base_url)

    _assert_unsupported(result, field="qdrant_service")
    assert len(source_requests) == 1
    assert target_requests == []


def test_connection_refusal_and_timeout_fail_closed() -> None:
    _assert_unsupported(
        _retrieve("http://127.0.0.1:1", timeout_seconds=0.05),
        field="qdrant_service",
    )
    with _service(_Response(delay_seconds=0.1)) as (base_url, _):
        timed_out = _retrieve(base_url, timeout_seconds=0.01)
    _assert_unsupported(timed_out, field="qdrant_service")


def test_transport_ignores_ambient_proxy_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:1")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("no_proxy", "")
    monkeypatch.setenv("NO_PROXY", "")

    with _service() as (base_url, requests):
        result = _retrieve(base_url)

    assert result.status is TerminalStatus.PASSED
    assert len(requests) == 1


def test_unexpected_transport_exception_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = "ISSUE28_UNEXPECTED_TRANSPORT_SECRET"

    def fail_unexpectedly(*args: object) -> bytes:
        del args
        raise RuntimeError(marker)

    monkeypatch.setattr(qdrant_module, "_post_query", fail_unexpectedly)
    result = _retrieve("http://127.0.0.1:6333")

    _assert_unsupported(result, field="qdrant_service")
    assert marker not in str(result.event.errors)


def test_non_success_response_is_not_retried() -> None:
    with _service(_Response(status=500)) as (base_url, requests):
        result = _retrieve(base_url)

    _assert_unsupported(result, field="qdrant_service")
    assert len(requests) == 1


def test_retriever_rejects_wrong_config_and_asset_types() -> None:
    with pytest.raises(TypeError, match="config must be a QdrantProceduralRetrieverConfig"):
        QdrantProceduralRetriever(cast(Any, {}))

    retriever = QdrantProceduralRetriever(
        QdrantProceduralRetrieverConfig("http://127.0.0.1:6333", _COLLECTION, 0.8, 1.0)
    )
    with pytest.raises(TypeError, match="resolved_asset must be a KnownAsset"):
        retriever.retrieve(
            resolved_asset=cast(Any, "ex:Pump_12"),
            query_vector=_QUERY_VECTOR,
            retrieval_run_id=_RUN_ID,
            query_id=_QUERY_ID,
        )


def test_unknown_asset_fails_closed_without_network_request() -> None:
    with _service() as (base_url, requests):
        result = QdrantProceduralRetriever(
            QdrantProceduralRetrieverConfig(base_url, _COLLECTION, 0.8, 1.0)
        ).retrieve(
            resolved_asset=KnownAsset("ex:OtherPump", "Other pump"),
            query_vector=_QUERY_VECTOR,
            retrieval_run_id=_RUN_ID,
            query_id=_QUERY_ID,
        )

    _assert_unsupported(result, field="resolved_asset.asset_id")
    assert requests == []


@pytest.mark.parametrize(
    "constant",
    (
        pytest.param(float("nan"), id="nan"),
        pytest.param(float("inf"), id="positive-infinity"),
        pytest.param(float("-inf"), id="negative-infinity"),
    ),
)
@pytest.mark.parametrize("location", ("envelope", "result", "point"))
def test_nonfinite_json_constants_fail_closed_at_every_response_level(
    constant: float,
    location: str,
) -> None:
    document: dict[str, Any] = {
        "status": "ok",
        "result": {"points": [_valid_point()]},
    }
    result = cast(dict[str, Any], document["result"])
    point = cast(dict[str, Any], result["points"][0])
    targets = {"envelope": document, "result": result, "point": point}
    targets[location]["ignored_nonfinite"] = constant
    response = _Response(body=json.dumps(document, allow_nan=True).encode())

    with _service(response) as (base_url, _):
        retrieval = _retrieve(base_url)

    _assert_unsupported(retrieval, field="qdrant_results")


@pytest.mark.parametrize(
    ("mutation", "field"),
    (
        (lambda point: point.update(score=float("nan")), "qdrant_results"),
        (lambda point: point.update(score=0.79), "qdrant_results"),
        (lambda point: point.update(score=True), "qdrant_results"),
        (lambda point: point.pop("payload"), "qdrant_results"),
        (lambda point: point.update(payload=[]), "qdrant_results"),
        (
            lambda point: cast(dict[str, Any], point["payload"]).pop("evidence_id"),
            "qdrant_results",
        ),
        (
            lambda point: cast(dict[str, Any], point["payload"]).update(
                evidence_id="ex:OtherChunk"
            ),
            "payload.evidence_id",
        ),
        (
            lambda point: cast(dict[str, Any], point["payload"]).update(document="OTHER"),
            "payload.document",
        ),
        (
            lambda point: cast(dict[str, Any], point["payload"]).update(chunk_index=True),
            "payload.chunk_index",
        ),
        (
            lambda point: cast(dict[str, Any], point["payload"]).update(
                related_procedure="ex:OtherProcedure"
            ),
            "payload.related_procedure",
        ),
        (
            lambda point: cast(dict[str, Any], point["payload"]).update(text="wrong"),
            "payload.text",
        ),
        (
            lambda point: cast(dict[str, Any], point["payload"]).update(
                applicable_asset_id="ex:OtherPump"
            ),
            "payload.applicable_asset_id",
        ),
        (
            lambda point: cast(dict[str, Any], point["payload"]).update(
                applicable_asset_type="compressor"
            ),
            "payload.applicable_asset_type",
        ),
    ),
)
def test_malformed_or_contradictory_points_fail_closed(mutation: Any, field: str) -> None:
    point = _valid_point()
    mutation(point)
    response = _Response(
        body=json.dumps(
            {"status": "ok", "result": {"points": [point]}},
            allow_nan=True,
        ).encode()
    )
    with _service(response) as (base_url, _):
        result = _retrieve(base_url)

    _assert_unsupported(result, field=field)


@pytest.mark.parametrize(
    "point_id",
    (
        pytest.param(None, id="missing"),
        pytest.param(7, id="integer"),
        pytest.param("not-a-uuid", id="malformed"),
        pytest.param("364C20EB-0324-5496-82D1-F163A5F78AEB", id="noncanonical"),
        pytest.param(
            str(uuid.uuid5(uuid.NAMESPACE_URL, '["other","document","evidence"]')),
            id="canonical-wrong",
        ),
    ),
)
def test_point_id_must_equal_the_canonical_fixture_uuidv5(point_id: object) -> None:
    point = _valid_point()
    if point_id is None:
        point.pop("id")
    else:
        point["id"] = point_id
    response = _Response(body=json.dumps({"status": "ok", "result": {"points": [point]}}).encode())

    with _service(response) as (base_url, _):
        result = _retrieve(base_url)

    _assert_unsupported(result, field="point.id")


@pytest.mark.parametrize(
    "field_name",
    (
        "source_path",
        "start_line",
        "end_line",
        "source_sha256",
        "index_contract_version",
        "vector_source",
        "vector_producer_id",
        "embedding_generated_by_indexer",
    ),
)
def test_missing_citation_or_provenance_payload_field_fails_closed(field_name: str) -> None:
    point = _valid_point()
    cast(dict[str, Any], point["payload"]).pop(field_name)
    response = _Response(body=json.dumps({"status": "ok", "result": {"points": [point]}}).encode())

    with _service(response) as (base_url, _):
        result = _retrieve(base_url)

    _assert_unsupported(result, field="qdrant_results")


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    (
        ("source_path", "other/path.txt"),
        ("source_path", "tests/fixtures/sop/pump12-sop.txt\n"),
        ("source_path", 7),
        ("start_line", 0),
        ("start_line", True),
        ("end_line", 2),
        ("end_line", "1"),
        ("source_sha256", "A" * 64),
        ("source_sha256", "0" * 64),
        ("source_sha256", None),
        ("index_contract_version", "other"),
        ("index_contract_version", "mfg-agentgraph-procedural-index-v1\x1f"),
        ("index_contract_version", False),
        ("vector_source", "indexer"),
        ("vector_source", "caller_supplied\n"),
        ("vector_source", None),
        ("vector_producer_id", "other"),
        ("vector_producer_id", "pump12-test-vector-v1\x00"),
        ("vector_producer_id", 1),
        ("embedding_generated_by_indexer", True),
        ("embedding_generated_by_indexer", 0),
    ),
)
def test_wrong_citation_or_provenance_payload_field_fails_closed(
    field_name: str, bad_value: object
) -> None:
    point = _valid_point()
    cast(dict[str, Any], point["payload"])[field_name] = bad_value
    response = _Response(body=json.dumps({"status": "ok", "result": {"points": [point]}}).encode())

    with _service(response) as (base_url, _):
        result = _retrieve(base_url)

    _assert_unsupported(result, field=f"payload.{field_name}")


def test_live_service_fixture_matches_the_unit_contract() -> None:
    fixture = cast(
        dict[str, Any],
        json.loads(_SERVICE_FIXTURE_PATH.read_text(encoding="utf-8")),
    )

    assert fixture["collection"] == {
        "name": _COLLECTION,
        "vector_size": len(_QUERY_VECTOR),
        "distance": "Cosine",
    }
    assert fixture["points"] == [_ARTIFACT["points"][0]]
    assert fixture["points"][0]["payload"] == _valid_point()["payload"]
    assert "score_threshold" not in fixture
    assert "query_vector" not in fixture
