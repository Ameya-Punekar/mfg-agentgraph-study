import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_FIXTURE_ROOT = _REPOSITORY_ROOT / "tests" / "fixtures" / "pump_12"
_SCENARIO_PATH = _FIXTURE_ROOT / "scenario.json"
_FAILURE_SCENARIOS_PATH = _FIXTURE_ROOT / "failure_scenarios.json"
_README_PATH = _FIXTURE_ROOT / "README.md"
_INDEX_ARTIFACT_PATH = _REPOSITORY_ROOT / "tests" / "fixtures" / "qdrant" / "pump12.json"
_EXPECTED_FAILURE_SCENARIOS = {
    "missing_target",
    "missing_observation",
    "missing_procedure",
    "invalid_evidence_package",
    "provenance_write_failure",
}
_EXPECTED_FALLBACK_INTENTS = {
    "missing_target": "ask_operator_to_disambiguate",
    "missing_observation": "insufficient_evidence",
    "missing_procedure": "unsupported_lower_ranked",
    "invalid_evidence_package": "fail_closed",
    "provenance_write_failure": "block_no_recommendation",
}
_EXPECTED_PREREQUISITES = {
    "missing_target": "resolved_target_asset",
    "missing_observation": "observation_support",
    "missing_procedure": "procedural_citation",
    "invalid_evidence_package": "complete_evidence_package",
    "provenance_write_failure": "persisted_provenance_trace",
}
_EXPECTED_MUTATIONS = {
    "missing_target": {
        "path": "/candidate_actions/repaired/target",
        "operation": "replace",
        "expected_before": "ex:Pump_12",
        "value": None,
    },
    "missing_observation": {
        "path": "/observation",
        "operation": "remove",
        "expected_before": {
            "id": "ex:Observation_Pump12_2026-05-18T14:03:00Z",
            "observed_asset": "ex:Pump_12",
            "observed_at": "2026-05-18T14:03:00Z",
            "signal": "anomalous_sound",
            "description": "Anomalous sound detected at Pump_12 at 14:03 UTC.",
            "anomaly": "anomalous_sound",
        },
    },
    "missing_procedure": {
        "path": "/candidate_actions/repaired/evidence_refs/1",
        "operation": "remove",
        "expected_before": "ex:SOP_Chunk_7",
    },
    "invalid_evidence_package": {
        "path": "/expected_evidence_package/validation_report",
        "operation": "remove",
        "expected_before": "ex:ValidationReport_Pump12_001",
    },
    "provenance_write_failure": {
        "path": "/provenance_trace/write_result",
        "operation": "replace",
        "expected_before": "success",
        "value": "failure",
    },
}
_EXPECTED_STABLE_IDS = {
    "ex:PumpStation_12",
    "ex:Pump_12",
    "ex:Observation_Pump12_2026-05-18T14:03:00Z",
    "ex:Procedure_InspectInletCavitation_Pump12",
    "ex:EvidenceEdge_001",
    "ex:SOP_Chunk_7",
    "ex:CandidateAction_Pump12_Incomplete_001",
    "ex:CandidateAction_Pump12_Repaired_001",
    "ex:EvidencePackage_Pump12_001",
    "ex:ValidationReport_Pump12_001",
    "ex:ProvenanceTrace_Pump12_001",
}


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fixture_file:
        data = json.load(fixture_file)
    assert isinstance(data, dict)
    return data


def _scenario() -> dict[str, Any]:
    return _load_json(_SCENARIO_PATH)


def _failure_scenarios() -> dict[str, Any]:
    return _load_json(_FAILURE_SCENARIOS_PATH)


def _parse_utc(timestamp: str) -> datetime:
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    assert parsed.tzinfo == UTC
    return parsed


def _collect_ids(value: object) -> list[str]:
    ids: list[str] = []
    if isinstance(value, dict):
        maybe_id = value.get("id")
        if isinstance(maybe_id, str):
            ids.append(maybe_id)
        for nested in value.values():
            ids.extend(_collect_ids(nested))
    elif isinstance(value, list):
        for item in value:
            ids.extend(_collect_ids(item))
    return ids


def _json_pointer_parts(path: str) -> list[str]:
    assert path.startswith("/")
    return [
        part.replace("~1", "/").replace("~0", "~") for part in path.removeprefix("/").split("/")
    ]


def _resolve_json_pointer(document: object, path: str) -> object:
    current = document
    for part in _json_pointer_parts(path):
        if isinstance(current, dict):
            current = current[part]
        elif isinstance(current, list):
            current = current[int(part)]
        else:
            raise TypeError(f"Cannot traverse through {type(current).__name__} at {path}")
    return current


def _apply_single_mutation(document: dict[str, Any], mutation: dict[str, Any]) -> dict[str, Any]:
    mutated = deepcopy(document)
    parts = _json_pointer_parts(mutation["path"])
    parent: object = mutated
    for part in parts[:-1]:
        if isinstance(parent, dict):
            parent = parent[part]
        elif isinstance(parent, list):
            parent = parent[int(part)]
        else:
            raise TypeError(f"Cannot traverse through {type(parent).__name__}")

    final_part = parts[-1]
    operation = mutation["operation"]
    if operation == "remove":
        if isinstance(parent, dict):
            del parent[final_part]
        elif isinstance(parent, list):
            del parent[int(final_part)]
        else:
            raise TypeError(f"Cannot remove from {type(parent).__name__}")
    elif operation == "replace":
        if isinstance(parent, dict):
            parent[final_part] = mutation["value"]
        elif isinstance(parent, list):
            parent[int(final_part)] = mutation["value"]
        else:
            raise TypeError(f"Cannot replace in {type(parent).__name__}")
    else:
        raise AssertionError(f"Unsupported mutation operation: {operation}")
    return mutated


def test_pump_12_fixture_files_and_documentation_exist() -> None:
    assert _SCENARIO_PATH.is_file()
    assert _FAILURE_SCENARIOS_PATH.is_file()
    assert _README_PATH.is_file()

    readme = _README_PATH.read_text(encoding="utf-8")
    for required_phrase in (
        "## Stable IDs",
        "valid/repair flow",
        "failure variants",
        "fixture JSON is test data",
        "JSON-Pointer-like fixture operations tested against the canonical scenario",
        "not final public CandidateAction/RDF/terminal-state API",
        "missing_target -> ask_operator_to_disambiguate",
        "missing_observation -> insufficient_evidence",
        "missing_procedure -> unsupported_lower_ranked",
        "invalid_evidence_package -> fail_closed",
        "provenance_write_failure -> block_no_recommendation",
    ):
        assert required_phrase in readme


def test_pump_12_fixture_uses_stable_canonical_ids_once_per_entity() -> None:
    scenario = _scenario()
    all_ids = _collect_ids(scenario)

    assert set(all_ids) >= _EXPECTED_STABLE_IDS
    assert len(all_ids) == len(set(all_ids))
    assert scenario["pump_station"]["id"] == "ex:PumpStation_12"
    assert scenario["asset"]["id"] == "ex:Pump_12"
    assert scenario["kg_evidence"]["id"] == "ex:EvidenceEdge_001"
    assert scenario["document_evidence"]["id"] == "ex:SOP_Chunk_7"


def test_pump_12_fixture_references_only_known_ids() -> None:
    scenario = _scenario()
    known_ids = set(_collect_ids(scenario))

    assert scenario["asset"]["located_at"] in known_ids
    assert scenario["observation"]["observed_asset"] in known_ids
    assert scenario["procedure"]["applicable_asset"] in known_ids
    assert scenario["procedure"]["requires_observation"] in known_ids
    assert scenario["kg_evidence"]["subject"] in known_ids
    assert scenario["kg_evidence"]["object"] in known_ids
    assert scenario["document_evidence"]["related_procedure"] in known_ids

    repaired_candidate = scenario["candidate_actions"]["repaired"]
    assert repaired_candidate["target"] in known_ids
    assert repaired_candidate["repair_of"] in known_ids
    assert set(repaired_candidate["evidence_refs"]) <= known_ids
    assert "kg_evidence_ref" not in repaired_candidate
    assert "document_evidence_ref" not in repaired_candidate

    evidence_package = scenario["expected_evidence_package"]
    assert evidence_package["candidate_action"] in known_ids
    assert set(evidence_package["evidence_refs"]) <= known_ids
    assert evidence_package["validation_report"] in known_ids
    assert evidence_package["provenance_trace"] in known_ids

    validation_report = scenario["validation_report"]
    assert validation_report["candidate_action"] in known_ids

    provenance_trace = scenario["provenance_trace"]
    assert provenance_trace["candidate_action"] in known_ids
    assert provenance_trace["evidence_package"] in known_ids


def test_pump_12_fixture_anomaly_window_is_explicit_consistent_utc() -> None:
    scenario = _scenario()
    anomaly_window = scenario["anomaly_window"]
    started_at = _parse_utc(anomaly_window["started_at"])
    ended_at = _parse_utc(anomaly_window["ended_at"])
    observed_at = _parse_utc(scenario["observation"]["observed_at"])
    validated_at = _parse_utc(scenario["validation_report"]["validated_at"])
    generated_at = _parse_utc(scenario["expected_evidence_package"]["generated_at"])
    recorded_at = _parse_utc(scenario["provenance_trace"]["recorded_at"])

    assert anomaly_window == {
        "started_at": "2026-05-18T14:00:00Z",
        "ended_at": "2026-05-18T14:10:00Z",
        "timezone": "UTC",
    }
    assert scenario["observation"]["observed_at"] == "2026-05-18T14:03:00Z"
    assert started_at < observed_at < ended_at
    assert ended_at < validated_at <= generated_at <= recorded_at


def test_pump_12_fixture_matches_frozen_architecture_v1_paper_example() -> None:
    scenario = _scenario()

    assert scenario["observation"] == {
        "id": "ex:Observation_Pump12_2026-05-18T14:03:00Z",
        "observed_asset": "ex:Pump_12",
        "observed_at": "2026-05-18T14:03:00Z",
        "signal": "anomalous_sound",
        "description": "Anomalous sound detected at Pump_12 at 14:03 UTC.",
        "anomaly": "anomalous_sound",
    }
    assert scenario["candidate_actions"]["repaired"]["label"] == (
        "Inspect the pump inlet of Pump_12 for cavitation"
    )
    assert "inlet" in scenario["document_evidence"]["text"]
    assert "cavitation" in scenario["document_evidence"]["text"]


def test_pump_12_document_evidence_matches_generated_index_artifact_exactly() -> None:
    scenario_evidence = _scenario()["document_evidence"]
    artifact = _load_json(_INDEX_ARTIFACT_PATH)
    payload = artifact["points"][0]["payload"]

    assert scenario_evidence == {
        "id": payload["evidence_id"],
        "type": "document_chunk",
        "document": payload["document"],
        "chunk_index": payload["chunk_index"],
        "related_procedure": payload["related_procedure"],
        "text": payload["text"],
        "source_path": payload["source_path"],
        "start_line": payload["start_line"],
        "end_line": payload["end_line"],
        "source_sha256": payload["source_sha256"],
        "index_contract_version": payload["index_contract_version"],
        "retrieved_at": "2026-05-18T14:04:05Z",
    }


def test_pump_12_fixture_models_incomplete_then_repaired_candidate() -> None:
    scenario = _scenario()
    incomplete_candidate = scenario["candidate_actions"]["incomplete"]
    repaired_candidate = scenario["candidate_actions"]["repaired"]
    known_ids = set(_collect_ids(scenario))

    assert incomplete_candidate["target"] is None
    assert incomplete_candidate["evidence_refs"] == []
    assert incomplete_candidate["known_gaps"] == ["target", "evidence_refs"]

    assert repaired_candidate["target"] == "ex:Pump_12"
    assert repaired_candidate["target"] in known_ids
    assert repaired_candidate["repair_of"] == incomplete_candidate["id"]
    assert set(repaired_candidate["evidence_refs"]) == {"ex:EvidenceEdge_001", "ex:SOP_Chunk_7"}
    assert repaired_candidate["evidence_refs"] == ["ex:EvidenceEdge_001", "ex:SOP_Chunk_7"]
    assert "kg_evidence_ref" not in repaired_candidate
    assert "document_evidence_ref" not in repaired_candidate


def test_pump_12_evidence_package_links_release_artifacts() -> None:
    scenario = _scenario()
    evidence_package = scenario["expected_evidence_package"]

    assert evidence_package["candidate_action"] == "ex:CandidateAction_Pump12_Repaired_001"
    assert evidence_package["validation_report"] == "ex:ValidationReport_Pump12_001"
    assert evidence_package["provenance_trace"] == "ex:ProvenanceTrace_Pump12_001"
    assert set(evidence_package["evidence_refs"]) == {"ex:EvidenceEdge_001", "ex:SOP_Chunk_7"}
    assert scenario["validation_report"]["candidate_action"] == evidence_package["candidate_action"]
    assert scenario["provenance_trace"]["candidate_action"] == evidence_package["candidate_action"]
    assert scenario["provenance_trace"]["evidence_package"] == evidence_package["id"]
    assert scenario["provenance_trace"]["write_result"] == "success"


def test_pump_12_failure_scenarios_are_deterministic_architecture_v1_fallbacks() -> None:
    failure_scenarios = _failure_scenarios()
    scenarios = failure_scenarios["failure_scenarios"]

    assert set(scenarios) == _EXPECTED_FAILURE_SCENARIOS
    assert failure_scenarios["expected_fallback_intents"] == _EXPECTED_FALLBACK_INTENTS
    for name, scenario in scenarios.items():
        assert scenario["id"] == f"ex:Pump12Failure_{name}"
        assert scenario["mutation"] == _EXPECTED_MUTATIONS[name]
        assert scenario["prerequisite"] == _EXPECTED_PREREQUISITES[name]
        assert isinstance(scenario["prerequisite"], str)
        assert "prerequisites" not in scenario
        assert "changed_prerequisite" not in scenario
        assert "changed_prerequisites" not in scenario
        assert scenario["expected_fallback_intent"] == _EXPECTED_FALLBACK_INTENTS[name]
        assert scenario["expected_architecture_v1_deviation"] is False


def test_pump_12_failure_mutations_apply_to_canonical_scenario() -> None:
    canonical_scenario = _scenario()
    failure_scenarios = _failure_scenarios()["failure_scenarios"]

    for name, failure_scenario in failure_scenarios.items():
        mutation = failure_scenario["mutation"]
        assert (
            _resolve_json_pointer(canonical_scenario, mutation["path"])
            == mutation["expected_before"]
        )

        mutated = _apply_single_mutation(canonical_scenario, mutation)

        if name == "missing_target":
            assert mutated["candidate_actions"]["repaired"]["target"] is None
        elif name == "missing_observation":
            assert "observation" not in mutated
        elif name == "missing_procedure":
            assert canonical_scenario["candidate_actions"]["repaired"]["evidence_refs"] == [
                "ex:EvidenceEdge_001",
                "ex:SOP_Chunk_7",
            ]
            assert mutated["candidate_actions"]["repaired"]["evidence_refs"] == [
                "ex:EvidenceEdge_001"
            ]
            assert canonical_scenario["document_evidence"]["id"] == "ex:SOP_Chunk_7"
        elif name == "invalid_evidence_package":
            assert "validation_report" not in mutated["expected_evidence_package"]
        elif name == "provenance_write_failure":
            assert mutated["provenance_trace"]["write_result"] == "failure"
        else:
            raise AssertionError(f"Unexpected failure scenario: {name}")
