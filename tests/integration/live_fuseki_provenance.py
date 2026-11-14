"""Explicit live proof for durable Fuseki provenance persistence.

This file is intentionally outside pytest's default ``test_*.py`` and
``*_test.py`` patterns. It requires a dedicated, test-owned Fuseki dataset.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
from typing import cast
from urllib.parse import urlsplit

import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF

from mfg_agentgraph.fuseki_provenance_store import (
    FusekiProvenanceStore,
    FusekiProvenanceStoreConfig,
)
from mfg_agentgraph.rdf_action_mapper import MFG

pytestmark = pytest.mark.integration

UPDATE_ENV = "MFG_AGENTGRAPH_FUSEKI_PROVENANCE_UPDATE_ENDPOINT"
QUERY_ENV = "MFG_AGENTGRAPH_FUSEKI_PROVENANCE_QUERY_ENDPOINT"
GRAPH_BASE_ENV = "MFG_AGENTGRAPH_FUSEKI_PROVENANCE_GRAPH_BASE"
TRACE_ENV = "MFG_AGENTGRAPH_FUSEKI_PROVENANCE_TRACE_ID"
_MAX_RESPONSE_BYTES = 1_048_576


def _configuration() -> FusekiProvenanceStoreConfig:
    values = {
        name: os.environ.get(name) for name in (UPDATE_ENV, QUERY_ENV, GRAPH_BASE_ENV, TRACE_ENV)
    }
    missing = [name for name, value in values.items() if not value]
    if missing:
        pytest.fail("required live Fuseki environment is missing: " + ", ".join(missing))
    assert all(value is not None for value in values.values())
    return FusekiProvenanceStoreConfig(
        cast(str, values[UPDATE_ENV]),
        cast(str, values[QUERY_ENV]),
        cast(str, values[GRAPH_BASE_ENV]),
    )


def _trace_id() -> str:
    value = os.environ.get(TRACE_ENV)
    if not value:
        pytest.fail(f"{TRACE_ENV} must be set for the explicit live-service test")
    return value


def _graph(trace_id: str) -> Graph:
    graph = Graph()
    root = URIRef(trace_id)
    graph.add((root, RDF.type, MFG.ProvenanceTrace))
    graph.add((root, MFG.runId, Literal("live-fuseki-provenance-proof")))
    return graph


def _derived_graph_iri(config: FusekiProvenanceStoreConfig, trace_id: str) -> str:
    return config.provenance_graph_base + ":trace:" + hashlib.sha256(trace_id.encode()).hexdigest()


def _post(
    endpoint: str, content_type: str, body: bytes, accept: str | None = None
) -> tuple[int, bytes, str | None]:
    parts = urlsplit(endpoint)
    assert parts.hostname is not None and parts.port is not None
    connection = http.client.HTTPConnection(parts.hostname, parts.port, timeout=5.0)
    try:
        headers = {
            "Host": parts.netloc,
            "Content-Type": content_type,
            "Content-Length": str(len(body)),
            "Connection": "close",
        }
        if accept is not None:
            headers["Accept"] = accept
        connection.request(
            "POST",
            parts.path,
            body=body,
            headers=headers,
        )
        response = connection.getresponse()
        payload = response.read(_MAX_RESPONSE_BYTES + 1)
        if len(payload) > _MAX_RESPONSE_BYTES:
            raise AssertionError("Fuseki response exceeds bound")
        return response.status, payload, response.getheader("Content-Type")
    finally:
        connection.close()


def _ask_graph_empty(config: FusekiProvenanceStoreConfig, graph_iri: str) -> bool:
    query = ("ASK { GRAPH <" + graph_iri + "> { ?s ?p ?o } }").encode("ascii")
    status, body, content_type = _post(
        config.query_endpoint,
        "application/sparql-query; charset=utf-8",
        query,
        accept="application/sparql-results+json",
    )
    assert status == 200
    assert content_type is not None
    assert content_type.split(";", 1)[0].strip() == "application/sparql-results+json"
    payload = json.loads(body.decode("utf-8"))
    value = payload.get("boolean")
    assert isinstance(value, bool)
    return value is False


def _assert_graph_empty(config: FusekiProvenanceStoreConfig, graph_iri: str) -> None:
    assert _ask_graph_empty(config, graph_iri)


def _delete_exact_graph(
    config: FusekiProvenanceStoreConfig, graph_iri: str, canonical: bytes
) -> None:
    body = b"DELETE DATA { GRAPH <" + graph_iri.encode("ascii") + b"> { " + canonical + b"} }"
    status, response_body, _ = _post(
        config.update_endpoint, "application/sparql-update; charset=utf-8", body
    )
    assert status == 204
    assert response_body == b""


def test_live_fuseki_provenance() -> None:
    config = _configuration()
    trace_id = _trace_id()
    graph = _graph(trace_id)
    store = FusekiProvenanceStore(config)
    canonical = store._canonicalize_graph(graph)
    derived_graph = _derived_graph_iri(config, trace_id)

    assert _ask_graph_empty(config, derived_graph)
    ownership_confirmed = False
    try:
        store.persist(graph)
        resolved = store.resolve(trace_id, graph)
        assert resolved is not graph
        assert store._canonicalize_graph(resolved) == canonical
        ownership_confirmed = True
    finally:
        if ownership_confirmed:
            _delete_exact_graph(config, derived_graph, canonical)
            _assert_graph_empty(config, derived_graph)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
