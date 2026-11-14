"""Contract tests for the Issue #114 idempotent stack bootstrap."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.compare import isomorphic
from rdflib.namespace import SH

from mfg_agentgraph.stack_bootstrap import (
    BootstrapReport,
    BootstrapSources,
    StepOutcome,
    bootstrap_stack,
    named_graph_from_trig,
)
from mfg_agentgraph.stack_config import ModelPin, ServiceEndpoint, StackConfig
from mfg_agentgraph.stack_preflight import HttpResponse

_DIGEST = "sha256:" + "a" * 64
_FUSEKI = "http://127.0.0.1:3030"
_QDRANT = "http://127.0.0.1:6333"
_OLLAMA = "http://127.0.0.1:11434"
_FACTORY = "urn:mfg-agentgraph:graph:factory"
_SHAPES = "urn:mfg-agentgraph:graph:shapes"
_TRIG_FIXTURE = Path(__file__).parent / "fixtures" / "fuseki" / "pump12.trig"

Handler = Callable[[str, str, bytes], HttpResponse]


@dataclass
class _FakeTransport:
    handler: Handler
    calls: list[tuple[str, str, bytes]] = field(default_factory=list)
    timeouts: list[tuple[str, str, float | None]] = field(default_factory=list)

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> HttpResponse:
        self.calls.append(("GET", url, b""))
        self.timeouts.append(("GET", url, timeout_seconds))
        return self.handler("GET", url, b"")

    def post(
        self,
        url: str,
        *,
        body: bytes = b"",
        content_type: str | None = None,
        headers: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> HttpResponse:
        self.calls.append(("POST", url, body))
        self.timeouts.append(("POST", url, timeout_seconds))
        return self.handler("POST", url, body)

    def put(
        self,
        url: str,
        *,
        body: bytes = b"",
        content_type: str | None = None,
        headers: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> HttpResponse:
        self.calls.append(("PUT", url, body))
        self.timeouts.append(("PUT", url, timeout_seconds))
        return self.handler("PUT", url, body)


def _config() -> StackConfig:
    return StackConfig(
        fuseki=ServiceEndpoint.parse(_FUSEKI),
        qdrant=ServiceEndpoint.parse(_QDRANT),
        ollama=ServiceEndpoint.parse(_OLLAMA),
        generation_model=ModelPin("qwen2.5:7b-instruct-q4_K_M", _DIGEST),
        embedding_model=ModelPin("nomic-embed-text", _DIGEST),
    )


def _graph(*triples: tuple[str, str, str]) -> Graph:
    graph = Graph()
    for subject, predicate, obj in triples:
        graph.add((URIRef(subject), URIRef(predicate), Literal(obj)))
    return graph


_FACTORY_GRAPH = _graph(("urn:ex:Pump_12", "urn:ex:locatedAt", "PumpStation_12"))
_SHAPES_GRAPH = _graph(("urn:ex:Shape", "urn:ex:targetClass", "urn:ex:Pump"))

_SHACL_WITH_BLANK_NODES = """
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix ex: <urn:ex:> .

ex:ActionShape
    a sh:NodeShape ;
    sh:targetClass ex:RecommendedAction ;
    sh:property [
        a sh:PropertyShape ;
        sh:path ex:hasSupportEvidence ;
        sh:minCount 1 ;
        sh:message "must cite evidence" ;
    ] .
"""


def _blank_node_shape_graph() -> Graph:
    graph = Graph()
    graph.parse(data=_SHACL_WITH_BLANK_NODES, format="turtle")
    return graph


def _relabel_bnodes(graph: Graph, tag: str) -> Graph:
    """Return a copy whose blank nodes carry different identifiers."""

    relabelled = Graph()
    for subject, predicate, obj in graph:
        relabelled.add(
            (
                BNode(f"{tag}-{subject}") if isinstance(subject, BNode) else subject,
                predicate,
                BNode(f"{tag}-{obj}") if isinstance(obj, BNode) else obj,
            )
        )
    return relabelled


def _sources() -> BootstrapSources:
    return BootstrapSources(factory_graph=_FACTORY_GRAPH, shapes_graph=_SHAPES_GRAPH)


def _turtle(graph: Graph) -> HttpResponse:
    return HttpResponse(status=200, body=graph.serialize(format="turtle").encode())


def _data_url(graph_iri: str) -> str:
    return f"{_FUSEKI}/ds/data?graph={quote(graph_iri, safe='')}"


def _collection_url() -> str:
    return f"{_QDRANT}/collections/procedural"


def _tags(models: list[dict[str, str]]) -> HttpResponse:
    return HttpResponse(status=200, body=json.dumps({"models": models}).encode())


def _collection(size: int, distance: str = "Cosine") -> HttpResponse:
    document = {"result": {"config": {"params": {"vectors": {"size": size, "distance": distance}}}}}
    return HttpResponse(status=200, body=json.dumps(document).encode())


_PINNED_MODELS = [
    {"name": "qwen2.5:7b-instruct-q4_K_M", "digest": _DIGEST},
    {"name": "nomic-embed-text:latest", "digest": _DIGEST},
]


def _stack_handler(
    *,
    existing_graphs: dict[str, HttpResponse] | None = None,
    collection: HttpResponse | None = None,
    models: list[dict[str, str]] | None = None,
    pulled_models: list[dict[str, str]] | None = None,
) -> Handler:
    graphs = existing_graphs or {_FACTORY: HttpResponse(200, b""), _SHAPES: HttpResponse(200, b"")}
    collection_response = collection or HttpResponse(404, b"")
    tags = models if models is not None else []

    def handler(method: str, url: str, body: bytes) -> HttpResponse:
        if method == "POST" and url == f"{_FUSEKI}/ds/sparql":
            for graph_iri, response in graphs.items():
                if graph_iri.encode() in body:
                    return response
            raise AssertionError(f"unexpected SPARQL query {body!r}")
        if method in {"POST", "PUT"} and url.startswith(f"{_FUSEKI}/ds/data"):
            return HttpResponse(204, b"")
        if method == "GET" and url == _collection_url():
            return collection_response
        if method == "PUT" and url == _collection_url():
            return HttpResponse(200, b"")
        if method == "GET" and url == f"{_OLLAMA}/api/tags":
            return _tags(tags if not pulled_models else [*tags, *pulled_models])
        if method == "POST" and url == f"{_OLLAMA}/api/pull":
            return HttpResponse(200, b'{"status":"success"}')
        raise AssertionError(f"unexpected call {method} {url}")

    return handler


def _run(handler: Handler, *, recreate: bool = False) -> tuple[BootstrapReport, _FakeTransport]:
    transport = _FakeTransport(handler)
    return bootstrap_stack(_config(), transport, _sources(), recreate=recreate), transport


def _step(report: BootstrapReport, name: str) -> StepOutcome:
    return next(step for step in report.steps if step.name == name).outcome


def test_an_empty_graph_is_loaded_once() -> None:
    report, transport = _run(
        _stack_handler(models=_PINNED_MODELS, pulled_models=[]),
    )

    assert _step(report, _FACTORY) is StepOutcome.CREATED
    assert ("POST", _data_url(_FACTORY), b"") in [
        (m, u, b"") for m, u, b in transport.calls
    ] or any(m == "POST" and u == _data_url(_FACTORY) for m, u, _ in transport.calls)


def test_an_identical_graph_is_not_written_again() -> None:
    handler = _stack_handler(
        existing_graphs={_FACTORY: _turtle(_FACTORY_GRAPH), _SHAPES: _turtle(_SHAPES_GRAPH)},
        models=_PINNED_MODELS,
    )

    report, transport = _run(handler)

    assert _step(report, _FACTORY) is StepOutcome.ALREADY_PRESENT
    assert not any(u.startswith(f"{_FUSEKI}/ds/data") for _, u, _ in transport.calls)


def test_a_blank_node_shape_with_different_identifiers_is_already_present() -> None:
    desired = _blank_node_shape_graph()
    remote = _relabel_bnodes(desired, "remote")
    assert set(desired) != set(remote)
    assert isomorphic(desired, remote) is True

    handler = _stack_handler(
        existing_graphs={_FACTORY: _turtle(_FACTORY_GRAPH), _SHAPES: _turtle(remote)},
        models=_PINNED_MODELS,
    )
    transport = _FakeTransport(handler)

    report = bootstrap_stack(
        _config(),
        transport,
        BootstrapSources(factory_graph=_FACTORY_GRAPH, shapes_graph=desired),
    )

    assert _step(report, _SHAPES) is StepOutcome.ALREADY_PRESENT
    assert report.exit_code == 0
    assert not any(u.startswith(f"{_FUSEKI}/ds/data") for _, u, _ in transport.calls)


def test_a_different_blank_node_shape_is_refused_without_recreate() -> None:
    desired = _blank_node_shape_graph()
    remote = _relabel_bnodes(desired, "remote")
    for subject, predicate, obj in list(remote):
        if predicate == SH.message:
            remote.remove((subject, predicate, obj))
            remote.add((subject, predicate, Literal("must cite two references")))
    assert isomorphic(desired, remote) is False

    handler = _stack_handler(
        existing_graphs={_FACTORY: _turtle(_FACTORY_GRAPH), _SHAPES: _turtle(remote)},
        models=_PINNED_MODELS,
    )
    transport = _FakeTransport(handler)

    report = bootstrap_stack(
        _config(),
        transport,
        BootstrapSources(factory_graph=_FACTORY_GRAPH, shapes_graph=desired),
    )

    assert _step(report, _SHAPES) is StepOutcome.REFUSED
    assert report.exit_code == 1
    assert not any(u == _data_url(_SHAPES) for _, u, _ in transport.calls)


def test_malformed_remote_graph_rdf_is_a_failed_step_not_a_crash() -> None:
    handler = _stack_handler(
        existing_graphs={
            _FACTORY: HttpResponse(200, b""),
            _SHAPES: HttpResponse(200, b"this is not turtle"),
        },
        models=_PINNED_MODELS,
    )

    report, transport = _run(handler)

    assert _step(report, _SHAPES) is StepOutcome.FAILED
    assert report.exit_code == 1
    assert not any(u == _data_url(_SHAPES) for _, u, _ in transport.calls)


def test_a_conflicting_graph_is_refused_without_recreate() -> None:
    conflicting = _graph(("urn:ex:Pump_12", "urn:ex:locatedAt", "SomewhereElse"))
    handler = _stack_handler(
        existing_graphs={_FACTORY: _turtle(conflicting), _SHAPES: HttpResponse(200, b"")},
        models=_PINNED_MODELS,
    )

    report, transport = _run(handler)

    assert _step(report, _FACTORY) is StepOutcome.REFUSED
    assert report.ok is False
    assert report.exit_code == 1
    assert not any(u == _data_url(_FACTORY) for _, u, _ in transport.calls)


def test_an_explicit_recreate_replaces_the_graph() -> None:
    conflicting = _graph(("urn:ex:Pump_12", "urn:ex:locatedAt", "SomewhereElse"))
    handler = _stack_handler(
        existing_graphs={_FACTORY: _turtle(conflicting), _SHAPES: HttpResponse(200, b"")},
        models=_PINNED_MODELS,
    )

    report, transport = _run(handler, recreate=True)

    assert _step(report, _FACTORY) is StepOutcome.CREATED
    assert any(m == "PUT" and u == _data_url(_FACTORY) for m, u, _ in transport.calls)


def test_a_missing_collection_is_created_with_the_configured_dimension() -> None:
    report, transport = _run(_stack_handler(models=_PINNED_MODELS))

    assert _step(report, "collection:procedural") is StepOutcome.CREATED
    create = next(c for c in transport.calls if c[0] == "PUT" and c[1] == _collection_url())
    vectors = json.loads(create[2])["vectors"]
    assert vectors["size"] == 768
    assert vectors["distance"] == "Cosine"


def test_an_existing_collection_with_the_expected_size_is_kept() -> None:
    handler = _stack_handler(
        collection=_collection(768),
        models=_PINNED_MODELS,
    )

    report, transport = _run(handler)

    assert _step(report, "collection:procedural") is StepOutcome.ALREADY_PRESENT
    assert not any(m == "PUT" and u == _collection_url() for m, u, _ in transport.calls)


def test_an_existing_collection_with_a_different_size_is_refused() -> None:
    handler = _stack_handler(
        collection=_collection(384),
        models=_PINNED_MODELS,
    )

    report, transport = _run(handler)

    assert _step(report, "collection:procedural") is StepOutcome.REFUSED
    assert not any(m == "PUT" and u == _collection_url() for m, u, _ in transport.calls)


def test_an_existing_collection_with_a_different_distance_is_refused() -> None:
    handler = _stack_handler(
        collection=_collection(768, distance="Euclid"),
        models=_PINNED_MODELS,
    )

    report, transport = _run(handler)

    step = next(step for step in report.steps if step.name == "collection:procedural")
    assert step.outcome is StepOutcome.REFUSED
    assert "Euclid" in step.detail
    assert report.exit_code == 1
    assert not any(m == "PUT" and u == _collection_url() for m, u, _ in transport.calls)


def test_a_missing_model_is_pulled_and_then_verified() -> None:
    def handler(method: str, url: str, body: bytes) -> HttpResponse:
        if method == "GET" and url == f"{_OLLAMA}/api/tags":
            return _tags([] if not _pulled["done"] else _PINNED_MODELS)
        if method == "POST" and url == f"{_OLLAMA}/api/pull":
            _pulled["done"] = True
            return HttpResponse(200, b'{"status":"success"}')
        return _stack_handler(models=[], pulled_models=[])(method, url, body)

    _pulled: dict[str, bool] = {"done": False}
    report, transport = _run(handler)

    assert _step(report, "model:qwen2.5:7b-instruct-q4_K_M") is StepOutcome.CREATED
    assert any(m == "POST" and u == f"{_OLLAMA}/api/pull" for m, u, _ in transport.calls)


def test_a_model_digest_mismatch_fails_without_pulling() -> None:
    wrong = [{"name": "qwen2.5:7b-instruct-q4_K_M", "digest": "sha256:" + "b" * 64}]
    handler = _stack_handler(models=wrong)

    report, transport = _run(handler)

    assert _step(report, "model:qwen2.5:7b-instruct-q4_K_M") is StepOutcome.FAILED
    pulls = [body for m, u, body in transport.calls if u == f"{_OLLAMA}/api/pull"]
    assert all(b"qwen2.5" not in body for body in pulls)


def test_a_transport_failure_is_a_failed_step_not_a_crash() -> None:
    def handler(method: str, url: str, body: bytes) -> HttpResponse:
        raise OSError("connection refused")

    report, _ = _run(handler)

    assert report.ok is False
    assert all(step.outcome is StepOutcome.FAILED for step in report.steps)


def test_named_graph_from_trig_extracts_only_the_requested_graph() -> None:
    content = _TRIG_FIXTURE.read_bytes()

    factory = named_graph_from_trig(content, _FACTORY)
    shapes = named_graph_from_trig(content, _SHAPES)

    assert len(factory) > 0
    assert len(shapes) == 0
    assert any("Pump_12" in str(subject) for subject, _, _ in factory)


def test_bootstrap_reports_a_fully_green_stack() -> None:
    handler = _stack_handler(
        existing_graphs={_FACTORY: _turtle(_FACTORY_GRAPH), _SHAPES: _turtle(_SHAPES_GRAPH)},
        collection=_collection(768),
        models=_PINNED_MODELS,
    )

    report, _ = _run(handler)

    assert report.ok is True
    assert report.exit_code == 0


def test_unprefixed_installed_digests_are_treated_as_already_present() -> None:
    bare = _DIGEST.removeprefix("sha256:")
    models = [
        {"name": "qwen2.5:7b-instruct-q4_K_M", "digest": bare},
        {"name": "nomic-embed-text:latest", "digest": bare},
    ]
    handler = _stack_handler(models=models)

    report, transport = _run(handler)

    assert _step(report, "model:qwen2.5:7b-instruct-q4_K_M") is StepOutcome.ALREADY_PRESENT
    assert not any(u == f"{_OLLAMA}/api/pull" for _, u, _ in transport.calls)


def test_a_failed_graph_write_is_reported_not_raised() -> None:
    def handler(method: str, url: str, body: bytes) -> HttpResponse:
        if method == "POST" and url == f"{_FUSEKI}/ds/sparql":
            return HttpResponse(200, b"")
        if method == "POST" and url.startswith(f"{_FUSEKI}/ds/data"):
            return HttpResponse(500, b"boom")
        return HttpResponse(404, b"")

    report, _ = _run(handler)

    assert _step(report, _FACTORY) is StepOutcome.FAILED
    assert report.exit_code == 1


def test_a_failed_model_pull_is_reported() -> None:
    def handler(method: str, url: str, body: bytes) -> HttpResponse:
        if method == "GET" and url == f"{_OLLAMA}/api/tags":
            return _tags([])
        if method == "POST" and url == f"{_OLLAMA}/api/pull":
            return HttpResponse(500, b"boom")
        return _stack_handler(models=[])(method, url, body)

    report, _ = _run(handler)

    assert _step(report, "model:qwen2.5:7b-instruct-q4_K_M") is StepOutcome.FAILED


def test_a_cold_model_pull_uses_the_long_pull_timeout_only_where_needed() -> None:
    def handler(method: str, url: str, body: bytes) -> HttpResponse:
        if method == "GET" and url == f"{_OLLAMA}/api/tags":
            return _tags([] if not pulled["done"] else _PINNED_MODELS)
        if method == "POST" and url == f"{_OLLAMA}/api/pull":
            pulled["done"] = True
            return HttpResponse(200, b'{"status":"success"}')
        return _stack_handler(models=[])(method, url, body)

    pulled: dict[str, bool] = {"done": False}
    report, transport = _run(handler)

    assert report.ok is True
    pull_timeouts = {t for _, u, t in transport.timeouts if u == f"{_OLLAMA}/api/pull"}
    assert pull_timeouts == {_config().pull_timeout_seconds}
    readiness_timeouts = {t for _, u, t in transport.timeouts if u == f"{_OLLAMA}/api/tags"}
    assert readiness_timeouts == {None}


def test_a_pulled_model_that_stays_absent_fails() -> None:
    def handler(method: str, url: str, body: bytes) -> HttpResponse:
        if method == "GET" and url == f"{_OLLAMA}/api/tags":
            return _tags([])
        if method == "POST" and url == f"{_OLLAMA}/api/pull":
            return HttpResponse(200, b"{}")
        return _stack_handler(models=[])(method, url, body)

    report, _ = _run(handler)

    assert _step(report, "model:nomic-embed-text") is StepOutcome.FAILED
