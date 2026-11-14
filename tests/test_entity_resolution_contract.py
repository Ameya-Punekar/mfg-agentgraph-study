from dataclasses import FrozenInstanceError
from math import inf, nan

import pytest

from mfg_agentgraph.entity_resolution import (
    AssetCatalog,
    KnownAsset,
    MatchKind,
    ResolutionCandidate,
    ResolutionResult,
)
from mfg_agentgraph.stage_instrumentation import TerminalStatus


def _pump(asset_id: str = "ex:Pump_12", *, aliases: tuple[str, ...] = ("Pump_12",)) -> KnownAsset:
    return KnownAsset(asset_id=asset_id, primary_label="Pump 12", aliases=aliases)


def _valve(
    asset_id: str = "ex:Valve_12", *, aliases: tuple[str, ...] = ("Valve_12",)
) -> KnownAsset:
    return KnownAsset(asset_id=asset_id, primary_label="Valve 12", aliases=aliases)


def test_known_asset_enforces_identifier_utf8_byte_limit() -> None:
    assert len(_pump(asset_id="é" * 512).asset_id.encode("utf-8")) == 1_024
    with pytest.raises(ValueError, match="asset_id exceeds"):
        _pump(asset_id="é" * 513)


def test_match_kind_vocabulary_and_tie_break_order_are_stable() -> None:
    assert tuple(kind.value for kind in MatchKind) == (
        "canonical_id",
        "primary_label",
        "registered_alias",
    )


def test_resolves_exact_canonical_id_without_case_normalization() -> None:
    catalog = AssetCatalog((_pump(),))

    result = catalog.resolve("ex:Pump_12")

    assert result.status is TerminalStatus.PASSED
    assert result.selected_asset == _pump()
    assert result.candidates == (
        ResolutionCandidate(
            asset=_pump(),
            match_kind=MatchKind.CANONICAL_ID,
            confidence=1.0,
        ),
    )
    assert catalog.resolve("EX:Pump_12").status is TerminalStatus.OPERATOR_DISAMBIGUATION_REQUIRED
    assert catalog.resolve("EX:Pump_12").candidates == ()
    assert catalog.resolve(" ex:Pump_12 ").status is TerminalStatus.OPERATOR_DISAMBIGUATION_REQUIRED
    assert catalog.resolve(" ex:Pump_12 ").candidates == ()


def test_resolves_exact_pump_12_primary_label() -> None:
    catalog = AssetCatalog((_pump(aliases=()),))

    result = catalog.resolve("Pump 12")

    assert result.status is TerminalStatus.PASSED
    assert result.selected_asset == _pump(aliases=())
    assert result.candidates[0].match_kind is MatchKind.PRIMARY_LABEL
    assert result.candidates[0].confidence == 1.0


def test_resolves_registered_pump_12_alias_only_when_explicitly_registered() -> None:
    catalog = AssetCatalog((_pump(aliases=("Pump_12",)),))

    result = catalog.resolve("Pump_12")

    assert result.status is TerminalStatus.PASSED
    assert result.selected_asset == _pump(aliases=("Pump_12",))
    assert result.candidates[0].match_kind is MatchKind.REGISTERED_ALIAS
    assert result.candidates[0].confidence == 0.9

    unregistered = AssetCatalog((_pump(aliases=()),)).resolve("Pump_12")
    assert unregistered.status is TerminalStatus.OPERATOR_DISAMBIGUATION_REQUIRED
    assert unregistered.selected_asset is None
    assert unregistered.candidates == ()


@pytest.mark.parametrize("term", ["pump 12", " PUMP 12 ", "\tpUmP 12\n"])
def test_human_facing_labels_and_aliases_normalize_surrounding_whitespace_and_case(
    term: str,
) -> None:
    catalog = AssetCatalog((_pump(aliases=("Pump_12",)),))

    result = catalog.resolve(term)

    assert result.status is TerminalStatus.PASSED
    assert result.selected_asset == _pump(aliases=("Pump_12",))
    assert result.candidates[0].match_kind is MatchKind.PRIMARY_LABEL


def test_normalization_does_not_change_internal_whitespace_punctuation_or_guess_fuzzily() -> None:
    catalog = AssetCatalog((_pump(aliases=("Pump_12",)),))

    assert catalog.resolve("Pump   12").candidates == ()
    assert catalog.resolve("Pump-12").candidates == ()
    assert catalog.resolve("Pum 12").candidates == ()


def test_no_match_returns_operator_disambiguation_without_selected_asset() -> None:
    result = AssetCatalog((_pump(),)).resolve("Compressor 7")

    assert result.status is TerminalStatus.OPERATOR_DISAMBIGUATION_REQUIRED
    assert result.selected_asset is None
    assert result.candidates == ()


def test_shared_alias_ambiguity_returns_all_matching_candidates_without_selection() -> None:
    pump = _pump(aliases=("Unit 12",))
    valve = _valve(aliases=("Unit 12",))
    result = AssetCatalog((valve, pump)).resolve("unit 12")

    assert result.status is TerminalStatus.OPERATOR_DISAMBIGUATION_REQUIRED
    assert result.selected_asset is None
    assert result.candidates == (
        ResolutionCandidate(asset=pump, match_kind=MatchKind.REGISTERED_ALIAS, confidence=0.9),
        ResolutionCandidate(asset=valve, match_kind=MatchKind.REGISTERED_ALIAS, confidence=0.9),
    )


def test_sole_candidate_below_threshold_requires_disambiguation_but_retains_candidate() -> None:
    result = AssetCatalog((_pump(aliases=("Pump_12",)),)).resolve("pump_12", min_confidence=0.95)

    assert result.status is TerminalStatus.OPERATOR_DISAMBIGUATION_REQUIRED
    assert result.selected_asset is None
    assert result.candidates == (
        ResolutionCandidate(
            asset=_pump(aliases=("Pump_12",)), match_kind=MatchKind.REGISTERED_ALIAS, confidence=0.9
        ),
    )


def test_deterministic_ordering_and_deduplication_are_independent_of_catalog_input_order() -> None:
    pump = KnownAsset("ex:Pump_12", "ex:Pump_12", aliases=("ex:Pump_12", "Unit 12"))
    valve = KnownAsset("ex:Valve_12", "Valve 12", aliases=("ex:Pump_12",))
    motor = KnownAsset("ex:Motor_12", "ex:Pump_12", aliases=("Unit 12",))

    left = AssetCatalog((valve, pump, motor)).resolve("ex:Pump_12")
    right = AssetCatalog((motor, pump, valve)).resolve("ex:Pump_12")

    assert left == right
    assert left.candidates == (
        ResolutionCandidate(asset=pump, match_kind=MatchKind.CANONICAL_ID, confidence=1.0),
        ResolutionCandidate(asset=motor, match_kind=MatchKind.PRIMARY_LABEL, confidence=1.0),
        ResolutionCandidate(asset=valve, match_kind=MatchKind.REGISTERED_ALIAS, confidence=0.9),
    )


@pytest.mark.parametrize("bad_term", ["", "   ", 12, None])
def test_resolve_rejects_blank_or_non_string_terms(bad_term: object) -> None:
    with pytest.raises((TypeError, ValueError), match="term"):
        AssetCatalog((_pump(),)).resolve(bad_term)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad_threshold", [True, "0.5", -0.1, 1.1, nan, inf, -inf])
def test_resolve_rejects_invalid_thresholds(bad_threshold: object) -> None:
    with pytest.raises((TypeError, ValueError), match="min_confidence"):
        AssetCatalog((_pump(),)).resolve("Pump 12", min_confidence=bad_threshold)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad_assets", [{_pump()}, "ex:Pump_12", None])
def test_catalog_rejects_invalid_asset_containers(bad_assets: object) -> None:
    with pytest.raises(TypeError, match="assets"):
        AssetCatalog(bad_assets)  # type: ignore[arg-type]


def test_catalog_rejects_invalid_asset_elements_and_duplicate_ids() -> None:
    with pytest.raises(TypeError, match="assets"):
        AssetCatalog((_pump(), "ex:Valve_12"))  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="duplicate asset_id"):
        AssetCatalog((_pump(), KnownAsset("ex:Pump_12", "Pump 12 copy")))


@pytest.mark.parametrize(
    ("field", "value", "error_type"),
    [
        ("asset_id", "", ValueError),
        ("asset_id", "   ", ValueError),
        ("asset_id", 12, TypeError),
        ("primary_label", "", ValueError),
        ("primary_label", "   ", ValueError),
        ("primary_label", 12, TypeError),
    ],
)
def test_known_asset_rejects_blank_or_non_string_id_and_label(
    field: str,
    value: object,
    error_type: type[Exception],
) -> None:
    kwargs: dict[str, object] = {"asset_id": "ex:Pump_12", "primary_label": "Pump 12"}
    kwargs[field] = value

    with pytest.raises(error_type, match=field):
        KnownAsset(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad_aliases", ["Pump_12", {"Pump_12"}, None])
def test_known_asset_rejects_invalid_alias_containers(bad_aliases: object) -> None:
    with pytest.raises(TypeError, match="aliases"):
        KnownAsset("ex:Pump_12", "Pump 12", aliases=bad_aliases)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad_alias", ["", "   ", 12])
def test_known_asset_rejects_blank_or_non_string_alias_entries(bad_alias: object) -> None:
    with pytest.raises((TypeError, ValueError), match="aliases"):
        KnownAsset("ex:Pump_12", "Pump 12", aliases=(bad_alias,))  # type: ignore[arg-type]


@pytest.mark.parametrize("asset_id", [" ex:Pump_12", "ex:Pump_12 ", " ex:Pump_12 "])
def test_known_asset_rejects_asset_id_with_surrounding_whitespace(asset_id: str) -> None:
    with pytest.raises(ValueError, match="asset_id"):
        KnownAsset(asset_id, "Pump 12")


def test_catalog_and_aliases_are_normalized_to_immutable_tuples() -> None:
    pump = KnownAsset("ex:Pump_12", " Pump 12 ", aliases=[" Pump_12 "])
    valve = _valve()
    catalog = AssetCatalog([valve, pump])

    assert pump.asset_id == "ex:Pump_12"
    assert pump.primary_label == "Pump 12"
    assert pump.aliases == ("Pump_12",)
    assert isinstance(pump.aliases, tuple)
    assert catalog.assets == (valve, pump)
    assert isinstance(catalog.assets, tuple)


def test_result_values_are_immutable_hashable_and_slotted() -> None:
    asset = _pump()
    candidate = ResolutionCandidate(asset, MatchKind.PRIMARY_LABEL, 1.0)
    result = ResolutionResult(TerminalStatus.PASSED, asset, (candidate,))

    assert hash(asset) == hash(_pump())
    assert hash(candidate) == hash(ResolutionCandidate(_pump(), MatchKind.PRIMARY_LABEL, 1.0))
    assert hash(result) == hash(ResolutionResult(TerminalStatus.PASSED, _pump(), (candidate,)))
    assert not hasattr(asset, "__dict__")
    assert not hasattr(candidate, "__dict__")
    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        result.selected_asset = None  # type: ignore[misc]
