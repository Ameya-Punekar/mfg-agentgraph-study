"""Human gold is the annotator consensus; author labels are a recorded cross-check only."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from mfg_agentgraph.annotation_cli import main as cli_main
from mfg_agentgraph.annotation_sources import SourceManifest, load_source_manifest
from mfg_agentgraph.anomaly_triage_dataset import QueryCategory, QuerySet, load_query_set
from mfg_agentgraph.gold_annotation import (
    ANNOTATION_CONTRACT_VERSION,
    AnnotationPacket,
    AnnotationSubmission,
    build_agreement_report,
    build_annotation_packet,
    parse_annotation_submission,
)
from mfg_agentgraph.human_gold import (
    ADJUDICATION_CONTRACT_VERSION,
    HUMAN_GOLD_CONTRACT_VERSION,
    AdjudicationRecord,
    build_human_gold,
    load_adjudication_record,
    parse_adjudication_record,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = REPOSITORY_ROOT / "evaluation" / "anomaly_triage" / "query-set-v1.json"
SOURCES_PATH = REPOSITORY_ROOT / "evaluation" / "anomaly_triage" / "sources-v1.json"


def _query_set() -> QuerySet:
    return load_query_set(DATASET_PATH)


def _manifest() -> SourceManifest:
    return load_source_manifest(SOURCES_PATH, root=REPOSITORY_ROOT)


def _packet() -> AnnotationPacket:
    return build_annotation_packet(_query_set(), manifest=_manifest())


def _judgment(query_id: str, support: str, evidence: list[str] | None = None) -> dict[str, object]:
    return {
        "action": None,
        "evidence_refs": [] if evidence is None else evidence,
        "query_id": query_id,
        "rubric": "Rubric text.",
        "support": support,
    }


def _submission(
    annotator_id: str, judgments: list[dict[str, object]], *, packet: AnnotationPacket
) -> AnnotationSubmission:
    document = {
        "annotator_id": annotator_id,
        "contract_version": ANNOTATION_CONTRACT_VERSION,
        "judgments": judgments,
        "manifest_sha256": packet.manifest_sha256,
        "packet_sha256": packet.document_sha256,
        "query_set_sha256": packet.query_set_sha256,
    }
    return parse_annotation_submission(document, packet=packet)


def _uniform(annotator_id: str, packet: AnnotationPacket, support: str) -> AnnotationSubmission:
    return _submission(
        annotator_id,
        [_judgment(query.query_id, support) for query in packet.queries],
        packet=packet,
    )


def _agreeing_submissions(packet: AnnotationPacket) -> list[AnnotationSubmission]:
    return [
        _uniform("annotator-a", packet, "unsupported"),
        _uniform("annotator-b", packet, "unsupported"),
    ]


def _disputed_submissions(
    packet: AnnotationPacket, index: int, support: str
) -> list[AnnotationSubmission]:
    first = [_judgment(query.query_id, "unsupported") for query in packet.queries]
    second = list(first)
    second[index] = _judgment(packet.queries[index].query_id, support)
    return [
        _submission("annotator-a", first, packet=packet),
        _submission("annotator-b", second, packet=packet),
    ]


def _adjudication(
    query_id: str, support: str, evidence: list[str] | None = None
) -> AdjudicationRecord:
    return parse_adjudication_record(
        {
            "adjudicator_id": "adjudicator-x",
            "contract_version": ADJUDICATION_CONTRACT_VERSION,
            "decisions": [
                {
                    "action": None,
                    "evidence_refs": [] if evidence is None else evidence,
                    "query_id": query_id,
                    "rationale": "Sources were re-read together.",
                    "support": support,
                }
            ],
        }
    )


def _records(document: dict[str, object], key: str) -> list[dict[str, object]]:
    value = document[key]
    assert isinstance(value, list)
    records: list[dict[str, object]] = []
    for item in value:
        assert isinstance(item, dict)
        records.append({str(name): entry for name, entry in item.items()})
    return records


def _mapping(document: dict[str, object], key: str) -> dict[str, object]:
    value = document[key]
    assert isinstance(value, dict)
    return {str(name): entry for name, entry in value.items()}


def test_unanimous_submissions_produce_gold_and_record_the_author_cross_check() -> None:
    packet = _packet()
    gold = build_human_gold(
        query_set=_query_set(), packet=packet, submissions=_agreeing_submissions(packet)
    )
    document = gold.to_document()

    assert document["contract_version"] == HUMAN_GOLD_CONTRACT_VERSION
    assert document["annotator_ids"] == ["annotator-a", "annotator-b"]
    assert document["query_set_sha256"] == packet.query_set_sha256
    assert document["manifest_sha256"] == packet.manifest_sha256
    assert document["packet_sha256"] == packet.document_sha256

    queries = _records(document, "queries")
    assert len(queries) == len(packet.queries)
    assert all(record["status"] == "unanimous" for record in queries)
    assert all(record["support"] == "unsupported" for record in queries)

    comparison = _mapping(document, "author_label_cross_check")
    # Author view: 26 supported, 2 trap_unsupported, 2 trap_unsafe. Every annotator said
    # unsupported, so only the two trap_unsupported queries agree with the author view.
    assert comparison["agreement_count"] == 2
    disagreements = comparison["disagreement_query_ids"]
    assert isinstance(disagreements, list)
    assert len(disagreements) == 28

    by_id = {record["query_id"]: record for record in queries}
    dissent = str(disagreements[0])
    assert by_id[dissent]["support"] == "unsupported"
    assert by_id[dissent]["author_support_cross_check"] == "supported"


def test_disputed_queries_must_be_adjudicated_before_gold_exists() -> None:
    packet = _packet()
    submissions = _disputed_submissions(packet, 0, "unsafe_request")

    with pytest.raises(ValueError, match="unadjudicated"):
        build_human_gold(query_set=_query_set(), packet=packet, submissions=submissions)


def test_adjudication_resolves_a_dispute_and_is_recorded_separately() -> None:
    packet = _packet()
    disputed_id = packet.queries[0].query_id
    submissions = _disputed_submissions(packet, 0, "unsafe_request")

    gold = build_human_gold(
        query_set=_query_set(),
        packet=packet,
        submissions=submissions,
        adjudication=_adjudication(disputed_id, "unsafe_request"),
    )
    document = gold.to_document()
    by_id = {record["query_id"]: record for record in _records(document, "queries")}

    assert by_id[disputed_id]["status"] == "adjudicated"
    assert by_id[disputed_id]["support"] == "unsafe_request"
    decisions = _records(document, "adjudication")
    assert decisions[0]["query_id"] == disputed_id
    assert decisions[0]["adjudicator_id"] == "adjudicator-x"
    agreement = _mapping(document, "agreement")
    assert agreement["query_count"] == len(packet.queries)

    # An adjudication that cites an allowed evidence identifier is accepted as-is.
    supported = build_human_gold(
        query_set=_query_set(),
        packet=packet,
        submissions=submissions,
        adjudication=_adjudication(disputed_id, "supported", ["ex:SOP_Chunk_7"]),
    )
    supported_records = {
        record["query_id"]: record for record in _records(supported.to_document(), "queries")
    }
    assert supported_records[disputed_id]["support"] == "supported"
    assert supported_records[disputed_id]["evidence_refs"] == ["ex:SOP_Chunk_7"]


def test_adjudication_must_target_a_real_dispute_and_the_frozen_manifest() -> None:
    packet = _packet()
    agreed = _agreeing_submissions(packet)

    with pytest.raises(ValueError, match="not disputed"):
        build_human_gold(
            query_set=_query_set(),
            packet=packet,
            submissions=agreed,
            adjudication=_adjudication(packet.queries[0].query_id, "unsupported"),
        )

    disputed_id = packet.queries[1].query_id
    with pytest.raises(ValueError, match="frozen source manifest"):
        build_human_gold(
            query_set=_query_set(),
            packet=packet,
            submissions=_disputed_submissions(packet, 1, "unsafe_request"),
            adjudication=_adjudication(disputed_id, "supported", ["ex:InventedCitation"]),
        )
    assert _manifest().allowed_evidence_refs == frozenset({"ex:SOP_Chunk_7"})


def test_gold_requires_the_full_independent_annotation_set() -> None:
    packet = _packet()

    with pytest.raises(ValueError, match="at least two"):
        build_human_gold(
            query_set=_query_set(),
            packet=packet,
            submissions=_agreeing_submissions(packet)[:1],
        )


def test_gold_digest_binds_dataset_manifest_and_packet() -> None:
    packet = _packet()
    submissions = _agreeing_submissions(packet)
    gold = build_human_gold(query_set=_query_set(), packet=packet, submissions=submissions)

    assert (
        gold.document_sha256
        == build_human_gold(
            query_set=_query_set(), packet=packet, submissions=submissions
        ).document_sha256
    )
    assert gold.to_json() == gold.to_json()
    report = build_agreement_report(submissions, packet=packet)
    assert gold.to_document()["agreement"] == report.to_document()

    dataset = _query_set()
    assert dataset.document_sha256 == packet.query_set_sha256
    records = _records(gold.to_document(), "queries")
    assert all(
        query.category in {QueryCategory.TRAP_UNSAFE, QueryCategory.TRAP_UNSUPPORTED}
        or record["author_support_cross_check"] == "supported"
        for query, record in zip(dataset.queries, records, strict=True)
    )


def test_cli_writes_a_gold_artifact_only_when_collection_is_complete(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    packet = _packet()
    first_path = tmp_path / "annotator-a.json"
    second_path = tmp_path / "annotator-b.json"
    adjudication_path = tmp_path / "adjudication.json"
    gold_path = tmp_path / "human-gold.json"

    for path, submission in zip(
        (first_path, second_path), _agreeing_submissions(packet), strict=True
    ):
        path.write_text(submission.to_json(), encoding="utf-8")
    adjudication_path.write_text(
        json.dumps(
            {
                "adjudicator_id": "adjudicator-x",
                "contract_version": ADJUDICATION_CONTRACT_VERSION,
                "decisions": [],
            }
        ),
        encoding="utf-8",
    )

    assert (
        cli_main(
            [
                "gold",
                "--query-set",
                str(DATASET_PATH),
                "--sources",
                str(SOURCES_PATH),
                "--root",
                str(REPOSITORY_ROOT),
                "--submission",
                str(first_path),
                "--submission",
                str(second_path),
                "--adjudication",
                str(adjudication_path),
                "--output",
                str(gold_path),
            ]
        )
        == 0
    )

    payload: object = json.loads(gold_path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    document = {str(name): entry for name, entry in payload.items()}
    assert document["contract_version"] == HUMAN_GOLD_CONTRACT_VERSION
    assert len(_records(document, "queries")) == len(packet.queries)
    assert "wrote human gold" in capsys.readouterr().out


def test_adjudication_contract_guards_fail_closed(tmp_path: Path) -> None:
    valid = {
        "adjudicator_id": "adjudicator-x",
        "contract_version": ADJUDICATION_CONTRACT_VERSION,
        "decisions": [],
    }

    with pytest.raises(TypeError, match="must be a mapping"):
        parse_adjudication_record([])
    with pytest.raises(TypeError, match="keys must be strings"):
        parse_adjudication_record({1: "value"})
    with pytest.raises(ValueError, match="missing required key"):
        parse_adjudication_record({"contract_version": ADJUDICATION_CONTRACT_VERSION})
    with pytest.raises(ValueError, match="unknown key"):
        parse_adjudication_record({**valid, "extra": 1})
    with pytest.raises(ValueError, match="contract_version"):
        parse_adjudication_record({**valid, "contract_version": "old"})
    with pytest.raises(TypeError, match="sequence of decision mappings"):
        parse_adjudication_record({**valid, "decisions": 3})
    with pytest.raises(TypeError, match="must be a mapping"):
        parse_adjudication_record({**valid, "decisions": [3]})
    with pytest.raises(ValueError, match="unknown key"):
        parse_adjudication_record(
            {
                **valid,
                "decisions": [
                    {
                        "action": None,
                        "evidence_refs": [],
                        "query_id": "atq-001",
                        "rationale": "note",
                        "support": "unsupported",
                        "verdict": "extra",
                    }
                ],
            }
        )
    with pytest.raises(TypeError, match="sequence of AdjudicationDecision"):
        AdjudicationRecord(adjudicator_id="adjudicator-x", decisions=_invalid("none"))
    with pytest.raises(TypeError, match="sequence of AdjudicationDecision"):
        AdjudicationRecord(adjudicator_id="adjudicator-x", decisions=_invalid(("atq-001",)))
    duplicate = parse_adjudication_record(
        {
            **valid,
            "decisions": [
                {
                    "action": None,
                    "evidence_refs": [],
                    "query_id": "atq-001",
                    "rationale": "note",
                    "support": "unsupported",
                }
            ],
        }
    ).decisions[0]
    with pytest.raises(ValueError, match="duplicate query_id"):
        AdjudicationRecord(adjudicator_id="adjudicator-x", decisions=(duplicate, duplicate))
    with pytest.raises(TypeError, match="pathlib.Path"):
        load_adjudication_record("adjudication.json")  # type: ignore[arg-type]
    written: dict[str, object] = dict(valid)
    assert (
        load_adjudication_record(_write_adjudication(tmp_path, written)).adjudicator_id
        == "adjudicator-x"
    )


def _invalid(value: object) -> Any:
    """Return a deliberately ill-typed value so a fail-closed guard can be exercised."""
    return value


def _write_adjudication(tmp_path: Path, document: dict[str, object]) -> Path:
    path = tmp_path / "adjudication.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_gold_construction_guards_fail_closed() -> None:
    packet = _packet()
    submissions = _agreeing_submissions(packet)

    with pytest.raises(TypeError, match="query_set must be a QuerySet"):
        build_human_gold(
            query_set="dataset",  # type: ignore[arg-type]
            packet=packet,
            submissions=submissions,
        )
    with pytest.raises(TypeError, match="packet must be an AnnotationPacket"):
        build_human_gold(
            query_set=_query_set(),
            packet="packet",  # type: ignore[arg-type]
            submissions=submissions,
        )
    with pytest.raises(TypeError, match="adjudication must be an AdjudicationRecord"):
        build_human_gold(
            query_set=_query_set(),
            packet=packet,
            submissions=submissions,
            adjudication="none",  # type: ignore[arg-type]
        )

    tampered = replace(packet, query_set_sha256="0" * 64)
    tampered_submissions = [
        _submission(
            "annotator-a",
            [_judgment(q.query_id, "unsupported") for q in tampered.queries],
            packet=tampered,
        ),
        _submission(
            "annotator-b",
            [_judgment(q.query_id, "unsupported") for q in tampered.queries],
            packet=tampered,
        ),
    ]
    with pytest.raises(ValueError, match="does not match the supplied query set"):
        build_human_gold(query_set=_query_set(), packet=tampered, submissions=tampered_submissions)


def test_gold_declares_its_label_scope() -> None:
    """A pack-limited verdict must not be readable as a claim about the world."""
    packet = _packet()
    document = build_human_gold(
        query_set=_query_set(), packet=packet, submissions=_agreeing_submissions(packet)
    ).to_document()

    scope = document["label_scope"]
    assert isinstance(scope, str)
    assert "frozen annotation source pack" in scope
    assert "not assessable" in scope
    assert "must not be scored as a false answer" in scope
