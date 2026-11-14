"""Live Fuseki verification for the Issue #27 structured retriever.

This file is intentionally not named ``test_*.py`` or ``*_test.py``. Run it
explicitly after loading ``tests/fixtures/fuseki/pump12.trig`` into Fuseki.
"""

from __future__ import annotations

import os

import pytest

from mfg_agentgraph.entity_resolution import KnownAsset
from mfg_agentgraph.fuseki_structured_retriever import (
    FusekiStructuredRetriever,
    FusekiStructuredRetrieverConfig,
)
from mfg_agentgraph.stage_instrumentation import TerminalStatus

pytestmark = pytest.mark.integration

_ENDPOINT_ENV = "MFG_AGENTGRAPH_FUSEKI_QUERY_ENDPOINT"
_FACTORY_GRAPH = "urn:mfg-agentgraph:graph:factory"
_SHAPES_GRAPH = "urn:mfg-agentgraph:graph:shapes"
_PROVENANCE_GRAPH = "urn:mfg-agentgraph:graph:provenance"
_RESOURCE_NAMESPACE = "https://w3id.org/mfg-agentgraph/example#"


def test_live_fuseki_returns_exact_pump_12_contract() -> None:
    endpoint = os.environ.get(_ENDPOINT_ENV)
    if endpoint is None:
        pytest.fail(f"{_ENDPOINT_ENV} must be set for the explicit live-service test")

    result = FusekiStructuredRetriever(
        FusekiStructuredRetrieverConfig(
            query_endpoint=endpoint,
            factory_graph=_FACTORY_GRAPH,
            shapes_graph=_SHAPES_GRAPH,
            provenance_graph=_PROVENANCE_GRAPH,
            resource_namespace=_RESOURCE_NAMESPACE,
        )
    ).retrieve(
        resolved_asset=KnownAsset("ex:Pump_12", "Pump 12", ("Pump_12",)),
        retrieval_run_id="live-fuseki-issue-27",
        query_id="query-pump-12-anomalous-sound",
    )

    assert result.status is TerminalStatus.PASSED
    assert tuple(item.observation_id for item in result.observations) == (
        "ex:Observation_Pump12_2026-05-18T14:03:00Z",
    )
    assert tuple(item.procedure_id for item in result.support_records) == (
        "ex:Procedure_InspectInletCavitation_Pump12",
    )
    assert tuple(item.evidence_id for item in result.support_records) == ("ex:EvidenceEdge_001",)
    assert tuple(item.stable_id for item in result.evidence_references) == ("ex:EvidenceEdge_001",)


def test_live_fuseki_missing_factory_graph_fails_without_fixture_fallback() -> None:
    endpoint = os.environ.get(_ENDPOINT_ENV)
    if endpoint is None:
        pytest.fail(f"{_ENDPOINT_ENV} must be set for the explicit live-service test")

    result = FusekiStructuredRetriever(
        FusekiStructuredRetrieverConfig(
            query_endpoint=endpoint,
            factory_graph="urn:mfg-agentgraph:graph:missing-factory",
            shapes_graph=_SHAPES_GRAPH,
            provenance_graph=_PROVENANCE_GRAPH,
            resource_namespace=_RESOURCE_NAMESPACE,
        )
    ).retrieve(
        resolved_asset=KnownAsset("ex:Pump_12", "Pump 12", ("Pump_12",)),
        retrieval_run_id="live-fuseki-issue-27-missing-graph",
        query_id="query-pump-12-anomalous-sound",
    )

    assert result.status is TerminalStatus.INSUFFICIENT_EVIDENCE
    assert result.observations == ()
    assert result.support_records == ()
    assert result.evidence_references == ()
    assert result.evidence_catalog.references == ()
    assert result.event.errors[0].field == "sparql_results"
