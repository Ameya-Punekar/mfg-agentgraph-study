"""Dependency-free deterministic structured retrieval for the Pump 12 fixture.

This module intentionally models only the minimal Issue #15 contract: validate the
resolved asset against the immutable fixture-shaped mapping, trace the required
observation, and expose the KG edge as the only structured support evidence.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from mfg_agentgraph.entity_resolution import KnownAsset
from mfg_agentgraph.evidence_reference import (
    EvidenceCatalog,
    EvidenceKind,
    EvidenceReference,
    EvidenceValidationStatus,
    RetrievalMetadata,
)
from mfg_agentgraph.stage_instrumentation import (
    StageError,
    StageErrorCode,
    StageEvent,
    StageName,
    TerminalStatus,
)

DETERMINISTIC_STRUCTURED_RETRIEVER_NAME = "deterministic_structured_fixture"
DEFAULT_STRUCTURED_RETRIEVAL_SOURCE = "tests/fixtures/pump_12/scenario.json"
_EXPECTED_OBSERVATION_ID = "ex:Observation_Pump12_2026-05-18T14:03:00Z"
_EXPECTED_ASSET_ID = "ex:Pump_12"
_EXPECTED_ASSET_LOCATION_ID = "ex:PumpStation_12"
_EXPECTED_KG_EDGE_ID = "ex:EvidenceEdge_001"
_EXPECTED_KG_PREDICATE = "ex:hasRecommendedProcedure"
_EXPECTED_OBSERVATION_SIGNAL = "anomalous_sound"
_EXPECTED_OBSERVATION_ANOMALY = "anomalous_sound"
_MAX_IDENTIFIER_BYTES = 1_024
_MAX_EVIDENCE_ID_BYTES = 8_192


@dataclass(frozen=True, slots=True)
class StructuredObservation:
    """Trace of the explicit asset observation required by structured support."""

    observation_id: str
    observed_asset: str
    observed_at: str
    signal: str
    anomaly: str
    description: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "observation_id", _require_nonblank(self.observation_id, "observation_id")
        )
        object.__setattr__(
            self, "observed_asset", _require_nonblank(self.observed_asset, "observed_asset")
        )
        object.__setattr__(self, "observed_at", _require_nonblank(self.observed_at, "observed_at"))
        object.__setattr__(self, "signal", _require_nonblank(self.signal, "signal"))
        object.__setattr__(self, "anomaly", _require_nonblank(self.anomaly, "anomaly"))
        object.__setattr__(self, "description", _require_nonblank(self.description, "description"))


@dataclass(frozen=True, slots=True)
class StructuredSupportRecord:
    """Validated KG edge support returned by the structured retriever."""

    evidence_id: str
    subject: str
    predicate: str
    procedure_id: str
    required_observation_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "evidence_id",
            _require_nonblank(
                self.evidence_id,
                "evidence_id",
                max_bytes=_MAX_EVIDENCE_ID_BYTES,
            ),
        )
        object.__setattr__(self, "subject", _require_nonblank(self.subject, "subject"))
        object.__setattr__(self, "predicate", _require_nonblank(self.predicate, "predicate"))
        object.__setattr__(
            self, "procedure_id", _require_nonblank(self.procedure_id, "procedure_id")
        )
        object.__setattr__(
            self,
            "required_observation_id",
            _require_nonblank(self.required_observation_id, "required_observation_id"),
        )


@dataclass(frozen=True, slots=True)
class StructuredRetrievalResult:
    """Immutable structured retrieval outcome and instrumentation event."""

    status: TerminalStatus
    asset: KnownAsset
    event: StageEvent
    observations: Sequence[StructuredObservation] = field(default_factory=tuple)
    support_records: Sequence[StructuredSupportRecord] = field(default_factory=tuple)
    evidence_references: Sequence[EvidenceReference] = field(default_factory=tuple)
    evidence_catalog: EvidenceCatalog = field(default_factory=EvidenceCatalog)

    def __post_init__(self) -> None:
        if not isinstance(self.status, TerminalStatus):
            raise TypeError("status must be a TerminalStatus")
        if not isinstance(self.asset, KnownAsset):
            raise TypeError("asset must be a KnownAsset")
        object.__setattr__(
            self,
            "observations",
            _normalize_sequence(self.observations, StructuredObservation, "observations"),
        )
        object.__setattr__(
            self,
            "support_records",
            _normalize_sequence(self.support_records, StructuredSupportRecord, "support_records"),
        )
        object.__setattr__(
            self,
            "evidence_references",
            _normalize_sequence(self.evidence_references, EvidenceReference, "evidence_references"),
        )
        if not isinstance(self.evidence_catalog, EvidenceCatalog):
            raise TypeError("evidence_catalog must be an EvidenceCatalog")
        if not isinstance(self.event, StageEvent):
            raise TypeError("event must be a StageEvent")
        _validate_result_invariants(self)


@dataclass(frozen=True, slots=True)
class StructuredRetriever:
    """Deterministic fixture-backed structured retriever."""

    source: str = DEFAULT_STRUCTURED_RETRIEVAL_SOURCE
    retriever_name: str = DETERMINISTIC_STRUCTURED_RETRIEVER_NAME

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", _require_nonblank(self.source, "source"))
        object.__setattr__(
            self,
            "retriever_name",
            _require_nonblank(self.retriever_name, "retriever_name"),
        )

    def retrieve(
        self,
        *,
        resolved_asset: KnownAsset,
        scenario: Mapping[str, Any],
        retrieval_run_id: str,
        query_id: str,
    ) -> StructuredRetrievalResult:
        """Return structured support for a resolved asset, failing closed on mismatch."""

        _validate_asset(resolved_asset)
        _validate_mapping(scenario, "scenario")
        run_id = _require_strict_nonblank(retrieval_run_id, "retrieval_run_id")
        normalized_query_id = _require_strict_nonblank(query_id, "query_id")
        input_ids = (resolved_asset.asset_id, normalized_query_id)

        asset_error = _validate_pump_12_fixture_asset(resolved_asset, scenario)
        if asset_error is not None:
            return _failure(resolved_asset, run_id, input_ids, (), asset_error)

        observation_result = _extract_valid_observation(scenario, resolved_asset.asset_id)
        if isinstance(observation_result, StageError):
            return _failure(resolved_asset, run_id, input_ids, (), observation_result)
        observation = observation_result

        support_result = _extract_valid_support(
            scenario, resolved_asset.asset_id, observation.observation_id
        )
        if isinstance(support_result, StageError):
            return _failure(
                resolved_asset,
                run_id,
                input_ids,
                (observation,),
                support_result,
            )
        support = support_result

        reference = EvidenceReference(
            kind=EvidenceKind.KG_EDGE,
            source=self.source,
            stable_id=support.evidence_id,
            retrieval=RetrievalMetadata(
                retrieval_run_id=run_id,
                query_id=normalized_query_id,
                retriever_name=self.retriever_name,
                rank=1,
                score=1.0,
            ),
            validation_status=EvidenceValidationStatus.VALIDATED,
        )
        references = (reference,)
        event = StageEvent(
            stage=StageName.STRUCTURED_RETRIEVAL,
            run_id=run_id,
            status=TerminalStatus.PASSED,
            duration_ms=0,
            input_ids=input_ids,
            output_ids=(observation.observation_id, support.procedure_id, support.evidence_id),
        )
        return StructuredRetrievalResult(
            status=TerminalStatus.PASSED,
            asset=resolved_asset,
            observations=(observation,),
            support_records=(support,),
            evidence_references=references,
            evidence_catalog=EvidenceCatalog(references),
            event=event,
        )


def retrieve_structured_support(
    *,
    resolved_asset: KnownAsset,
    scenario: Mapping[str, Any],
    retrieval_run_id: str,
    query_id: str,
    source: str = DEFAULT_STRUCTURED_RETRIEVAL_SOURCE,
) -> StructuredRetrievalResult:
    """Convenience wrapper around :class:`StructuredRetriever`."""

    return StructuredRetriever(source=source).retrieve(
        resolved_asset=resolved_asset,
        scenario=scenario,
        retrieval_run_id=retrieval_run_id,
        query_id=query_id,
    )


def _validate_pump_12_fixture_asset(
    resolved_asset: KnownAsset, scenario: Mapping[str, Any]
) -> StageError | None:
    if resolved_asset.asset_id != _EXPECTED_ASSET_ID:
        return _insufficient(
            "resolved_asset.asset_id",
            f"expected {_EXPECTED_ASSET_ID}, got {resolved_asset.asset_id!r}",
        )

    fixture_asset = scenario.get("asset")
    if not isinstance(fixture_asset, Mapping):
        return _insufficient("asset", "required Pump 12 asset record is missing")
    fixture_asset_id = _string_or_none(fixture_asset.get("id"))
    if fixture_asset_id != _EXPECTED_ASSET_ID:
        return _insufficient("asset.id", f"expected {_EXPECTED_ASSET_ID}, got {fixture_asset_id!r}")
    located_at = _string_or_none(fixture_asset.get("located_at"))
    if located_at != _EXPECTED_ASSET_LOCATION_ID:
        return _insufficient(
            "asset.located_at", f"expected {_EXPECTED_ASSET_LOCATION_ID}, got {located_at!r}"
        )

    pump_station = scenario.get("pump_station")
    if not isinstance(pump_station, Mapping):
        return _insufficient("pump_station", "required Pump Station 12 record is missing")
    pump_station_id = _string_or_none(pump_station.get("id"))
    if pump_station_id != _EXPECTED_ASSET_LOCATION_ID:
        return _insufficient(
            "pump_station.id", f"expected {_EXPECTED_ASSET_LOCATION_ID}, got {pump_station_id!r}"
        )

    return None


def _extract_valid_observation(
    scenario: Mapping[str, Any],
    asset_id: str,
) -> StructuredObservation | StageError:
    procedure = scenario.get("procedure")
    if not isinstance(procedure, Mapping):
        return _insufficient("procedure", "required procedure record is missing")
    required_observation_id = _string_or_none(procedure.get("requires_observation"))
    if required_observation_id != _EXPECTED_OBSERVATION_ID:
        return _insufficient(
            "procedure.requires_observation",
            f"expected {_EXPECTED_OBSERVATION_ID}, got {required_observation_id!r}",
        )
    applicable_asset = _string_or_none(procedure.get("applicable_asset"))
    if applicable_asset != asset_id:
        return _insufficient(
            "procedure.applicable_asset", f"expected {asset_id}, got {applicable_asset!r}"
        )

    observation = scenario.get("observation")
    if not isinstance(observation, Mapping):
        return _insufficient(
            "observation", f"required observation {_EXPECTED_OBSERVATION_ID} is missing"
        )
    observation_id = _string_or_none(observation.get("id"))
    if observation_id != required_observation_id:
        return _insufficient(
            "observation.id", f"expected {required_observation_id}, got {observation_id!r}"
        )
    observed_asset = _string_or_none(observation.get("observed_asset"))
    if observed_asset != asset_id:
        return _insufficient(
            "observation.observed_asset", f"expected {asset_id}, got {observed_asset!r}"
        )
    signal = _string_or_none(observation.get("signal"))
    if signal != _EXPECTED_OBSERVATION_SIGNAL:
        return _insufficient(
            "observation.signal", f"expected {_EXPECTED_OBSERVATION_SIGNAL}, got {signal!r}"
        )
    anomaly = _string_or_none(observation.get("anomaly"))
    if anomaly != _EXPECTED_OBSERVATION_ANOMALY:
        return _insufficient(
            "observation.anomaly", f"expected {_EXPECTED_OBSERVATION_ANOMALY}, got {anomaly!r}"
        )

    try:
        return StructuredObservation(
            observation_id=observation_id,
            observed_asset=observed_asset,
            observed_at=_string_or_none(observation.get("observed_at")) or "",
            signal=signal,
            anomaly=anomaly,
            description=_string_or_none(observation.get("description")) or "",
        )
    except (TypeError, ValueError) as exc:
        return _insufficient("observation", str(exc))


def _extract_valid_support(
    scenario: Mapping[str, Any],
    asset_id: str,
    observation_id: str,
) -> StructuredSupportRecord | StageError:
    procedure = scenario.get("procedure")
    if not isinstance(procedure, Mapping):
        return _insufficient("procedure", "required procedure record is missing")
    procedure_id = _string_or_none(procedure.get("id"))
    if procedure_id != "ex:Procedure_InspectInletCavitation_Pump12":
        return _insufficient("procedure.id", f"unexpected procedure {procedure_id!r}")
    if _string_or_none(procedure.get("requires_observation")) != observation_id:
        return _insufficient("procedure.requires_observation", f"expected {observation_id}")

    kg_edge = scenario.get("kg_evidence")
    if not isinstance(kg_edge, Mapping):
        return _insufficient("kg_evidence", f"required KG edge {_EXPECTED_KG_EDGE_ID} is missing")
    edge_id = _string_or_none(kg_edge.get("id"))
    if edge_id != _EXPECTED_KG_EDGE_ID:
        return _insufficient("kg_evidence.id", f"expected {_EXPECTED_KG_EDGE_ID}, got {edge_id!r}")
    edge_type = _string_or_none(kg_edge.get("type"))
    if edge_type != "kg_edge":
        return _insufficient("kg_evidence.type", f"expected 'kg_edge', got {edge_type!r}")
    subject = _string_or_none(kg_edge.get("subject"))
    if subject != asset_id:
        return _insufficient("kg_evidence.subject", f"expected {asset_id}, got {subject!r}")
    predicate = _string_or_none(kg_edge.get("predicate"))
    if predicate != _EXPECTED_KG_PREDICATE:
        return _insufficient(
            "kg_evidence.predicate", f"expected {_EXPECTED_KG_PREDICATE}, got {predicate!r}"
        )
    procedure_object = _string_or_none(kg_edge.get("object"))
    if procedure_object != procedure_id:
        return _insufficient(
            "kg_evidence.object", f"expected {procedure_id}, got {procedure_object!r}"
        )

    return StructuredSupportRecord(
        evidence_id=edge_id,
        subject=subject,
        predicate=predicate,
        procedure_id=procedure_id,
        required_observation_id=observation_id,
    )


def _failure(
    asset: KnownAsset,
    run_id: str,
    input_ids: tuple[str, ...],
    observations: tuple[StructuredObservation, ...],
    error: StageError,
) -> StructuredRetrievalResult:
    event = StageEvent(
        stage=StageName.STRUCTURED_RETRIEVAL,
        run_id=run_id,
        status=TerminalStatus.INSUFFICIENT_EVIDENCE,
        duration_ms=0,
        input_ids=input_ids,
        output_ids=tuple(observation.observation_id for observation in observations),
        errors=(error,),
    )
    return StructuredRetrievalResult(
        status=TerminalStatus.INSUFFICIENT_EVIDENCE,
        asset=asset,
        observations=observations,
        support_records=(),
        evidence_references=(),
        evidence_catalog=EvidenceCatalog(()),
        event=event,
    )


def _insufficient(field: str, detail: str) -> StageError:
    return StageError(
        StageErrorCode.INSUFFICIENT_EVIDENCE,
        field=field,
        detail=_bounded_error_detail(detail),
    )


def _bounded_error_detail(detail: str) -> str:
    encoded = detail.encode("utf-8")
    if len(encoded) <= _MAX_IDENTIFIER_BYTES:
        return detail
    prefix = encoded[: _MAX_IDENTIFIER_BYTES - 3].decode("utf-8", errors="ignore")
    return f"{prefix}..."


def _validate_asset(value: object) -> None:
    if not isinstance(value, KnownAsset):
        raise TypeError("resolved_asset must be a KnownAsset")


def _validate_mapping(value: object, field_name: str) -> None:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")


def _validate_result_invariants(result: StructuredRetrievalResult) -> None:
    if result.event.stage is not StageName.STRUCTURED_RETRIEVAL:
        raise ValueError("event.stage must be structured_retrieval")
    if result.status != result.event.status:
        raise ValueError("status must match event.status")
    if result.status not in {TerminalStatus.PASSED, TerminalStatus.INSUFFICIENT_EVIDENCE}:
        raise ValueError("status must be passed or insufficient_evidence")

    if result.status is TerminalStatus.PASSED:
        _validate_passed_result(result)
        return
    _validate_insufficient_evidence_result(result)


def _validate_passed_result(result: StructuredRetrievalResult) -> None:
    if len(result.observations) != 1:
        raise ValueError("passed result must contain exactly one observation")
    if len(result.support_records) != 1:
        raise ValueError("passed result must contain exactly one support record")
    if len(result.evidence_references) != 1:
        raise ValueError("passed result must contain exactly one evidence reference")
    if result.event.errors:
        raise ValueError("passed result must not contain event errors")
    if result.evidence_catalog.references != result.evidence_references:
        raise ValueError("evidence catalog references must equal evidence_references")

    observation = result.observations[0]
    support = result.support_records[0]
    reference = result.evidence_references[0]
    if reference.kind is not EvidenceKind.KG_EDGE:
        raise ValueError("passed evidence reference must be a KG edge")
    if reference.validation_status is not EvidenceValidationStatus.VALIDATED:
        raise ValueError("passed evidence reference must be validated")
    if support.evidence_id != reference.stable_id:
        raise ValueError("support evidence_id must equal evidence reference stable_id")
    if support.required_observation_id != observation.observation_id:
        raise ValueError("support required_observation_id must equal observation_id")
    if result.event.output_ids != (
        observation.observation_id,
        support.procedure_id,
        support.evidence_id,
    ):
        raise ValueError(
            "passed event.output_ids must equal observation, procedure, and evidence IDs"
        )


def _validate_insufficient_evidence_result(result: StructuredRetrievalResult) -> None:
    if result.support_records:
        raise ValueError("insufficient evidence result must not contain support records")
    if result.evidence_references:
        raise ValueError("insufficient evidence result must not contain evidence references")
    if result.evidence_catalog.references:
        raise ValueError("insufficient evidence result must have an empty evidence catalog")
    if not result.event.errors:
        raise ValueError("insufficient evidence result must contain event errors")
    observation_ids = tuple(observation.observation_id for observation in result.observations)
    if result.event.output_ids != observation_ids:
        raise ValueError("insufficient evidence event.output_ids must equal observation IDs")


def _require_nonblank(
    value: object,
    field_name: str,
    *,
    max_bytes: int = _MAX_IDENTIFIER_BYTES,
) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string")
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must be nonblank")
    if len(stripped.encode("utf-8")) > max_bytes:
        raise ValueError(f"{field_name} exceeds the identifier byte limit")
    return stripped


def _require_strict_nonblank(value: object, field_name: str) -> str:
    normalized = _require_nonblank(value, field_name)
    assert isinstance(value, str)
    if value != normalized:
        raise ValueError(f"{field_name} must not contain surrounding whitespace")
    return value


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _normalize_sequence(
    values: Sequence[object], expected_type: type[Any], field_name: str
) -> tuple[Any, ...]:
    if isinstance(values, str) or not isinstance(values, Sequence):
        raise TypeError(f"{field_name} must be a sequence")
    normalized: list[Any] = []
    for value in values:
        if not isinstance(value, expected_type):
            raise TypeError(f"{field_name} must contain {expected_type.__name__} instances")
        normalized.append(value)
    return tuple(normalized)
