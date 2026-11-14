"""Behavior contract for independent human gold annotation of the benchmark query set."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from mfg_agentgraph.annotation_cli import main as cli_main
from mfg_agentgraph.annotation_sources import (
    SourceArtifact,
    SourceManifest,
    load_source_manifest,
)
from mfg_agentgraph.anomaly_triage_dataset import QueryCategory, QuerySet, load_query_set
from mfg_agentgraph.gold_annotation import (
    ANNOTATION_CONTRACT_VERSION,
    PACKET_CONTRACT_VERSION,
    SUPPORT_JUDGMENTS,
    AnnotationJudgment,
    AnnotationPacket,
    AnnotationQuery,
    AnnotationSourceView,
    AnnotationSubmission,
    SupportJudgment,
    build_agreement_report,
    build_annotation_packet,
    compare_annotation_submissions,
    load_annotation_submission,
    parse_annotation_submission,
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


def _two_source_manifest() -> SourceManifest:
    """Return a two-identifier vocabulary so set arithmetic stays testable."""
    return SourceManifest(
        sources=(
            SourceArtifact(
                evidence_id="ex:SOP_Chunk_7",
                path="sop.txt",
                sha256=hashlib.sha256(b"Inspect the inlet.").hexdigest(),
                text="Inspect the inlet.",
            ),
            SourceArtifact(
                evidence_id="ex:EvidenceEdge_002",
                path="edge.txt",
                sha256=hashlib.sha256(b"Record the finding.").hexdigest(),
                text="Record the finding.",
            ),
        )
    )


def _two_source_packet() -> AnnotationPacket:
    return build_annotation_packet(_query_set(), manifest=_two_source_manifest())


def _judgment(
    query_id: str,
    support: str,
    evidence_refs: list[str],
    action: str | None = None,
    rubric: str = "Rubric text.",
) -> dict[str, object]:
    return {
        "action": action,
        "evidence_refs": evidence_refs,
        "query_id": query_id,
        "rubric": rubric,
        "support": support,
    }


def _submission_document(
    annotator_id: str,
    judgments: list[dict[str, object]],
    *,
    packet: AnnotationPacket,
) -> dict[str, object]:
    return {
        "annotator_id": annotator_id,
        "contract_version": ANNOTATION_CONTRACT_VERSION,
        "judgments": judgments,
        "manifest_sha256": packet.manifest_sha256,
        "packet_sha256": packet.document_sha256,
        "query_set_sha256": packet.query_set_sha256,
    }


def _uniform_judgments(packet: AnnotationPacket) -> list[dict[str, object]]:
    return [_judgment(query.query_id, "unsupported", []) for query in packet.queries]


def test_packet_exposes_only_query_identity_and_text() -> None:
    query_set = _query_set()
    packet = build_annotation_packet(query_set, manifest=_manifest())
    document = packet.to_document()

    assert document["contract_version"] == PACKET_CONTRACT_VERSION
    assert document["dataset_id"] == query_set.dataset_id
    assert document["query_set_id"] == query_set.query_set_id
    assert document["query_set_sha256"] == query_set.document_sha256
    queries = document["queries"]
    assert isinstance(queries, list)
    assert [item["query_id"] for item in queries] == [query.query_id for query in query_set.queries]
    assert all(set(item) == {"query_id", "text"} for item in queries)

    assert document["manifest_sha256"] == _manifest().document_sha256
    sources = document["sources"]
    assert isinstance(sources, list)
    assert [item["evidence_id"] for item in sources] == ["ex:SOP_Chunk_7"]
    assert all(set(item) == {"evidence_id", "text"} for item in sources)

    serialized = packet.to_json()
    assert "ex:EvidenceEdge_001" not in serialized
    for value in (category.value for category in QueryCategory):
        assert f'"{value}"' not in serialized
    for query in query_set.queries:
        assert query.text in serialized
        assert query.gold_rubric not in serialized
        if query.expected_action is not None:
            assert query.expected_action not in serialized
    # The frozen SOP identifier is shared corpus vocabulary, not a per-query label, so it
    # appears exactly once: in the sources list.
    assert serialized.count('"ex:SOP_Chunk_7"') == 1


def test_packet_digest_binds_query_text_only() -> None:
    query_set = _query_set()
    packet = build_annotation_packet(query_set, manifest=_manifest())

    assert packet.document_sha256 == hashlib.sha256(packet.to_json().encode("utf-8")).hexdigest()
    assert packet.to_json() == json.dumps(
        packet.to_document(),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    assert json.dumps(packet.to_document(), indent=4) != packet.to_json()

    relabelled = QuerySet(
        dataset_id=query_set.dataset_id,
        query_set_id=query_set.query_set_id,
        version=query_set.version,
        queries=[
            replace(query_set.queries[0], gold_rubric="Independently irrelevant rubric."),
            *query_set.queries[1:],
        ],
    )
    reworded = QuerySet(
        dataset_id=query_set.dataset_id,
        query_set_id=query_set.query_set_id,
        version=query_set.version,
        queries=[
            replace(query_set.queries[0], text="A different operator question?"),
            *query_set.queries[1:],
        ],
    )
    manifest = _manifest()
    relabelled_packet = build_annotation_packet(relabelled, manifest=manifest)
    reworded_packet = build_annotation_packet(reworded, manifest=manifest)
    assert relabelled_packet.queries == packet.queries
    assert relabelled_packet.document_sha256 != packet.document_sha256
    assert reworded_packet.document_sha256 != packet.document_sha256


def test_parse_annotation_submission_accepts_a_complete_submission() -> None:
    packet = _packet()
    submission = parse_annotation_submission(
        _submission_document("annotator-a", _uniform_judgments(packet), packet=packet),
        packet=packet,
    )

    assert submission.annotator_id == "annotator-a"
    assert submission.query_set_sha256 == packet.query_set_sha256
    assert submission.packet_sha256 == packet.document_sha256
    assert [judgment.query_id for judgment in submission.judgments] == [
        query.query_id for query in packet.queries
    ]
    assert all(judgment.support is SupportJudgment.UNSUPPORTED for judgment in submission.judgments)


def test_parse_annotation_submission_requires_exact_query_coverage() -> None:
    packet = _packet()
    complete = _uniform_judgments(packet)

    with pytest.raises(ValueError, match="missing"):
        parse_annotation_submission(
            _submission_document("annotator-a", complete[:-1], packet=packet), packet=packet
        )

    with pytest.raises(ValueError, match="duplicate"):
        parse_annotation_submission(
            _submission_document("annotator-a", [*complete[:-1], complete[0]], packet=packet),
            packet=packet,
        )

    with pytest.raises(ValueError, match="unknown"):
        parse_annotation_submission(
            _submission_document(
                "annotator-a",
                [*complete[:-1], _judgment("atq-999", "unsupported", [])],
                packet=packet,
            ),
            packet=packet,
        )


def test_parse_annotation_submission_binds_the_exact_dataset_and_packet() -> None:
    packet = _packet()
    judgments = _uniform_judgments(packet)

    wrong_dataset = _submission_document("annotator-a", judgments, packet=packet)
    wrong_dataset["query_set_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="query_set_sha256"):
        parse_annotation_submission(wrong_dataset, packet=packet)

    wrong_packet = _submission_document("annotator-a", judgments, packet=packet)
    wrong_packet["packet_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="packet_sha256"):
        parse_annotation_submission(wrong_packet, packet=packet)

    wrong_contract = _submission_document("annotator-a", judgments, packet=packet)
    wrong_contract["contract_version"] = "mfg-agentgraph-gold-annotation-v0"
    with pytest.raises(ValueError, match="contract_version"):
        parse_annotation_submission(wrong_contract, packet=packet)

    with pytest.raises(ValueError, match="annotator_id"):
        parse_annotation_submission(
            _submission_document("   ", judgments, packet=packet), packet=packet
        )


def test_parse_annotation_submission_enforces_judgment_invariants() -> None:
    packet = _packet()
    first_query_id = packet.queries[0].query_id

    def _with(replacement: dict[str, object]) -> list[dict[str, object]]:
        judgments = _uniform_judgments(packet)
        judgments[0] = replacement
        return judgments

    supported_without_evidence = _with(_judgment(first_query_id, "supported", []))
    with pytest.raises(ValueError, match="evidence_refs"):
        parse_annotation_submission(
            _submission_document("annotator-a", supported_without_evidence, packet=packet),
            packet=packet,
        )

    unsupported_with_evidence = _with(_judgment(first_query_id, "unsupported", ["ex:SOP_Chunk_7"]))
    with pytest.raises(ValueError, match="evidence_refs"):
        parse_annotation_submission(
            _submission_document("annotator-a", unsupported_with_evidence, packet=packet),
            packet=packet,
        )

    unsupported_with_action = _with(
        _judgment(first_query_id, "unsupported", [], action="Inspect the inlet.")
    )
    with pytest.raises(ValueError, match="action"):
        parse_annotation_submission(
            _submission_document("annotator-a", unsupported_with_action, packet=packet),
            packet=packet,
        )

    noncanonical_reference = _with(_judgment(first_query_id, "supported", ["SOP_Chunk_7"]))
    with pytest.raises(ValueError, match="evidence_refs"):
        parse_annotation_submission(
            _submission_document("annotator-a", noncanonical_reference, packet=packet),
            packet=packet,
        )

    invalid_support = _with(_judgment(first_query_id, "maybe", []))
    with pytest.raises(ValueError, match="support"):
        parse_annotation_submission(
            _submission_document("annotator-a", invalid_support, packet=packet), packet=packet
        )

    blank_rubric = _with(_judgment(first_query_id, "unsupported", [], rubric="   "))
    with pytest.raises(ValueError, match="rubric"):
        parse_annotation_submission(
            _submission_document("annotator-a", blank_rubric, packet=packet), packet=packet
        )


def _labelled_submission(
    annotator_id: str,
    packet: AnnotationPacket,
    supports: list[str],
    evidence: list[list[str]],
) -> AnnotationSubmission:
    judgments = [
        _judgment(query.query_id, support, refs)
        for query, support, refs in zip(packet.queries, supports, evidence, strict=True)
    ]
    return parse_annotation_submission(
        _submission_document(annotator_id, judgments, packet=packet), packet=packet
    )


def test_compare_reports_agreement_and_kappa_before_adjudication() -> None:
    packet = _two_source_packet()
    count = len(packet.queries)
    first_supports = ["supported"] * 10 + ["unsupported"] * 10 + ["unsafe_request"] * 10
    second_supports = ["supported"] * 10 + ["unsupported"] * 11 + ["unsafe_request"] * 9
    first_evidence = [["ex:SOP_Chunk_7"]] * 10 + [[] for _ in range(count - 10)]
    second_evidence = (
        [["ex:EvidenceEdge_002", "ex:SOP_Chunk_7"]]
        + [["ex:SOP_Chunk_7"]] * 9
        + [[] for _ in range(count - 10)]
    )

    first = _labelled_submission("annotator-a", packet, first_supports, first_evidence)
    second = _labelled_submission("annotator-b", packet, second_supports, second_evidence)

    comparison = compare_annotation_submissions(first, second)

    assert comparison.annotator_ids == ("annotator-a", "annotator-b")
    assert comparison.query_count == count
    assert comparison.support_agreement_count == count - 1
    assert comparison.support_agreement_rate == pytest.approx((count - 1) / count)
    assert comparison.cohen_kappa == pytest.approx(0.95)
    assert comparison.cohen_kappa_undefined_reason is None
    assert comparison.evidence_exact_match_rate == pytest.approx((count - 1) / count)
    assert comparison.evidence_mean_jaccard == pytest.approx((count - 0.5) / count)
    assert comparison.disagreement_query_ids == (
        packet.queries[0].query_id,
        packet.queries[20].query_id,
    )


def test_compare_reports_undefined_kappa_without_inventing_a_value() -> None:
    packet = _packet()
    count = len(packet.queries)
    first = _labelled_submission(
        "annotator-a", packet, ["unsupported"] * count, [[] for _ in range(count)]
    )
    second = _labelled_submission(
        "annotator-b", packet, ["unsupported"] * count, [[] for _ in range(count)]
    )

    comparison = compare_annotation_submissions(first, second)

    assert comparison.support_agreement_rate == pytest.approx(1.0)
    assert comparison.evidence_mean_jaccard == pytest.approx(1.0)
    assert comparison.cohen_kappa is None
    assert comparison.cohen_kappa_undefined_reason is not None
    assert "single" in comparison.cohen_kappa_undefined_reason
    assert comparison.disagreement_query_ids == ()


def test_compare_rejects_submissions_bound_to_different_packets() -> None:
    packet = _packet()
    count = len(packet.queries)
    first = _labelled_submission(
        "annotator-a", packet, ["unsupported"] * count, [[] for _ in range(count)]
    )
    second = replace(first, annotator_id="annotator-b", packet_sha256="0" * 64)

    with pytest.raises(ValueError, match="packet_sha256"):
        compare_annotation_submissions(first, second)


def test_agreement_report_requires_two_distinct_annotators() -> None:
    packet = _packet()
    count = len(packet.queries)
    first = _labelled_submission(
        "annotator-a", packet, ["unsupported"] * count, [[] for _ in range(count)]
    )
    same_annotator = _labelled_submission(
        "annotator-a", packet, ["unsupported"] * count, [[] for _ in range(count)]
    )

    with pytest.raises(ValueError, match="at least two"):
        build_agreement_report([first], packet=packet)
    with pytest.raises(ValueError, match="distinct"):
        build_agreement_report([first, same_annotator], packet=packet)


def test_agreement_report_covers_every_pair_and_counts_unanimity() -> None:
    packet = _packet()
    count = len(packet.queries)
    agreed_supports = ["supported"] * count
    agreed_evidence = [["ex:SOP_Chunk_7"]] * count
    dissenting_supports = ["supported"] * 2 + ["unsupported"] * (count - 2)
    dissenting_evidence = [["ex:SOP_Chunk_7"]] * 2 + [[] for _ in range(count - 2)]

    submissions = [
        _labelled_submission("annotator-a", packet, agreed_supports, agreed_evidence),
        _labelled_submission("annotator-b", packet, agreed_supports, agreed_evidence),
        _labelled_submission("annotator-c", packet, dissenting_supports, dissenting_evidence),
    ]

    report = build_agreement_report(submissions, packet=packet)
    document = report.to_document()
    pairs = document["pairs"]

    assert report.annotator_ids == ("annotator-a", "annotator-b", "annotator-c")
    assert report.query_count == count
    assert len(report.pairs) == 3
    assert report.unanimous_support_query_count == 2
    assert report.unanimous_evidence_query_count == 2
    assert document["query_set_sha256"] == packet.query_set_sha256
    assert document["packet_sha256"] == packet.document_sha256
    assert isinstance(pairs, list)
    assert len(pairs) == 3
    assert SUPPORT_JUDGMENTS == (
        SupportJudgment.SUPPORTED,
        SupportJudgment.UNSUPPORTED,
        SupportJudgment.UNSAFE_REQUEST,
    )


def _write_submission(path: Path, annotator_id: str, packet: AnnotationPacket) -> Path:
    path.write_text(
        json.dumps(
            _submission_document(annotator_id, _uniform_judgments(packet), packet=packet),
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    return path


def test_cli_exports_a_blinded_packet_and_reports_agreement(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    packet = _packet()
    packet_path = tmp_path / "packet.json"
    assert (
        cli_main(
            [
                "packet",
                "--query-set",
                str(DATASET_PATH),
                "--sources",
                str(SOURCES_PATH),
                "--root",
                str(REPOSITORY_ROOT),
                "--output",
                str(packet_path),
            ]
        )
        == 0
    )

    exported: object = json.loads(packet_path.read_text(encoding="utf-8"))
    assert isinstance(exported, dict)
    exported_queries = exported["queries"]
    assert exported["contract_version"] == PACKET_CONTRACT_VERSION
    assert exported["query_set_sha256"] == packet.query_set_sha256
    assert isinstance(exported_queries, list)
    assert all(set(item) == {"query_id", "text"} for item in exported_queries)
    assert f"wrote blinded packet for {len(packet.queries)} queries" in capsys.readouterr().out

    first = _write_submission(tmp_path / "annotator-a.json", "annotator-a", packet)
    second = _write_submission(tmp_path / "annotator-b.json", "annotator-b", packet)
    report_path = tmp_path / "report.json"
    assert (
        cli_main(
            [
                "agreement",
                "--query-set",
                str(DATASET_PATH),
                "--sources",
                str(SOURCES_PATH),
                "--root",
                str(REPOSITORY_ROOT),
                "--submission",
                str(first),
                "--submission",
                str(second),
                "--output",
                str(report_path),
            ]
        )
        == 0
    )

    report: object = json.loads(report_path.read_text(encoding="utf-8"))
    assert isinstance(report, dict)
    pairs = report["pairs"]
    assert report["query_count"] == len(packet.queries)
    assert report["annotator_ids"] == ["annotator-a", "annotator-b"]
    assert isinstance(pairs, list)
    assert len(pairs) == 1
    assert pairs[0]["cohen_kappa"] is None
    assert "kappa=undefined" in capsys.readouterr().out


def test_cli_rejects_a_submission_missing_a_query(tmp_path: Path) -> None:
    packet = _packet()
    partial_path = tmp_path / "annotator-a.json"
    partial = _submission_document("annotator-a", _uniform_judgments(packet)[:-1], packet=packet)
    partial_path.write_text(json.dumps(partial), encoding="utf-8")
    second = _write_submission(tmp_path / "annotator-b.json", "annotator-b", packet)

    with pytest.raises(ValueError, match="missing"):
        cli_main(
            [
                "agreement",
                "--query-set",
                str(DATASET_PATH),
                "--sources",
                str(SOURCES_PATH),
                "--root",
                str(REPOSITORY_ROOT),
                "--submission",
                str(partial_path),
                "--submission",
                str(second),
                "--output",
                str(tmp_path / "report.json"),
            ]
        )


def _invalid(value: object) -> Any:
    """Return a deliberately ill-typed value so a fail-closed guard can be exercised."""
    return value


def test_packet_and_judgment_construction_guards_fail_closed() -> None:
    packet = _packet()
    first_query = packet.queries[0]

    with pytest.raises(ValueError, match="query_set_sha256"):
        AnnotationPacket(
            dataset_id=packet.dataset_id,
            query_set_id=packet.query_set_id,
            manifest_sha256=packet.manifest_sha256,
            query_set_sha256="not-a-digest",
            sources=packet.sources,
            queries=packet.queries,
        )
    with pytest.raises(TypeError, match="sequence of AnnotationQuery"):
        AnnotationPacket(
            dataset_id=packet.dataset_id,
            query_set_id=packet.query_set_id,
            manifest_sha256=packet.manifest_sha256,
            query_set_sha256=packet.query_set_sha256,
            sources=packet.sources,
            queries=_invalid("atq-001"),
        )
    with pytest.raises(ValueError, match="must not be empty"):
        AnnotationPacket(
            dataset_id=packet.dataset_id,
            query_set_id=packet.query_set_id,
            manifest_sha256=packet.manifest_sha256,
            query_set_sha256=packet.query_set_sha256,
            sources=packet.sources,
            queries=(),
        )
    with pytest.raises(TypeError, match="sequence of AnnotationQuery"):
        AnnotationPacket(
            dataset_id=packet.dataset_id,
            query_set_id=packet.query_set_id,
            manifest_sha256=packet.manifest_sha256,
            query_set_sha256=packet.query_set_sha256,
            sources=packet.sources,
            queries=_invalid([("atq-001", "text")]),
        )
    with pytest.raises(ValueError, match="duplicate query_id"):
        AnnotationPacket(
            dataset_id=packet.dataset_id,
            query_set_id=packet.query_set_id,
            manifest_sha256=packet.manifest_sha256,
            query_set_sha256=packet.query_set_sha256,
            sources=packet.sources,
            queries=(first_query, first_query),
        )
    with pytest.raises(ValueError, match="ascending query_id"):
        AnnotationPacket(
            dataset_id=packet.dataset_id,
            query_set_id=packet.query_set_id,
            manifest_sha256=packet.manifest_sha256,
            query_set_sha256=packet.query_set_sha256,
            sources=packet.sources,
            queries=tuple(reversed(packet.queries)),
        )
    with pytest.raises(ValueError, match="atq-NNN"):
        AnnotationQuery(query_id="atq-1", text="text")
    with pytest.raises(TypeError, match="query_set must be a QuerySet"):
        build_annotation_packet(_invalid("not a query set"), manifest=_manifest())
    with pytest.raises(TypeError, match="manifest must be a SourceManifest"):
        build_annotation_packet(_query_set(), manifest=_invalid("manifest"))

    assert (
        AnnotationJudgment(
            query_id=first_query.query_id,
            support=SupportJudgment.SUPPORTED,
            evidence_refs=("ex:SOP_Chunk_7",),
            action="Inspect the inlet.",
            rubric="Rubric.",
        ).support
        is SupportJudgment.SUPPORTED
    )
    with pytest.raises(TypeError, match="support must be a string"):
        AnnotationJudgment(
            query_id=first_query.query_id,
            support=_invalid(1),
            evidence_refs=(),
            action=None,
            rubric="Rubric.",
        )
    with pytest.raises(TypeError, match="evidence_refs"):
        AnnotationJudgment(
            query_id=first_query.query_id,
            support=SupportJudgment.SUPPORTED,
            evidence_refs=_invalid("ex:EvidenceEdge_001"),
            action=None,
            rubric="Rubric.",
        )
    with pytest.raises(ValueError, match="duplicate identifiers"):
        AnnotationJudgment(
            query_id=first_query.query_id,
            support=SupportJudgment.SUPPORTED,
            evidence_refs=("ex:A", "ex:A"),
            action=None,
            rubric="Rubric.",
        )


def test_submission_and_report_construction_guards_fail_closed() -> None:
    packet = _packet()
    judgments = tuple(
        parse_annotation_submission(
            _submission_document("annotator-a", _uniform_judgments(packet), packet=packet),
            packet=packet,
        ).judgments
    )

    with pytest.raises(TypeError, match="sequence of AnnotationJudgment"):
        AnnotationSubmission(
            annotator_id="annotator-a",
            query_set_sha256=packet.query_set_sha256,
            manifest_sha256=packet.manifest_sha256,
            packet_sha256=packet.document_sha256,
            judgments=_invalid("atq-001"),
        )
    with pytest.raises(ValueError, match="must not be empty"):
        AnnotationSubmission(
            annotator_id="annotator-a",
            query_set_sha256=packet.query_set_sha256,
            manifest_sha256=packet.manifest_sha256,
            packet_sha256=packet.document_sha256,
            judgments=(),
        )
    with pytest.raises(TypeError, match="sequence of AnnotationJudgment"):
        AnnotationSubmission(
            annotator_id="annotator-a",
            query_set_sha256=packet.query_set_sha256,
            manifest_sha256=packet.manifest_sha256,
            packet_sha256=packet.document_sha256,
            judgments=_invalid([("atq-001", "unsupported")]),
        )
    with pytest.raises(ValueError, match="duplicate judgment"):
        AnnotationSubmission(
            annotator_id="annotator-a",
            query_set_sha256=packet.query_set_sha256,
            manifest_sha256=packet.manifest_sha256,
            packet_sha256=packet.document_sha256,
            judgments=(judgments[0], judgments[0]),
        )


def test_parse_compare_and_report_guards_fail_closed() -> None:
    packet = _packet()
    counts = len(packet.queries)
    first = _labelled_submission(
        "annotator-a", packet, ["unsupported"] * counts, [[] for _ in range(counts)]
    )
    other_dataset = replace(first, annotator_id="annotator-b", query_set_sha256="1" * 64)
    shorter = replace(first, annotator_id="annotator-b", judgments=first.judgments[:-1])
    other_packet = replace(first, annotator_id="annotator-b", packet_sha256="1" * 64)
    document = _submission_document("annotator-a", _uniform_judgments(packet), packet=packet)

    with pytest.raises(TypeError, match="must be a mapping"):
        parse_annotation_submission(_invalid([]), packet=packet)
    with pytest.raises(TypeError, match="keys must be strings"):
        parse_annotation_submission(_invalid({1: "value"}), packet=packet)
    with pytest.raises(ValueError, match="missing required key"):
        parse_annotation_submission(
            {key: value for key, value in document.items() if key != "annotator_id"},
            packet=packet,
        )
    with pytest.raises(ValueError, match="unknown key"):
        parse_annotation_submission({**document, "extra": 1}, packet=packet)
    with pytest.raises(TypeError, match="packet must be an AnnotationPacket"):
        parse_annotation_submission(document, packet=_invalid("packet"))
    with pytest.raises(TypeError, match="sequence of judgment mappings"):
        parse_annotation_submission({**document, "judgments": 3}, packet=packet)
    with pytest.raises(ValueError, match="judgments must not be empty"):
        parse_annotation_submission({**document, "judgments": []}, packet=packet)
    with pytest.raises(TypeError, match="judgment must be a mapping"):
        parse_annotation_submission({**document, "judgments": [3]}, packet=packet)

    with pytest.raises(TypeError, match="first submission must be an AnnotationSubmission"):
        compare_annotation_submissions(_invalid("first"), first)
    with pytest.raises(ValueError, match="query_set_sha256"):
        compare_annotation_submissions(first, other_dataset)
    with pytest.raises(ValueError, match="same query_id"):
        compare_annotation_submissions(first, shorter)

    with pytest.raises(TypeError, match="sequence of AnnotationSubmission"):
        build_agreement_report(_invalid("submissions"), packet=packet)
    with pytest.raises(TypeError, match="sequence of AnnotationSubmission"):
        build_agreement_report([first, _invalid("second")], packet=packet)
    with pytest.raises(TypeError, match="packet must be an AnnotationPacket"):
        build_agreement_report([first, other_packet], packet=_invalid("packet"))
    with pytest.raises(ValueError, match="query_set_sha256"):
        build_agreement_report(
            [first, replace(other_packet, query_set_sha256="2" * 64)], packet=packet
        )
    with pytest.raises(ValueError, match="packet_sha256"):
        build_agreement_report([first, other_packet], packet=packet)

    with pytest.raises(TypeError, match="pathlib.Path"):
        load_annotation_submission(_invalid("annotations/annotator-a.json"), packet=packet)


def test_submission_round_trips_through_its_canonical_json() -> None:
    packet = _packet()
    submission = parse_annotation_submission(
        _submission_document("annotator-a", _uniform_judgments(packet), packet=packet),
        packet=packet,
    )

    reloaded = parse_annotation_submission(json.loads(submission.to_json()), packet=packet)

    assert reloaded.to_document() == submission.to_document()
    assert reloaded.to_json() == submission.to_json()
    judgment_documents = submission.to_document()["judgments"]
    assert isinstance(judgment_documents, list)
    assert set(judgment_documents[0]) == {
        "action",
        "evidence_refs",
        "query_id",
        "rubric",
        "support",
    }
    first_judgment = submission.judgment_map()[packet.queries[0].query_id]
    assert first_judgment.to_document()["support"] == "unsupported"


def test_evidence_citations_are_set_semantics_not_order_semantics() -> None:
    packet = _two_source_packet()
    count = len(packet.queries)
    forward = [["ex:EvidenceEdge_002", "ex:SOP_Chunk_7"]] + [
        ["ex:SOP_Chunk_7"] for _ in range(count - 1)
    ]
    reversed_order = [["ex:SOP_Chunk_7", "ex:EvidenceEdge_002"]] + [
        ["ex:SOP_Chunk_7"] for _ in range(count - 1)
    ]
    first = _labelled_submission("annotator-a", packet, ["supported"] * count, forward)
    second = _labelled_submission("annotator-b", packet, ["supported"] * count, reversed_order)

    comparison = compare_annotation_submissions(first, second)
    report = build_agreement_report([first, second], packet=packet)

    assert tuple(first.judgments[0].evidence_refs) == ("ex:EvidenceEdge_002", "ex:SOP_Chunk_7")
    assert comparison.evidence_exact_match_rate == pytest.approx(1.0)
    assert comparison.disagreement_query_ids == ()
    assert report.unanimous_evidence_query_count == count


def test_compare_rejects_comparing_one_annotator_with_itself() -> None:
    packet = _packet()
    count = len(packet.queries)
    first = _labelled_submission(
        "annotator-a", packet, ["unsupported"] * count, [[] for _ in range(count)]
    )
    revised = replace(first, judgments=tuple(reversed(first.judgments)))

    with pytest.raises(ValueError, match="distinct"):
        compare_annotation_submissions(first, revised)


def test_agreement_report_requires_complete_packet_coverage() -> None:
    packet = _packet()
    single = replace(
        _labelled_submission(
            "annotator-a",
            packet,
            ["unsupported"] * len(packet.queries),
            [[] for _ in range(len(packet.queries))],
        ),
        judgments=(
            AnnotationJudgment(
                query_id=packet.queries[0].query_id,
                support=SupportJudgment.UNSUPPORTED,
                evidence_refs=(),
                action=None,
                rubric="Only one query judged.",
            ),
        ),
    )
    other = replace(single, annotator_id="annotator-b")

    with pytest.raises(ValueError, match="missing"):
        build_agreement_report([single, other], packet=packet)


def test_cli_refuses_to_overwrite_an_existing_artifact(tmp_path: Path) -> None:
    query_set_path = tmp_path / "query-set-v1.json"
    query_set_path.write_text(DATASET_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    packet_path = tmp_path / "packet.json"

    assert (
        cli_main(
            [
                "packet",
                "--query-set",
                str(query_set_path),
                "--sources",
                str(SOURCES_PATH),
                "--root",
                str(REPOSITORY_ROOT),
                "--output",
                str(packet_path),
            ]
        )
        == 0
    )
    frozen = packet_path.read_bytes()

    with pytest.raises(ValueError, match="refusing to overwrite"):
        cli_main(
            [
                "packet",
                "--query-set",
                str(query_set_path),
                "--sources",
                str(SOURCES_PATH),
                "--root",
                str(REPOSITORY_ROOT),
                "--output",
                str(packet_path),
            ]
        )

    assert packet_path.read_bytes() == frozen


def test_cli_refuses_output_paths_that_would_destroy_an_input(tmp_path: Path) -> None:
    query_set_path = tmp_path / "query-set-v1.json"
    query_set_path.write_text(DATASET_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    frozen_query_set = query_set_path.read_bytes()

    with pytest.raises(ValueError, match="must not overwrite an input artifact"):
        cli_main(
            [
                "packet",
                "--query-set",
                str(query_set_path),
                "--sources",
                str(SOURCES_PATH),
                "--root",
                str(REPOSITORY_ROOT),
                "--output",
                str(query_set_path),
            ]
        )
    assert query_set_path.read_bytes() == frozen_query_set

    packet = _packet()
    first = _write_submission(tmp_path / "annotator-a.json", "annotator-a", packet)
    second = _write_submission(tmp_path / "annotator-b.json", "annotator-b", packet)
    frozen_submission = first.read_bytes()

    with pytest.raises(ValueError, match="must not overwrite an input artifact"):
        cli_main(
            [
                "agreement",
                "--query-set",
                str(query_set_path),
                "--sources",
                str(SOURCES_PATH),
                "--root",
                str(REPOSITORY_ROOT),
                "--submission",
                str(first),
                "--submission",
                str(second),
                "--output",
                str(first),
            ]
        )
    assert first.read_bytes() == frozen_submission


def test_submission_rejects_evidence_outside_the_frozen_manifest() -> None:
    packet = _packet()
    judgments = _uniform_judgments(packet)
    judgments[0] = _judgment(packet.queries[0].query_id, "supported", ["ex:InventedCitation"])

    with pytest.raises(ValueError, match="frozen source manifest"):
        parse_annotation_submission(
            _submission_document("annotator-a", judgments, packet=packet), packet=packet
        )


def test_manifest_digest_binds_every_annotation_artifact() -> None:
    packet = _packet()
    judgments = _uniform_judgments(packet)

    tampered_submission = _submission_document("annotator-a", judgments, packet=packet)
    tampered_submission["manifest_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="manifest_sha256"):
        parse_annotation_submission(tampered_submission, packet=packet)

    count = len(packet.queries)
    first = _labelled_submission(
        "annotator-a", packet, ["unsupported"] * count, [[] for _ in range(count)]
    )
    second = _labelled_submission(
        "annotator-b", packet, ["unsupported"] * count, [[] for _ in range(count)]
    )
    with pytest.raises(ValueError, match="manifest_sha256"):
        build_agreement_report([first, replace(second, manifest_sha256="1" * 64)], packet=packet)
    assert build_agreement_report([first, second], packet=packet).manifest_sha256 == (
        packet.manifest_sha256
    )


def test_packet_digest_changes_when_the_frozen_manifest_changes() -> None:
    query_set = _query_set()
    shipped = build_annotation_packet(query_set, manifest=_manifest())
    extended = build_annotation_packet(query_set, manifest=_two_source_manifest())

    assert shipped.manifest_sha256 != extended.manifest_sha256
    assert shipped.document_sha256 != extended.document_sha256
    assert shipped.allowed_evidence_refs == frozenset({"ex:SOP_Chunk_7"})
    assert extended.allowed_evidence_refs == frozenset({"ex:SOP_Chunk_7", "ex:EvidenceEdge_002"})


def test_packet_source_view_guards_fail_closed() -> None:
    packet = _packet()
    first_source = packet.sources[0]

    with pytest.raises(ValueError, match="ex: identifier"):
        AnnotationSourceView(evidence_id="SOP_Chunk_7", text="Inspect the inlet.")
    with pytest.raises(TypeError, match="sequence of AnnotationSourceView"):
        AnnotationPacket(
            dataset_id=packet.dataset_id,
            query_set_id=packet.query_set_id,
            query_set_sha256=packet.query_set_sha256,
            manifest_sha256=packet.manifest_sha256,
            sources=_invalid("ex:SOP_Chunk_7"),
            queries=packet.queries,
        )
    with pytest.raises(ValueError, match="must not be empty"):
        AnnotationPacket(
            dataset_id=packet.dataset_id,
            query_set_id=packet.query_set_id,
            query_set_sha256=packet.query_set_sha256,
            manifest_sha256=packet.manifest_sha256,
            sources=(),
            queries=packet.queries,
        )
    with pytest.raises(TypeError, match="sequence of AnnotationSourceView"):
        AnnotationPacket(
            dataset_id=packet.dataset_id,
            query_set_id=packet.query_set_id,
            query_set_sha256=packet.query_set_sha256,
            manifest_sha256=packet.manifest_sha256,
            sources=_invalid([("ex:SOP_Chunk_7", "text")]),
            queries=packet.queries,
        )
    with pytest.raises(ValueError, match="duplicate evidence_id"):
        AnnotationPacket(
            dataset_id=packet.dataset_id,
            query_set_id=packet.query_set_id,
            query_set_sha256=packet.query_set_sha256,
            manifest_sha256=packet.manifest_sha256,
            sources=(first_source, first_source),
            queries=packet.queries,
        )


def test_packet_source_view_preserves_exact_frozen_text(tmp_path: Path) -> None:
    """The packet must publish the exact bytes its manifest digest commits to."""
    raw = "\nInspect the inlet.\r\n"
    (tmp_path / "sop.txt").write_bytes(raw.encode("utf-8"))
    manifest_path = tmp_path / "sources.json"
    manifest_path.write_text(
        json.dumps(
            {
                "contract_version": "mfg-agentgraph-annotation-sources-v1",
                "sources": [
                    {
                        "evidence_id": "ex:SOP_Chunk_7",
                        "path": "sop.txt",
                        "sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = load_source_manifest(manifest_path, root=tmp_path)

    packet = build_annotation_packet(_query_set(), manifest=manifest)

    assert packet.sources[0].text == raw
    sources = packet.to_document()["sources"]
    assert isinstance(sources, list)
    assert sources[0]["text"] == raw
