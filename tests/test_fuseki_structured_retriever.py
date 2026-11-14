"""Contract tests for the Issue #27 Fuseki structured retriever."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast

import pytest

import mfg_agentgraph.fuseki_structured_retriever as fuseki_module
from mfg_agentgraph.entity_resolution import KnownAsset
from mfg_agentgraph.evidence_reference import EvidenceKind, EvidenceValidationStatus
from mfg_agentgraph.fuseki_structured_retriever import (
    FUSEKI_STRUCTURED_RETRIEVER_NAME,
    FusekiStructuredRetriever,
    FusekiStructuredRetrieverConfig,
)
from mfg_agentgraph.stage_instrumentation import StageErrorCode, StageName, TerminalStatus
from mfg_agentgraph.structured_retrieval import (
    StructuredRetrievalResult,
    retrieve_structured_support,
)

_FACTORY_GRAPH = "urn:mfg-agentgraph:graph:factory"
_SHAPES_GRAPH = "urn:mfg-agentgraph:graph:shapes"
_PROVENANCE_GRAPH = "urn:mfg-agentgraph:graph:provenance"
_RESOURCE_NAMESPACE = "https://w3id.org/mfg-agentgraph/example#"
_ASSET = KnownAsset("ex:Pump_12", "Pump 12", ("Pump_12",))
_RUN_ID = "run-issue-27"
_QUERY_ID = "query-pump-12-anomalous-sound"
_SCENARIO_PATH = Path(__file__).parent / "fixtures" / "pump_12" / "scenario.json"
_RESULT_VARS = (
    "asset",
    "location",
    "observation",
    "observedAt",
    "signal",
    "anomaly",
    "description",
    "procedure",
    "evidence",
    "predicate",
)


def _uri(local_name: str) -> dict[str, str]:
    return {"type": "uri", "value": f"{_RESOURCE_NAMESPACE}{local_name}"}


def _literal(value: str, *, datatype: str | None = None) -> dict[str, str]:
    binding = {"type": "literal", "value": value}
    if datatype is not None:
        binding["datatype"] = datatype
    return binding


def _valid_binding() -> dict[str, dict[str, str]]:
    return {
        "asset": _uri("Pump_12"),
        "location": _uri("PumpStation_12"),
        "observation": _uri("Observation_Pump12_2026-05-18T14:03:00Z"),
        "observedAt": _literal(
            "2026-05-18T14:03:00Z",
            datatype="http://www.w3.org/2001/XMLSchema#dateTime",
        ),
        "signal": _literal("anomalous_sound"),
        "anomaly": _literal("anomalous_sound"),
        "description": _literal("Anomalous sound detected at Pump_12 at 14:03 UTC."),
        "procedure": _uri("Procedure_InspectInletCavitation_Pump12"),
        "evidence": _uri("EvidenceEdge_001"),
        "predicate": _uri("hasRecommendedProcedure"),
    }


def _sparql_results(
    bindings: list[dict[str, dict[str, str]]] | None = None,
    *,
    variables: tuple[str, ...] = _RESULT_VARS,
) -> bytes:
    return json.dumps(
        {
            "head": {"vars": list(variables)},
            "results": {"bindings": bindings if bindings is not None else [_valid_binding()]},
        }
    ).encode()


def _duplicate_results_key_payload() -> bytes:
    return _sparql_results().replace(
        b'"results":',
        b'"results":{"bindings":[]},"results":',
        1,
    )


@dataclass
class _Response:
    status: int = 200
    content_type: str = "application/sparql-results+json; charset=utf-8"
    body: bytes = _sparql_results()
    delay_seconds: float = 0.0
    location: str | None = None


@dataclass
class _CapturedRequest:
    method: str
    path: str
    content_type: str | None
    accept: str | None
    body: bytes


@contextmanager
def _service(response: _Response) -> Iterator[tuple[str, list[_CapturedRequest]]]:
    requests: list[_CapturedRequest] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            requests.append(
                _CapturedRequest(
                    method=self.command,
                    path=self.path,
                    content_type=self.headers.get("Content-Type"),
                    accept=self.headers.get("Accept"),
                    body=self.rfile.read(length),
                )
            )
            if response.delay_seconds:
                time.sleep(response.delay_seconds)
            self.send_response(response.status)
            self.send_header("Content-Type", response.content_type)
            if response.location is not None:
                self.send_header("Location", response.location)
            self.end_headers()
            with suppress(BrokenPipeError):
                self.wfile.write(response.body)

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = cast(tuple[str, int], server.server_address)
        yield f"http://{host}:{port}/mfg/query", requests
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def _config(endpoint: str, **overrides: object) -> FusekiStructuredRetrieverConfig:
    values: dict[str, object] = {
        "query_endpoint": endpoint,
        "factory_graph": _FACTORY_GRAPH,
        "shapes_graph": _SHAPES_GRAPH,
        "provenance_graph": _PROVENANCE_GRAPH,
        "resource_namespace": _RESOURCE_NAMESPACE,
        "timeout_seconds": 1.0,
    }
    values.update(overrides)
    return FusekiStructuredRetrieverConfig(
        query_endpoint=cast(Any, values["query_endpoint"]),
        factory_graph=cast(Any, values["factory_graph"]),
        shapes_graph=cast(Any, values["shapes_graph"]),
        provenance_graph=cast(Any, values["provenance_graph"]),
        resource_namespace=cast(Any, values["resource_namespace"]),
        timeout_seconds=cast(Any, values["timeout_seconds"]),
    )


def _retrieve(endpoint: str, **config_overrides: object) -> StructuredRetrievalResult:
    return FusekiStructuredRetriever(_config(endpoint, **config_overrides)).retrieve(
        resolved_asset=_ASSET,
        retrieval_run_id=_RUN_ID,
        query_id=_QUERY_ID,
    )


def _assert_insufficient(result: object, *, field: str) -> None:
    typed = cast(Any, result)
    assert typed.status is TerminalStatus.INSUFFICIENT_EVIDENCE
    assert typed.observations == ()
    assert typed.support_records == ()
    assert typed.evidence_references == ()
    assert typed.evidence_catalog.references == ()
    assert typed.event.stage is StageName.STRUCTURED_RETRIEVAL
    assert typed.event.status is TerminalStatus.INSUFFICIENT_EVIDENCE
    assert typed.event.output_ids == ()
    assert len(typed.event.errors) == 1
    assert typed.event.errors[0].code is StageErrorCode.INSUFFICIENT_EVIDENCE
    assert typed.event.errors[0].field == field


def test_live_result_matches_fixture_domain_contract_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = cast(dict[str, Any], json.loads(_SCENARIO_PATH.read_text(encoding="utf-8")))
    fixture = retrieve_structured_support(
        resolved_asset=_ASSET,
        scenario=scenario,
        retrieval_run_id=_RUN_ID,
        query_id=_QUERY_ID,
    )

    def forbidden_fixture_call(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("Fuseki adapter silently called fixture retriever")

    monkeypatch.setattr(
        "mfg_agentgraph.structured_retrieval.StructuredRetriever.retrieve",
        forbidden_fixture_call,
    )
    with _service(_Response()) as (endpoint, _):
        live = _retrieve(endpoint)

    assert live.status is fixture.status is TerminalStatus.PASSED
    assert live.asset == fixture.asset
    assert live.observations == fixture.observations
    assert live.support_records == fixture.support_records
    assert live.evidence_catalog.references == live.evidence_references
    assert tuple(ref.stable_id for ref in live.evidence_references) == tuple(
        ref.stable_id for ref in fixture.evidence_references
    )
    reference = live.evidence_references[0]
    assert reference.kind is EvidenceKind.KG_EDGE
    assert reference.validation_status is EvidenceValidationStatus.VALIDATED
    assert reference.source == _FACTORY_GRAPH
    assert reference.retrieval.retrieval_run_id == _RUN_ID
    assert reference.retrieval.query_id == _QUERY_ID
    assert reference.retrieval.retriever_name == FUSEKI_STRUCTURED_RETRIEVER_NAME
    assert reference.retrieval.rank == 1
    assert reference.retrieval.score == 1.0
    assert live.event.input_ids == fixture.event.input_ids
    assert live.event.output_ids == fixture.event.output_ids
    assert live.event.errors == fixture.event.errors == ()
    assert live.event.duration_ms is not None
    assert live.event.duration_ms >= 0


def test_http_transport_posts_sparql_json_query_to_explicit_factory_graph() -> None:
    with _service(_Response()) as (endpoint, requests):
        result = _retrieve(endpoint)

    assert result.status is TerminalStatus.PASSED
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert request.path == "/mfg/query"
    assert request.content_type == "application/sparql-query; charset=utf-8"
    assert request.accept == "application/sparql-results+json"
    query = request.body.decode()
    assert f"GRAPH <{_FACTORY_GRAPH}>" in query
    assert f"<{_RESOURCE_NAMESPACE}Pump_12>" in query
    assert _SHAPES_GRAPH not in query
    assert _PROVENANCE_GRAPH not in query


def test_http_transport_ignores_ambient_proxy_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:1")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("no_proxy", "")
    monkeypatch.setenv("NO_PROXY", "")

    with _service(_Response()) as (endpoint, requests):
        result = _retrieve(endpoint)

    assert result.status is TerminalStatus.PASSED
    assert len(requests) == 1


def test_graph_configuration_and_resource_namespace_are_independent() -> None:
    alternate_shapes = "urn:independent:shapes"
    alternate_provenance = "urn:independent:provenance"
    with _service(_Response()) as (endpoint, requests):
        result = _retrieve(
            endpoint,
            shapes_graph=alternate_shapes,
            provenance_graph=alternate_provenance,
        )

    assert result.status is TerminalStatus.PASSED
    query = requests[0].body.decode()
    assert _RESOURCE_NAMESPACE in query
    assert alternate_shapes not in query
    assert alternate_provenance not in query


@pytest.mark.parametrize(
    ("override", "value", "message"),
    (
        ("query_endpoint", "ftp://localhost/query", "query_endpoint must use http or https"),
        ("query_endpoint", None, "query_endpoint must be a string"),
        ("query_endpoint", "http://user:secret@localhost/query", "must not contain credentials"),
        ("query_endpoint", "http://localhost/query#fragment", "must not contain a fragment"),
        ("query_endpoint", "http://localhost/query?union=true", "must not contain a query"),
        ("query_endpoint", "http:///query", "must include a host"),
        ("query_endpoint", "http://localhost:bad/query", "valid port"),
        ("factory_graph", "relative", "factory_graph must be an absolute IRI"),
        ("factory_graph", "urn:", "factory_graph must be an absolute IRI"),
        ("resource_namespace", "relative/", "resource_namespace must be an absolute IRI"),
        ("timeout_seconds", 0, "timeout_seconds must be positive and finite"),
        ("timeout_seconds", float("inf"), "timeout_seconds must be positive and finite"),
        ("timeout_seconds", True, "timeout_seconds must be a number"),
    ),
)
def test_configuration_rejects_unsafe_or_invalid_values(
    override: str, value: object, message: str
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        _config("http://localhost:3030/mfg/query", **{override: value})


def test_configuration_requires_distinct_named_graphs() -> None:
    with pytest.raises(ValueError, match="named graph IRIs must be distinct"):
        _config("http://localhost:3030/mfg/query", shapes_graph=_FACTORY_GRAPH)


def test_retriever_rejects_wrong_config_type() -> None:
    with pytest.raises(TypeError, match="config must be a FusekiStructuredRetrieverConfig"):
        FusekiStructuredRetriever(cast(Any, {}))


@pytest.mark.parametrize(
    ("response", "field"),
    (
        (_Response(status=500), "fuseki_service"),
        (
            _Response(
                status=302,
                content_type="text/plain",
                body=b"redirect",
                location="http://example.invalid/elsewhere",
            ),
            "fuseki_service",
        ),
        (_Response(content_type="text/html"), "sparql_results"),
        (_Response(body=b"not-json"), "sparql_results"),
        (_Response(body=_duplicate_results_key_payload()), "sparql_results"),
        (_Response(body=b"[]"), "sparql_results"),
        (
            _Response(
                body=json.dumps({"head": {"vars": list(_RESULT_VARS)}, "results": []}).encode()
            ),
            "sparql_results",
        ),
        (_Response(body=_sparql_results([])), "sparql_results"),
        (_Response(body=_sparql_results([_valid_binding(), _valid_binding()])), "sparql_results"),
        (_Response(body=b"{" + b" " * 1_000_000 + b"}"), "sparql_results"),
    ),
)
def test_service_and_result_failures_are_sanitized_and_fail_closed(
    response: _Response, field: str
) -> None:
    with _service(response) as (endpoint, _):
        result = _retrieve(endpoint)

    _assert_insufficient(result, field=field)
    detail = result.event.errors[0].detail
    assert detail is not None
    assert endpoint not in detail
    assert "not-json" not in detail


def test_connection_refusal_and_timeout_fail_closed() -> None:
    refused = _retrieve("http://127.0.0.1:1/mfg/query", timeout_seconds=0.05)
    _assert_insufficient(refused, field="fuseki_service")

    with _service(_Response(delay_seconds=0.1)) as (endpoint, _):
        timed_out = _retrieve(endpoint, timeout_seconds=0.01)
    _assert_insufficient(timed_out, field="fuseki_service")


def test_unexpected_transport_exception_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = "ISSUE27_UNEXPECTED_TRANSPORT_SECRET"

    def fail_unexpectedly(*args: object) -> bytes:
        del args
        raise RuntimeError(marker)

    monkeypatch.setattr(fuseki_module, "_post_sparql_query", fail_unexpectedly)
    result = _retrieve("http://localhost:3030/mfg/query")

    _assert_insufficient(result, field="fuseki_service")
    assert marker not in str(result.event.errors)


@pytest.mark.parametrize(
    ("mutate", "field"),
    (
        (lambda body: body["head"].update(vars=["asset"]), "sparql_results"),
        (lambda body: body["results"].update(bindings="not-a-list"), "sparql_results"),
        (lambda body: body["results"]["bindings"][0].pop("evidence"), "sparql_results"),
        (lambda body: body["results"]["bindings"][0].update(asset=None), "sparql_results"),
        (
            lambda body: body["results"]["bindings"][0]["asset"].update(type="literal"),
            "sparql_results",
        ),
        (
            lambda body: body["results"]["bindings"][0]["asset"].update(
                value="https://other.example/Pump_12"
            ),
            "sparql_results",
        ),
        (
            lambda body: body["results"]["bindings"][0]["asset"].update(value=_RESOURCE_NAMESPACE),
            "sparql_results",
        ),
        (lambda body: body["results"]["bindings"][0].update(signal=None), "sparql_results"),
        (
            lambda body: body["results"]["bindings"][0]["signal"].update(type="uri"),
            "sparql_results",
        ),
        (
            lambda body: body["results"]["bindings"][0]["signal"].update(value=""),
            "sparql_results",
        ),
        (
            lambda body: body["results"]["bindings"][0]["observedAt"].update(
                datatype="http://www.w3.org/2001/XMLSchema#string"
            ),
            "sparql_results",
        ),
        (
            lambda body: body["results"]["bindings"][0]["location"].update(
                value=f"{_RESOURCE_NAMESPACE}OtherStation"
            ),
            "asset.location",
        ),
        (
            lambda body: body["results"]["bindings"][0]["signal"].update(value="temperature"),
            "observation.signal",
        ),
        (
            lambda body: body["results"]["bindings"][0]["predicate"].update(
                value=f"{_RESOURCE_NAMESPACE}otherPredicate"
            ),
            "kg_evidence.predicate",
        ),
    ),
)
def test_malformed_or_contradictory_bindings_fail_closed(mutate: Any, field: str) -> None:
    body = json.loads(_sparql_results())
    mutate(body)
    with _service(_Response(body=json.dumps(body).encode())) as (endpoint, _):
        result = _retrieve(endpoint)

    _assert_insufficient(result, field=field)


def test_input_validation_matches_fixture_fail_fast_boundary() -> None:
    with _service(_Response()) as (endpoint, _):
        retriever = FusekiStructuredRetriever(_config(endpoint))
        with pytest.raises(TypeError, match="resolved_asset must be a KnownAsset"):
            retriever.retrieve(
                resolved_asset=cast(Any, "ex:Pump_12"),
                retrieval_run_id=_RUN_ID,
                query_id=_QUERY_ID,
            )
        with pytest.raises(ValueError, match="retrieval_run_id must not contain surrounding"):
            retriever.retrieve(
                resolved_asset=_ASSET,
                retrieval_run_id=f" {_RUN_ID}",
                query_id=_QUERY_ID,
            )
        with pytest.raises(ValueError, match="query_id must be nonblank"):
            retriever.retrieve(
                resolved_asset=_ASSET,
                retrieval_run_id=_RUN_ID,
                query_id=" ",
            )


def test_unknown_asset_fails_closed_without_network_request() -> None:
    with _service(_Response()) as (endpoint, requests):
        result = FusekiStructuredRetriever(_config(endpoint)).retrieve(
            resolved_asset=KnownAsset("ex:OtherPump", "Other pump"),
            retrieval_run_id=_RUN_ID,
            query_id=_QUERY_ID,
        )

    _assert_insufficient(result, field="resolved_asset.asset_id")
    assert requests == []
