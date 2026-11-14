from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import pytest
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD

from mfg_agentgraph.candidate_action import CandidateAction, parse_candidate_actions
from mfg_agentgraph.entity_resolution import KnownAsset
from mfg_agentgraph.fixture_model_adapter import (
    FixtureModelVariant,
    generate_fixture_candidate_actions,
)
from mfg_agentgraph.procedural_retrieval import retrieve_procedural_support
from mfg_agentgraph.rdf_action_mapper import MFG
from mfg_agentgraph.shacl_validation import validate_recommended_action
from mfg_agentgraph.stage_instrumentation import TerminalStatus
from mfg_agentgraph.structured_retrieval import retrieve_structured_support

EX = Namespace("http://example.org/")
SOSA = Namespace("http://www.w3.org/ns/sosa/")
FIXTURE = Path(__file__).parent / "fixtures" / "pump_12" / "scenario.json"
ACTION_IRI = EX.CandidateAction_Pump12_Repaired_001
REPORT_IRI = EX.ValidationReport_Issue72_001
RUN_ID = "run-issue-72-rdf-assembly"
QUERY_ID = "query-issue-72-pump-12"


def _scenario() -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(FIXTURE.read_text(encoding="utf-8")))


def _uri(curie: str) -> URIRef:
    assert curie.startswith("ex:")
    return URIRef(str(EX) + curie.removeprefix("ex:"))


def _resource_iris(scenario: Mapping[str, Any]) -> dict[str, URIRef]:
    return {
        scenario["asset"]["id"]: _uri(scenario["asset"]["id"]),
        scenario["observation"]["id"]: _uri(scenario["observation"]["id"]),
        scenario["procedure"]["id"]: _uri(scenario["procedure"]["id"]),
        scenario["kg_evidence"]["id"]: _uri(scenario["kg_evidence"]["id"]),
        scenario["document_evidence"]["id"]: _uri(scenario["document_evidence"]["id"]),
    }


def _canonical_inputs() -> tuple[
    Mapping[str, Any],
    CandidateAction,
    Any,
    Any,
    dict[str, URIRef],
]:
    scenario = _scenario()
    asset = KnownAsset("ex:Pump_12", "Pump 12", ("Pump_12",))
    structured = retrieve_structured_support(
        resolved_asset=asset,
        scenario=scenario,
        retrieval_run_id="run-issue-72-structured",
        query_id=QUERY_ID,
    )
    procedural = retrieve_procedural_support(
        resolved_asset=asset,
        scenario=scenario,
        retrieval_run_id="run-issue-72-procedural",
        query_id=QUERY_ID,
    )
    generation = generate_fixture_candidate_actions(
        scenario=scenario,
        structured_result=structured,
        procedural_result=procedural,
        generation_run_id="run-issue-72-generation",
        query_id=QUERY_ID,
        variant=FixtureModelVariant.REPAIRED,
    )
    plan = parse_candidate_actions(
        generation.raw_json,
        known_assets={scenario["asset"]["id"]},
        evidence_catalog=generation.evidence_catalog,
    )
    return scenario, plan.ranked_actions[0], structured, procedural, _resource_iris(scenario)


def test_product_assembly_emits_complete_support_graph_that_conforms_with_real_shacl() -> None:
    from mfg_agentgraph.recommended_action_rdf_assembly import assemble_recommended_action_rdf

    scenario, action, structured, procedural, resource_iris = _canonical_inputs()

    assembled = assemble_recommended_action_rdf(
        action,
        action_iri=ACTION_IRI,
        resource_iris=resource_iris,
        anomaly_window_start=scenario["anomaly_window"]["started_at"],
        anomaly_window_end=scenario["anomaly_window"]["ended_at"],
        structured_result=structured,
        procedural_result=procedural,
    )

    result = validate_recommended_action(
        assembled.action_graph,
        action_uri=ACTION_IRI,
        support_graph=assembled.support_graph,
        report_uri=REPORT_IRI,
        run_id=RUN_ID,
    )

    assert result.conforms is True
    assert result.violations == ()
    target = resource_iris[scenario["asset"]["id"]]
    observation = resource_iris[scenario["observation"]["id"]]
    procedure = resource_iris[scenario["procedure"]["id"]]
    kg_evidence = resource_iris[scenario["kg_evidence"]["id"]]
    doc_evidence = resource_iris[scenario["document_evidence"]["id"]]
    assert (
        ACTION_IRI,
        MFG.anomalyWindowStart,
        Literal("2026-05-18T14:00:00Z", datatype=XSD.dateTime),
    ) in assembled.support_graph
    assert (
        ACTION_IRI,
        MFG.anomalyWindowEnd,
        Literal("2026-05-18T14:10:00Z", datatype=XSD.dateTime),
    ) in assembled.support_graph
    assert (target, RDF.type, MFG.Asset) in assembled.support_graph
    assert (target, MFG.assetType, MFG.CentrifugalPump) in assembled.support_graph
    assert (kg_evidence, RDF.type, MFG.SupportEvidence) in assembled.support_graph
    assert (kg_evidence, MFG.observation, observation) in assembled.support_graph
    assert (observation, RDF.type, SOSA.Observation) in assembled.support_graph
    assert (observation, SOSA.hasFeatureOfInterest, target) in assembled.support_graph
    assert (doc_evidence, RDF.type, MFG.SupportEvidence) in assembled.support_graph
    assert (doc_evidence, MFG.procedure, procedure) in assembled.support_graph
    assert (procedure, RDF.type, MFG.Procedure) in assembled.support_graph
    assert (procedure, MFG.applicableAssetType, MFG.CentrifugalPump) in assembled.support_graph


@pytest.mark.parametrize(
    ("field", "kwargs"),
    [
        ("action", {"action": object()}),
        ("action_iri", {"action_iri": "not-a-uri"}),
        ("resource_iris", {"resource_iris": "not-a-mapping"}),
        ("structured_result", {"structured_result": object()}),
        ("procedural_result", {"procedural_result": object()}),
    ],
)
def test_bad_input_types_fail_closed(field: str, kwargs: dict[str, object]) -> None:
    from mfg_agentgraph.recommended_action_rdf_assembly import (
        RecommendedActionRdfAssemblyError,
        RecommendedActionRdfAssemblyErrorCode,
        assemble_recommended_action_rdf,
    )

    scenario, action, structured, procedural, resource_iris = _canonical_inputs()
    params: dict[str, object] = {
        "action": action,
        "action_iri": ACTION_IRI,
        "resource_iris": resource_iris,
        "anomaly_window_start": scenario["anomaly_window"]["started_at"],
        "anomaly_window_end": scenario["anomaly_window"]["ended_at"],
        "structured_result": structured,
        "procedural_result": procedural,
    }
    params.update(kwargs)

    with pytest.raises(RecommendedActionRdfAssemblyError) as exc_info:
        assemble_recommended_action_rdf(**params)  # type: ignore[arg-type]

    assert exc_info.value.code is RecommendedActionRdfAssemblyErrorCode.INVALID_INPUT
    assert exc_info.value.field == field


@pytest.mark.parametrize(
    ("missing_id", "field"),
    [
        ("ex:Observation_Pump12_2026-05-18T14:03:00Z", "observation"),
        ("ex:Procedure_InspectInletCavitation_Pump12", "procedure"),
        ("ex:SOP_Chunk_7", "support_evidence"),
    ],
)
def test_missing_resource_mapping_fails_before_partial_graph(missing_id: str, field: str) -> None:
    from mfg_agentgraph.recommended_action_rdf_assembly import (
        RecommendedActionRdfAssemblyError,
        RecommendedActionRdfAssemblyErrorCode,
        assemble_recommended_action_rdf,
    )

    scenario, action, structured, procedural, resource_iris = _canonical_inputs()
    del resource_iris[missing_id]

    with pytest.raises(RecommendedActionRdfAssemblyError) as exc_info:
        assemble_recommended_action_rdf(
            action,
            action_iri=ACTION_IRI,
            resource_iris=resource_iris,
            anomaly_window_start=scenario["anomaly_window"]["started_at"],
            anomaly_window_end=scenario["anomaly_window"]["ended_at"],
            structured_result=structured,
            procedural_result=procedural,
        )

    assert exc_info.value.code is RecommendedActionRdfAssemblyErrorCode.UNKNOWN_RESOURCE_ID
    assert exc_info.value.field == field


def test_unsuccessful_retrieval_status_fails_closed() -> None:
    from mfg_agentgraph.recommended_action_rdf_assembly import (
        RecommendedActionRdfAssemblyError,
        RecommendedActionRdfAssemblyErrorCode,
        assemble_recommended_action_rdf,
    )

    scenario, action, _structured, procedural, resource_iris = _canonical_inputs()
    broken_scenario = dict(scenario)
    broken_scenario.pop("observation")
    failed_structured = retrieve_structured_support(
        resolved_asset=KnownAsset("ex:Pump_12", "Pump 12", ("Pump_12",)),
        scenario=broken_scenario,
        retrieval_run_id="run-issue-72-structured-failed",
        query_id=QUERY_ID,
    )
    assert failed_structured.status is TerminalStatus.INSUFFICIENT_EVIDENCE

    with pytest.raises(RecommendedActionRdfAssemblyError) as exc_info:
        assemble_recommended_action_rdf(
            action,
            action_iri=ACTION_IRI,
            resource_iris=resource_iris,
            anomaly_window_start=scenario["anomaly_window"]["started_at"],
            anomaly_window_end=scenario["anomaly_window"]["ended_at"],
            structured_result=failed_structured,
            procedural_result=procedural,
        )

    assert exc_info.value.code is RecommendedActionRdfAssemblyErrorCode.UNSUCCESSFUL_RETRIEVAL
    assert exc_info.value.field == "structured_result.status"


def test_unsuccessful_procedural_status_fails_closed() -> None:
    from mfg_agentgraph.recommended_action_rdf_assembly import (
        RecommendedActionRdfAssemblyError,
        RecommendedActionRdfAssemblyErrorCode,
        assemble_recommended_action_rdf,
    )

    scenario, action, structured, procedural, resource_iris = _canonical_inputs()
    object.__setattr__(procedural, "status", TerminalStatus.UNSUPPORTED_LOWER_RANK)

    with pytest.raises(RecommendedActionRdfAssemblyError) as exc_info:
        assemble_recommended_action_rdf(
            action,
            action_iri=ACTION_IRI,
            resource_iris=resource_iris,
            anomaly_window_start=scenario["anomaly_window"]["started_at"],
            anomaly_window_end=scenario["anomaly_window"]["ended_at"],
            structured_result=structured,
            procedural_result=procedural,
        )

    assert exc_info.value.code is RecommendedActionRdfAssemblyErrorCode.UNSUCCESSFUL_RETRIEVAL
    assert exc_info.value.field == "procedural_result.status"


@pytest.mark.parametrize(
    ("start", "end", "field"),
    [
        ("not-a-dateTime", "2026-05-18T14:10:00Z", "anomaly_window_start"),
        ("2026-05-18x14:00:00Z", "2026-05-18T14:10:00Z", "anomaly_window_start"),
        ("2026-W21-1T14:00:00Z", "2026-05-18T14:10:00Z", "anomaly_window_start"),
        ("2026-05-18T14:00:00Z", "not-a-dateTime", "anomaly_window_end"),
        ("2026-05-18T14:10:01Z", "2026-05-18T14:10:00Z", "anomaly_window"),
    ],
)
def test_malformed_or_reversed_anomaly_window_fails_closed(
    start: str, end: str, field: str
) -> None:
    from mfg_agentgraph.recommended_action_rdf_assembly import (
        RecommendedActionRdfAssemblyError,
        RecommendedActionRdfAssemblyErrorCode,
        assemble_recommended_action_rdf,
    )

    _scenario, action, structured, procedural, resource_iris = _canonical_inputs()

    with pytest.raises(RecommendedActionRdfAssemblyError) as exc_info:
        assemble_recommended_action_rdf(
            action,
            action_iri=ACTION_IRI,
            resource_iris=resource_iris,
            anomaly_window_start=start,
            anomaly_window_end=end,
            structured_result=structured,
            procedural_result=procedural,
        )

    assert exc_info.value.code is RecommendedActionRdfAssemblyErrorCode.INVALID_TIMESTAMP
    assert exc_info.value.field == field


def test_identity_mismatch_between_candidate_and_retrieval_fails_closed() -> None:
    from dataclasses import replace

    from mfg_agentgraph.recommended_action_rdf_assembly import (
        RecommendedActionRdfAssemblyError,
        RecommendedActionRdfAssemblyErrorCode,
        assemble_recommended_action_rdf,
    )

    scenario, action, structured, procedural, resource_iris = _canonical_inputs()
    mismatched_action = replace(action, target_asset="ex:OtherPump")

    with pytest.raises(RecommendedActionRdfAssemblyError) as exc_info:
        assemble_recommended_action_rdf(
            mismatched_action,
            action_iri=ACTION_IRI,
            resource_iris=resource_iris,
            anomaly_window_start=scenario["anomaly_window"]["started_at"],
            anomaly_window_end=scenario["anomaly_window"]["ended_at"],
            structured_result=structured,
            procedural_result=procedural,
        )

    assert exc_info.value.code is RecommendedActionRdfAssemblyErrorCode.IDENTITY_MISMATCH
    assert exc_info.value.field == "action.target_asset"


@pytest.mark.parametrize(
    ("mutation", "field"),
    [
        ("observation_asset", "structured_result.observations.observed_asset"),
        ("support_subject", "structured_result.support_records.subject"),
        ("support_predicate", "structured_result.support_records.predicate"),
    ],
)
def test_structured_identity_drift_fails_closed_with_sanitized_fields(
    mutation: str, field: str
) -> None:
    from dataclasses import replace

    from mfg_agentgraph.recommended_action_rdf_assembly import (
        RecommendedActionRdfAssemblyError,
        RecommendedActionRdfAssemblyErrorCode,
        assemble_recommended_action_rdf,
    )

    scenario, action, structured, procedural, resource_iris = _canonical_inputs()
    rejected_marker = "ISSUE72_REJECTED_ASSET_DO_NOT_RETAIN"
    if mutation == "observation_asset":
        observation = replace(structured.observations[0], observed_asset=rejected_marker)
        structured = replace(structured, observations=(observation,))
    elif mutation == "support_subject":
        support = replace(structured.support_records[0], subject=rejected_marker)
        structured = replace(structured, support_records=(support,))
    else:
        support = replace(structured.support_records[0], predicate="ex:unsupportedPredicate")
        structured = replace(structured, support_records=(support,))

    with pytest.raises(RecommendedActionRdfAssemblyError) as exc_info:
        assemble_recommended_action_rdf(
            action,
            action_iri=ACTION_IRI,
            resource_iris=resource_iris,
            anomaly_window_start=scenario["anomaly_window"]["started_at"],
            anomaly_window_end=scenario["anomaly_window"]["ended_at"],
            structured_result=structured,
            procedural_result=procedural,
        )

    assert exc_info.value.code is RecommendedActionRdfAssemblyErrorCode.IDENTITY_MISMATCH
    assert exc_info.value.field == field
    error_text = repr(exc_info.value) + repr(exc_info.value.args) + repr(vars(exc_info.value))
    assert rejected_marker not in error_text


def test_semantic_observation_outside_window_is_left_to_real_shacl() -> None:
    from dataclasses import replace

    from mfg_agentgraph.recommended_action_rdf_assembly import assemble_recommended_action_rdf

    scenario, action, structured, procedural, resource_iris = _canonical_inputs()
    late_observation = replace(structured.observations[0], observed_at="2026-05-18T14:11:00Z")
    late_structured = replace(structured, observations=(late_observation,))

    assembled = assemble_recommended_action_rdf(
        action,
        action_iri=ACTION_IRI,
        resource_iris=resource_iris,
        anomaly_window_start=scenario["anomaly_window"]["started_at"],
        anomaly_window_end=scenario["anomaly_window"]["ended_at"],
        structured_result=late_structured,
        procedural_result=procedural,
    )
    result = validate_recommended_action(
        assembled.action_graph,
        action_uri=ACTION_IRI,
        support_graph=assembled.support_graph,
        report_uri=REPORT_IRI,
        run_id=RUN_ID,
    )

    assert result.conforms is False
    assert tuple(violation.shape_id for violation in result.violations) == (
        str(MFG.ObservationWithinAnomalyWindowShape),
    )


def test_errors_do_not_retain_rejected_marker() -> None:
    from mfg_agentgraph.recommended_action_rdf_assembly import (
        RecommendedActionRdfAssemblyError,
        assemble_recommended_action_rdf,
    )

    marker = "ISSUE72_SECRET_RESOURCE_DO_NOT_RETAIN"
    scenario, action, structured, procedural, resource_iris = _canonical_inputs()
    resource_iris[marker] = URIRef(f"http://example.org/{marker}")
    resource_iris["ex:SOP_Chunk_7"] = cast(URIRef, marker)

    with pytest.raises(RecommendedActionRdfAssemblyError) as exc_info:
        assemble_recommended_action_rdf(
            action,
            action_iri=ACTION_IRI,
            resource_iris=resource_iris,
            anomaly_window_start=scenario["anomaly_window"]["started_at"],
            anomaly_window_end=scenario["anomaly_window"]["ended_at"],
            structured_result=structured,
            procedural_result=procedural,
        )

    error_text = repr(exc_info.value) + repr(exc_info.value.args) + repr(vars(exc_info.value))
    assert marker not in error_text
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


def test_stateful_resource_mapping_drift_uses_initial_snapshot_without_marker_leakage() -> None:
    from mfg_agentgraph.recommended_action_rdf_assembly import assemble_recommended_action_rdf

    class DriftingResourceIris(Mapping[str, URIRef]):
        def __init__(self, stable: Mapping[str, URIRef], marker: str) -> None:
            self._stable = stable
            self._marker = marker

        def __getitem__(self, key: str) -> URIRef:
            return self._stable[key]

        def __iter__(self):  # type: ignore[no-untyped-def]
            return iter(self._stable)

        def __len__(self) -> int:
            return len(self._stable)

        def items(self):  # type: ignore[no-untyped-def]
            return self._stable.items()

        def get(self, key: str, default: object = None) -> object:  # type: ignore[override]
            if key in self._stable:
                return self._marker
            return default

    marker = "ISSUE72_RESOURCE_GET_DRIFT_DO_NOT_LEAK"
    scenario, action, structured, procedural, resource_iris = _canonical_inputs()

    assembled = assemble_recommended_action_rdf(
        action,
        action_iri=ACTION_IRI,
        resource_iris=DriftingResourceIris(resource_iris, marker),
        anomaly_window_start=scenario["anomaly_window"]["started_at"],
        anomaly_window_end=scenario["anomaly_window"]["ended_at"],
        structured_result=structured,
        procedural_result=procedural,
    )

    error_text = assembled.action_graph.serialize() + assembled.support_graph.serialize()
    assert marker not in error_text
    assert (
        ACTION_IRI,
        MFG.targetAsset,
        resource_iris[scenario["asset"]["id"]],
    ) in assembled.action_graph


@pytest.mark.parametrize(
    ("mutation", "field"),
    [
        ("empty_observations", "structured_result.observations"),
        ("malformed_observations", "structured_result.observations"),
        ("empty_structured_support", "structured_result.support_records"),
        ("malformed_structured_support", "structured_result.support_records"),
        ("empty_procedural_support", "procedural_result.support_records"),
        ("malformed_procedural_support", "procedural_result.support_records"),
    ],
)
def test_tampered_passed_results_exact_cardinality_and_nested_types_fail_closed(
    mutation: str, field: str
) -> None:
    from mfg_agentgraph.recommended_action_rdf_assembly import (
        RecommendedActionRdfAssemblyError,
        RecommendedActionRdfAssemblyErrorCode,
        assemble_recommended_action_rdf,
    )

    scenario, action, structured, procedural, resource_iris = _canonical_inputs()
    if mutation == "empty_observations":
        object.__setattr__(structured, "observations", ())
    elif mutation == "malformed_observations":
        object.__setattr__(structured, "observations", (object(),))
    elif mutation == "empty_structured_support":
        object.__setattr__(structured, "support_records", ())
    elif mutation == "malformed_structured_support":
        object.__setattr__(structured, "support_records", (object(),))
    elif mutation == "empty_procedural_support":
        object.__setattr__(procedural, "support_records", ())
    else:
        object.__setattr__(procedural, "support_records", (object(),))

    with pytest.raises(RecommendedActionRdfAssemblyError) as exc_info:
        assemble_recommended_action_rdf(
            action,
            action_iri=ACTION_IRI,
            resource_iris=resource_iris,
            anomaly_window_start=scenario["anomaly_window"]["started_at"],
            anomaly_window_end=scenario["anomaly_window"]["ended_at"],
            structured_result=structured,
            procedural_result=procedural,
        )

    assert exc_info.value.code is RecommendedActionRdfAssemblyErrorCode.INVALID_INPUT
    assert exc_info.value.field == field
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


def test_procedural_applicable_asset_id_drift_fails_closed_before_shacl() -> None:
    from dataclasses import replace

    from mfg_agentgraph.recommended_action_rdf_assembly import (
        RecommendedActionRdfAssemblyError,
        RecommendedActionRdfAssemblyErrorCode,
        assemble_recommended_action_rdf,
    )

    scenario, action, structured, procedural, resource_iris = _canonical_inputs()
    support = replace(procedural.support_records[0], applicable_asset_id="ex:OtherPump")
    object.__setattr__(procedural, "support_records", (support,))

    with pytest.raises(RecommendedActionRdfAssemblyError) as exc_info:
        assemble_recommended_action_rdf(
            action,
            action_iri=ACTION_IRI,
            resource_iris=resource_iris,
            anomaly_window_start=scenario["anomaly_window"]["started_at"],
            anomaly_window_end=scenario["anomaly_window"]["ended_at"],
            structured_result=structured,
            procedural_result=procedural,
        )

    assert exc_info.value.code is RecommendedActionRdfAssemblyErrorCode.IDENTITY_MISMATCH
    assert exc_info.value.field == "procedural_result.support_records.applicable_asset_id"


def test_unknown_procedural_asset_type_fails_closed() -> None:
    from dataclasses import replace

    from mfg_agentgraph.recommended_action_rdf_assembly import (
        RecommendedActionRdfAssemblyError,
        RecommendedActionRdfAssemblyErrorCode,
        assemble_recommended_action_rdf,
    )

    scenario, action, structured, procedural, resource_iris = _canonical_inputs()
    unsupported = replace(procedural.support_records[0], applicable_asset_type="rotary_pump")
    object.__setattr__(procedural, "support_records", (unsupported,))

    with pytest.raises(RecommendedActionRdfAssemblyError) as exc_info:
        assemble_recommended_action_rdf(
            action,
            action_iri=ACTION_IRI,
            resource_iris=resource_iris,
            anomaly_window_start=scenario["anomaly_window"]["started_at"],
            anomaly_window_end=scenario["anomaly_window"]["ended_at"],
            structured_result=structured,
            procedural_result=procedural,
        )

    assert exc_info.value.code is RecommendedActionRdfAssemblyErrorCode.UNKNOWN_RESOURCE_ID
    assert exc_info.value.field == "procedural_result.support_records.applicable_asset_type"


@pytest.mark.parametrize(
    ("mutation", "field"),
    [
        ("duplicate_cardinality", "action.support_evidence"),
        ("malformed_reference", "action.support_evidence"),
        ("wrong_kg_kind", "action.support_evidence.kind"),
        ("wrong_doc_status", "action.support_evidence.validation_status"),
        ("swapped_kinds", "action.support_evidence.kind"),
    ],
)
def test_candidate_support_evidence_cardinality_ids_kinds_and_status_fail_closed(
    mutation: str, field: str
) -> None:
    from mfg_agentgraph.evidence_reference import EvidenceKind, EvidenceValidationStatus
    from mfg_agentgraph.recommended_action_rdf_assembly import (
        RecommendedActionRdfAssemblyError,
        RecommendedActionRdfAssemblyErrorCode,
        assemble_recommended_action_rdf,
    )

    scenario, action, structured, procedural, resource_iris = _canonical_inputs()
    kg_reference, doc_reference = action.support_evidence
    if mutation == "duplicate_cardinality":
        tampered_support: tuple[object, ...] = (kg_reference, kg_reference)
    elif mutation == "malformed_reference":
        tampered_support = (kg_reference, object())
    elif mutation == "wrong_kg_kind":
        object.__setattr__(kg_reference, "kind", EvidenceKind.KG_RESOURCE)
        tampered_support = (kg_reference, doc_reference)
    elif mutation == "wrong_doc_status":
        object.__setattr__(doc_reference, "validation_status", EvidenceValidationStatus.INVALID)
        tampered_support = (kg_reference, doc_reference)
    else:
        object.__setattr__(kg_reference, "kind", EvidenceKind.DOCUMENT_CHUNK)
        object.__setattr__(doc_reference, "kind", EvidenceKind.KG_EDGE)
        tampered_support = (kg_reference, doc_reference)
    object.__setattr__(action, "support_evidence", tampered_support)

    with pytest.raises(RecommendedActionRdfAssemblyError) as exc_info:
        assemble_recommended_action_rdf(
            action,
            action_iri=ACTION_IRI,
            resource_iris=resource_iris,
            anomaly_window_start=scenario["anomaly_window"]["started_at"],
            anomaly_window_end=scenario["anomaly_window"]["ended_at"],
            structured_result=structured,
            procedural_result=procedural,
        )

    assert exc_info.value.code is RecommendedActionRdfAssemblyErrorCode.IDENTITY_MISMATCH
    assert exc_info.value.field == field
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


@pytest.mark.parametrize(("field", "value"), [("rank", object()), ("action", object())])
def test_tampered_candidate_action_scalars_fail_closed(field: str, value: object) -> None:
    from mfg_agentgraph.recommended_action_rdf_assembly import (
        RecommendedActionRdfAssemblyError,
        RecommendedActionRdfAssemblyErrorCode,
        assemble_recommended_action_rdf,
    )

    scenario, action, structured, procedural, resource_iris = _canonical_inputs()
    object.__setattr__(action, field, value)

    with pytest.raises(RecommendedActionRdfAssemblyError) as exc_info:
        assemble_recommended_action_rdf(
            action,
            action_iri=ACTION_IRI,
            resource_iris=resource_iris,
            anomaly_window_start=scenario["anomaly_window"]["started_at"],
            anomaly_window_end=scenario["anomaly_window"]["ended_at"],
            structured_result=structured,
            procedural_result=procedural,
        )

    assert exc_info.value.code is RecommendedActionRdfAssemblyErrorCode.INVALID_INPUT
    assert exc_info.value.field == f"action.{field}"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


def test_hostile_resource_mapping_snapshot_failure_is_sanitized() -> None:
    from mfg_agentgraph.recommended_action_rdf_assembly import (
        RecommendedActionRdfAssemblyError,
        RecommendedActionRdfAssemblyErrorCode,
        assemble_recommended_action_rdf,
    )

    class HostileResourceIris(Mapping[str, URIRef]):
        def __getitem__(self, key: str) -> URIRef:
            raise KeyError(key)

        def __iter__(self):  # type: ignore[no-untyped-def]
            return iter(())

        def __len__(self) -> int:
            return 1

        def items(self):  # type: ignore[no-untyped-def]
            raise RuntimeError("ISSUE72_HOSTILE_MAPPING_MARKER")

    scenario, action, structured, procedural, _resource_iris = _canonical_inputs()

    with pytest.raises(RecommendedActionRdfAssemblyError) as exc_info:
        assemble_recommended_action_rdf(
            action,
            action_iri=ACTION_IRI,
            resource_iris=HostileResourceIris(),
            anomaly_window_start=scenario["anomaly_window"]["started_at"],
            anomaly_window_end=scenario["anomaly_window"]["ended_at"],
            structured_result=structured,
            procedural_result=procedural,
        )

    assert exc_info.value.code is RecommendedActionRdfAssemblyErrorCode.INVALID_INPUT
    assert exc_info.value.field == "resource_iris"
    assert "ISSUE72_HOSTILE_MAPPING_MARKER" not in repr(exc_info.value)
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


@pytest.mark.parametrize(
    ("mutation", "field"),
    [
        ("structured_asset", "structured_result.asset"),
        ("procedural_asset", "procedural_result.asset"),
        ("observation_timestamp", "structured_result.observations"),
        ("support_stable_id", "action.support_evidence"),
    ],
)
def test_deeply_tampered_nested_values_fail_closed_without_marker_leakage(
    mutation: str, field: str
) -> None:
    from mfg_agentgraph.recommended_action_rdf_assembly import (
        RecommendedActionRdfAssemblyError,
        RecommendedActionRdfAssemblyErrorCode,
        assemble_recommended_action_rdf,
    )

    marker = "ISSUE72_NESTED_TAMPER_MARKER"
    scenario, action, structured, procedural, resource_iris = _canonical_inputs()
    if mutation == "structured_asset":
        object.__setattr__(structured, "asset", object())
    elif mutation == "procedural_asset":
        object.__setattr__(procedural, "asset", object())
    elif mutation == "observation_timestamp":
        object.__setattr__(structured.observations[0], "observed_at", object())
    else:
        object.__setattr__(action.support_evidence[0], "stable_id", [marker])

    with pytest.raises(RecommendedActionRdfAssemblyError) as exc_info:
        assemble_recommended_action_rdf(
            action,
            action_iri=ACTION_IRI,
            resource_iris=resource_iris,
            anomaly_window_start=scenario["anomaly_window"]["started_at"],
            anomaly_window_end=scenario["anomaly_window"]["ended_at"],
            structured_result=structured,
            procedural_result=procedural,
        )

    assert exc_info.value.code is RecommendedActionRdfAssemblyErrorCode.INVALID_INPUT
    assert exc_info.value.field == field
    error_surface = repr(exc_info.value) + repr(exc_info.value.args) + repr(vars(exc_info.value))
    assert marker not in error_surface
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


def test_assembly_result_container_is_frozen_while_rdflib_graphs_are_mutable_snapshots() -> None:
    from dataclasses import FrozenInstanceError

    from mfg_agentgraph.recommended_action_rdf_assembly import assemble_recommended_action_rdf

    scenario, action, structured, procedural, resource_iris = _canonical_inputs()

    assembled = assemble_recommended_action_rdf(
        action,
        action_iri=ACTION_IRI,
        resource_iris=dict(resource_iris),
        anomaly_window_start=scenario["anomaly_window"]["started_at"],
        anomaly_window_end=scenario["anomaly_window"]["ended_at"],
        structured_result=structured,
        procedural_result=procedural,
    )
    resource_iris.clear()

    assert isinstance(assembled.action_graph, Graph)
    assert (ACTION_IRI, RDF.type, MFG.RecommendedAction) in assembled.action_graph
    assembled.support_graph.add((ACTION_IRI, MFG.testMutation, Literal("graph remains mutable")))
    assert (
        ACTION_IRI,
        MFG.testMutation,
        Literal("graph remains mutable"),
    ) in assembled.support_graph
    with pytest.raises(FrozenInstanceError):
        assembled.action_uri = EX.OtherAction  # type: ignore[misc]
