import json
from collections.abc import Collection, Mapping
from typing import Any, cast

import pytest

from mfg_agentgraph.candidate_action import (
    CandidateActionError,
    CandidateActionErrorCode,
    CandidateActionPlan,
    parse_candidate_actions,
)
from mfg_agentgraph.evidence_reference import (
    EvidenceCatalog,
    EvidenceKind,
    EvidenceReference,
    EvidenceValidationStatus,
    RetrievalMetadata,
)


def _reference(
    stable_id: str = "ex:EvidenceEdge_001",
    *,
    kind: EvidenceKind = EvidenceKind.KG_EDGE,
    validation_status: EvidenceValidationStatus = EvidenceValidationStatus.VALIDATED,
) -> EvidenceReference:
    return EvidenceReference(
        kind=kind,
        source="fixture-kg",
        stable_id=stable_id,
        retrieval=RetrievalMetadata(
            retrieval_run_id="retrieval-run-001",
            query_id="query-001",
            retriever_name="fixture-retriever",
            rank=1,
            score=0.83,
        ),
        validation_status=validation_status,
    )


def _catalog(*references: EvidenceReference) -> EvidenceCatalog:
    if not references:
        references = (_reference(),)
    return EvidenceCatalog(references)


def _valid_payload(**action_overrides: object) -> str:
    action = {
        "rank": 1,
        "action": "Inspect pump 12 seal",
        "target_asset": "asset:pump-12",
        "support_evidence": [
            {"type": "kg_edge", "id": "ex:EvidenceEdge_001"},
        ],
    }
    action.update(action_overrides)
    return json.dumps({"ranked_actions": [action]})


def _parse(raw_output: str) -> CandidateActionPlan:
    return parse_candidate_actions(
        raw_output,
        known_assets={"asset:pump-12", "asset:compressor-4"},
        evidence_catalog=_catalog(
            _reference(),
            _reference("doc:SOP_7", kind=EvidenceKind.DOCUMENT_CHUNK),
            _reference("ex:Pump_12", kind=EvidenceKind.KG_RESOURCE),
        ),
    )


def _assert_error(raw_output: str, code: CandidateActionErrorCode) -> None:
    with pytest.raises(CandidateActionError) as exc_info:
        _parse(raw_output)
    assert exc_info.value.code is code
    assert raw_output not in str(exc_info.value)


def _assert_marker_not_retained(
    value: object,
    marker: str,
    *,
    seen: set[int] | None = None,
) -> None:
    if seen is None:
        seen = set()
    if id(value) in seen:
        return
    seen.add(id(value))

    if isinstance(value, str):
        assert marker not in value
        return
    if isinstance(value, bytes):
        assert marker.encode() not in value
        return
    if isinstance(value, BaseException):
        _assert_marker_not_retained(value.args, marker, seen=seen)
        for attr in ("__cause__", "__context__", "__notes__"):
            retained = getattr(value, attr, None)
            if retained is not None:
                _assert_marker_not_retained(retained, marker, seen=seen)
        for attr in getattr(value, "__slots__", ()):
            if hasattr(value, attr):
                _assert_marker_not_retained(getattr(value, attr), marker, seen=seen)
        if hasattr(value, "__dict__"):
            _assert_marker_not_retained(vars(value), marker, seen=seen)
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _assert_marker_not_retained(key, marker, seen=seen)
            _assert_marker_not_retained(item, marker, seen=seen)
        return
    if isinstance(value, Collection) and not isinstance(value, str | bytes):
        for item in value:
            _assert_marker_not_retained(item, marker, seen=seen)


def test_duplicate_json_key_error_does_not_retain_arbitrary_key() -> None:
    marker = "ISSUE13_DUPLICATE_KEY_SECRET_DO_NOT_RETAIN"
    raw_output = f'{{"ranked_actions": [], "{marker}": 1, "{marker}": 2}}'

    with pytest.raises(CandidateActionError) as exc_info:
        _parse(raw_output)

    error = exc_info.value
    assert error.code is CandidateActionErrorCode.DUPLICATE_JSON_KEY
    assert error.field is None
    assert error.__cause__ is None
    assert error.__context__ is None
    _assert_marker_not_retained(error, marker)


def test_invalid_evidence_type_error_does_not_retain_arbitrary_type() -> None:
    marker = "ISSUE13_EVIDENCE_TYPE_SECRET_DO_NOT_RETAIN"
    raw_output = _valid_payload(support_evidence=[{"type": marker, "id": "ex:EvidenceEdge_001"}])

    with pytest.raises(CandidateActionError) as exc_info:
        _parse(raw_output)

    error = exc_info.value
    assert error.code is CandidateActionErrorCode.INVALID_EVIDENCE_REFERENCE
    assert error.field == "type"
    assert error.__cause__ is None
    assert error.__context__ is None
    _assert_marker_not_retained(error, marker)


@pytest.mark.parametrize(
    ("marker", "catalog", "code"),
    [
        (
            "ISSUE13_UNKNOWN_EVIDENCE_ID_SECRET_DO_NOT_RETAIN",
            _catalog(_reference()),
            CandidateActionErrorCode.UNKNOWN_EVIDENCE_ID,
        ),
        (
            "ISSUE13_UNVALIDATED_EVIDENCE_ID_SECRET_DO_NOT_RETAIN",
            _catalog(
                _reference(
                    "ISSUE13_UNVALIDATED_EVIDENCE_ID_SECRET_DO_NOT_RETAIN",
                    validation_status=EvidenceValidationStatus.UNVALIDATED,
                )
            ),
            CandidateActionErrorCode.EVIDENCE_NOT_VALIDATED,
        ),
    ],
)
def test_evidence_resolution_errors_do_not_retain_arbitrary_id(
    marker: str,
    catalog: EvidenceCatalog,
    code: CandidateActionErrorCode,
) -> None:
    raw_output = _valid_payload(support_evidence=[{"type": "kg_edge", "id": marker}])

    with pytest.raises(CandidateActionError) as exc_info:
        parse_candidate_actions(
            raw_output,
            known_assets={"asset:pump-12"},
            evidence_catalog=catalog,
        )

    error = exc_info.value
    assert error.code is code
    assert error.field == "support_evidence"
    assert error.__cause__ is None
    assert error.__context__ is None
    _assert_marker_not_retained(error, marker)


def test_parse_minimal_valid_candidate_action_plan() -> None:
    plan = parse_candidate_actions(
        _valid_payload(),
        known_assets={"asset:pump-12"},
        evidence_catalog=EvidenceCatalog((_reference(),)),
    )

    assert len(plan.ranked_actions) == 1
    action = plan.ranked_actions[0]
    assert action.rank == 1
    assert action.action == "Inspect pump 12 seal"
    assert action.target_asset == "asset:pump-12"
    assert action.support_evidence == (_reference(),)
    assert not hasattr(action, "__dict__")
    with pytest.raises(Exception, match="cannot assign|FrozenInstanceError"):
        action.rank = 2  # type: ignore[misc]


@pytest.mark.parametrize("known_assets", (None, 12))
def test_non_iterable_known_assets_fail_with_typed_error(known_assets: object) -> None:
    with pytest.raises(CandidateActionError) as exc_info:
        parse_candidate_actions(
            _valid_payload(),
            known_assets=cast(Any, known_assets),
            evidence_catalog=_catalog(),
        )

    assert exc_info.value.code is CandidateActionErrorCode.INVALID_TARGET_ASSET
    assert exc_info.value.field == "known_assets"


def test_accepts_valid_payload_wrapped_in_json_whitespace() -> None:
    raw_output = f"\n\t  {_valid_payload()}  \r\n"

    plan = _parse(raw_output)

    assert len(plan.ranked_actions) == 1
    assert plan.ranked_actions[0].rank == 1


def test_malformed_json_error_does_not_retain_raw_output() -> None:
    marker = "ISSUE13_SECRET_MARKER_DO_NOT_RETAIN"
    raw_output = f'{{"ranked_actions": [{marker}'

    with pytest.raises(CandidateActionError) as exc_info:
        _parse(raw_output)

    error = exc_info.value
    assert error.code is CandidateActionErrorCode.MALFORMED_JSON
    assert error.__cause__ is None
    assert marker not in str(error)
    _assert_marker_not_retained(error, marker)


@pytest.mark.parametrize(
    ("raw_output", "code"),
    [
        ("ordinary free-text answer", CandidateActionErrorCode.MALFORMED_JSON),
        ('{"ranked_actions": []} trailing', CandidateActionErrorCode.MALFORMED_JSON),
        ('{"ranked_actions": NaN}', CandidateActionErrorCode.MALFORMED_JSON),
        ('{"ranked_actions": Infinity}', CandidateActionErrorCode.MALFORMED_JSON),
        (
            '{"ranked_actions": [], "ranked_actions": []}',
            CandidateActionErrorCode.DUPLICATE_JSON_KEY,
        ),
        ('[{"ranked_actions": []}]', CandidateActionErrorCode.ROOT_NOT_OBJECT),
        ('{"ranked_actions": []}', CandidateActionErrorCode.EMPTY_RANKED_ACTIONS),
        ('{"ranked_actions": {}, "extra": 1}', CandidateActionErrorCode.INVALID_TOP_LEVEL_FIELDS),
        ('{"ranked_actions": {}}', CandidateActionErrorCode.INVALID_FIELD_TYPE),
    ],
)
def test_rejects_non_strict_json_boundary_failures(
    raw_output: str,
    code: CandidateActionErrorCode,
) -> None:
    _assert_error(raw_output, code)


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (
            {"rank": 1, "action": "Inspect", "target_asset": "asset:pump-12"},
            CandidateActionErrorCode.INVALID_ACTION_FIELDS,
        ),
        (
            {
                "rank": 1,
                "action": "Inspect",
                "target_asset": "asset:pump-12",
                "support_evidence": [],
                "extra": 1,
            },
            CandidateActionErrorCode.INVALID_ACTION_FIELDS,
        ),
        (
            {
                "rank": True,
                "action": "Inspect",
                "target_asset": "asset:pump-12",
                "support_evidence": [{"type": "kg_edge", "id": "ex:EvidenceEdge_001"}],
            },
            CandidateActionErrorCode.INVALID_RANK,
        ),
        (
            {
                "rank": 0,
                "action": "Inspect",
                "target_asset": "asset:pump-12",
                "support_evidence": [{"type": "kg_edge", "id": "ex:EvidenceEdge_001"}],
            },
            CandidateActionErrorCode.INVALID_RANK,
        ),
        (
            {
                "rank": 1,
                "action": "   ",
                "target_asset": "asset:pump-12",
                "support_evidence": [{"type": "kg_edge", "id": "ex:EvidenceEdge_001"}],
            },
            CandidateActionErrorCode.EMPTY_ACTION,
        ),
        (
            {
                "rank": 1,
                "action": "Inspect",
                "target_asset": "   ",
                "support_evidence": [{"type": "kg_edge", "id": "ex:EvidenceEdge_001"}],
            },
            CandidateActionErrorCode.INVALID_TARGET_ASSET,
        ),
        (
            {
                "rank": 1,
                "action": "Inspect",
                "target_asset": "asset:unknown",
                "support_evidence": [{"type": "kg_edge", "id": "ex:EvidenceEdge_001"}],
            },
            CandidateActionErrorCode.UNKNOWN_TARGET_ASSET,
        ),
        (
            {
                "rank": 1,
                "action": "Inspect",
                "target_asset": "asset:pump-12",
                "support_evidence": [],
            },
            CandidateActionErrorCode.EMPTY_SUPPORT_EVIDENCE,
        ),
        (
            {
                "rank": 1,
                "action": "Inspect",
                "target_asset": "asset:pump-12",
                "support_evidence": [{"type": "kg_edge"}],
            },
            CandidateActionErrorCode.INVALID_EVIDENCE_FIELDS,
        ),
        (
            {
                "rank": 1,
                "action": "Inspect",
                "target_asset": "asset:pump-12",
                "support_evidence": [{"type": "kg_edge", "id": 12}],
            },
            CandidateActionErrorCode.INVALID_EVIDENCE_REFERENCE,
        ),
    ],
)
def test_rejects_action_shape_and_scalar_contract_failures(
    payload: dict[str, object],
    code: CandidateActionErrorCode,
) -> None:
    _assert_error(json.dumps({"ranked_actions": [payload]}), code)


@pytest.mark.parametrize(
    ("actions", "code"),
    [
        ([{"rank": 1}, {"rank": 1}], CandidateActionErrorCode.DUPLICATE_RANK),
        ([{"rank": 2}, {"rank": 1}], CandidateActionErrorCode.OUT_OF_ORDER_RANK),
        ([{"rank": 1}, {"rank": 3}], CandidateActionErrorCode.NON_CONTIGUOUS_RANK),
    ],
)
def test_rejects_rank_sequence_contract_failures(
    actions: list[dict[str, int]],
    code: CandidateActionErrorCode,
) -> None:
    full_actions = []
    for action in actions:
        full_action = {
            "rank": action["rank"],
            "action": "Inspect",
            "target_asset": "asset:pump-12",
            "support_evidence": [{"type": "kg_edge", "id": "ex:EvidenceEdge_001"}],
        }
        full_actions.append(full_action)
    _assert_error(json.dumps({"ranked_actions": full_actions}), code)


def test_accepts_multiple_ranked_actions_and_evidence_types_in_rank_order() -> None:
    raw_output = json.dumps(
        {
            "ranked_actions": [
                {
                    "rank": 1,
                    "action": " Inspect pump 12 seal ",
                    "target_asset": " asset:pump-12 ",
                    "support_evidence": [
                        {"type": "kg_edge", "id": "ex:EvidenceEdge_001"},
                        {"type": "document_chunk", "id": "doc:SOP_7"},
                    ],
                },
                {
                    "rank": 2,
                    "action": "Review compressor 4 trend",
                    "target_asset": "asset:compressor-4",
                    "support_evidence": [{"type": "kg_resource", "id": "ex:Pump_12"}],
                },
            ]
        }
    )

    plan = parse_candidate_actions(
        raw_output,
        known_assets={"asset:pump-12", "asset:compressor-4"},
        evidence_catalog=_catalog(
            _reference(),
            _reference("doc:SOP_7", kind=EvidenceKind.DOCUMENT_CHUNK),
            _reference("ex:Pump_12", kind=EvidenceKind.KG_RESOURCE),
        ),
    )

    assert tuple(action.rank for action in plan.ranked_actions) == (1, 2)
    assert plan.ranked_actions[0].action == "Inspect pump 12 seal"
    assert plan.ranked_actions[0].target_asset == "asset:pump-12"
    assert tuple(ref.kind for ref in plan.ranked_actions[0].support_evidence) == (
        EvidenceKind.KG_EDGE,
        EvidenceKind.DOCUMENT_CHUNK,
    )


@pytest.mark.parametrize(
    ("support_evidence", "catalog", "code"),
    [
        (
            [{"type": "kg_edge", "id": "ex:unknown"}],
            _catalog(_reference()),
            CandidateActionErrorCode.UNKNOWN_EVIDENCE_ID,
        ),
        (
            [{"type": "document_chunk", "id": "ex:EvidenceEdge_001"}],
            _catalog(_reference()),
            CandidateActionErrorCode.EVIDENCE_KIND_MISMATCH,
        ),
        (
            [{"type": "kg_edge", "id": "ex:not-valid"}],
            _catalog(
                _reference("ex:not-valid", validation_status=EvidenceValidationStatus.UNVALIDATED)
            ),
            CandidateActionErrorCode.EVIDENCE_NOT_VALIDATED,
        ),
        (
            [
                {"type": "kg_edge", "id": "ex:EvidenceEdge_001"},
                {"type": "document_chunk", "id": "ex:EvidenceEdge_001"},
            ],
            _catalog(_reference()),
            CandidateActionErrorCode.DUPLICATE_EVIDENCE_REFERENCE,
        ),
    ],
)
def test_rejects_evidence_resolution_support_failures(
    support_evidence: list[dict[str, str]],
    catalog: EvidenceCatalog,
    code: CandidateActionErrorCode,
) -> None:
    raw_output = _valid_payload(support_evidence=support_evidence)
    with pytest.raises(CandidateActionError) as exc_info:
        parse_candidate_actions(
            raw_output,
            known_assets={"asset:pump-12"},
            evidence_catalog=catalog,
        )
    assert exc_info.value.code is code
