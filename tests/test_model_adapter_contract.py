"""Focused contract tests for Issue #17 deterministic fixture model adapter."""

from __future__ import annotations

import copy
import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Any, cast

import pytest

from mfg_agentgraph.candidate_action import (
    CandidateActionError,
    CandidateActionErrorCode,
    parse_candidate_actions,
)
from mfg_agentgraph.entity_resolution import KnownAsset
from mfg_agentgraph.evidence_reference import EvidenceCatalog, EvidenceKind, RetrievalMetadata
from mfg_agentgraph.fixture_model_adapter import (
    DETERMINISTIC_FIXTURE_MODEL_ID,
    DETERMINISTIC_FIXTURE_PROMPT_ID,
    FixtureCandidateGenerationResult,
    FixtureModelAdapterError,
    FixtureModelAdapterErrorCode,
    FixtureModelVariant,
    generate_fixture_candidate_actions,
)
from mfg_agentgraph.procedural_retrieval import (
    ProceduralRetrievalResult,
    retrieve_procedural_support,
)
from mfg_agentgraph.stage_instrumentation import (
    StageError,
    StageErrorCode,
    StageEvent,
    StageName,
    TerminalStatus,
)
from mfg_agentgraph.structured_retrieval import (
    StructuredRetrievalResult,
    retrieve_structured_support,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "pump_12" / "scenario.json"
GENERATION_RUN_ID = "run-issue-17-generation"
QUERY_ID = "query-pump-12-candidate-generation"
ASSET = KnownAsset("ex:Pump_12", "Pump 12", ("Pump_12",))
KG_EDGE_ID = "ex:EvidenceEdge_001"
DOCUMENT_EVIDENCE_ID = "ex:SOP_Chunk_7"
REPAIRED_CANDIDATE_ID = "ex:CandidateAction_Pump12_Repaired_001"
INCOMPLETE_CANDIDATE_ID = "ex:CandidateAction_Pump12_Incomplete_001"


def _scenario() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(FIXTURE_PATH.read_text(encoding="utf-8")))


def _structured_result(scenario: dict[str, Any] | None = None) -> StructuredRetrievalResult:
    return retrieve_structured_support(
        resolved_asset=ASSET,
        scenario=scenario if scenario is not None else _scenario(),
        retrieval_run_id="run-issue-17-structured",
        query_id=QUERY_ID,
    )


def _procedural_result(scenario: dict[str, Any] | None = None) -> ProceduralRetrievalResult:
    return retrieve_procedural_support(
        resolved_asset=ASSET,
        scenario=scenario if scenario is not None else _scenario(),
        retrieval_run_id="run-issue-17-procedural",
        query_id=QUERY_ID,
    )


def _generate(
    *,
    scenario: dict[str, Any] | None = None,
    variant: FixtureModelVariant = FixtureModelVariant.REPAIRED,
    structured: StructuredRetrievalResult | None = None,
    procedural: ProceduralRetrievalResult | None = None,
    query_id: str = QUERY_ID,
) -> FixtureCandidateGenerationResult:
    fixture = scenario if scenario is not None else _scenario()
    return generate_fixture_candidate_actions(
        scenario=fixture,
        structured_result=structured if structured is not None else _structured_result(fixture),
        procedural_result=procedural if procedural is not None else _procedural_result(fixture),
        generation_run_id=GENERATION_RUN_ID,
        query_id=query_id,
        variant=variant,
    )


def test_repaired_variant_emits_strict_candidate_json_parsable_with_combined_evidence() -> None:
    scenario = _scenario()
    before = copy.deepcopy(scenario)

    result = _generate(scenario=scenario)

    assert scenario == before
    assert result.candidate_id == REPAIRED_CANDIDATE_ID
    assert result.model_id == DETERMINISTIC_FIXTURE_MODEL_ID
    assert result.prompt_id == DETERMINISTIC_FIXTURE_PROMPT_ID
    payload = json.loads(result.raw_json)
    assert payload == {
        "ranked_actions": [
            {
                "rank": 1,
                "action": "Inspect the pump inlet of Pump_12 for cavitation",
                "target_asset": "ex:Pump_12",
                "support_evidence": [
                    {"type": "kg_edge", "id": KG_EDGE_ID},
                    {"type": "document_chunk", "id": DOCUMENT_EVIDENCE_ID},
                ],
            }
        ]
    }

    plan = parse_candidate_actions(
        result.raw_json,
        known_assets={ASSET.asset_id},
        evidence_catalog=result.evidence_catalog,
    )
    action = plan.ranked_actions[0]
    assert action.target_asset == ASSET.asset_id
    assert tuple(ref.stable_id for ref in action.support_evidence) == (
        KG_EDGE_ID,
        DOCUMENT_EVIDENCE_ID,
    )
    assert tuple(ref.kind for ref in action.support_evidence) == (
        EvidenceKind.KG_EDGE,
        EvidenceKind.DOCUMENT_CHUNK,
    )


def test_incomplete_variant_emits_fixture_gap_without_repair_and_parser_rejects_target() -> None:
    result = _generate(variant=FixtureModelVariant.INCOMPLETE)

    assert result.candidate_id == INCOMPLETE_CANDIDATE_ID
    assert json.loads(result.raw_json) == {
        "ranked_actions": [
            {
                "rank": 1,
                "action": "Inspect pump inlet for cavitation",
                "target_asset": None,
                "support_evidence": [],
            }
        ]
    }
    with pytest.raises(CandidateActionError) as exc_info:
        parse_candidate_actions(
            result.raw_json,
            known_assets={ASSET.asset_id},
            evidence_catalog=result.evidence_catalog,
        )
    assert exc_info.value.code is CandidateActionErrorCode.INVALID_TARGET_ASSET


def test_repeated_generation_is_deterministic_and_result_records_are_immutable() -> None:
    first = _generate()
    second = _generate()

    assert first == second
    assert hash(first) == hash(second)
    assert isinstance(first.metadata, tuple)
    assert isinstance(first.evidence_catalog.references, tuple)
    with pytest.raises(FrozenInstanceError):
        first.raw_json = "{}"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        first.event.run_id = "changed"  # type: ignore[misc]


def test_metadata_and_stage_event_contain_only_stable_fixture_identifiers() -> None:
    result = _generate()

    assert result.metadata == (
        ("fixture_variant", "repaired"),
        ("fixture_candidate_id", REPAIRED_CANDIDATE_ID),
        ("fixture_model_id", DETERMINISTIC_FIXTURE_MODEL_ID),
        ("fixture_prompt_id", DETERMINISTIC_FIXTURE_PROMPT_ID),
    )
    assert result.event == StageEvent(
        stage=StageName.CANDIDATE_GENERATION,
        run_id=GENERATION_RUN_ID,
        status=TerminalStatus.PASSED,
        duration_ms=0,
        input_ids=(ASSET.asset_id, QUERY_ID, KG_EDGE_ID, DOCUMENT_EVIDENCE_ID),
        output_ids=(REPAIRED_CANDIDATE_ID,),
    )
    metadata_text = repr(result.metadata).casefold()
    forbidden = ("operator", "credential", "provider", "token", "timing", "inference")
    assert "fixture_prompt_id" in metadata_text
    assert all(term not in metadata_text for term in forbidden)


def test_requires_both_retrieval_results_to_have_passed() -> None:
    failed_structured = _structured_result()
    failed_structured = replace(
        failed_structured,
        status=TerminalStatus.INSUFFICIENT_EVIDENCE,
        observations=(),
        support_records=(),
        evidence_references=(),
        evidence_catalog=EvidenceCatalog(()),
        event=StageEvent(
            stage=StageName.STRUCTURED_RETRIEVAL,
            run_id="run-issue-17-structured",
            status=TerminalStatus.INSUFFICIENT_EVIDENCE,
            input_ids=(ASSET.asset_id, QUERY_ID),
            output_ids=(),
            errors=(StageError(StageErrorCode.INSUFFICIENT_EVIDENCE, field="kg_evidence"),),
        ),
    )

    with pytest.raises(FixtureModelAdapterError) as exc_info:
        _generate(structured=failed_structured)
    assert exc_info.value.code is FixtureModelAdapterErrorCode.RETRIEVAL_NOT_PASSED
    assert exc_info.value.field == "structured_result.status"

    failed_procedural = _procedural_result()
    failed_procedural = replace(
        failed_procedural,
        status=TerminalStatus.UNSUPPORTED_LOWER_RANK,
        support_records=(),
        evidence_references=(),
        evidence_catalog=EvidenceCatalog(()),
        event=StageEvent(
            stage=StageName.PROCEDURAL_RETRIEVAL,
            run_id="run-issue-17-procedural",
            status=TerminalStatus.UNSUPPORTED_LOWER_RANK,
            input_ids=(ASSET.asset_id, QUERY_ID),
            output_ids=(),
            errors=(StageError(StageErrorCode.UNSUPPORTED_LOWER_RANK, field="document_evidence"),),
        ),
    )
    with pytest.raises(FixtureModelAdapterError) as exc_info:
        _generate(procedural=failed_procedural)
    assert exc_info.value.code is FixtureModelAdapterErrorCode.RETRIEVAL_NOT_PASSED
    assert exc_info.value.field == "procedural_result.status"


def test_mismatched_retrieval_asset_identity_fails_closed() -> None:
    structured = replace(_structured_result(), asset=KnownAsset("ex:OtherPump", "Other Pump"))
    procedural = _procedural_result()

    with pytest.raises(FixtureModelAdapterError) as exc_info:
        _generate(structured=structured, procedural=procedural)
    assert exc_info.value.code is FixtureModelAdapterErrorCode.IDENTITY_MISMATCH
    assert exc_info.value.field == "asset"


@pytest.mark.parametrize(
    ("event_kwargs", "field"),
    (
        ({"input_ids": ("ex:OtherPump", QUERY_ID)}, "structured_result.event.input_ids"),
        ({"input_ids": (ASSET.asset_id, "query-other")}, "structured_result.event.input_ids"),
    ),
)
def test_structured_stage_event_must_match_caller_asset_and_query_identity(
    event_kwargs: dict[str, object], field: str
) -> None:
    structured = _structured_result()
    structured = replace(structured, event=cast(Any, replace)(structured.event, **event_kwargs))

    with pytest.raises(FixtureModelAdapterError) as exc_info:
        _generate(structured=structured)
    assert exc_info.value.code is FixtureModelAdapterErrorCode.IDENTITY_MISMATCH
    assert exc_info.value.field == field


def test_structured_evidence_retrieval_query_identity_must_match_caller_query() -> None:
    structured = _structured_result()
    reference = structured.evidence_references[0]
    mismatched_reference = replace(
        reference,
        retrieval=RetrievalMetadata(
            retrieval_run_id=reference.retrieval.retrieval_run_id,
            query_id="query-other",
            retriever_name=reference.retrieval.retriever_name,
            rank=reference.retrieval.rank,
            score=reference.retrieval.score,
        ),
    )
    structured = replace(
        structured,
        evidence_references=(mismatched_reference,),
        evidence_catalog=EvidenceCatalog((mismatched_reference,)),
    )

    with pytest.raises(FixtureModelAdapterError) as exc_info:
        _generate(structured=structured)
    assert exc_info.value.code is FixtureModelAdapterErrorCode.IDENTITY_MISMATCH
    assert exc_info.value.field == "structured_result.evidence_references[0].retrieval.query_id"


def test_procedural_stage_event_must_match_caller_asset_and_query_identity() -> None:
    procedural = _procedural_result()
    object.__setattr__(
        procedural,
        "event",
        replace(procedural.event, input_ids=(ASSET.asset_id, "query-other")),
    )

    with pytest.raises(FixtureModelAdapterError) as exc_info:
        _generate(procedural=procedural)
    assert exc_info.value.code is FixtureModelAdapterErrorCode.IDENTITY_MISMATCH
    assert exc_info.value.field == "procedural_result.event.input_ids"


def test_fixture_candidate_ids_must_match_canonical_fixture_ids() -> None:
    expectations = (
        (FixtureModelVariant.REPAIRED, "candidate_actions.repaired.id"),
        (FixtureModelVariant.INCOMPLETE, "candidate_actions.incomplete.id"),
    )
    for variant, field_path in expectations:
        scenario = _scenario()
        scenario["candidate_actions"] = copy.deepcopy(scenario["candidate_actions"])
        scenario["candidate_actions"][variant.value] = copy.deepcopy(
            scenario["candidate_actions"][variant.value]
        )
        scenario["candidate_actions"][variant.value]["id"] = f"{field_path}:mutated"

        with pytest.raises(FixtureModelAdapterError) as exc_info:
            _generate(scenario=scenario, variant=variant)
        assert exc_info.value.code is FixtureModelAdapterErrorCode.INVALID_SCENARIO
        assert exc_info.value.field == field_path


@pytest.mark.parametrize("variant", tuple(FixtureModelVariant))
def test_fixture_candidate_labels_must_match_canonical_fixture_labels(
    variant: FixtureModelVariant,
) -> None:
    scenario = _scenario()
    scenario["candidate_actions"] = copy.deepcopy(scenario["candidate_actions"])
    scenario["candidate_actions"][variant.value] = copy.deepcopy(
        scenario["candidate_actions"][variant.value]
    )
    scenario["candidate_actions"][variant.value]["label"] = "Mutated fixture action"

    with pytest.raises(FixtureModelAdapterError) as exc_info:
        _generate(scenario=scenario, variant=variant)
    assert exc_info.value.code is FixtureModelAdapterErrorCode.INVALID_SCENARIO
    assert exc_info.value.field == f"candidate_actions.{variant.value}.label"


@pytest.mark.parametrize("variant", tuple(FixtureModelVariant))
def test_fixture_candidate_labels_reject_surrounding_whitespace(
    variant: FixtureModelVariant,
) -> None:
    scenario = _scenario()
    scenario["candidate_actions"] = copy.deepcopy(scenario["candidate_actions"])
    scenario["candidate_actions"][variant.value] = copy.deepcopy(
        scenario["candidate_actions"][variant.value]
    )
    canonical_label = scenario["candidate_actions"][variant.value]["label"]
    scenario["candidate_actions"][variant.value]["label"] = f" {canonical_label} "

    with pytest.raises(FixtureModelAdapterError) as exc_info:
        _generate(scenario=scenario, variant=variant)
    assert exc_info.value.code is FixtureModelAdapterErrorCode.INVALID_SCENARIO
    assert exc_info.value.field == f"candidate_actions.{variant.value}.label"


@pytest.mark.parametrize(
    ("field_path", "bad_value"),
    (
        ("candidate_actions", None),
        ("candidate_actions.repaired", None),
        ("candidate_actions.repaired.id", ""),
        ("candidate_actions.repaired.label", ""),
        ("candidate_actions.repaired.target", "ex:OtherPump"),
        ("candidate_actions.repaired.evidence_refs", [KG_EDGE_ID]),
        ("candidate_actions.incomplete.target", "ex:Pump_12"),
        ("candidate_actions.incomplete.evidence_refs", [KG_EDGE_ID]),
    ),
)
def test_fixture_scenario_shape_failures_are_rejected_before_json_emission(
    field_path: str, bad_value: object
) -> None:
    scenario = _scenario()
    parts = field_path.split(".")
    if len(parts) == 1:
        scenario.pop(parts[0])
    else:
        parent: dict[str, Any] = scenario
        for part in parts[:-1]:
            parent[part] = copy.deepcopy(parent[part])
            parent = parent[part]
        if bad_value is None:
            parent.pop(parts[-1])
        else:
            parent[parts[-1]] = bad_value

    variant = (
        FixtureModelVariant.INCOMPLETE
        if ".incomplete." in field_path
        else FixtureModelVariant.REPAIRED
    )

    with pytest.raises(FixtureModelAdapterError) as exc_info:
        _generate(scenario=scenario, variant=variant)
    assert exc_info.value.code is FixtureModelAdapterErrorCode.INVALID_SCENARIO
    assert exc_info.value.field == field_path


def test_input_validation_is_typed_and_fail_fast() -> None:
    scenario = _scenario()
    structured = _structured_result(scenario)
    procedural = _procedural_result(scenario)

    with pytest.raises(TypeError, match="scenario must be a mapping"):
        generate_fixture_candidate_actions(
            scenario=cast(Any, []),
            structured_result=structured,
            procedural_result=procedural,
            generation_run_id=GENERATION_RUN_ID,
            query_id=QUERY_ID,
            variant=FixtureModelVariant.REPAIRED,
        )
    with pytest.raises(TypeError, match="structured_result must be a StructuredRetrievalResult"):
        generate_fixture_candidate_actions(
            scenario=scenario,
            structured_result=cast(Any, object()),
            procedural_result=procedural,
            generation_run_id=GENERATION_RUN_ID,
            query_id=QUERY_ID,
            variant=FixtureModelVariant.REPAIRED,
        )
    with pytest.raises(TypeError, match="procedural_result must be a ProceduralRetrievalResult"):
        generate_fixture_candidate_actions(
            scenario=scenario,
            structured_result=structured,
            procedural_result=cast(Any, object()),
            generation_run_id=GENERATION_RUN_ID,
            query_id=QUERY_ID,
            variant=FixtureModelVariant.REPAIRED,
        )
    with pytest.raises(ValueError, match="generation_run_id must be nonblank"):
        generate_fixture_candidate_actions(
            scenario=scenario,
            structured_result=structured,
            procedural_result=procedural,
            generation_run_id="",
            query_id=QUERY_ID,
            variant=FixtureModelVariant.REPAIRED,
        )
    with pytest.raises(ValueError, match="query_id must not contain surrounding whitespace"):
        generate_fixture_candidate_actions(
            scenario=scenario,
            structured_result=structured,
            procedural_result=procedural,
            generation_run_id=GENERATION_RUN_ID,
            query_id=" query ",
            variant=FixtureModelVariant.REPAIRED,
        )
    with pytest.raises(TypeError, match="variant must be a FixtureModelVariant"):
        generate_fixture_candidate_actions(
            scenario=scenario,
            structured_result=structured,
            procedural_result=procedural,
            generation_run_id=GENERATION_RUN_ID,
            query_id=QUERY_ID,
            variant=cast(Any, "repaired"),
        )


def test_direct_result_rejects_non_candidate_generation_stage_event() -> None:
    result = _generate()
    event = replace(result.event, stage=StageName.PROCEDURAL_RETRIEVAL)

    with pytest.raises(ValueError, match="event.stage must be candidate_generation"):
        replace(result, event=event)


def test_direct_result_rejects_catalog_and_output_contradictions() -> None:
    result = _generate()
    with pytest.raises(
        ValueError, match="evidence catalog references must equal evidence_references"
    ):
        replace(result, evidence_catalog=EvidenceCatalog(()))
    with pytest.raises(ValueError, match="event.output_ids must equal candidate_id"):
        replace(result, event=replace(result.event, output_ids=("ex:OtherCandidate",)))


def test_error_and_result_constructors_reject_wrong_boundary_types() -> None:
    with pytest.raises(TypeError, match="code must be a FixtureModelAdapterErrorCode"):
        FixtureModelAdapterError(cast(Any, "invalid"), "field")

    result = _generate()
    with pytest.raises(TypeError, match="evidence_catalog must be an EvidenceCatalog"):
        replace(result, evidence_catalog=cast(Any, object()))
    with pytest.raises(TypeError, match="event must be a StageEvent"):
        replace(result, event=cast(Any, object()))
    with pytest.raises(TypeError, match="candidate_id must be a string"):
        replace(result, candidate_id=cast(Any, 12))


def test_hostile_post_construction_asset_drift_fails_closed() -> None:
    structured = _structured_result()
    procedural = _procedural_result()
    hostile_asset = object()
    object.__setattr__(structured, "asset", hostile_asset)
    object.__setattr__(procedural, "asset", hostile_asset)

    with pytest.raises(TypeError, match="asset must be a KnownAsset"):
        _generate(structured=structured, procedural=procedural)

    wrong_asset = KnownAsset("ex:OtherPump", "Other Pump")
    object.__setattr__(structured, "asset", wrong_asset)
    object.__setattr__(procedural, "asset", wrong_asset)
    with pytest.raises(FixtureModelAdapterError) as exc_info:
        _generate(structured=structured, procedural=procedural)
    assert exc_info.value.code is FixtureModelAdapterErrorCode.IDENTITY_MISMATCH
    assert exc_info.value.field == "asset"


@pytest.mark.parametrize(
    ("result_kind", "mutation", "field"),
    (
        ("structured", "missing", "structured_result.evidence_references"),
        ("structured", "wrong_id", "structured_result.evidence_references"),
        ("structured", "wrong_kind", "structured_result.evidence_references"),
        ("procedural", "missing", "procedural_result.evidence_references"),
        ("procedural", "wrong_id", "procedural_result.evidence_references"),
        ("procedural", "wrong_kind", "procedural_result.evidence_references"),
    ),
)
def test_hostile_post_construction_evidence_drift_fails_closed(
    result_kind: str, mutation: str, field: str
) -> None:
    structured = _structured_result()
    procedural = _procedural_result()
    result = structured if result_kind == "structured" else procedural
    reference = result.evidence_references[0]
    references: tuple[Any, ...]
    if mutation == "missing":
        references = ()
    elif mutation == "wrong_id":
        references = (replace(reference, stable_id="ex:UnexpectedEvidence"),)
    else:
        wrong_kind = (
            EvidenceKind.DOCUMENT_CHUNK if result_kind == "structured" else EvidenceKind.KG_EDGE
        )
        references = (replace(reference, kind=wrong_kind),)
    object.__setattr__(result, "evidence_references", references)

    with pytest.raises(FixtureModelAdapterError) as exc_info:
        _generate(structured=structured, procedural=procedural)
    assert exc_info.value.code is FixtureModelAdapterErrorCode.IDENTITY_MISMATCH
    assert exc_info.value.field == field


@pytest.mark.parametrize(
    ("field_path", "bad_value"),
    (
        ("candidate_actions.repaired.target", 12),
        ("candidate_actions.repaired.evidence_refs", None),
        ("candidate_actions.repaired.evidence_refs", KG_EDGE_ID),
        ("candidate_actions.repaired.evidence_refs", [KG_EDGE_ID, " "]),
    ),
)
def test_additional_fixture_shape_failures_are_rejected(field_path: str, bad_value: object) -> None:
    scenario = _scenario()
    candidate = copy.deepcopy(scenario["candidate_actions"]["repaired"])
    scenario["candidate_actions"] = copy.deepcopy(scenario["candidate_actions"])
    scenario["candidate_actions"]["repaired"] = candidate
    field = field_path.rsplit(".", maxsplit=1)[1]
    if bad_value is None:
        candidate.pop(field)
    else:
        candidate[field] = bad_value

    with pytest.raises(FixtureModelAdapterError) as exc_info:
        _generate(scenario=scenario)
    assert exc_info.value.code is FixtureModelAdapterErrorCode.INVALID_SCENARIO
    assert exc_info.value.field == field_path


@pytest.mark.parametrize(
    ("event_kwargs", "result_kwargs", "message"),
    (
        ({"status": TerminalStatus.INSUFFICIENT_EVIDENCE}, {}, "event.status must be passed"),
        (
            {"errors": (StageError(StageErrorCode.INSUFFICIENT_EVIDENCE, field="fixture"),)},
            {},
            "passed event must not contain errors",
        ),
        ({"retry_count": 1}, {}, "fixture candidate generation must not retry or repair"),
        ({"repair_count": 1}, {}, "fixture candidate generation must not retry or repair"),
        ({}, {"model_id": "fixture-model:other"}, "model_id must equal"),
        ({}, {"prompt_id": "fixture-prompt:other"}, "prompt_id must equal"),
    ),
)
def test_direct_result_rejects_additional_invariant_drift(
    event_kwargs: dict[str, object], result_kwargs: dict[str, object], message: str
) -> None:
    result = _generate()
    if event_kwargs:
        result_kwargs["event"] = cast(Any, replace)(result.event, **event_kwargs)
    with pytest.raises(ValueError, match=message):
        cast(Any, replace)(result, **result_kwargs)


@pytest.mark.parametrize(
    ("field", "bad_value", "message"),
    (
        ("evidence_references", object(), "evidence_references must be a sequence"),
        (
            "evidence_references",
            (object(),),
            "evidence_references must contain EvidenceReference instances",
        ),
        ("metadata", object(), "metadata must be a sequence"),
        ("metadata", (("only-key",),), "metadata must contain key/value string tuples"),
    ),
)
def test_direct_result_rejects_malformed_collections(
    field: str, bad_value: object, message: str
) -> None:
    with pytest.raises(TypeError, match=message):
        replace(_generate(), **{field: cast(Any, bad_value)})
