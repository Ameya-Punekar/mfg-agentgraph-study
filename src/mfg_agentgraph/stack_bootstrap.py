"""Idempotent bootstrap of the free local deployment envelope (Issue #114).

Bootstrap loads the factory and shapes graphs, creates the document collection
and pins the local models. It never destroys data silently: an existing graph or
collection whose content or shape differs from the request is reported as
``REFUSED`` unless the caller passes the explicit recreate flag.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from rdflib import Dataset, Graph, URIRef
from rdflib.compare import isomorphic
from rdflib.exceptions import ParserError
from rdflib.plugins.parsers.notation3 import BadSyntax

from mfg_agentgraph.stack_config import DEFAULT_QDRANT_DISTANCE, ModelPin, StackConfig
from mfg_agentgraph.stack_preflight import (
    HttpResponse,
    HttpTransport,
    TransportError,
    collection_distance,
    collection_vector_size,
    digest_matches,
    installed_model_digests,
)

_OK_WRITE_STATUSES: Final = frozenset({200, 201, 204})
_TURTLE: Final = "text/turtle"
_SPARQL_QUERY: Final = "application/sparql-query"
_JSON: Final = "application/json"
_TURTLE_ACCEPT: Final = {"Accept": _TURTLE}
_FAILURE_TYPES: Final = (
    TransportError,
    OSError,
    ValueError,
    KeyError,
    TypeError,
    ParserError,
    BadSyntax,
)


class StepOutcome(StrEnum):
    """The result of one bootstrap step."""

    CREATED = "created"
    ALREADY_PRESENT = "already_present"
    REFUSED = "refused"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class BootstrapStep:
    """One bootstrap step and its outcome."""

    name: str
    outcome: StepOutcome
    detail: str


@dataclass(frozen=True, slots=True)
class BootstrapReport:
    """The ordered bootstrap outcome for one configuration."""

    steps: tuple[BootstrapStep, ...]

    @property
    def ok(self) -> bool:
        """Return whether every step was created or already present."""

        return all(
            step.outcome in {StepOutcome.CREATED, StepOutcome.ALREADY_PRESENT}
            for step in self.steps
        )

    @property
    def exit_code(self) -> int:
        """Return a process exit code for this report."""

        return 0 if self.ok else 1


@dataclass(frozen=True, slots=True)
class BootstrapSources:
    """The source graphs bootstrap loads into their named graphs."""

    factory_graph: Graph
    shapes_graph: Graph

    def __post_init__(self) -> None:
        for name in ("factory_graph", "shapes_graph"):
            if not isinstance(getattr(self, name), Graph):
                raise TypeError(f"{name} must be an rdflib Graph")


def named_graph_from_trig(content: bytes, graph_iri: str) -> Graph:
    """Return one named graph from a TriG document."""

    dataset = Dataset()
    dataset.parse(data=content, format="trig")
    graph = Graph()
    for triple in dataset.get_context(URIRef(graph_iri)):
        graph.add(triple)
    return graph


def _sparql_construct(config: StackConfig, transport: HttpTransport, graph_iri: str) -> Graph:
    query = "CONSTRUCT { ?s ?p ?o } WHERE { GRAPH <" + graph_iri + "> { ?s ?p ?o } }"
    response = transport.post(
        config.fuseki_query_url(),
        body=query.encode(),
        content_type=_SPARQL_QUERY,
        headers=_TURTLE_ACCEPT,
    )
    if response.status not in _OK_WRITE_STATUSES:
        raise TransportError(f"graph query for {graph_iri} returned HTTP {response.status}")
    graph = Graph()
    graph.parse(data=response.body, format="turtle")
    return graph


def _write_graph(
    config: StackConfig,
    transport: HttpTransport,
    graph_iri: str,
    graph: Graph,
    *,
    replace: bool,
) -> HttpResponse:
    url = config.fuseki_data_url(graph_iri)
    body = graph.serialize(format="turtle").encode()
    if replace:
        return transport.put(url, body=body, content_type=_TURTLE)
    return transport.post(url, body=body, content_type=_TURTLE)


def _bootstrap_graph(
    config: StackConfig,
    transport: HttpTransport,
    graph_iri: str,
    desired: Graph,
    *,
    recreate: bool,
) -> BootstrapStep:
    try:
        existing = _sparql_construct(config, transport, graph_iri)
        if len(existing) == 0:
            response = _write_graph(config, transport, graph_iri, desired, replace=False)
            if response.status not in _OK_WRITE_STATUSES:
                raise TransportError(f"graph write returned HTTP {response.status}")
            return BootstrapStep(graph_iri, StepOutcome.CREATED, f"loaded {len(desired)} triples")
        if isomorphic(existing, desired):
            return BootstrapStep(
                graph_iri, StepOutcome.ALREADY_PRESENT, f"{len(desired)} triples already loaded"
            )
        if not recreate:
            return BootstrapStep(
                graph_iri,
                StepOutcome.REFUSED,
                f"graph holds {len(existing)} different triples; "
                "re-run with --recreate to replace it",
            )
        response = _write_graph(config, transport, graph_iri, desired, replace=True)
        if response.status not in _OK_WRITE_STATUSES:
            raise TransportError(f"graph replace returned HTTP {response.status}")
        return BootstrapStep(
            graph_iri, StepOutcome.CREATED, f"replaced with {len(desired)} triples"
        )
    except _FAILURE_TYPES as exc:
        return BootstrapStep(graph_iri, StepOutcome.FAILED, str(exc))


def _bootstrap_collection(config: StackConfig, transport: HttpTransport) -> BootstrapStep:
    name = f"collection:{config.qdrant_collection}"
    url = config.qdrant.url(f"/collections/{config.qdrant_collection}")
    body = json.dumps(
        {
            "vectors": {
                "size": config.embedding_dimension,
                "distance": DEFAULT_QDRANT_DISTANCE,
            }
        }
    ).encode()
    try:
        response = transport.get(url)
        if response.status == 404:
            created = transport.put(url, body=body, content_type=_JSON)
            if created.status not in _OK_WRITE_STATUSES:
                raise TransportError(f"collection create returned HTTP {created.status}")
            return BootstrapStep(
                name,
                StepOutcome.CREATED,
                f"size {config.embedding_dimension} {DEFAULT_QDRANT_DISTANCE}",
            )
        if response.status not in _OK_WRITE_STATUSES:
            raise TransportError(f"collection read returned HTTP {response.status}")
        document = json.loads(response.body)
        if not isinstance(document, dict):
            raise TransportError("collection document is not an object")
        size = collection_vector_size(document)
        distance = collection_distance(document)
        if size != config.embedding_dimension or distance != DEFAULT_QDRANT_DISTANCE:
            return BootstrapStep(
                name,
                StepOutcome.REFUSED,
                f"collection is {size} {distance!r}, expected "
                f"{config.embedding_dimension} {DEFAULT_QDRANT_DISTANCE!r}; "
                "bootstrap never deletes an existing collection",
            )
        return BootstrapStep(name, StepOutcome.ALREADY_PRESENT, f"size {size} {distance}")
    except _FAILURE_TYPES as exc:
        return BootstrapStep(name, StepOutcome.FAILED, str(exc))


def _pull_model(config: StackConfig, transport: HttpTransport, pin: ModelPin) -> HttpResponse:
    body = json.dumps({"model": pin.model_id, "stream": False}).encode()
    # ``stream`` is false, so Ollama answers only once the transfer finishes; a
    # cold pull of a multi-gigabyte model must not be bounded by the readiness
    # timeout.
    return transport.post(
        config.ollama.url("/api/pull"),
        body=body,
        content_type=_JSON,
        timeout_seconds=config.pull_timeout_seconds,
    )


def _bootstrap_model(config: StackConfig, transport: HttpTransport, pin: ModelPin) -> BootstrapStep:
    name = f"model:{pin.model_id}"
    try:
        digests = installed_model_digests(transport, config)
        installed = digests.get(pin.installed_name)
        if installed is not None:
            if not digest_matches(installed, pin.digest):
                return BootstrapStep(
                    name,
                    StepOutcome.FAILED,
                    f"installed digest {installed} does not match pinned {pin.digest}",
                )
            return BootstrapStep(name, StepOutcome.ALREADY_PRESENT, "digest matches the pin")
        response = _pull_model(config, transport, pin)
        if response.status not in _OK_WRITE_STATUSES:
            raise TransportError(f"model pull returned HTTP {response.status}")
        digests = installed_model_digests(transport, config)
        installed = digests.get(pin.installed_name)
        if installed is None or not digest_matches(installed, pin.digest):
            return BootstrapStep(
                name,
                StepOutcome.FAILED,
                f"pulled model digest {installed} does not match pinned {pin.digest}",
            )
        return BootstrapStep(name, StepOutcome.CREATED, "pulled and verified")
    except _FAILURE_TYPES as exc:
        return BootstrapStep(name, StepOutcome.FAILED, str(exc))


def bootstrap_stack(
    config: StackConfig,
    transport: HttpTransport,
    sources: BootstrapSources,
    *,
    recreate: bool = False,
    include_shapes: bool = True,
) -> BootstrapReport:
    """Load the graphs, create the collection and pin the models.

    ``include_shapes=False`` publishes only ``sources.factory_graph`` into
    ``config.factory_graph``; the corpus loader uses it so a corpus release can
    never create or replace the stack's shapes graph.
    """

    if not isinstance(config, StackConfig):
        raise TypeError("config must be a StackConfig")
    if not isinstance(sources, BootstrapSources):
        raise TypeError("sources must be a BootstrapSources")
    if not isinstance(recreate, bool):
        raise TypeError("recreate must be a boolean")
    if not isinstance(include_shapes, bool):
        raise TypeError("include_shapes must be a boolean")
    graph_steps = [
        _bootstrap_graph(
            config, transport, config.factory_graph, sources.factory_graph, recreate=recreate
        )
    ]
    if include_shapes:
        graph_steps.append(
            _bootstrap_graph(
                config, transport, config.shapes_graph, sources.shapes_graph, recreate=recreate
            )
        )
    steps = (
        *graph_steps,
        _bootstrap_collection(config, transport),
        _bootstrap_model(config, transport, config.generation_model),
        _bootstrap_model(config, transport, config.embedding_model),
    )
    return BootstrapReport(steps=steps)
