"""Explicitly invoked live proof for the native Ollama chat adapter."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from mfg_agentgraph.entity_resolution import KnownAsset
from mfg_agentgraph.ollama_model_adapter import (
    OLLAMA_PROMPT_ID,
    OLLAMA_SCHEMA_ID,
    OllamaCandidateAdapter,
    OllamaModelAdapterConfig,
)
from mfg_agentgraph.procedural_retrieval import retrieve_procedural_support
from mfg_agentgraph.stage_instrumentation import StageName, TerminalStatus
from mfg_agentgraph.structured_retrieval import retrieve_structured_support

_SUCCESS = "LIVE_OLLAMA_MODEL_ADAPTER_OK"
_FAILURE = "LIVE_OLLAMA_MODEL_ADAPTER_FAILED"
_RUNTIME_ID = "ollama-live-script"
_QUERY_ID = "query-pump-12-candidate-generation"
_GENERATION_RUN_ID = "generation-run-live-ollama"


def _build_inputs() -> tuple[Any, Any]:
    fixture_path = Path(__file__).parents[1] / "fixtures" / "pump_12" / "scenario.json"
    scenario = json.loads(fixture_path.read_text(encoding="utf-8"))
    asset = KnownAsset("ex:Pump_12", "Pump 12", ("Pump_12",))
    structured = retrieve_structured_support(
        resolved_asset=asset,
        scenario=scenario,
        retrieval_run_id="structured-run-live-ollama",
        query_id=_QUERY_ID,
    )
    procedural = retrieve_procedural_support(
        resolved_asset=asset,
        scenario=scenario,
        retrieval_run_id="procedural-run-live-ollama",
        query_id=_QUERY_ID,
    )
    return structured, procedural


def _build_adapter(base_url: str, model_id: str) -> OllamaCandidateAdapter:
    config = OllamaModelAdapterConfig(base_url, model_id, _RUNTIME_ID)
    return OllamaCandidateAdapter(config)


def _is_accepted(result: Any, model_id: str) -> bool:
    return (
        type(result.status) is TerminalStatus
        and result.status is TerminalStatus.PASSED
        and result.model_id == model_id
        and result.runtime_id == _RUNTIME_ID
        and result.prompt_id == OLLAMA_PROMPT_ID
        and result.schema_id == OLLAMA_SCHEMA_ID
        and type(result.event.stage) is StageName
        and result.event.stage is StageName.CANDIDATE_GENERATION
    )


def main() -> int:
    base_url = os.environ.get("MFG_AGENTGRAPH_OLLAMA_BASE_URL")
    model_id = os.environ.get("MFG_AGENTGRAPH_OLLAMA_MODEL")
    if not base_url or not model_id:
        print(_FAILURE, file=sys.stderr)
        return 1
    try:
        structured, procedural = _build_inputs()
        adapter = _build_adapter(base_url, model_id)
        result = adapter.generate(structured, procedural, _GENERATION_RUN_ID, _QUERY_ID)
        if not _is_accepted(result, model_id):
            raise ValueError
    except Exception:
        print(_FAILURE, file=sys.stderr)
        return 1
    print(_SUCCESS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
