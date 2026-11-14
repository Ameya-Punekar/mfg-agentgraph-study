"""Behavior contract for the versioned synthetic-reference label artifact.

The artifact answers one narrow, mechanically checkable question: can every cited reference
identifier be resolved against the frozen scenario fixtures? It deliberately does not claim
independent human annotation, expert review, or inter-annotator agreement.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from mfg_agentgraph.annotation_cli import main as cli_main
from mfg_agentgraph.annotation_sources import SourceManifest, load_source_manifest
from mfg_agentgraph.anomaly_triage_dataset import (
    TRAP_CATEGORIES,
    TRAP_TERMINAL_STATUS,
    QuerySet,
    load_query_set,
)
from mfg_agentgraph.evaluation_harness import EvaluationRunManifest
from mfg_agentgraph.synthetic_reference import (
    SYNTHETIC_REFERENCE_CONTRACT_VERSION,
    ReferenceStrength,
    SyntheticReference,
    SyntheticReferenceEntry,
    build_synthetic_reference,
    inspect_scenario_identifiers,
    load_scenario_fixture,
    require_reference_matches_run,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = REPOSITORY_ROOT / "evaluation" / "anomaly_triage" / "query-set-v1.json"
SOURCES_PATH = REPOSITORY_ROOT / "evaluation" / "anomaly_triage" / "sources-v1.json"
SCENARIO_PATH = REPOSITORY_ROOT / "tests" / "fixtures" / "pump_12" / "scenario.json"


def _query_set() -> QuerySet:
    return load_query_set(DATASET_PATH)


def _manifest() -> SourceManifest:
    return load_source_manifest(SOURCES_PATH, root=REPOSITORY_ROOT)


def _scenario() -> dict[str, object]:
    return load_scenario_fixture(SCENARIO_PATH)


def _reference(**overrides: object) -> SyntheticReference:
    arguments: dict[str, object] = {
        "query_set": _query_set(),
        "scenario": _scenario(),
        "source_manifest": _manifest(),
    }
    arguments.update(overrides)
    return build_synthetic_reference(**arguments)  # type: ignore[arg-type]


def test_fixture_identifiers_include_graph_and_document_evidence() -> None:
    declared, referenced = inspect_scenario_identifiers(_scenario())

    # Both a KG evidence edge and the SOP chunk are declared resources.
    assert "ex:EvidenceEdge_001" in declared
    assert "ex:SOP_Chunk_7" in declared
    assert "Pump 12" not in declared
    assert all(identifier.startswith("ex:") for identifier in declared)
    # A predicate name appears in the fixture but is not a declarable resource, so it must
    # be reported as reference-only rather than treated as evidence.
    assert "ex:hasRecommendedProcedure" in referenced
    assert "ex:hasRecommendedProcedure" not in declared


def test_fixture_identifier_extraction_rejects_non_json_and_blank_ids() -> None:
    with pytest.raises(TypeError, match="scenario must be a mapping"):
        inspect_scenario_identifiers(["ex:Pump_12"])  # type: ignore[arg-type]

    scenario = _scenario()
    scenario["asset"] = {"id": "   "}
    with pytest.raises(ValueError, match="nonblank"):
        inspect_scenario_identifiers(scenario)


def test_scenario_loader_rejects_malformed_documents(tmp_path: Path) -> None:
    broken = tmp_path / "scenario.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        load_scenario_fixture(broken)

    broken.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    with pytest.raises(TypeError, match="must be a mapping"):
        load_scenario_fixture(broken)


def test_reference_covers_every_query_once_in_order() -> None:
    query_set = _query_set()
    reference = _reference()

    assert [entry.query_id for entry in reference.entries] == [
        query.query_id for query in query_set.queries
    ]
    assert reference.query_set_sha256 == query_set.document_sha256
    assert reference.query_set_id == query_set.query_set_id
    assert reference.dataset_id == query_set.dataset_id
    assert reference.document_sha256 == _reference().document_sha256


def test_every_shipped_reference_is_fixture_anchored() -> None:
    reference = _reference()

    assert len(reference.entries) == 30
    assert reference.strength_counts == {
        "fixture_anchored": 26,
        "not_applicable": 4,
        "unanchored": 0,
    }
    for entry in reference.entries:
        assert entry.unresolved_evidence_refs == (), entry.query_id
        if entry.reference_evidence_refs:
            assert entry.strength is ReferenceStrength.FIXTURE_ANCHORED, entry.query_id


def _query_set_with_citation(query_id: str, citation: str) -> QuerySet:
    """Return the shipped query set with one query citing an unknown identifier."""
    query_set = _query_set()
    patched = tuple(
        replace(query, expected_evidence_refs=(citation,)) if query.query_id == query_id else query
        for query in query_set.queries
    )
    return replace(query_set, queries=patched)


def test_citations_absent_from_both_frozen_artifacts_are_unanchored() -> None:
    reference = _reference(query_set=_query_set_with_citation("atq-004", "ex:InventedChunk"))

    entry = next(item for item in reference.entries if item.query_id == "atq-004")
    assert entry.strength is ReferenceStrength.UNANCHORED
    assert entry.unresolved_evidence_refs == ("ex:InventedChunk",)
    assert "ex:InventedChunk" not in reference.resolvable_identifiers
    # Every other citable query is unaffected: one bad citation cannot poison the artifact.
    # The four trap queries cite nothing, so they are not applicable rather than anchored.
    assert reference.strength_counts == {
        "fixture_anchored": 25,
        "not_applicable": 4,
        "unanchored": 1,
    }


def test_a_reference_only_string_cannot_anchor_a_citation() -> None:
    reference = _reference(
        query_set=_query_set_with_citation("atq-001", "ex:hasRecommendedProcedure")
    )

    entry = next(item for item in reference.entries if item.query_id == "atq-001")
    assert entry.strength is ReferenceStrength.UNANCHORED
    assert entry.unresolved_evidence_refs == ("ex:hasRecommendedProcedure",)
    assert "ex:hasRecommendedProcedure" in reference.fixture_reference_only_identifiers
    assert "ex:hasRecommendedProcedure" not in reference.resolvable_identifiers


def test_source_manifest_anchors_a_chunk_the_scenario_fixture_omits() -> None:
    scenario = _scenario()
    scenario.pop("document_evidence", None)

    reference = _reference(scenario=scenario)

    entry = next(item for item in reference.entries if item.query_id == "atq-004")
    assert entry.strength is ReferenceStrength.FIXTURE_ANCHORED
    assert reference.source_manifest_sha256 == _manifest().document_sha256
    assert "ex:SOP_Chunk_7" in reference.resolvable_identifiers


def test_reference_records_trap_strength_without_evidence() -> None:
    reference = _reference()
    traps = [entry for entry in reference.entries if entry.category in TRAP_CATEGORIES]

    assert len(traps) == 4
    for entry in traps:
        assert entry.reference_evidence_refs == ()
        assert entry.reference_action is None
        # An empty citation set cannot be "anchored": there is nothing to resolve.
        assert entry.strength is ReferenceStrength.NOT_APPLICABLE
        assert entry.reference_terminal_status is TRAP_TERMINAL_STATUS[entry.category]


def test_artifact_declares_its_authoring_and_unmet_original_requirement() -> None:
    document = _reference().to_document()

    assert document["contract_version"] == SYNTHETIC_REFERENCE_CONTRACT_VERSION
    authoring = document["authoring"]
    assert isinstance(authoring, dict)
    assert authoring["independent_annotation"] is False
    assert authoring["human_expert_review"] is False
    assert authoring["inter_annotator_agreement"] is None
    requirement_status = document["original_requirement_status"]
    assert isinstance(requirement_status, str)
    assert "unmet" in requirement_status
    assert document["scenario_sha256"] == _reference().scenario_sha256
    scope = document["scope"]
    assert isinstance(scope, str)
    assert "not benchmark gold" in scope
    assert "not independently validated" in scope


def test_artifact_digest_is_stable_and_binds_the_query_set() -> None:
    reference = _reference()
    document = reference.to_document()

    assert reference.to_json() == json.dumps(
        document, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    assert reference.to_document()["query_set_sha256"] == reference.query_set_sha256

    rebuilt = build_synthetic_reference(
        query_set=_query_set(),
        scenario=_scenario(),
        source_manifest=_manifest(),
    )
    assert rebuilt.document_sha256 == reference.document_sha256

    changed_scenario = _scenario()
    changed_scenario["anomaly_window"] = {"started_at": "2026-05-18T14:00:00Z"}
    drifted = build_synthetic_reference(
        query_set=_query_set(),
        scenario=changed_scenario,
        source_manifest=_manifest(),
    )
    # The fixture's own content must bind the artifact: identical identifiers alone must
    # not leave the digest unchanged when the scenario's substance moved.
    assert drifted.scenario_sha256 != reference.scenario_sha256
    assert drifted.document_sha256 != reference.document_sha256


def test_reference_must_match_the_run_dataset_digest() -> None:
    reference = _reference()
    matching = EvaluationRunManifest(
        run_id="run-1",
        repository_revision="c7d5efb",
        harness_version="v1",
        dataset_sha256=reference.query_set_sha256,
    )

    require_reference_matches_run(reference, matching)

    mismatched = EvaluationRunManifest(
        run_id="run-2",
        repository_revision="c7d5efb",
        harness_version="v1",
        dataset_sha256="0" * 64,
    )
    with pytest.raises(ValueError, match="dataset_sha256"):
        require_reference_matches_run(reference, mismatched)


def test_build_rejects_wrong_types_and_an_empty_query_set() -> None:
    with pytest.raises(TypeError, match="source_manifest"):
        build_synthetic_reference(
            query_set=_query_set(),
            scenario=_scenario(),
            source_manifest={"sources": ()},  # type: ignore[arg-type]
        )


def test_cli_writes_a_new_artifact_and_refuses_to_clobber_inputs(tmp_path: Path) -> None:
    output = tmp_path / "synthetic-reference.json"

    exit_code = cli_main(
        [
            "synthetic",
            "--query-set",
            str(DATASET_PATH),
            "--sources",
            str(SOURCES_PATH),
            "--scenario",
            str(SCENARIO_PATH),
            "--root",
            str(REPOSITORY_ROOT),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["contract_version"] == SYNTHETIC_REFERENCE_CONTRACT_VERSION
    assert written["authoring"]["independent_annotation"] is False

    with pytest.raises(ValueError, match="refusing to overwrite"):
        cli_main(
            [
                "synthetic",
                "--query-set",
                str(DATASET_PATH),
                "--sources",
                str(SOURCES_PATH),
                "--scenario",
                str(SCENARIO_PATH),
                "--root",
                str(REPOSITORY_ROOT),
                "--output",
                str(output),
            ]
        )

    with pytest.raises(ValueError, match="must not overwrite an input"):
        cli_main(
            [
                "synthetic",
                "--query-set",
                str(DATASET_PATH),
                "--sources",
                str(SOURCES_PATH),
                "--scenario",
                str(SCENARIO_PATH),
                "--root",
                str(REPOSITORY_ROOT),
                "--output",
                str(DATASET_PATH),
            ]
        )


def test_committed_artifact_matches_what_the_frozen_inputs_derive() -> None:
    """The committed artifact must not drift from its inputs; a hand edit is a red flag.

    This is a provenance guard, not a formatting check: the file is the citable reference,
    so a silent edit that leaves the digests intact would misrepresent the fixtures.
    """
    committed = REPOSITORY_ROOT / "evaluation" / "anomaly_triage" / "synthetic-reference-v2.json"

    derived = _reference()

    assert committed.read_text(encoding="utf-8") == derived.to_json() + "\n"


def test_reference_value_objects_fail_closed() -> None:
    """A malformed reference must not be constructible, or its digest would lie."""
    reference = _reference()
    entry = reference.entries[0]

    with pytest.raises(TypeError, match="category must be a QueryCategory"):
        SyntheticReferenceEntry(
            query_id=entry.query_id,
            category="single_hop",  # type: ignore[arg-type]
            reference_evidence_refs=entry.reference_evidence_refs,
            reference_action=None,
            reference_terminal_status=None,
            strength=ReferenceStrength.FIXTURE_ANCHORED,
            unresolved_evidence_refs=(),
        )
    with pytest.raises(TypeError, match="must be a sequence of identifiers"):
        SyntheticReferenceEntry(
            query_id=entry.query_id,
            category=entry.category,
            reference_evidence_refs="ex:Pump_12",
            reference_action=None,
            reference_terminal_status=None,
            strength=ReferenceStrength.FIXTURE_ANCHORED,
            unresolved_evidence_refs=(),
        )
    with pytest.raises(TypeError, match="strength must be a ReferenceStrength"):
        SyntheticReferenceEntry(
            query_id=entry.query_id,
            category=entry.category,
            reference_evidence_refs=(),
            reference_action=None,
            reference_terminal_status=None,
            strength="fixture_anchored",  # type: ignore[arg-type]
            unresolved_evidence_refs=(),
        )
    with pytest.raises(ValueError, match="nonblank"):
        SyntheticReferenceEntry(
            query_id="   ",
            category=entry.category,
            reference_evidence_refs=(),
            reference_action=None,
            reference_terminal_status=None,
            strength=ReferenceStrength.FIXTURE_ANCHORED,
            unresolved_evidence_refs=(),
        )


def test_reference_artifact_guards_reject_broken_digests_and_duplicates() -> None:
    reference = _reference()
    base: dict[str, object] = {
        "dataset_id": reference.dataset_id,
        "query_set_id": reference.query_set_id,
        "query_set_sha256": reference.query_set_sha256,
        "source_manifest_sha256": reference.source_manifest_sha256,
        "scenario_sha256": reference.scenario_sha256,
        "declared_fixture_identifiers": reference.declared_fixture_identifiers,
        "fixture_reference_only_identifiers": reference.fixture_reference_only_identifiers,
        "resolvable_identifiers": reference.resolvable_identifiers,
        "entries": reference.entries,
    }

    with pytest.raises(ValueError, match="64 lowercase hexadecimal"):
        SyntheticReference(**{**base, "query_set_sha256": "not-a-digest"})  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="must not be empty"):
        SyntheticReference(**{**base, "entries": ()})  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="must be a sequence of SyntheticReferenceEntry"):
        SyntheticReference(**{**base, "entries": "atq-001"})  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="duplicate query_id"):
        SyntheticReference(
            **{**base, "entries": (reference.entries[0], reference.entries[0])}  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="must be a sequence of identifiers"):
        SyntheticReference(**{**base, "resolvable_identifiers": "ex:Pump_12"})  # type: ignore[arg-type]


def test_fixture_guard_rejects_a_scenario_with_no_evidence() -> None:
    with pytest.raises(ValueError, match="no evidence identifiers"):
        inspect_scenario_identifiers({"asset": {"label": "Pump 12"}})

    with pytest.raises(ValueError, match="not a canonical IRI"):
        inspect_scenario_identifiers({"asset": {"id": "ex:Pump 12"}})


def test_build_and_run_guard_reject_wrong_input_types() -> None:
    with pytest.raises(TypeError, match="query_set must be a QuerySet"):
        build_synthetic_reference(
            query_set={"queries": ()},  # type: ignore[arg-type]
            scenario=_scenario(),
            source_manifest=_manifest(),
        )

    reference = _reference()
    with pytest.raises(TypeError, match="reference must be a SyntheticReference"):
        require_reference_matches_run({"query_set_sha256": "0" * 64}, object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="manifest must be an EvaluationRunManifest"):
        require_reference_matches_run(reference, object())  # type: ignore[arg-type]


def test_remaining_guards_reject_wrong_types() -> None:
    with pytest.raises(TypeError, match="path must be a pathlib.Path"):
        load_scenario_fixture(str(SCENARIO_PATH))  # type: ignore[arg-type]

    reference = _reference()
    with pytest.raises(TypeError, match="must be a sequence of SyntheticReferenceEntry"):
        SyntheticReference(
            dataset_id=reference.dataset_id,
            query_set_id=reference.query_set_id,
            query_set_sha256=reference.query_set_sha256,
            source_manifest_sha256=reference.source_manifest_sha256,
            declared_fixture_identifiers=reference.declared_fixture_identifiers,
            fixture_reference_only_identifiers=reference.fixture_reference_only_identifiers,
            scenario_sha256=reference.scenario_sha256,
            resolvable_identifiers=reference.resolvable_identifiers,
            entries=(reference.entries[0], "atq-002"),  # type: ignore[arg-type]
        )


def test_build_rejects_a_non_mapping_scenario() -> None:
    with pytest.raises(TypeError, match="scenario must be a mapping"):
        build_synthetic_reference(
            query_set=_query_set(),
            scenario=["ex:Pump_12"],  # type: ignore[arg-type]
            source_manifest=_manifest(),
        )


def test_reference_rejects_entries_that_contradict_the_resolvable_set() -> None:
    """An artifact must not be constructible with a self-contradicting provenance claim."""
    reference = _reference()
    entry = reference.entries[0]
    base: dict[str, object] = {
        "dataset_id": reference.dataset_id,
        "query_set_id": reference.query_set_id,
        "query_set_sha256": reference.query_set_sha256,
        "source_manifest_sha256": reference.source_manifest_sha256,
        "scenario_sha256": reference.scenario_sha256,
        "declared_fixture_identifiers": reference.declared_fixture_identifiers,
        "fixture_reference_only_identifiers": reference.fixture_reference_only_identifiers,
        "resolvable_identifiers": reference.resolvable_identifiers,
    }

    claiming = SyntheticReferenceEntry(
        query_id="atq-001",
        category=entry.category,
        reference_evidence_refs=("ex:InventedEdge",),
        reference_action=None,
        reference_terminal_status=None,
        strength=ReferenceStrength.FIXTURE_ANCHORED,
        unresolved_evidence_refs=(),
    )
    with pytest.raises(ValueError, match="ex:InventedEdge"):
        SyntheticReference(**{**base, "entries": (claiming,)})  # type: ignore[arg-type]

    # An entry that lists the right unresolved set but calls itself anchored is also refused.
    mislabelled = SyntheticReferenceEntry(
        query_id="atq-001",
        category=entry.category,
        reference_evidence_refs=("ex:InventedEdge",),
        reference_action=None,
        reference_terminal_status=None,
        strength=ReferenceStrength.FIXTURE_ANCHORED,
        unresolved_evidence_refs=("ex:InventedEdge",),
    )
    with pytest.raises(ValueError, match="strength"):
        SyntheticReference(**{**base, "entries": (mislabelled,)})  # type: ignore[arg-type]
