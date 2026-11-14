"""Deterministic entity/asset resolution over an explicit in-memory catalog."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from math import isfinite

from mfg_agentgraph.stage_instrumentation import TerminalStatus


class MatchKind(StrEnum):
    """Deterministic asset match kinds in stable strongest-to-weakest order."""

    CANONICAL_ID = "canonical_id"
    PRIMARY_LABEL = "primary_label"
    REGISTERED_ALIAS = "registered_alias"


_MATCH_KIND_RANK: dict[MatchKind, int] = {
    MatchKind.CANONICAL_ID: 0,
    MatchKind.PRIMARY_LABEL: 1,
    MatchKind.REGISTERED_ALIAS: 2,
}
_MAX_IDENTIFIER_BYTES = 1_024


@dataclass(frozen=True, slots=True)
class KnownAsset:
    """Known asset with one canonical ID, one primary label, and explicit aliases."""

    asset_id: str
    primary_label: str
    aliases: Sequence[str] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset_id", _require_strict_nonblank(self.asset_id, "asset_id"))
        object.__setattr__(
            self,
            "primary_label",
            _require_nonblank(self.primary_label, "primary_label"),
        )
        object.__setattr__(self, "aliases", _normalize_strings(self.aliases, "aliases"))


@dataclass(frozen=True, slots=True)
class ResolutionCandidate:
    """One transparent candidate produced by deterministic catalog lookup."""

    asset: KnownAsset
    match_kind: MatchKind
    confidence: float

    def __post_init__(self) -> None:
        if not isinstance(self.asset, KnownAsset):
            raise TypeError("asset must be a KnownAsset")
        if not isinstance(self.match_kind, MatchKind):
            raise TypeError("match_kind must be a MatchKind")
        object.__setattr__(
            self,
            "confidence",
            _normalize_confidence(self.confidence, "confidence"),
        )


@dataclass(frozen=True, slots=True)
class ResolutionResult:
    """Resolution outcome using S4 terminal statuses."""

    status: TerminalStatus
    selected_asset: KnownAsset | None
    candidates: Sequence[ResolutionCandidate] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.status, TerminalStatus):
            raise TypeError("status must be a TerminalStatus")
        if self.selected_asset is not None and not isinstance(self.selected_asset, KnownAsset):
            raise TypeError("selected_asset must be a KnownAsset or None")
        object.__setattr__(self, "candidates", self._normalize_candidates(self.candidates))

    @staticmethod
    def _normalize_candidates(
        candidates: Sequence[ResolutionCandidate],
    ) -> tuple[ResolutionCandidate, ...]:
        if isinstance(candidates, str) or not isinstance(candidates, Sequence):
            raise TypeError("candidates must be a sequence of ResolutionCandidate instances")
        normalized: list[ResolutionCandidate] = []
        for candidate in candidates:
            if not isinstance(candidate, ResolutionCandidate):
                raise TypeError("candidates must contain ResolutionCandidate instances")
            normalized.append(candidate)
        return tuple(normalized)


@dataclass(frozen=True, slots=True)
class AssetCatalog:
    """Tuple-backed deterministic asset catalog."""

    assets: Sequence[KnownAsset] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if isinstance(self.assets, str) or not isinstance(self.assets, Sequence):
            raise TypeError("assets must be a sequence of KnownAsset instances")
        normalized: list[KnownAsset] = []
        seen_asset_ids: set[str] = set()
        for asset in self.assets:
            if not isinstance(asset, KnownAsset):
                raise TypeError("assets must contain KnownAsset instances")
            if asset.asset_id in seen_asset_ids:
                raise ValueError(f"duplicate asset_id: {asset.asset_id}")
            seen_asset_ids.add(asset.asset_id)
            normalized.append(asset)
        object.__setattr__(self, "assets", tuple(normalized))

    def resolve(self, term: str, *, min_confidence: float = 0.0) -> ResolutionResult:
        """Resolve a term against only canonical IDs, primary labels, and registered aliases."""

        _validate_nonblank_string(term, "term")
        threshold = _normalize_confidence(min_confidence, "min_confidence")
        candidates = self._matching_candidates(term)
        if len(candidates) == 1 and candidates[0].confidence >= threshold:
            return ResolutionResult(TerminalStatus.PASSED, candidates[0].asset, candidates)
        return ResolutionResult(
            TerminalStatus.OPERATOR_DISAMBIGUATION_REQUIRED,
            None,
            candidates,
        )

    def _matching_candidates(self, term: str) -> tuple[ResolutionCandidate, ...]:
        strongest_by_asset_id: dict[str, ResolutionCandidate] = {}
        normalized_human_term = _normalize_human_facing(term)
        for asset in self.assets:
            candidate = _candidate_for_asset(asset, term, normalized_human_term)
            if candidate is None:
                continue
            current = strongest_by_asset_id.get(asset.asset_id)
            if current is None or _candidate_sort_key(candidate) < _candidate_sort_key(current):
                strongest_by_asset_id[asset.asset_id] = candidate
        return tuple(sorted(strongest_by_asset_id.values(), key=_candidate_sort_key))


def _candidate_for_asset(
    asset: KnownAsset,
    term: str,
    normalized_human_term: str,
) -> ResolutionCandidate | None:
    if term == asset.asset_id:
        return ResolutionCandidate(asset, MatchKind.CANONICAL_ID, 1.0)
    if normalized_human_term == _normalize_human_facing(asset.primary_label):
        return ResolutionCandidate(asset, MatchKind.PRIMARY_LABEL, 1.0)
    if normalized_human_term in {_normalize_human_facing(alias) for alias in asset.aliases}:
        return ResolutionCandidate(asset, MatchKind.REGISTERED_ALIAS, 0.9)
    return None


def _candidate_sort_key(candidate: ResolutionCandidate) -> tuple[int, str]:
    return (_MATCH_KIND_RANK[candidate.match_kind], candidate.asset.asset_id)


def _validate_nonblank_string(value: object, field_name: str) -> None:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must be nonblank")
    if len(value.encode("utf-8")) > _MAX_IDENTIFIER_BYTES:
        raise ValueError(f"{field_name} exceeds the identifier byte limit")


def _require_nonblank(value: object, field_name: str) -> str:
    _validate_nonblank_string(value, field_name)
    assert isinstance(value, str)
    return value.strip()


def _require_strict_nonblank(value: object, field_name: str) -> str:
    _validate_nonblank_string(value, field_name)
    assert isinstance(value, str)
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")
    return value


def _normalize_strings(values: Sequence[str], field_name: str) -> tuple[str, ...]:
    if isinstance(values, str) or not isinstance(values, Sequence):
        raise TypeError(f"{field_name} must be a sequence of strings")
    return tuple(_require_nonblank(value, field_name) for value in values)


def _normalize_human_facing(value: str) -> str:
    return value.strip().casefold()


def _normalize_confidence(value: object, field_name: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be a finite numeric value")
    normalized = float(value)
    if not isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    if not 0.0 <= normalized <= 1.0:
        raise ValueError(f"{field_name} must be between 0.0 and 1.0")
    return normalized
