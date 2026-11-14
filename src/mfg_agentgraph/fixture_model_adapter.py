"""Fixture-only deterministic candidate generation for the Pump 12 scenario.

This module intentionally emits only the raw CandidateAction JSON carried by the
existing Pump 12 fixture. It is not a provider adapter boundary, does not call a
model, and leaves candidate semantics to ``parse_candidate_actions``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from mfg_agentgraph.entity_resolution import KnownAsset
from mfg_agentgraph.evidence_reference import EvidenceCatalog, EvidenceKind, EvidenceReference
from mfg_agentgraph.procedural_retrieval import ProceduralRetrievalResult
from mfg_agentgraph.stage_instrumentation import StageEvent, StageName, TerminalStatus
from mfg_agentgraph.structured_retrieval import StructuredRetrievalResult

DETERMINISTIC_FIXTURE_MODEL_ID = "fixture-model:pump-12-candidate-actions-v1"
DETERMINISTIC_FIXTURE_PROMPT_ID = "fixture-prompt:pump-12-candidate-actions-v1"
_EXPECTED_ASSET_ID = "ex:Pump_12"
_EXPECTED_KG_EDGE_ID = "ex:EvidenceEdge_001"
_EXPECTED_DOCUMENT_EVIDENCE_ID = "ex:SOP_Chunk_7"


class FixtureModelVariant(StrEnum):
    """Supported raw fixture candidate variants."""

    REPAIRED = "repaired"
    INCOMPLETE = "incomplete"


_EXPECTED_CANDIDATE_IDS: Mapping[FixtureModelVariant, str] = MappingProxyType(
    {
        FixtureModelVariant.REPAIRED: "ex:CandidateAction_Pump12_Repaired_001",
        FixtureModelVariant.INCOMPLETE: "ex:CandidateAction_Pump12_Incomplete_001",
    }
)
_EXPECTED_ACTION_LABELS: Mapping[FixtureModelVariant, str] = MappingProxyType(
    {
        FixtureModelVariant.REPAIRED: "Inspect the pump inlet of Pump_12 for cavitation",
        FixtureModelVariant.INCOMPLETE: "Inspect pump inlet for cavitation",
    }
)


class FixtureModelAdapterErrorCode(StrEnum):
    """Stable fixture adapter failure codes."""

    RETRIEVAL_NOT_PASSED = "retrieval_not_passed"
    IDENTITY_MISMATCH = "identity_mismatch"
    INVALID_SCENARIO = "invalid_scenario"


class FixtureModelAdapterError(ValueError):
    """Deterministic fail-closed fixture adapter error."""

    __slots__ = ("code", "field")

    def __init__(self, code: FixtureModelAdapterErrorCode, field: str) -> None:
        if not isinstance(code, FixtureModelAdapterErrorCode):
            raise TypeError("code must be a FixtureModelAdapterErrorCode")
        self.code = code
        self.field = _require_nonblank(field, "field")
        super().__init__(f"{self.code.value}: {self.field}")


@dataclass(frozen=True, slots=True)
class FixtureCandidateGenerationResult:
    """Immutable raw fixture candidate-generation result."""

    raw_json: str
    candidate_id: str
    model_id: str
    prompt_id: str
    evidence_catalog: EvidenceCatalog
    event: StageEvent
    metadata: Sequence[tuple[str, str]] = field(default_factory=tuple)
    evidence_references: Sequence[EvidenceReference] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw_json", _require_nonblank(self.raw_json, "raw_json"))
        object.__setattr__(
            self, "candidate_id", _require_nonblank(self.candidate_id, "candidate_id")
        )
        object.__setattr__(self, "model_id", _require_nonblank(self.model_id, "model_id"))
        object.__setattr__(self, "prompt_id", _require_nonblank(self.prompt_id, "prompt_id"))
        if not isinstance(self.evidence_catalog, EvidenceCatalog):
            raise TypeError("evidence_catalog must be an EvidenceCatalog")
        if not isinstance(self.event, StageEvent):
            raise TypeError("event must be a StageEvent")
        object.__setattr__(
            self,
            "metadata",
            _normalize_metadata(self.metadata),
        )
        object.__setattr__(
            self,
            "evidence_references",
            _normalize_references(self.evidence_references, "evidence_references"),
        )
        _validate_result_invariants(self)


def generate_fixture_candidate_actions(
    *,
    scenario: Mapping[str, Any],
    structured_result: StructuredRetrievalResult,
    procedural_result: ProceduralRetrievalResult,
    generation_run_id: str,
    query_id: str,
    variant: FixtureModelVariant,
) -> FixtureCandidateGenerationResult:
    """Emit deterministic raw CandidateAction JSON from the Pump 12 fixture."""

    _validate_mapping(scenario, "scenario")
    if not isinstance(structured_result, StructuredRetrievalResult):
        raise TypeError("structured_result must be a StructuredRetrievalResult")
    if not isinstance(procedural_result, ProceduralRetrievalResult):
        raise TypeError("procedural_result must be a ProceduralRetrievalResult")
    run_id = _require_strict_nonblank(generation_run_id, "generation_run_id")
    normalized_query_id = _require_strict_nonblank(query_id, "query_id")
    if not isinstance(variant, FixtureModelVariant):
        raise TypeError("variant must be a FixtureModelVariant")

    _validate_retrieval_prerequisites(structured_result, procedural_result, normalized_query_id)
    candidate_mapping = _candidate_mapping(scenario, variant)
    action_label = _canonical_action_label(candidate_mapping, variant)
    candidate_id = _required_string(
        candidate_mapping, "id", f"candidate_actions.{variant.value}.id"
    )
    _validate_candidate_id(variant, candidate_id)
    target = _candidate_target(candidate_mapping, variant)
    evidence_ids = _candidate_evidence_ids(candidate_mapping, variant)
    _validate_candidate_shape(variant, target, evidence_ids)

    references = _combined_evidence_references(
        structured_result, procedural_result, normalized_query_id
    )
    catalog = EvidenceCatalog(references)
    raw_json = _raw_candidate_json(action=action_label, target=target, evidence_ids=evidence_ids)
    event = StageEvent(
        stage=StageName.CANDIDATE_GENERATION,
        run_id=run_id,
        status=TerminalStatus.PASSED,
        duration_ms=0,
        input_ids=(structured_result.asset.asset_id, normalized_query_id, *evidence_ids),
        output_ids=(candidate_id,),
    )
    return FixtureCandidateGenerationResult(
        raw_json=raw_json,
        candidate_id=candidate_id,
        model_id=DETERMINISTIC_FIXTURE_MODEL_ID,
        prompt_id=DETERMINISTIC_FIXTURE_PROMPT_ID,
        evidence_catalog=catalog,
        event=event,
        metadata=(
            ("fixture_variant", variant.value),
            ("fixture_candidate_id", candidate_id),
            ("fixture_model_id", DETERMINISTIC_FIXTURE_MODEL_ID),
            ("fixture_prompt_id", DETERMINISTIC_FIXTURE_PROMPT_ID),
        ),
        evidence_references=references,
    )


def _validate_retrieval_prerequisites(
    structured_result: StructuredRetrievalResult,
    procedural_result: ProceduralRetrievalResult,
    query_id: str,
) -> None:
    if structured_result.status is not TerminalStatus.PASSED:
        raise FixtureModelAdapterError(
            FixtureModelAdapterErrorCode.RETRIEVAL_NOT_PASSED, "structured_result.status"
        )
    if procedural_result.status is not TerminalStatus.PASSED:
        raise FixtureModelAdapterError(
            FixtureModelAdapterErrorCode.RETRIEVAL_NOT_PASSED, "procedural_result.status"
        )
    if structured_result.asset != procedural_result.asset:
        raise FixtureModelAdapterError(FixtureModelAdapterErrorCode.IDENTITY_MISMATCH, "asset")
    asset = structured_result.asset
    if not isinstance(asset, KnownAsset):
        raise TypeError("asset must be a KnownAsset")
    if asset.asset_id != _EXPECTED_ASSET_ID:
        raise FixtureModelAdapterError(FixtureModelAdapterErrorCode.IDENTITY_MISMATCH, "asset")
    _validate_event_input_ids(
        structured_result.event, asset.asset_id, query_id, "structured_result"
    )
    _validate_event_input_ids(
        procedural_result.event, asset.asset_id, query_id, "procedural_result"
    )


def _validate_event_input_ids(
    event: StageEvent,
    asset_id: str,
    query_id: str,
    field_prefix: str,
) -> None:
    if event.input_ids != (asset_id, query_id):
        raise FixtureModelAdapterError(
            FixtureModelAdapterErrorCode.IDENTITY_MISMATCH,
            f"{field_prefix}.event.input_ids",
        )


def _combined_evidence_references(
    structured_result: StructuredRetrievalResult,
    procedural_result: ProceduralRetrievalResult,
    query_id: str,
) -> tuple[EvidenceReference, ...]:
    structured_refs = _normalize_references(
        structured_result.evidence_references, "structured_result.evidence_references"
    )
    procedural_refs = _normalize_references(
        procedural_result.evidence_references, "procedural_result.evidence_references"
    )
    if len(structured_refs) != 1 or structured_refs[0].stable_id != _EXPECTED_KG_EDGE_ID:
        raise FixtureModelAdapterError(
            FixtureModelAdapterErrorCode.IDENTITY_MISMATCH,
            "structured_result.evidence_references",
        )
    if structured_refs[0].kind is not EvidenceKind.KG_EDGE:
        raise FixtureModelAdapterError(
            FixtureModelAdapterErrorCode.IDENTITY_MISMATCH,
            "structured_result.evidence_references",
        )
    if structured_refs[0].retrieval.query_id != query_id:
        raise FixtureModelAdapterError(
            FixtureModelAdapterErrorCode.IDENTITY_MISMATCH,
            "structured_result.evidence_references[0].retrieval.query_id",
        )
    if len(procedural_refs) != 1 or procedural_refs[0].stable_id != _EXPECTED_DOCUMENT_EVIDENCE_ID:
        raise FixtureModelAdapterError(
            FixtureModelAdapterErrorCode.IDENTITY_MISMATCH,
            "procedural_result.evidence_references",
        )
    if procedural_refs[0].kind is not EvidenceKind.DOCUMENT_CHUNK:
        raise FixtureModelAdapterError(
            FixtureModelAdapterErrorCode.IDENTITY_MISMATCH,
            "procedural_result.evidence_references",
        )
    return (*structured_refs, *procedural_refs)


def _candidate_mapping(
    scenario: Mapping[str, Any], variant: FixtureModelVariant
) -> Mapping[str, Any]:
    candidates = scenario.get("candidate_actions")
    if not isinstance(candidates, Mapping):
        raise FixtureModelAdapterError(
            FixtureModelAdapterErrorCode.INVALID_SCENARIO, "candidate_actions"
        )
    candidate = candidates.get(variant.value)
    if not isinstance(candidate, Mapping):
        raise FixtureModelAdapterError(
            FixtureModelAdapterErrorCode.INVALID_SCENARIO, f"candidate_actions.{variant.value}"
        )
    return candidate


def _validate_candidate_id(variant: FixtureModelVariant, candidate_id: str) -> None:
    if candidate_id != _EXPECTED_CANDIDATE_IDS[variant]:
        raise FixtureModelAdapterError(
            FixtureModelAdapterErrorCode.INVALID_SCENARIO,
            f"candidate_actions.{variant.value}.id",
        )


def _canonical_action_label(candidate: Mapping[str, Any], variant: FixtureModelVariant) -> str:
    expected = _EXPECTED_ACTION_LABELS[variant]
    if candidate.get("label") != expected:
        raise FixtureModelAdapterError(
            FixtureModelAdapterErrorCode.INVALID_SCENARIO,
            f"candidate_actions.{variant.value}.label",
        )
    return expected


def _candidate_target(candidate: Mapping[str, Any], variant: FixtureModelVariant) -> str | None:
    if "target" not in candidate:
        raise FixtureModelAdapterError(
            FixtureModelAdapterErrorCode.INVALID_SCENARIO,
            f"candidate_actions.{variant.value}.target",
        )
    target = candidate["target"]
    if target is None:
        return None
    if not isinstance(target, str) or not target.strip():
        raise FixtureModelAdapterError(
            FixtureModelAdapterErrorCode.INVALID_SCENARIO,
            f"candidate_actions.{variant.value}.target",
        )
    return target.strip()


def _candidate_evidence_ids(
    candidate: Mapping[str, Any], variant: FixtureModelVariant
) -> tuple[str, ...]:
    if "evidence_refs" not in candidate:
        raise FixtureModelAdapterError(
            FixtureModelAdapterErrorCode.INVALID_SCENARIO,
            f"candidate_actions.{variant.value}.evidence_refs",
        )
    evidence_refs = candidate["evidence_refs"]
    if isinstance(evidence_refs, str) or not isinstance(evidence_refs, Sequence):
        raise FixtureModelAdapterError(
            FixtureModelAdapterErrorCode.INVALID_SCENARIO,
            f"candidate_actions.{variant.value}.evidence_refs",
        )
    normalized: list[str] = []
    for evidence_ref in evidence_refs:
        if not isinstance(evidence_ref, str) or not evidence_ref.strip():
            raise FixtureModelAdapterError(
                FixtureModelAdapterErrorCode.INVALID_SCENARIO,
                f"candidate_actions.{variant.value}.evidence_refs",
            )
        normalized.append(evidence_ref.strip())
    return tuple(normalized)


def _validate_candidate_shape(
    variant: FixtureModelVariant, target: str | None, evidence_ids: tuple[str, ...]
) -> None:
    if variant is FixtureModelVariant.REPAIRED:
        if target != _EXPECTED_ASSET_ID:
            raise FixtureModelAdapterError(
                FixtureModelAdapterErrorCode.INVALID_SCENARIO, "candidate_actions.repaired.target"
            )
        if evidence_ids != (_EXPECTED_KG_EDGE_ID, _EXPECTED_DOCUMENT_EVIDENCE_ID):
            raise FixtureModelAdapterError(
                FixtureModelAdapterErrorCode.INVALID_SCENARIO,
                "candidate_actions.repaired.evidence_refs",
            )
        return
    if target is not None:
        raise FixtureModelAdapterError(
            FixtureModelAdapterErrorCode.INVALID_SCENARIO, "candidate_actions.incomplete.target"
        )
    if evidence_ids != ():
        raise FixtureModelAdapterError(
            FixtureModelAdapterErrorCode.INVALID_SCENARIO,
            "candidate_actions.incomplete.evidence_refs",
        )


def _raw_candidate_json(*, action: str, target: str | None, evidence_ids: tuple[str, ...]) -> str:
    support_evidence = []
    for evidence_id in evidence_ids:
        if evidence_id == _EXPECTED_KG_EDGE_ID:
            support_evidence.append({"type": EvidenceKind.KG_EDGE.value, "id": evidence_id})
        elif evidence_id == _EXPECTED_DOCUMENT_EVIDENCE_ID:
            support_evidence.append({"type": EvidenceKind.DOCUMENT_CHUNK.value, "id": evidence_id})
    return json.dumps(
        {
            "ranked_actions": [
                {
                    "rank": 1,
                    "action": action,
                    "target_asset": target,
                    "support_evidence": support_evidence,
                }
            ]
        },
        sort_keys=False,
        separators=(",", ":"),
    )


def _validate_result_invariants(result: FixtureCandidateGenerationResult) -> None:
    if result.event.stage is not StageName.CANDIDATE_GENERATION:
        raise ValueError("event.stage must be candidate_generation")
    if result.event.status is not TerminalStatus.PASSED:
        raise ValueError("event.status must be passed")
    if result.event.output_ids != (result.candidate_id,):
        raise ValueError("event.output_ids must equal candidate_id")
    if result.event.errors:
        raise ValueError("passed event must not contain errors")
    if result.event.retry_count != 0 or result.event.repair_count != 0:
        raise ValueError("fixture candidate generation must not retry or repair")
    if result.model_id != DETERMINISTIC_FIXTURE_MODEL_ID:
        raise ValueError("model_id must equal deterministic fixture model ID")
    if result.prompt_id != DETERMINISTIC_FIXTURE_PROMPT_ID:
        raise ValueError("prompt_id must equal deterministic fixture prompt ID")
    if result.evidence_catalog.references != result.evidence_references:
        raise ValueError("evidence catalog references must equal evidence_references")


def _required_string(candidate: Mapping[str, Any], key: str, field: str) -> str:
    value = candidate.get(key)
    if not isinstance(value, str) or not value.strip():
        raise FixtureModelAdapterError(FixtureModelAdapterErrorCode.INVALID_SCENARIO, field)
    return value.strip()


def _normalize_references(
    values: Sequence[EvidenceReference], field_name: str
) -> tuple[EvidenceReference, ...]:
    if isinstance(values, str) or not isinstance(values, Sequence):
        raise TypeError(f"{field_name} must be a sequence")
    normalized: list[EvidenceReference] = []
    for value in values:
        if not isinstance(value, EvidenceReference):
            raise TypeError(f"{field_name} must contain EvidenceReference instances")
        normalized.append(value)
    return tuple(normalized)


def _normalize_metadata(values: Sequence[tuple[str, str]]) -> tuple[tuple[str, str], ...]:
    if isinstance(values, str) or not isinstance(values, Sequence):
        raise TypeError("metadata must be a sequence")
    normalized: list[tuple[str, str]] = []
    for item in values:
        if not isinstance(item, tuple) or len(item) != 2:
            raise TypeError("metadata must contain key/value string tuples")
        key, value = item
        normalized.append(
            (_require_nonblank(key, "metadata key"), _require_nonblank(value, "metadata value"))
        )
    return tuple(normalized)


def _validate_mapping(value: object, field_name: str) -> None:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")


def _require_nonblank(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must be nonblank")
    return stripped


def _require_strict_nonblank(value: object, field_name: str) -> str:
    normalized = _require_nonblank(value, field_name)
    assert isinstance(value, str)
    if value != normalized:
        raise ValueError(f"{field_name} must not contain surrounding whitespace")
    return value
