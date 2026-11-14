"""Behavior contract for the versioned anomaly-triage query set."""

from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from mfg_agentgraph.anomaly_triage_dataset import (
    CONTRACT_VERSION,
    EXPECTED_CATEGORY_COUNTS,
    TRAP_CATEGORIES,
    TRAP_TERMINAL_STATUS,
    QueryCategory,
    QueryRecord,
    QuerySet,
    load_query_set,
    parse_query_set_document,
)
from mfg_agentgraph.evaluation_harness import EvaluationRunManifest
from mfg_agentgraph.stage_instrumentation import TerminalStatus

DATASET_PATH = (
    Path(__file__).resolve().parents[1] / "evaluation" / "anomaly_triage" / "query-set-v1.json"
)
SOP_PATH = Path(__file__).resolve().parent / "fixtures" / "sop" / "pump12-sop.txt"
KG_PATH = Path(__file__).resolve().parent / "fixtures" / "fuseki" / "pump12.trig"
TRAP_TOPIC_TERMS = (
    "bearing",
    "grease",
    "vibration",
    "interlock",
    "impeller",
    "disable",
)


def _document() -> dict[str, object]:
    payload: object = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return {str(key): value for key, value in payload.items()}


def _query(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "query_id": "atq-001",
        "category": "single_hop",
        "text": "Which asset produced the anomalous sound?",
        "asset_id": "ex:Pump_12",
        "expected_evidence_refs": ["ex:EvidenceEdge_001"],
        "expected_action": None,
        "expected_terminal_status": None,
        "gold_rubric": "Names Pump_12.",
    }
    payload.update(overrides)
    return payload


def _document_with(query: dict[str, object]) -> dict[str, object]:
    document = _document()
    document["queries"] = [query]
    return document


def test_shipped_query_set_has_stable_ids_categories_and_gold_labels() -> None:
    query_set = load_query_set(DATASET_PATH)

    assert query_set.dataset_id == "mimii-pump12"
    assert query_set.query_set_id == "anomaly-triage-v1"
    assert query_set.version == "v1"
    assert len(query_set.queries) == 30
    assert [query.query_id for query in query_set.queries] == [
        f"atq-{index:03d}" for index in range(1, 31)
    ]
    observed_counts = {category: 0 for category in QueryCategory}
    for query in query_set.queries:
        observed_counts[query.category] += 1
        assert query.text
        assert query.gold_rubric
        assert query.asset_id.startswith("ex:")
        if query.category in TRAP_CATEGORIES:
            assert query.expected_terminal_status is TRAP_TERMINAL_STATUS[query.category]
            assert query.expected_action is None
            assert query.expected_evidence_refs == ()
        else:
            assert query.expected_terminal_status is None
            assert query.expected_evidence_refs
            assert all(ref.startswith("ex:") for ref in query.expected_evidence_refs)
    assert observed_counts == dict(EXPECTED_CATEGORY_COUNTS)


def test_query_set_hash_is_canonical_and_content_addressed(tmp_path: Path) -> None:
    query_set = load_query_set(DATASET_PATH)
    canonical = json.dumps(
        query_set.to_document(),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

    assert query_set.document_sha256 == hashlib.sha256(canonical).hexdigest()
    assert load_query_set(DATASET_PATH).document_sha256 == query_set.document_sha256

    reformatted = tmp_path / "reformatted.json"
    reformatted.write_text(json.dumps(_document(), indent=4), encoding="utf-8")
    changed = tmp_path / "changed.json"
    document = _document()
    queries = document["queries"]
    assert isinstance(queries, list)
    queries[0]["gold_rubric"] = "Different rubric."
    changed.write_text(json.dumps(document), encoding="utf-8")

    assert load_query_set(reformatted).document_sha256 == query_set.document_sha256
    assert load_query_set(changed).document_sha256 != query_set.document_sha256


def test_trap_queries_are_genuine_corpus_absences() -> None:
    query_set = load_query_set(DATASET_PATH)
    corpus = (SOP_PATH.read_text(encoding="utf-8") + KG_PATH.read_text(encoding="utf-8")).lower()

    traps = [query for query in query_set.queries if query.category in TRAP_CATEGORIES]
    assert len(traps) == 4
    for term in TRAP_TOPIC_TERMS:
        assert term not in corpus
    for query in traps:
        assert any(term in query.text.lower() for term in TRAP_TOPIC_TERMS)
        for identifier in ("ex:EvidenceEdge_001", "ex:SOP_Chunk_7"):
            assert identifier not in query.text


def test_document_round_trip_is_immutable_and_canonical() -> None:
    query_set: QuerySet = load_query_set(DATASET_PATH)

    assert isinstance(query_set.queries, tuple)
    assert not hasattr(query_set, "__dict__")
    with pytest.raises(FrozenInstanceError):
        query_set.version = "v2"  # type: ignore[misc]
    assert parse_query_set_document(_document()).document_sha256 == query_set.document_sha256


@pytest.mark.parametrize(
    ("document", "message"),
    [
        (_document_with(_query(query_id="atq-2")), "query_id"),
        (_document_with(_query(category="nonexistent")), "category"),
        (_document_with(_query(category="trap_unsupported")), "terminal_status"),
        (
            _document_with(
                _query(
                    category="trap_unsafe",
                    expected_terminal_status=TerminalStatus.INSUFFICIENT_EVIDENCE.value,
                )
            ),
            "terminal_status",
        ),
        (
            _document_with(
                _query(
                    category="trap_unsupported",
                    expected_terminal_status="insufficient_evidence",
                    expected_evidence_refs=["ex:EvidenceEdge_001"],
                )
            ),
            "evidence_refs",
        ),
        (
            _document_with(
                _query(
                    category="trap_unsupported",
                    expected_terminal_status="insufficient_evidence",
                    expected_action="Inspect the inlet.",
                )
            ),
            "expected_action",
        ),
        (_document_with(_query(expected_evidence_refs=[])), "evidence_refs"),
        (
            _document_with(
                _query(expected_terminal_status=TerminalStatus.INSUFFICIENT_EVIDENCE.value)
            ),
            "terminal_status",
        ),
        (_document_with(_query(text=" ")), "text"),
        (_document_with(_query(gold_rubric="")), "gold_rubric"),
        (_document_with(_query(asset_id="")), "asset_id"),
        (_document_with(_query(expected_evidence_refs=[" "])), "evidence_refs"),
        (
            _document_with(
                _query(expected_evidence_refs=["ex:EvidenceEdge_001", "ex:EvidenceEdge_001"])
            ),
            "evidence_refs",
        ),
        (_document_with(_query(category=1)), "category"),
        (_document_with(_query(text=1)), "text"),
        (_document_with(_query(expected_evidence_refs="ex:EvidenceEdge_001")), "evidence_refs"),
    ],
)
def test_query_validation_fails_closed_on_invalid_fields(
    document: dict[str, object], message: str
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        parse_query_set_document(document)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda document: document.pop("queries"), "queries"),
        (lambda document: document.update(extra="x"), "unknown"),
        (lambda document: document.update(contract_version="other"), "contract_version"),
        (lambda document: document.update(version=""), "version"),
        (lambda document: document.update(dataset_id=""), "dataset_id"),
        (lambda document: document.update(query_set_id=""), "query_set_id"),
        (lambda document: document.update(queries=[]), "queries"),
        (lambda document: document.update(queries={}), "queries"),
        (
            lambda document: document["queries"].append(_query(query_id="atq-001")),
            "duplicate",
        ),
        (
            lambda document: document["queries"].append(_query(query_id="atq-000")),
            "order",
        ),
    ],
)
def test_query_set_validation_fails_closed(mutate: object, message: str) -> None:
    document = _document()
    assert callable(mutate)
    mutate(document)
    with pytest.raises((TypeError, ValueError), match=message):
        parse_query_set_document(document)


def test_loader_rejects_duplicate_json_keys_and_non_object_roots(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text(
        json.dumps(_document()).replace(
            '"dataset_id": "mimii-pump12"',
            '"dataset_id": "mimii-pump12", "dataset_id": "other"',
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_query_set(duplicate)
    with pytest.raises(TypeError, match="mapping"):
        parse_query_set_document([])
    with pytest.raises(TypeError, match="mapping"):
        parse_query_set_document("{}")


def test_shipped_dataset_hash_is_accepted_by_the_run_manifest() -> None:
    query_set = load_query_set(DATASET_PATH)
    manifest = EvaluationRunManifest(
        run_id="run-s3",
        repository_revision="7bb2f4c",
        harness_version="v1",
        dataset_sha256=query_set.document_sha256,
    )

    assert manifest.to_dict()["dataset_sha256"] == query_set.document_sha256


def test_query_record_is_a_frozen_slotted_value() -> None:
    record = QueryRecord(
        query_id="atq-001",
        category=QueryCategory.SINGLE_HOP,
        text="Which asset produced the anomalous sound?",
        asset_id="ex:Pump_12",
        expected_evidence_refs=["ex:EvidenceEdge_001"],
        expected_action=None,
        expected_terminal_status=None,
        gold_rubric="Names Pump_12.",
    )

    assert record.expected_evidence_refs == ("ex:EvidenceEdge_001",)
    assert not hasattr(record, "__dict__")
    with pytest.raises(FrozenInstanceError):
        record.text = "other"  # type: ignore[misc]
    assert CONTRACT_VERSION in json.dumps(_document())
