"""Explicit live Qdrant 1.19.2 proof for Issue #29 indexing.

Run only with ``MFG_AGENTGRAPH_QDRANT_BASE_URL`` set. The test owns and removes
the dedicated fixture collection; production code has no delete operation.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

import pytest

from mfg_agentgraph.entity_resolution import KnownAsset
from mfg_agentgraph.procedural_indexing import (
    IndexingTerminalStatus,
    QdrantIndexServiceConfig,
    build_procedural_index,
    execute_procedural_index,
)
from mfg_agentgraph.qdrant_procedural_retriever import (
    QdrantProceduralRetriever,
    QdrantProceduralRetrieverConfig,
)
from mfg_agentgraph.stage_instrumentation import TerminalStatus

pytestmark = pytest.mark.integration

_BASE_URL_ENV = "MFG_AGENTGRAPH_QDRANT_BASE_URL"
_FIXTURES = Path(__file__).parents[1] / "fixtures"
_MAX_RESPONSE_BYTES = 1_000_000
_ASSET = KnownAsset("ex:Pump_12", "Pump 12", ("Pump_12",))


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
        return None


def _base_url() -> str:
    value = os.environ.get(_BASE_URL_ENV)
    if value is None:
        pytest.fail(f"{_BASE_URL_ENV} must be set for the explicit live-service test")
    return value.rstrip("/")


def _strict_request(method: str, path: str, body: object | None = None) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, separators=(",", ":"), allow_nan=False).encode()
        headers["Content-Type"] = "application/json"
    request = Request(f"{_base_url()}{path}", data=data, method=method, headers=headers)
    opener = build_opener(ProxyHandler({}), _NoRedirectHandler())
    with opener.open(request, timeout=5.0) as response:
        assert response.status == 200
        assert response.headers.get("Content-Type", "").partition(";")[0] == "application/json"
        payload = response.read(_MAX_RESPONSE_BYTES + 1)
    assert len(payload) <= _MAX_RESPONSE_BYTES

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            assert key not in result
            result[key] = value
        return result

    document = json.loads(
        payload,
        object_pairs_hook=unique,
        parse_constant=lambda value: pytest.fail(f"nonfinite JSON constant: {value}"),
    )
    assert type(document) is dict
    assert document.get("status") == "ok"
    return cast(dict[str, Any], document)


def _delete_collection(collection: str) -> str | None:
    try:
        document = _strict_request("DELETE", f"/collections/{collection}")
        if document.get("result") is not True:
            return "cleanup response result was not true"
    except (AssertionError, HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
        return f"cleanup failed: {type(error).__name__}"
    return None


def test_live_qdrant_indexes_twice_and_retrieves_exact_generated_point() -> None:
    plan = build_procedural_index(
        (_FIXTURES / "qdrant" / "pump12-index-config.json").read_bytes(),
        (_FIXTURES / "sop" / "pump12-sop.txt").read_bytes(),
        (_FIXTURES / "qdrant" / "pump12-vectors.json").read_bytes(),
    )
    collection = plan.config.collection_name
    point = plan.points[0]
    cleanup_error: str | None = None
    primary_error: BaseException | None = None
    try:
        for run_number in (1, 2):
            indexed = execute_procedural_index(plan, QdrantIndexServiceConfig(_base_url()))
            assert indexed.status is IndexingTerminalStatus.PASSED
            assert indexed.completed_point_count == 1
            assert indexed.intended_point_ids == (point.point_id,)

            stored = _strict_request(
                "GET",
                f"/collections/{collection}/points/{point.point_id}",
            )["result"]
            assert type(stored) is dict
            assert stored["id"] == point.point_id
            assert stored["payload"] == dict(point.payload)
            assert stored["vector"] == list(point.vector)

            count = _strict_request(
                "POST",
                f"/collections/{collection}/points/count",
                {"exact": True},
            )["result"]["count"]
            assert type(count) is int
            assert count == len(plan.points)

            retrieved = QdrantProceduralRetriever(
                QdrantProceduralRetrieverConfig(_base_url(), collection, 0.8)
            ).retrieve(
                resolved_asset=_ASSET,
                query_vector=point.vector,
                retrieval_run_id=f"live-qdrant-indexing-{run_number}",
                query_id="query-pump-12-sop-cavitation",
            )
            assert retrieved.status is TerminalStatus.PASSED
            assert retrieved.support_records[0].evidence_id == point.payload["evidence_id"]
            assert retrieved.support_records[0].source_path == point.payload["source_path"]
    except BaseException as error:
        primary_error = error
        raise
    finally:
        cleanup_error = _delete_collection(collection)
        if cleanup_error is not None and primary_error is None:
            pytest.fail(cleanup_error)
        if cleanup_error is not None and primary_error is not None:
            print(cleanup_error)
