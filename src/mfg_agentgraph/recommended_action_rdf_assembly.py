"""Assemble recommended-action RDF and its SHACL support graph.

This is the narrow Issue #72 seam between the candidate-action RDF mapper and the
package SHACL gate. It does not retrieve, generate, repair, or validate with
SHACL. It only turns already validated stage outputs plus caller-owned stable IRIs
into the two RDF graphs expected by ``validate_recommended_action``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Any, TypeVar, cast

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD

from mfg_agentgraph.candidate_action import CandidateAction
from mfg_agentgraph.entity_resolution import KnownAsset
from mfg_agentgraph.evidence_reference import (
    EvidenceKind,
    EvidenceReference,
    EvidenceValidationStatus,
)
from mfg_agentgraph.procedural_retrieval import ProceduralRetrievalResult, ProceduralSupportRecord
from mfg_agentgraph.rdf_action_mapper import MFG, RdfActionMappingError, map_candidate_action_to_rdf
from mfg_agentgraph.stage_instrumentation import TerminalStatus
from mfg_agentgraph.structured_retrieval import (
    StructuredObservation,
    StructuredRetrievalResult,
    StructuredSupportRecord,
)

SOSA = Namespace("http://www.w3.org/ns/sosa/")
_EXPECTED_KG_PREDICATE = "ex:hasRecommendedProcedure"
_XSD_DATETIME_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d"
    r"(?:\.\d+)?(?:Z|[+-](?:(?:0\d|1[0-3]):[0-5]\d|14:00))"
)
_T = TypeVar("_T")


class RecommendedActionRdfAssemblyErrorCode(StrEnum):
    """Stable machine-readable RDF assembly failure codes."""

    INVALID_INPUT = "invalid_input"
    UNSUCCESSFUL_RETRIEVAL = "unsuccessful_retrieval"
    IDENTITY_MISMATCH = "identity_mismatch"
    UNKNOWN_RESOURCE_ID = "unknown_resource_id"
    INVALID_TIMESTAMP = "invalid_timestamp"


class RecommendedActionRdfAssemblyError(ValueError):
    """Deterministic assembly error without retaining rejected objects or IDs."""

    __slots__ = ("code", "field")

    def __init__(self, code: RecommendedActionRdfAssemblyErrorCode, field: str) -> None:
        if not isinstance(code, RecommendedActionRdfAssemblyErrorCode):
            raise TypeError("code must be a RecommendedActionRdfAssemblyErrorCode")
        self.code = code
        self.field = field
        super().__init__(f"{code.value}: {field}")


@dataclass(frozen=True, slots=True)
class RecommendedActionRdfGraphs:
    """Frozen container for new RDFLib graph snapshots assembled for the SHACL gate."""

    action_uri: URIRef
    action_graph: Graph
    support_graph: Graph

    def __post_init__(self) -> None:
        if not isinstance(self.action_uri, URIRef):
            raise TypeError("action_uri must be a URIRef")
        if not isinstance(self.action_graph, Graph):
            raise TypeError("action_graph must be a Graph")
        if not isinstance(self.support_graph, Graph):
            raise TypeError("support_graph must be a Graph")


def assemble_recommended_action_rdf(
    action: CandidateAction,
    *,
    action_iri: URIRef,
    resource_iris: Mapping[str, URIRef],
    anomaly_window_start: str,
    anomaly_window_end: str,
    structured_result: StructuredRetrievalResult,
    procedural_result: ProceduralRetrievalResult,
) -> RecommendedActionRdfGraphs:
    """Assemble action RDF plus complete support RDF for one recommendation.

    The caller owns stable resource IDs/IRIs and the explicit anomaly window. The
    retrieval results must already be successful immutable product results. SHACL
    remains responsible for semantic constraints such as observation-in-window.
    """

    resource_iris_snapshot = _validate_input_types(
        action,
        action_iri,
        resource_iris,
        anomaly_window_start,
        anomaly_window_end,
        structured_result,
        procedural_result,
    )
    window_start = _parse_datetime(anomaly_window_start, "anomaly_window_start")
    window_end = _parse_datetime(anomaly_window_end, "anomaly_window_end")
    if window_start > window_end:
        raise RecommendedActionRdfAssemblyError(
            RecommendedActionRdfAssemblyErrorCode.INVALID_TIMESTAMP, "anomaly_window"
        )
    if structured_result.status is not TerminalStatus.PASSED:
        raise RecommendedActionRdfAssemblyError(
            RecommendedActionRdfAssemblyErrorCode.UNSUCCESSFUL_RETRIEVAL,
            "structured_result.status",
        )
    if procedural_result.status is not TerminalStatus.PASSED:
        raise RecommendedActionRdfAssemblyError(
            RecommendedActionRdfAssemblyErrorCode.UNSUCCESSFUL_RETRIEVAL,
            "procedural_result.status",
        )

    structured_observation = _expect_exactly_one(
        structured_result.observations,
        StructuredObservation,
        "structured_result.observations",
    )
    structured_support = _expect_exactly_one(
        structured_result.support_records,
        StructuredSupportRecord,
        "structured_result.support_records",
    )
    procedural_support = _expect_exactly_one(
        procedural_result.support_records,
        ProceduralSupportRecord,
        "procedural_result.support_records",
    )
    _revalidate_record(
        structured_observation,
        StructuredObservation,
        "structured_result.observations",
    )
    _revalidate_record(
        structured_support,
        StructuredSupportRecord,
        "structured_result.support_records",
    )
    _revalidate_record(
        procedural_support,
        ProceduralSupportRecord,
        "procedural_result.support_records",
    )
    _validate_identity(action, structured_result, procedural_result)
    if structured_support.required_observation_id != structured_observation.observation_id:
        raise RecommendedActionRdfAssemblyError(
            RecommendedActionRdfAssemblyErrorCode.IDENTITY_MISMATCH,
            "structured_result.support_records",
        )
    if structured_support.procedure_id != procedural_support.related_procedure:
        raise RecommendedActionRdfAssemblyError(
            RecommendedActionRdfAssemblyErrorCode.IDENTITY_MISMATCH,
            "procedure",
        )
    _validate_action_support_evidence(action, structured_support, procedural_support)

    target_iri = _resolve_resource(resource_iris_snapshot, action.target_asset, "target_asset")
    observation_iri = _resolve_resource(
        resource_iris_snapshot, structured_observation.observation_id, "observation"
    )
    procedure_iri = _resolve_resource(
        resource_iris_snapshot, structured_support.procedure_id, "procedure"
    )
    kg_evidence_iri = _resolve_resource(
        resource_iris_snapshot, structured_support.evidence_id, "support_evidence"
    )
    doc_evidence_iri = _resolve_resource(
        resource_iris_snapshot, procedural_support.evidence_id, "support_evidence"
    )
    asset_type_iri = _asset_type_iri(procedural_support.applicable_asset_type)
    observation_time = _parse_datetime(
        structured_observation.observed_at, "observation.observed_at"
    )

    try:
        action_graph = map_candidate_action_to_rdf(
            action,
            action_iri=action_iri,
            resource_iris=resource_iris_snapshot,
        )
    except RdfActionMappingError as exc:
        raise _map_action_mapping_error(exc) from None
    support_graph = Graph()
    support_graph.bind("mfg", MFG)
    support_graph.bind("sosa", SOSA)

    support_graph.add(
        (action_iri, MFG.anomalyWindowStart, _date_time_literal(anomaly_window_start))
    )
    support_graph.add((action_iri, MFG.anomalyWindowEnd, _date_time_literal(anomaly_window_end)))
    support_graph.add((target_iri, RDF.type, MFG.Asset))
    support_graph.add((target_iri, MFG.assetType, asset_type_iri))
    support_graph.add((kg_evidence_iri, RDF.type, MFG.SupportEvidence))
    support_graph.add((kg_evidence_iri, MFG.observation, observation_iri))
    support_graph.add((observation_iri, RDF.type, SOSA.Observation))
    support_graph.add((observation_iri, SOSA.hasFeatureOfInterest, target_iri))
    support_graph.add(
        (observation_iri, SOSA.resultTime, _date_time_literal(structured_observation.observed_at))
    )
    support_graph.add((doc_evidence_iri, RDF.type, MFG.SupportEvidence))
    support_graph.add((doc_evidence_iri, MFG.procedure, procedure_iri))
    support_graph.add((procedure_iri, RDF.type, MFG.Procedure))
    support_graph.add((procedure_iri, MFG.applicableAssetType, asset_type_iri))

    # Keep the parsed value live until graph construction to make the timestamp
    # validation boundary explicit without changing caller-provided lexical forms.
    assert observation_time is not None
    return RecommendedActionRdfGraphs(
        action_uri=action_iri,
        action_graph=action_graph,
        support_graph=support_graph,
    )


def _validate_input_types(
    action: object,
    action_iri: object,
    resource_iris: object,
    anomaly_window_start: object,
    anomaly_window_end: object,
    structured_result: object,
    procedural_result: object,
) -> dict[str, URIRef]:
    if type(action) is not CandidateAction:
        raise RecommendedActionRdfAssemblyError(
            RecommendedActionRdfAssemblyErrorCode.INVALID_INPUT, "action"
        )
    if type(action.rank) is not int or action.rank < 1:
        raise RecommendedActionRdfAssemblyError(
            RecommendedActionRdfAssemblyErrorCode.INVALID_INPUT, "action.rank"
        )
    if (
        not isinstance(action.action, str)
        or not action.action.strip()
        or action.action != action.action.strip()
    ):
        raise RecommendedActionRdfAssemblyError(
            RecommendedActionRdfAssemblyErrorCode.INVALID_INPUT, "action.action"
        )
    if (
        not isinstance(action.target_asset, str)
        or not action.target_asset.strip()
        or action.target_asset != action.target_asset.strip()
    ):
        raise RecommendedActionRdfAssemblyError(
            RecommendedActionRdfAssemblyErrorCode.INVALID_INPUT, "action.target_asset"
        )
    if not isinstance(action_iri, URIRef):
        raise RecommendedActionRdfAssemblyError(
            RecommendedActionRdfAssemblyErrorCode.INVALID_INPUT, "action_iri"
        )
    if isinstance(resource_iris, str | bytes) or not isinstance(resource_iris, Mapping):
        raise RecommendedActionRdfAssemblyError(
            RecommendedActionRdfAssemblyErrorCode.INVALID_INPUT, "resource_iris"
        )
    resource_iris_snapshot: dict[str, URIRef] = {}
    snapshot_failed = False
    try:
        for key, value in resource_iris.items():
            if not isinstance(key, str) or not isinstance(value, URIRef):
                raise RecommendedActionRdfAssemblyError(
                    RecommendedActionRdfAssemblyErrorCode.INVALID_INPUT, "resource_iris"
                )
            resource_iris_snapshot[key] = value
    except RecommendedActionRdfAssemblyError:
        raise
    except Exception:
        snapshot_failed = True
    if snapshot_failed:
        raise RecommendedActionRdfAssemblyError(
            RecommendedActionRdfAssemblyErrorCode.INVALID_INPUT, "resource_iris"
        )
    if not isinstance(anomaly_window_start, str):
        raise RecommendedActionRdfAssemblyError(
            RecommendedActionRdfAssemblyErrorCode.INVALID_INPUT, "anomaly_window_start"
        )
    if not isinstance(anomaly_window_end, str):
        raise RecommendedActionRdfAssemblyError(
            RecommendedActionRdfAssemblyErrorCode.INVALID_INPUT, "anomaly_window_end"
        )
    if type(structured_result) is not StructuredRetrievalResult:
        raise RecommendedActionRdfAssemblyError(
            RecommendedActionRdfAssemblyErrorCode.INVALID_INPUT, "structured_result"
        )
    _revalidate_record(structured_result.asset, KnownAsset, "structured_result.asset")
    if type(procedural_result) is not ProceduralRetrievalResult:
        raise RecommendedActionRdfAssemblyError(
            RecommendedActionRdfAssemblyErrorCode.INVALID_INPUT, "procedural_result"
        )
    _revalidate_record(procedural_result.asset, KnownAsset, "procedural_result.asset")
    return resource_iris_snapshot


def _expect_exactly_one(values: object, expected_type: type[_T], field: str) -> _T:
    if isinstance(values, str | bytes) or not isinstance(values, tuple):
        raise RecommendedActionRdfAssemblyError(
            RecommendedActionRdfAssemblyErrorCode.INVALID_INPUT, field
        )
    if len(values) != 1 or not isinstance(values[0], expected_type):
        raise RecommendedActionRdfAssemblyError(
            RecommendedActionRdfAssemblyErrorCode.INVALID_INPUT, field
        )
    return values[0]


def _revalidate_record(value: _T, expected_type: type[_T], field: str) -> None:
    if type(value) is not expected_type:
        raise RecommendedActionRdfAssemblyError(
            RecommendedActionRdfAssemblyErrorCode.INVALID_INPUT, field
        )
    validation_failed = False
    try:
        replace(cast(Any, value))
    except Exception:
        validation_failed = True
    if validation_failed:
        raise RecommendedActionRdfAssemblyError(
            RecommendedActionRdfAssemblyErrorCode.INVALID_INPUT, field
        )


def _validate_action_support_evidence(
    action: CandidateAction,
    structured_support: StructuredSupportRecord,
    procedural_support: ProceduralSupportRecord,
) -> None:
    references = action.support_evidence
    if not isinstance(references, tuple) or len(references) != 2:
        raise RecommendedActionRdfAssemblyError(
            RecommendedActionRdfAssemblyErrorCode.IDENTITY_MISMATCH,
            "action.support_evidence",
        )
    if not all(isinstance(reference, EvidenceReference) for reference in references):
        raise RecommendedActionRdfAssemblyError(
            RecommendedActionRdfAssemblyErrorCode.IDENTITY_MISMATCH,
            "action.support_evidence",
        )
    for reference in references:
        _revalidate_record(reference, EvidenceReference, "action.support_evidence")

    expected_kinds = {
        structured_support.evidence_id: EvidenceKind.KG_EDGE,
        procedural_support.evidence_id: EvidenceKind.DOCUMENT_CHUNK,
    }
    stable_ids = tuple(reference.stable_id for reference in references)
    if len(set(stable_ids)) != 2 or set(stable_ids) != set(expected_kinds):
        raise RecommendedActionRdfAssemblyError(
            RecommendedActionRdfAssemblyErrorCode.IDENTITY_MISMATCH,
            "action.support_evidence",
        )
    for reference in references:
        if reference.kind is not expected_kinds[reference.stable_id]:
            raise RecommendedActionRdfAssemblyError(
                RecommendedActionRdfAssemblyErrorCode.IDENTITY_MISMATCH,
                "action.support_evidence.kind",
            )
        if reference.validation_status is not EvidenceValidationStatus.VALIDATED:
            raise RecommendedActionRdfAssemblyError(
                RecommendedActionRdfAssemblyErrorCode.IDENTITY_MISMATCH,
                "action.support_evidence.validation_status",
            )


def _validate_identity(
    action: CandidateAction,
    structured_result: StructuredRetrievalResult,
    procedural_result: ProceduralRetrievalResult,
) -> None:
    structured_observation = structured_result.observations[0]
    structured_support = structured_result.support_records[0]
    if action.target_asset != structured_result.asset.asset_id:
        raise RecommendedActionRdfAssemblyError(
            RecommendedActionRdfAssemblyErrorCode.IDENTITY_MISMATCH, "action.target_asset"
        )
    if action.target_asset != procedural_result.asset.asset_id:
        raise RecommendedActionRdfAssemblyError(
            RecommendedActionRdfAssemblyErrorCode.IDENTITY_MISMATCH, "action.target_asset"
        )
    if structured_result.asset.asset_id != procedural_result.asset.asset_id:
        raise RecommendedActionRdfAssemblyError(
            RecommendedActionRdfAssemblyErrorCode.IDENTITY_MISMATCH, "retrieval.asset"
        )
    if structured_observation.observed_asset != action.target_asset:
        raise RecommendedActionRdfAssemblyError(
            RecommendedActionRdfAssemblyErrorCode.IDENTITY_MISMATCH,
            "structured_result.observations.observed_asset",
        )
    if structured_support.subject != action.target_asset:
        raise RecommendedActionRdfAssemblyError(
            RecommendedActionRdfAssemblyErrorCode.IDENTITY_MISMATCH,
            "structured_result.support_records.subject",
        )
    if structured_support.predicate != _EXPECTED_KG_PREDICATE:
        raise RecommendedActionRdfAssemblyError(
            RecommendedActionRdfAssemblyErrorCode.IDENTITY_MISMATCH,
            "structured_result.support_records.predicate",
        )
    procedural_support = procedural_result.support_records[0]
    if procedural_support.applicable_asset_id != action.target_asset:
        raise RecommendedActionRdfAssemblyError(
            RecommendedActionRdfAssemblyErrorCode.IDENTITY_MISMATCH,
            "procedural_result.support_records.applicable_asset_id",
        )


def _resolve_resource(resource_iris: Mapping[str, URIRef], stable_id: str, field: str) -> URIRef:
    resolved = resource_iris.get(stable_id)
    if resolved is None:
        raise RecommendedActionRdfAssemblyError(
            RecommendedActionRdfAssemblyErrorCode.UNKNOWN_RESOURCE_ID, field
        )
    return resolved


def _map_action_mapping_error(error: RdfActionMappingError) -> RecommendedActionRdfAssemblyError:
    if error.code.value == RecommendedActionRdfAssemblyErrorCode.UNKNOWN_RESOURCE_ID.value:
        return RecommendedActionRdfAssemblyError(
            RecommendedActionRdfAssemblyErrorCode.UNKNOWN_RESOURCE_ID, error.field
        )
    return RecommendedActionRdfAssemblyError(
        RecommendedActionRdfAssemblyErrorCode.INVALID_INPUT, error.field
    )


def _asset_type_iri(asset_type: str) -> URIRef:
    if asset_type == "centrifugal_pump":
        return MFG.CentrifugalPump
    raise RecommendedActionRdfAssemblyError(
        RecommendedActionRdfAssemblyErrorCode.UNKNOWN_RESOURCE_ID,
        "procedural_result.support_records.applicable_asset_type",
    )


def _parse_datetime(value: str, field: str) -> datetime:
    if not isinstance(value, str):
        raise RecommendedActionRdfAssemblyError(
            RecommendedActionRdfAssemblyErrorCode.INVALID_TIMESTAMP, field
        )
    if (
        not value.strip()
        or value != value.strip()
        or _XSD_DATETIME_PATTERN.fullmatch(value) is None
    ):
        raise RecommendedActionRdfAssemblyError(
            RecommendedActionRdfAssemblyErrorCode.INVALID_TIMESTAMP, field
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise RecommendedActionRdfAssemblyError(
            RecommendedActionRdfAssemblyErrorCode.INVALID_TIMESTAMP, field
        ) from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RecommendedActionRdfAssemblyError(
            RecommendedActionRdfAssemblyErrorCode.INVALID_TIMESTAMP, field
        )
    return parsed


def _date_time_literal(value: str) -> Literal:
    return Literal(value, datatype=XSD.dateTime)


__all__ = [
    "RecommendedActionRdfAssemblyError",
    "RecommendedActionRdfAssemblyErrorCode",
    "RecommendedActionRdfGraphs",
    "assemble_recommended_action_rdf",
]
