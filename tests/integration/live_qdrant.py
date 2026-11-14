"""Live Qdrant verification for the Issue #28 procedural retriever.

This file is intentionally not named ``test_*.py`` or ``*_test.py``. Run it
explicitly after preloading ``tests/fixtures/qdrant/pump12.json`` into Qdrant.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, cast

import pytest

from mfg_agentgraph.entity_resolution import KnownAsset
from mfg_agentgraph.qdrant_procedural_retriever import (
    QdrantProceduralRetriever,
    QdrantProceduralRetrieverConfig,
)
from mfg_agentgraph.stage_instrumentation import TerminalStatus

pytestmark = pytest.mark.integration

_BASE_URL_ENV = "MFG_AGENTGRAPH_QDRANT_BASE_URL"
_FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "qdrant" / "pump12.json"
_ASSET = KnownAsset("ex:Pump_12", "Pump 12", ("Pump_12",))


def _base_url() -> str:
    value = os.environ.get(_BASE_URL_ENV)
    if value is None:
        pytest.fail(f"{_BASE_URL_ENV} must be set for the explicit live-service test")
    return value


def _fixture() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(_FIXTURE_PATH.read_text(encoding="utf-8")))


def test_live_qdrant_returns_exact_pump_12_contract() -> None:
    fixture = _fixture()
    point = fixture["points"][0]
    result = QdrantProceduralRetriever(
        QdrantProceduralRetrieverConfig(
            base_url=_base_url(),
            collection_name=fixture["collection"]["name"],
            score_threshold=0.8,
        )
    ).retrieve(
        resolved_asset=_ASSET,
        query_vector=point["vector"],
        retrieval_run_id="live-qdrant-issue-28",
        query_id="query-pump-12-sop-cavitation",
    )

    assert result.status is TerminalStatus.PASSED
    assert tuple(item.evidence_id for item in result.support_records) == ("ex:SOP_Chunk_7",)
    assert tuple(item.stable_id for item in result.evidence_references) == ("ex:SOP_Chunk_7",)
    assert result.evidence_references[0].retrieval.score == pytest.approx(1.0)


def test_live_qdrant_missing_collection_fails_without_fixture_fallback() -> None:
    fixture = _fixture()
    point = fixture["points"][0]
    result = QdrantProceduralRetriever(
        QdrantProceduralRetrieverConfig(
            base_url=_base_url(),
            collection_name="missing-pump12-procedures",
            score_threshold=0.8,
        )
    ).retrieve(
        resolved_asset=_ASSET,
        query_vector=point["vector"],
        retrieval_run_id="live-qdrant-issue-28-missing-collection",
        query_id="query-pump-12-sop-cavitation",
    )

    assert result.status is TerminalStatus.UNSUPPORTED_LOWER_RANK
    assert result.support_records == ()
    assert result.evidence_references == ()
    assert result.evidence_catalog.references == ()
    assert result.event.errors[0].field == "qdrant_service"
