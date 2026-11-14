"""Strict candidate-action JSON boundary before RDF/SHACL mapping."""

import json
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import NoReturn

from mfg_agentgraph.evidence_reference import (
    EvidenceCatalog,
    EvidenceKind,
    EvidenceReference,
    EvidenceReferenceResolutionCode,
    EvidenceReferenceResolutionError,
)


class CandidateActionErrorCode(StrEnum):
    """Stable machine-readable candidate-action validation failure codes."""

    MALFORMED_JSON = "malformed_json"
    DUPLICATE_JSON_KEY = "duplicate_json_key"
    ROOT_NOT_OBJECT = "root_not_object"
    INVALID_TOP_LEVEL_FIELDS = "invalid_top_level_fields"
    INVALID_FIELD_TYPE = "invalid_field_type"
    EMPTY_RANKED_ACTIONS = "empty_ranked_actions"
    INVALID_ACTION_FIELDS = "invalid_action_fields"
    INVALID_RANK = "invalid_rank"
    DUPLICATE_RANK = "duplicate_rank"
    OUT_OF_ORDER_RANK = "out_of_order_rank"
    NON_CONTIGUOUS_RANK = "non_contiguous_rank"
    EMPTY_ACTION = "empty_action"
    INVALID_TARGET_ASSET = "invalid_target_asset"
    UNKNOWN_TARGET_ASSET = "unknown_target_asset"
    EMPTY_SUPPORT_EVIDENCE = "empty_support_evidence"
    INVALID_EVIDENCE_FIELDS = "invalid_evidence_fields"
    INVALID_EVIDENCE_REFERENCE = "invalid_evidence_reference"
    UNKNOWN_EVIDENCE_ID = "unknown_evidence_id"
    EVIDENCE_KIND_MISMATCH = "evidence_kind_mismatch"
    EVIDENCE_NOT_VALIDATED = "evidence_not_validated"
    DUPLICATE_EVIDENCE_REFERENCE = "duplicate_evidence_reference"


class CandidateActionError(ValueError):
    """Deterministic candidate-action boundary error without raw model output."""

    __slots__ = ("code", "field")

    def __init__(self, code: CandidateActionErrorCode, field: str | None = None) -> None:
        if not isinstance(code, CandidateActionErrorCode):
            raise TypeError("code must be a CandidateActionErrorCode")
        self.code = code
        self.field = field
        message = code.value if field is None else f"{code.value}: {field}"
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class CandidateAction:
    """Immutable ranked action with resolved validated support evidence."""

    rank: int
    action: str
    target_asset: str
    support_evidence: tuple[EvidenceReference, ...]


@dataclass(frozen=True, slots=True)
class CandidateActionPlan:
    """Immutable candidate action plan suitable for later RDF mapping."""

    ranked_actions: tuple[CandidateAction, ...]


def parse_candidate_actions(
    raw_output: str,
    *,
    known_assets: Collection[str],
    evidence_catalog: EvidenceCatalog,
) -> CandidateActionPlan:
    """Parse a strict candidate-action JSON payload into immutable typed records."""

    if not isinstance(raw_output, str):
        raise CandidateActionError(CandidateActionErrorCode.MALFORMED_JSON)
    if isinstance(known_assets, str) or not isinstance(known_assets, Collection):
        raise CandidateActionError(CandidateActionErrorCode.INVALID_TARGET_ASSET, "known_assets")
    if not isinstance(evidence_catalog, EvidenceCatalog):
        raise TypeError("evidence_catalog must be an EvidenceCatalog")

    payload = _loads_strict(raw_output)
    if not isinstance(payload, Mapping):
        raise CandidateActionError(CandidateActionErrorCode.ROOT_NOT_OBJECT)
    if set(payload) != {"ranked_actions"}:
        raise CandidateActionError(CandidateActionErrorCode.INVALID_TOP_LEVEL_FIELDS)

    ranked_actions = payload["ranked_actions"]
    if isinstance(ranked_actions, str) or not isinstance(ranked_actions, Sequence):
        raise CandidateActionError(CandidateActionErrorCode.INVALID_FIELD_TYPE, "ranked_actions")
    if not ranked_actions:
        raise CandidateActionError(CandidateActionErrorCode.EMPTY_RANKED_ACTIONS)

    normalized_known_assets = _normalize_known_assets(known_assets)
    actions: list[CandidateAction] = []
    seen_ranks: set[int] = set()
    for index, raw_action in enumerate(ranked_actions, start=1):
        action = _parse_action(
            raw_action,
            index=index,
            known_assets=normalized_known_assets,
            evidence_catalog=evidence_catalog,
        )
        if action.rank in seen_ranks:
            raise CandidateActionError(CandidateActionErrorCode.DUPLICATE_RANK, "rank")
        seen_ranks.add(action.rank)
        actions.append(action)

    ranks = [action.rank for action in actions]
    expected_ranks = list(range(1, len(actions) + 1))
    if sorted(ranks) != expected_ranks:
        raise CandidateActionError(CandidateActionErrorCode.NON_CONTIGUOUS_RANK, "rank")
    if ranks != expected_ranks:
        raise CandidateActionError(CandidateActionErrorCode.OUT_OF_ORDER_RANK, "rank")

    return CandidateActionPlan(tuple(actions))


def _loads_strict(raw_output: str) -> object:
    decoder = json.JSONDecoder(
        object_pairs_hook=_reject_duplicate_object_keys, parse_constant=_reject_constant
    )
    malformed_json = False
    try:
        return decoder.decode(raw_output)
    except CandidateActionError:
        raise
    except json.JSONDecodeError:
        malformed_json = True
    if malformed_json:
        raise CandidateActionError(CandidateActionErrorCode.MALFORMED_JSON)
    raise AssertionError("unreachable")


def _reject_duplicate_object_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise CandidateActionError(CandidateActionErrorCode.DUPLICATE_JSON_KEY)
        result[key] = value
    return result


def _reject_constant(_value: str) -> NoReturn:
    raise CandidateActionError(CandidateActionErrorCode.MALFORMED_JSON)


def _normalize_known_assets(known_assets: Collection[str]) -> frozenset[str]:
    normalized: set[str] = set()
    for asset in known_assets:
        if not isinstance(asset, str):
            raise CandidateActionError(
                CandidateActionErrorCode.INVALID_TARGET_ASSET, "known_assets"
            )
        stripped = asset.strip()
        if not stripped:
            raise CandidateActionError(
                CandidateActionErrorCode.INVALID_TARGET_ASSET, "known_assets"
            )
        normalized.add(stripped)
    return frozenset(normalized)


def _parse_action(
    raw_action: object,
    *,
    index: int,
    known_assets: frozenset[str],
    evidence_catalog: EvidenceCatalog,
) -> CandidateAction:
    if not isinstance(raw_action, Mapping):
        raise CandidateActionError(
            CandidateActionErrorCode.INVALID_FIELD_TYPE, f"ranked_actions[{index}]"
        )
    if set(raw_action) != {"rank", "action", "target_asset", "support_evidence"}:
        raise CandidateActionError(
            CandidateActionErrorCode.INVALID_ACTION_FIELDS, f"ranked_actions[{index}]"
        )

    rank = raw_action["rank"]
    if not isinstance(rank, int) or isinstance(rank, bool) or rank < 1:
        raise CandidateActionError(CandidateActionErrorCode.INVALID_RANK, "rank")

    action = raw_action["action"]
    if not isinstance(action, str):
        raise CandidateActionError(CandidateActionErrorCode.INVALID_FIELD_TYPE, "action")
    normalized_action = action.strip()
    if not normalized_action:
        raise CandidateActionError(CandidateActionErrorCode.EMPTY_ACTION, "action")

    target_asset = raw_action["target_asset"]
    if not isinstance(target_asset, str):
        raise CandidateActionError(CandidateActionErrorCode.INVALID_TARGET_ASSET, "target_asset")
    normalized_target_asset = target_asset.strip()
    if not normalized_target_asset:
        raise CandidateActionError(CandidateActionErrorCode.INVALID_TARGET_ASSET, "target_asset")
    if normalized_target_asset not in known_assets:
        raise CandidateActionError(CandidateActionErrorCode.UNKNOWN_TARGET_ASSET, "target_asset")

    support_evidence = _parse_support_evidence(raw_action["support_evidence"], evidence_catalog)
    return CandidateAction(
        rank=rank,
        action=normalized_action,
        target_asset=normalized_target_asset,
        support_evidence=support_evidence,
    )


def _parse_support_evidence(
    raw_support: object,
    evidence_catalog: EvidenceCatalog,
) -> tuple[EvidenceReference, ...]:
    if isinstance(raw_support, str) or not isinstance(raw_support, Sequence):
        raise CandidateActionError(CandidateActionErrorCode.INVALID_FIELD_TYPE, "support_evidence")
    if not raw_support:
        raise CandidateActionError(
            CandidateActionErrorCode.EMPTY_SUPPORT_EVIDENCE, "support_evidence"
        )

    declared_kinds: list[EvidenceKind] = []
    stable_ids: list[str] = []
    seen_refs: set[str] = set()
    for raw_reference in raw_support:
        if not isinstance(raw_reference, Mapping):
            raise CandidateActionError(CandidateActionErrorCode.INVALID_EVIDENCE_REFERENCE)
        if set(raw_reference) != {"type", "id"}:
            raise CandidateActionError(CandidateActionErrorCode.INVALID_EVIDENCE_FIELDS)
        kind = _parse_evidence_kind(raw_reference["type"])
        stable_id = raw_reference["id"]
        if not isinstance(stable_id, str) or not stable_id.strip():
            raise CandidateActionError(CandidateActionErrorCode.INVALID_EVIDENCE_REFERENCE, "id")
        normalized_stable_id = stable_id.strip()
        if normalized_stable_id in seen_refs:
            raise CandidateActionError(CandidateActionErrorCode.DUPLICATE_EVIDENCE_REFERENCE)
        seen_refs.add(normalized_stable_id)
        declared_kinds.append(kind)
        stable_ids.append(normalized_stable_id)

    mapped_error: CandidateActionError | None = None
    try:
        resolved = evidence_catalog.resolve_validated_support(tuple(stable_ids))
    except EvidenceReferenceResolutionError as exc:
        mapped_error = _map_evidence_error(exc)
    if mapped_error is not None:
        raise mapped_error

    for declared_kind, reference in zip(declared_kinds, resolved, strict=True):
        if reference.kind is not declared_kind:
            raise CandidateActionError(
                CandidateActionErrorCode.EVIDENCE_KIND_MISMATCH, "support_evidence"
            )
    return resolved


def _parse_evidence_kind(value: object) -> EvidenceKind:
    if not isinstance(value, str):
        raise CandidateActionError(CandidateActionErrorCode.INVALID_EVIDENCE_REFERENCE, "type")
    invalid_kind = False
    try:
        return EvidenceKind(value.strip())
    except ValueError:
        invalid_kind = True
    if invalid_kind:
        raise CandidateActionError(CandidateActionErrorCode.INVALID_EVIDENCE_REFERENCE, "type")
    raise AssertionError("unreachable")


def _map_evidence_error(error: EvidenceReferenceResolutionError) -> CandidateActionError:
    if error.code is EvidenceReferenceResolutionCode.UNKNOWN_EVIDENCE_ID:
        return CandidateActionError(
            CandidateActionErrorCode.UNKNOWN_EVIDENCE_ID, "support_evidence"
        )
    if error.code is EvidenceReferenceResolutionCode.EVIDENCE_NOT_VALIDATED:
        return CandidateActionError(
            CandidateActionErrorCode.EVIDENCE_NOT_VALIDATED, "support_evidence"
        )
    return CandidateActionError(
        CandidateActionErrorCode.INVALID_EVIDENCE_REFERENCE, "support_evidence"
    )
