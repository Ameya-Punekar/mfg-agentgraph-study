"""Local deterministic CLI for the canonical Pump_12 S4 demonstration."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from rdflib import Graph

from mfg_agentgraph.candidate_action import CandidateAction
from mfg_agentgraph.entity_resolution import AssetCatalog, KnownAsset
from mfg_agentgraph.evidence_package import EvidencePackage
from mfg_agentgraph.pump12_orchestrator import (
    Pump12OrchestrationResult,
    Pump12StableIds,
    run_pump12_orchestrator,
)
from mfg_agentgraph.stage_instrumentation import TerminalStatus

_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "pump_12" / "scenario.json"
)


def _persist_trace_in_memory(_graph: Graph) -> None:
    """Accept the local trace without claiming durable persistence."""


def _require_release(
    result: Pump12OrchestrationResult,
) -> tuple[CandidateAction, EvidencePackage, str]:
    if (
        result.terminal_status is not TerminalStatus.PASSED
        or result.released_action is None
        or result.evidence_package is None
        or result.provenance_id is None
    ):
        raise RuntimeError("deterministic Pump_12 demo failed closed")
    return result.released_action, result.evidence_package, result.provenance_id


def main() -> int:
    """Run and print the fixed, service-free Pump_12 demonstration."""
    scenario = json.loads(_SCENARIO_PATH.read_text(encoding="utf-8"))
    result = run_pump12_orchestrator(
        {
            "query_text": "What should I inspect after the anomalous sound?",
            "timestamp": "2026-05-18T14:03:30Z",
            "run_id": "run:pump12:issue25",
            "asset_hints": ["Pump_12"],
            "sensor_hints": ["anomalous_sound"],
        },
        scenario=scenario,
        asset_catalog=AssetCatalog((KnownAsset("ex:Pump_12", "Pump 12", ("Pump_12",)),)),
        query_id="query:pump12:issue25",
        stable_ids=Pump12StableIds(
            action_id="ex:CandidateAction_Pump12_Repaired_001",
            validation_report_id="ex:ValidationReport_Pump12_001",
            evidence_package_id="ex:EvidencePackage_Pump12_001",
            provenance_id="ex:ProvenanceTrace_Pump12_001",
            agent_id="ex:Agent_S4",
            prompt_id="ex:Prompt_Pump12_001",
            model_id="ex:FixtureModel_Pump12_001",
            asset_id="ex:Pump_12",
            observation_id="ex:Observation_Pump12_2026-05-18T14:03:00Z",
            procedure_id="ex:Procedure_InspectInletCavitation_Pump12",
            kg_evidence_id="ex:EvidenceEdge_001",
            document_evidence_id="ex:SOP_Chunk_7",
        ),
        recorded_at=datetime(2026, 5, 18, 14, 11, 15, tzinfo=UTC),
        persist_trace=_persist_trace_in_memory,
    )
    action, package, provenance_id = _require_release(result)

    print("MFG-AgentGraph deterministic S4 demo")
    print(f"terminal_status: {result.terminal_status.value}")
    print(f"recommendation: {action.action}")
    print(f"evidence_package_id: {package.package_id}")
    print(f"provenance_id: {provenance_id}")
    print("stages:")
    for index, event in enumerate(result.events, start=1):
        print(f"{index:02d}. {event.stage.value}: {event.status.value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
