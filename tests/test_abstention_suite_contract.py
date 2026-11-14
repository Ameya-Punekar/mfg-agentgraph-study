"""Behaviour contract for abstention measurement over the registered trap queries."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, dataclass, replace
from pathlib import Path

import pytest

from mfg_agentgraph.abstention_suite import (
    ABSTENTION_RATE_NAMES,
    ABSTENTION_SUITE_CONTRACT_VERSION,
    AbstentionOutcome,
    AbstentionRate,
    AbstentionReport,
    QueryAbstention,
    abstention_suite_queries,
    build_abstention_report,
    classify_abstention,
)
from mfg_agentgraph.anomaly_triage_dataset import (
    TRAP_CATEGORIES,
    QueryCategory,
    QueryRecord,
    QuerySet,
    load_query_set,
)
from mfg_agentgraph.evaluation_harness import (
    ArtifactApplicability,
    ArtifactKind,
    EvaluationArtifact,
    EvaluationResult,
    EvaluationRunConfiguration,
    EvaluationRunManifest,
    EvaluationStrategy,
)
from mfg_agentgraph.evaluation_metrics import MetricObservation
from mfg_agentgraph.s1_naive_rag import build_s1_run_configuration
from mfg_agentgraph.s4_evaluation_strategy import build_s4_run_configuration
from mfg_agentgraph.stage_instrumentation import TerminalStatus

DATASET_PATH = (
    Path(__file__).resolve().parents[1] / "evaluation" / "anomaly_triage" / "query-set-v1.json"
)
RELEASED_ANSWER = "Inspect the pump inlet of Pump_12 for cavitation"


@dataclass(frozen=True, slots=True)
class _Record:
    """Minimal strategy evaluation record: a comparable result plus its observation."""

    result: EvaluationResult
    observation: MetricObservation


def _query_set() -> QuerySet:
    return load_query_set(DATASET_PATH)


def _configuration(query_set: QuerySet) -> EvaluationRunConfiguration:
    return build_s4_run_configuration(query_set)


def _observation(query: QueryRecord, status: TerminalStatus) -> MetricObservation:
    released = status is TerminalStatus.PASSED
    return MetricObservation(
        query_id=query.query_id,
        predicted_answer=RELEASED_ANSWER if released else "",
        cited_evidence_refs=query.expected_evidence_refs if released else (),
        terminal_status=status,
    )


def _result(
    query: QueryRecord,
    status: TerminalStatus,
    configuration: EvaluationRunConfiguration,
    query_set: QuerySet,
) -> EvaluationResult:
    released = status is TerminalStatus.PASSED
    return EvaluationResult(
        configuration=configuration,
        manifest=EvaluationRunManifest(
            run_id=f"run:{configuration.strategy.value}:{query.query_id}",
            repository_revision="8806d53",
            harness_version="v1",
            dataset_sha256=query_set.document_sha256,
        ),
        query_id=query.query_id,
        raw_output={"terminal_status": status.value},
        errors=(),
        artifacts=(
            EvaluationArtifact(
                kind=ArtifactKind.ANSWER,
                applicability=ArtifactApplicability.PRESENT,
                value={"released": released, "text": RELEASED_ANSWER if released else ""},
                reason=None,
            ),
            EvaluationArtifact(
                kind=ArtifactKind.RETRIEVED_CONTEXT,
                applicability=ArtifactApplicability.PRESENT,
                value={"evidence_ids": list(query.expected_evidence_refs) if released else []},
                reason=None,
            ),
            EvaluationArtifact(
                kind=ArtifactKind.VALIDATION_REPORT,
                applicability=ArtifactApplicability.NOT_APPLICABLE,
                value=None,
                reason="record fixture carries no validation report",
            ),
            EvaluationArtifact(
                kind=ArtifactKind.PROVENANCE_TRACE,
                applicability=ArtifactApplicability.NOT_APPLICABLE,
                value=None,
                reason="record fixture carries no provenance trace",
            ),
        ),
    )


def _record(
    query: QueryRecord,
    status: TerminalStatus,
    *,
    configuration: EvaluationRunConfiguration,
    query_set: QuerySet,
) -> _Record:
    return _Record(
        result=_result(query, status, configuration, query_set),
        observation=_observation(query, status),
    )


def _baseline_records(
    query_set: QuerySet, configuration: EvaluationRunConfiguration | None = None
) -> tuple[_Record, ...]:
    """Every trap declines for the expected reason; every answerable query answers."""
    run = _configuration(query_set) if configuration is None else configuration
    records: list[_Record] = []
    for query in query_set.queries:
        status = (
            query.expected_terminal_status
            if query.category in TRAP_CATEGORIES
            else TerminalStatus.PASSED
        )
        assert status is not None
        records.append(_record(query, status, configuration=run, query_set=query_set))
    return tuple(records)


def _report(
    query_set: QuerySet,
    records: tuple[_Record, ...],
    configuration: EvaluationRunConfiguration | None = None,
) -> AbstentionReport:
    return build_abstention_report(
        configuration=_configuration(query_set) if configuration is None else configuration,
        query_set=query_set,
        records=records,
    )


def _rates(report: AbstentionReport) -> dict[str, AbstentionRate]:
    return dict(report.rates)


def _query(query_set: QuerySet, query_id: str) -> QueryRecord:
    return next(query for query in query_set.queries if query.query_id == query_id)


def _replace_status(
    query_set: QuerySet,
    query_id: str,
    status: TerminalStatus,
    *,
    configuration: EvaluationRunConfiguration | None = None,
) -> tuple[_Record, ...]:
    """Rebuild one record with a different status, keeping every other record intact."""
    run = _configuration(query_set) if configuration is None else configuration
    records = _baseline_records(query_set, run)
    return tuple(
        _record(_query(query_set, query_id), status, configuration=run, query_set=query_set)
        if record.result.query_id == query_id
        else record
        for record in records
    )


def test_suite_is_the_registered_trap_queries_and_names_unevaluated_ones() -> None:
    query_set = _query_set()

    report = _report(query_set, _baseline_records(query_set))

    assert report.suite_query_ids == ("atq-027", "atq-028", "atq-029", "atq-030")
    assert report.not_evaluated_query_ids == ()
    assert [entry.category for entry in report.per_query if entry.category in TRAP_CATEGORIES] == [
        QueryCategory.TRAP_UNSUPPORTED,
        QueryCategory.TRAP_UNSUPPORTED,
        QueryCategory.TRAP_UNSAFE,
        QueryCategory.TRAP_UNSAFE,
    ]


def test_every_trap_abstaining_for_the_expected_reason_scores_full_recall() -> None:
    query_set = _query_set()

    report = _report(query_set, _baseline_records(query_set))

    rates = _rates(report)
    assert rates["trap_abstention_recall"].value == 1.0
    assert rates["trap_abstention_recall"].numerator == 4
    assert rates["trap_abstention_recall"].denominator == 4
    assert rates["trap_false_answer_rate"].value == 0.0
    assert rates["trap_wrong_abstention_rate"].value == 0.0
    assert rates["unsupported_abstention_recall"].value == 1.0
    assert rates["unsafe_refusal_recall"].value == 1.0
    assert rates["answerable_over_abstention_rate"].value == 0.0
    assert report.outcome_counts[AbstentionOutcome.CORRECT_ABSTENTION] == 4
    assert report.outcome_counts[AbstentionOutcome.ANSWERED] == 26
    assert report.outcome_counts[AbstentionOutcome.FALSE_ANSWER] == 0


def test_a_trap_that_passes_is_a_false_answer_and_never_a_credit() -> None:
    query_set = _query_set()
    records = _replace_status(query_set, "atq-029", TerminalStatus.PASSED)

    report = _report(query_set, records)

    entry = next(item for item in report.per_query if item.query_id == "atq-029")
    assert entry.outcome is AbstentionOutcome.FALSE_ANSWER
    assert entry.expected_terminal_status is TerminalStatus.VALIDATION_FAILED_CLOSED
    assert entry.observed_terminal_status is TerminalStatus.PASSED
    rates = _rates(report)
    assert rates["trap_abstention_recall"].value == 0.75
    assert rates["trap_false_answer_rate"].value == 0.25
    assert rates["unsafe_refusal_recall"].value == 0.5
    assert rates["trap_wrong_abstention_rate"].value == 0.0
    assert report.outcome_counts[AbstentionOutcome.FALSE_ANSWER] == 1
    assert report.outcome_counts[AbstentionOutcome.CORRECT_ABSTENTION] == 3


def test_abstaining_for_the_wrong_reason_is_not_credited_as_abstention() -> None:
    query_set = _query_set()
    records = _replace_status(query_set, "atq-027", TerminalStatus.PROVENANCE_FAILED_CLOSED)

    report = _report(query_set, records)

    entry = next(item for item in report.per_query if item.query_id == "atq-027")
    assert entry.outcome is AbstentionOutcome.WRONG_ABSTENTION
    assert entry.observed_terminal_status is TerminalStatus.PROVENANCE_FAILED_CLOSED
    rates = _rates(report)
    assert rates["trap_abstention_recall"].value == 0.75
    assert rates["trap_wrong_abstention_rate"].value == 0.25
    assert rates["trap_false_answer_rate"].value == 0.0
    assert rates["unsupported_abstention_recall"].value == 0.5
    assert report.outcome_counts[AbstentionOutcome.WRONG_ABSTENTION] == 1


def test_over_abstention_on_an_answerable_query_does_not_change_trap_recall() -> None:
    query_set = _query_set()
    records = _replace_status(query_set, "atq-013", TerminalStatus.INSUFFICIENT_EVIDENCE)

    report = _report(query_set, records)

    entry = next(item for item in report.per_query if item.query_id == "atq-013")
    assert entry.outcome is AbstentionOutcome.OVER_ABSTAINED
    rates = _rates(report)
    assert rates["answerable_over_abstention_rate"].value == pytest.approx(1 / 26, rel=0, abs=1e-6)
    assert rates["trap_abstention_recall"].value == 1.0
    assert report.outcome_counts[AbstentionOutcome.OVER_ABSTAINED] == 1


def test_trap_rates_with_no_trap_observation_are_not_applicable_not_zero() -> None:
    query_set = _query_set()
    answerable_records = tuple(
        record
        for record in _baseline_records(query_set)
        if _query(query_set, record.result.query_id).category not in TRAP_CATEGORIES
    )

    report = _report(query_set, answerable_records[:5])

    rates = _rates(report)
    assert rates["trap_abstention_recall"].value is None
    assert rates["trap_abstention_recall"].denominator == 0
    assert rates["trap_abstention_recall"].reason is not None
    assert rates["unsupported_abstention_recall"].value is None
    assert rates["unsafe_refusal_recall"].value is None
    assert rates["answerable_over_abstention_rate"].value == 0.0
    assert report.outcome_counts[AbstentionOutcome.CORRECT_ABSTENTION] == 0
    assert set(report.not_evaluated_query_ids) >= {"atq-027", "atq-028", "atq-029", "atq-030"}


def test_partial_run_reports_only_what_it_evaluated() -> None:
    query_set = _query_set()
    partial = tuple(
        record
        for record in _baseline_records(query_set)
        if record.result.query_id in {"atq-027", "atq-030"}
    )

    report = _report(query_set, partial)

    assert report.evaluated_query_ids == ("atq-027", "atq-030")
    assert len(report.not_evaluated_query_ids) == 28
    rates = _rates(report)
    assert rates["trap_abstention_recall"].denominator == 2
    assert rates["trap_abstention_recall"].value == 1.0
    assert rates["answerable_over_abstention_rate"].value is None
    assert rates["answerable_over_abstention_rate"].reason is not None


def test_run_for_a_different_query_set_digest_is_refused() -> None:
    query_set = _query_set()
    other_query_set = replace(query_set, version="v2")

    with pytest.raises(ValueError, match="dataset_sha256"):
        build_abstention_report(
            configuration=_configuration(query_set),
            query_set=other_query_set,
            records=_baseline_records(query_set),
        )


def test_configuration_identifiers_must_match_the_query_set() -> None:
    query_set = _query_set()
    records = _baseline_records(query_set)

    with pytest.raises(ValueError, match="query_set_id"):
        build_abstention_report(
            configuration=replace(_configuration(query_set), query_set_id="other-set"),
            query_set=query_set,
            records=records,
        )
    with pytest.raises(ValueError, match="dataset_id"):
        build_abstention_report(
            configuration=replace(_configuration(query_set), dataset_id="other-dataset"),
            query_set=query_set,
            records=records,
        )


def test_records_must_have_been_produced_by_the_supplied_configuration() -> None:
    query_set = _query_set()
    s1_records = _baseline_records(query_set, build_s1_run_configuration(query_set))

    with pytest.raises(ValueError, match="different configuration"):
        build_abstention_report(
            configuration=_configuration(query_set),
            query_set=query_set,
            records=s1_records,
        )


def test_record_supplied_configuration_is_the_reported_strategy() -> None:
    query_set = _query_set()
    s1_configuration = build_s1_run_configuration(query_set)

    report = _report(
        query_set,
        _baseline_records(query_set, s1_configuration),
        s1_configuration,
    )

    assert report.strategy is EvaluationStrategy.S1
    assert report.model_configuration_id == s1_configuration.model_configuration_id
    assert json.loads(report.to_json())["strategy"] == EvaluationStrategy.S1.value


def test_record_observation_must_match_its_recorded_terminal_status() -> None:
    query_set = _query_set()
    trap = _query(query_set, "atq-029")
    configuration = _configuration(query_set)
    genuine = _record(trap, TerminalStatus.PASSED, configuration=configuration, query_set=query_set)
    doctored = _Record(
        result=genuine.result,
        observation=replace(
            genuine.observation, terminal_status=TerminalStatus.VALIDATION_FAILED_CLOSED
        ),
    )

    with pytest.raises(ValueError, match="terminal_status"):
        _report(query_set, (doctored,))


def test_record_observation_must_match_its_record_query_id() -> None:
    query_set = _query_set()
    configuration = _configuration(query_set)
    trap = _query(query_set, "atq-029")
    other = _query(query_set, "atq-013")
    genuine = _record(trap, TerminalStatus.PASSED, configuration=configuration, query_set=query_set)
    mismatched = _Record(
        result=genuine.result,
        observation=replace(genuine.observation, query_id=other.query_id),
    )

    with pytest.raises(ValueError, match="query_id"):
        _report(query_set, (mismatched,))


def test_record_manifest_digest_must_match_the_query_set() -> None:
    query_set = _query_set()
    trap = _query(query_set, "atq-027")
    configuration = _configuration(query_set)
    genuine = _record(
        trap, TerminalStatus.INSUFFICIENT_EVIDENCE, configuration=configuration, query_set=query_set
    )
    foreign = replace(genuine.result.manifest, dataset_sha256="0" * 64)

    with pytest.raises(ValueError, match="dataset_sha256"):
        _report(
            query_set,
            (
                _Record(
                    result=replace(genuine.result, manifest=foreign),
                    observation=genuine.observation,
                ),
            ),
        )


def test_records_must_expose_a_result_and_an_observation() -> None:
    query_set = _query_set()

    with pytest.raises(TypeError, match=r"records\[0\]"):
        _report(query_set, (object(),))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="records"):
        _report(query_set, "records")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="at least one"):
        _report(query_set, ())


def test_duplicate_and_unknown_records_are_refused() -> None:
    query_set = _query_set()
    records = _baseline_records(query_set)
    configuration = _configuration(query_set)
    unknown_query = replace(_query(query_set, "atq-027"), query_id="atq-099")
    unknown = _Record(
        result=_result(
            unknown_query, TerminalStatus.INSUFFICIENT_EVIDENCE, configuration, query_set
        ),
        observation=_observation(unknown_query, TerminalStatus.INSUFFICIENT_EVIDENCE),
    )

    with pytest.raises(ValueError, match="atq-099"):
        _report(query_set, (*records, unknown))
    with pytest.raises(ValueError, match="duplicate"):
        _report(query_set, (records[0], records[0]))


def test_report_is_immutable_canonical_and_digest_stable() -> None:
    query_set = _query_set()
    records = _baseline_records(query_set)

    first = _report(query_set, records)
    second = _report(query_set, records)

    assert first.document_sha256 == second.document_sha256
    assert first.to_json() == second.to_json()
    document = json.loads(first.to_json())
    assert document["contract_version"] == ABSTENTION_SUITE_CONTRACT_VERSION
    assert document["strategy"] == EvaluationStrategy.S4.value
    assert document["query_set_sha256"] == query_set.document_sha256
    assert set(document["rates"]) == set(ABSTENTION_RATE_NAMES)
    assert set(document["outcome_counts"]) == {outcome.value for outcome in AbstentionOutcome}
    assert document["suite_query_ids"] == list(first.suite_query_ids)
    assert document["scope"]
    assert not hasattr(first, "__dict__")
    with pytest.raises(FrozenInstanceError):
        first.strategy = "s1"  # type: ignore[misc, assignment]


def test_unsafe_refusal_recall_is_not_applicable_without_a_validation_gate() -> None:
    query_set = _query_set()
    s1_configuration = build_s1_run_configuration(query_set)

    report = _report(
        query_set,
        _baseline_records(query_set, s1_configuration),
        s1_configuration,
    )

    rates = _rates(report)
    assert rates["unsafe_refusal_recall"].value is None
    assert rates["unsafe_refusal_recall"].reason is not None
    assert "gate" in rates["unsafe_refusal_recall"].reason
    assert report.outcome_counts[AbstentionOutcome.CORRECT_ABSTENTION] == 4
    assert rates["answerable_over_abstention_rate"].value == 0.0


def test_wrong_input_types_are_rejected() -> None:
    query_set = _query_set()
    records = _baseline_records(query_set)

    with pytest.raises(TypeError, match="configuration"):
        build_abstention_report(
            configuration="configuration",  # type: ignore[arg-type]
            query_set=query_set,
            records=records,
        )
    with pytest.raises(TypeError, match="query_set"):
        build_abstention_report(
            configuration=_configuration(query_set),
            query_set="query-set",  # type: ignore[arg-type]
            records=records,
        )


def test_classification_uses_the_trap_contract_not_the_supplied_label() -> None:
    query_set = _query_set()
    trap = _query(query_set, "atq-028")
    answerable = _query(query_set, "atq-014")

    assert (
        classify_abstention(trap, _observation(trap, TerminalStatus.INSUFFICIENT_EVIDENCE))
        is AbstentionOutcome.CORRECT_ABSTENTION
    )
    assert (
        classify_abstention(
            trap, _observation(trap, TerminalStatus.OPERATOR_DISAMBIGUATION_REQUIRED)
        )
        is AbstentionOutcome.WRONG_ABSTENTION
    )
    assert (
        classify_abstention(answerable, _observation(answerable, TerminalStatus.PASSED))
        is AbstentionOutcome.ANSWERED
    )
    with pytest.raises(ValueError, match="query_id"):
        classify_abstention(trap, _observation(answerable, TerminalStatus.PASSED))


def test_hand_built_report_cannot_disagree_with_its_own_per_query_rows() -> None:
    query_set = _query_set()
    report = _report(query_set, _baseline_records(query_set))
    tampered_counts = dict(report.outcome_counts)
    tampered_counts[AbstentionOutcome.FALSE_ANSWER] = 1

    with pytest.raises(ValueError, match="outcome_counts"):
        replace(report, outcome_counts=tampered_counts)
    with pytest.raises(ValueError, match="rates"):
        replace(
            report, rates={k: v for k, v in report.rates.items() if k != "unsafe_refusal_recall"}
        )


def test_report_rejects_evaluated_ids_that_disagree_with_its_own_rows() -> None:
    query_set = _query_set()
    report = _report(query_set, _baseline_records(query_set))

    with pytest.raises(ValueError, match="evaluated_query_ids"):
        replace(report, evaluated_query_ids=("atq-027",))
    with pytest.raises(ValueError, match="evaluated_query_ids"):
        replace(report, evaluated_query_ids=())


def test_report_rejects_a_rate_that_disagrees_with_its_own_rows() -> None:
    query_set = _query_set()
    report = _report(query_set, _baseline_records(query_set))
    forged = AbstentionRate(
        name="trap_abstention_recall", value=0.75, numerator=3, denominator=4, reason=None
    )

    assert report.rates["trap_abstention_recall"].value == 1.0
    with pytest.raises(ValueError, match="trap_abstention_recall"):
        replace(report, rates={**dict(report.rates), "trap_abstention_recall": forged})


def test_report_rejects_a_suite_that_omits_an_evaluated_trap() -> None:
    query_set = _query_set()
    report = _report(query_set, _baseline_records(query_set))

    with pytest.raises(ValueError, match="suite_query_ids"):
        replace(report, suite_query_ids=("atq-027",))
    with pytest.raises(ValueError, match="suite_query_ids"):
        replace(report, suite_query_ids=("atq-030", "atq-029", "atq-028", "atq-027"))


def test_suite_cannot_name_an_evaluated_answerable_query() -> None:
    query_set = _query_set()
    report = _report(query_set, _baseline_records(query_set))

    with pytest.raises(ValueError, match="suite_query_ids"):
        replace(
            report,
            suite_query_ids=("atq-001", "atq-027", "atq-028", "atq-029", "atq-030"),
        )


def test_unevaluated_ids_must_be_the_exact_complement_of_the_query_set() -> None:
    query_set = _query_set()
    full = _report(query_set, _baseline_records(query_set))
    partial = _report(
        query_set,
        tuple(
            record for record in _baseline_records(query_set) if record.result.query_id == "atq-027"
        ),
    )

    assert full.not_evaluated_query_ids == ()
    with pytest.raises(ValueError, match="not_evaluated_query_ids"):
        replace(full, not_evaluated_query_ids=("atq-999",))
    with pytest.raises(ValueError, match="not_evaluated_query_ids"):
        replace(partial, not_evaluated_query_ids=("atq-001",))
    asserted = set(partial.not_evaluated_query_ids)
    assert "atq-027" not in asserted
    assert len(asserted) == 29


def test_report_names_the_full_query_set_universe() -> None:
    query_set = _query_set()
    partial = _report(
        query_set,
        tuple(
            record for record in _baseline_records(query_set) if record.result.query_id == "atq-027"
        ),
    )

    document = json.loads(partial.to_json())

    assert document["dataset_id"] == query_set.dataset_id
    assert document["query_set_id"] == query_set.query_set_id
    assert document["query_set_query_ids"] == [query.query_id for query in query_set.queries]
    assert set(document["evaluated_query_ids"]) | set(document["not_evaluated_query_ids"]) == set(
        document["query_set_query_ids"]
    )


def test_trap_row_expectation_must_match_the_trap_contract() -> None:
    query_set = _query_set()
    trap = _query(query_set, "atq-029")

    with pytest.raises(ValueError, match="expected_terminal_status"):
        QueryAbstention(
            query_id=trap.query_id,
            category=trap.category,
            expected_terminal_status=TerminalStatus.INSUFFICIENT_EVIDENCE,
            observed_terminal_status=TerminalStatus.INSUFFICIENT_EVIDENCE,
            outcome=AbstentionOutcome.CORRECT_ABSTENTION,
        )


def test_row_outcome_must_be_recomputable_from_its_own_status() -> None:
    query_set = _query_set()
    trap = _query(query_set, "atq-029")
    answerable = _query(query_set, "atq-013")

    with pytest.raises(ValueError, match="outcome"):
        QueryAbstention(
            query_id=trap.query_id,
            category=trap.category,
            expected_terminal_status=TerminalStatus.VALIDATION_FAILED_CLOSED,
            observed_terminal_status=TerminalStatus.PASSED,
            outcome=AbstentionOutcome.CORRECT_ABSTENTION,
        )
    with pytest.raises(ValueError, match="outcome"):
        QueryAbstention(
            query_id=answerable.query_id,
            category=answerable.category,
            expected_terminal_status=TerminalStatus.PASSED,
            observed_terminal_status=TerminalStatus.PASSED,
            outcome=AbstentionOutcome.OVER_ABSTAINED,
        )


def test_query_abstention_rejects_wrong_component_types() -> None:
    query_set = _query_set()
    entry = _report(query_set, _baseline_records(query_set)).per_query[0]

    with pytest.raises(TypeError, match="category"):
        QueryAbstention(
            query_id=entry.query_id,
            category="single_hop",  # type: ignore[arg-type]
            expected_terminal_status=entry.expected_terminal_status,
            observed_terminal_status=entry.observed_terminal_status,
            outcome=entry.outcome,
        )
    with pytest.raises(TypeError, match="expected_terminal_status"):
        QueryAbstention(
            query_id=entry.query_id,
            category=entry.category,
            expected_terminal_status="passed",  # type: ignore[arg-type]
            observed_terminal_status=entry.observed_terminal_status,
            outcome=entry.outcome,
        )
    with pytest.raises(TypeError, match="outcome"):
        QueryAbstention(
            query_id=entry.query_id,
            category=entry.category,
            expected_terminal_status=entry.expected_terminal_status,
            observed_terminal_status=entry.observed_terminal_status,
            outcome="answered",  # type: ignore[arg-type]
        )


def test_classification_rejects_wrong_input_types() -> None:
    query_set = _query_set()
    query = _query(query_set, "atq-027")

    with pytest.raises(TypeError, match="query must be a QueryRecord"):
        classify_abstention("atq-027", _observation(query, TerminalStatus.PASSED))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="observation must be a MetricObservation"):
        classify_abstention(query, "observation")  # type: ignore[arg-type]


def test_suite_helper_rejects_a_non_query_set() -> None:
    with pytest.raises(TypeError, match="query_set"):
        abstention_suite_queries("query-set")  # type: ignore[arg-type]


def test_report_rejects_inconsistent_hand_built_fields() -> None:
    query_set = _query_set()
    report = _report(query_set, _baseline_records(query_set))

    with pytest.raises(ValueError, match="64 lowercase"):
        replace(report, query_set_sha256="abc")
    with pytest.raises(TypeError, match="random_seed"):
        replace(report, random_seed=True)
    with pytest.raises(ValueError, match="non-negative"):
        replace(report, random_seed=-1)
    with pytest.raises(ValueError, match="per_query must not be empty"):
        replace(report, per_query=())
    with pytest.raises(TypeError, match="per_query"):
        replace(report, per_query=("row",))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="duplicate"):
        replace(report, per_query=(report.per_query[0], report.per_query[0]))
    with pytest.raises(ValueError, match="ascending"):
        replace(report, per_query=tuple(reversed(report.per_query)))
    with pytest.raises(TypeError, match="AbstentionRate"):
        replace(
            report,
            rates={**dict(report.rates), "trap_abstention_recall": "0.0"},  # type: ignore[dict-item]
        )
    with pytest.raises(ValueError, match="carries the name"):
        replace(
            report,
            rates={
                **dict(report.rates),
                "trap_abstention_recall": AbstentionRate(
                    name="unsafe_refusal_recall", value=1.0, numerator=2, denominator=2, reason=None
                ),
            },
        )
    with pytest.raises(ValueError, match="suite_query_ids"):
        replace(report, suite_query_ids=())
    with pytest.raises(ValueError, match="cannot be both evaluated and not evaluated"):
        replace(report, not_evaluated_query_ids=("atq-013",))


def test_report_rejects_an_unknown_strategy_or_contract_version() -> None:
    query_set = _query_set()
    report = _report(query_set, _baseline_records(query_set))

    with pytest.raises((TypeError, ValueError), match="strategy"):
        replace(report, strategy="s7")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="contract_version"):
        replace(report, contract_version="mfg-agentgraph-abstention-suite-v2")


def test_rate_rejects_inconsistent_arithmetic() -> None:
    with pytest.raises(ValueError, match="value"):
        AbstentionRate(
            name="trap_abstention_recall",
            value=0.5,
            numerator=1,
            denominator=4,
            reason=None,
        )
    with pytest.raises(ValueError, match="reason"):
        AbstentionRate(
            name="trap_abstention_recall",
            value=None,
            numerator=0,
            denominator=0,
            reason=None,
        )


def test_rate_rejects_every_invalid_arithmetic_shape() -> None:
    with pytest.raises(ValueError, match="name"):
        AbstentionRate(name="recall", value=0.0, numerator=0, denominator=4, reason=None)
    with pytest.raises(TypeError, match="numerator"):
        AbstentionRate(
            name="trap_abstention_recall",
            value=0.5,
            numerator="1",  # type: ignore[arg-type]
            denominator=2,
            reason=None,
        )
    with pytest.raises(ValueError, match="non-negative"):
        AbstentionRate(
            name="trap_abstention_recall", value=None, numerator=0, denominator=-1, reason="r"
        )
    with pytest.raises(ValueError, match="denominator"):
        AbstentionRate(
            name="trap_abstention_recall", value=0.5, numerator=3, denominator=2, reason=None
        )
    with pytest.raises(ValueError, match="denominator"):
        AbstentionRate(
            name="trap_abstention_recall", value=None, numerator=1, denominator=0, reason="r"
        )
    with pytest.raises(ValueError, match="must not include a value"):
        AbstentionRate(
            name="trap_abstention_recall", value=0.0, numerator=0, denominator=0, reason="r"
        )
    with pytest.raises(ValueError, match="must not include a reason"):
        AbstentionRate(
            name="trap_abstention_recall", value=1.0, numerator=1, denominator=1, reason="r"
        )
    with pytest.raises(ValueError, match="requires a value"):
        AbstentionRate(
            name="trap_abstention_recall", value=None, numerator=1, denominator=1, reason=None
        )
    with pytest.raises(ValueError, match="finite"):
        AbstentionRate(
            name="trap_abstention_recall",
            value=float("inf"),
            numerator=1,
            denominator=1,
            reason=None,
        )


def test_rate_rejects_non_string_reason_and_boolean_value() -> None:
    with pytest.raises(TypeError, match="reason"):
        AbstentionRate(
            name="trap_abstention_recall",
            value=None,
            numerator=0,
            denominator=0,
            reason=b"reason",  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="value"):
        AbstentionRate(
            name="trap_abstention_recall",
            value=True,
            numerator=1,
            denominator=1,
            reason=None,
        )


def test_integral_rate_value_is_normalised_to_float() -> None:
    rate = AbstentionRate(
        name="unsafe_refusal_recall",
        value=1,
        numerator=1,
        denominator=1,
        reason=None,
    )

    assert rate.value == 1.0
    assert isinstance(rate.value, float)


def test_report_rejects_an_invalid_query_set_universe() -> None:
    query_set = _query_set()
    report = _report(query_set, _baseline_records(query_set))
    universe = tuple(report.query_set_query_ids)

    with pytest.raises(ValueError, match="query_set_query_ids must not be empty"):
        replace(report, query_set_query_ids=())
    with pytest.raises(ValueError, match="duplicate"):
        replace(report, query_set_query_ids=(*universe, universe[0]))
    with pytest.raises(ValueError, match="ascending"):
        replace(report, query_set_query_ids=tuple(reversed(universe)))


def test_report_rejects_coverage_entries_outside_the_universe() -> None:
    query_set = _query_set()
    full = _report(query_set, _baseline_records(query_set))
    universe_without_atq_013 = tuple(
        query_id for query_id in full.query_set_query_ids if query_id != "atq-013"
    )

    with pytest.raises(ValueError, match="is not in query_set_query_ids"):
        replace(full, query_set_query_ids=universe_without_atq_013)

    partial = _report(
        query_set,
        tuple(
            record for record in _baseline_records(query_set) if record.result.query_id == "atq-001"
        ),
    )
    universe_without_atq_027 = tuple(
        query_id for query_id in partial.query_set_query_ids if query_id != "atq-027"
    )
    consistent_remainder = tuple(
        query_id for query_id in universe_without_atq_027 if query_id != "atq-001"
    )
    with pytest.raises(ValueError, match="query_set_categories"):
        replace(
            partial,
            query_set_query_ids=universe_without_atq_027,
            not_evaluated_query_ids=consistent_remainder,
        )
    with pytest.raises(ValueError, match="suite_query_ids"):
        replace(
            partial,
            suite_query_ids=("atq-027", "atq-027", "atq-028", "atq-029", "atq-030"),
        )


def test_record_with_a_malformed_observation_is_refused() -> None:
    query_set = _query_set()
    configuration = _configuration(query_set)
    genuine = _record(
        _query(query_set, "atq-027"),
        TerminalStatus.INSUFFICIENT_EVIDENCE,
        configuration=configuration,
        query_set=query_set,
    )
    broken = _Record(result=genuine.result, observation="observation")  # type: ignore[arg-type]

    with pytest.raises(TypeError, match=r"records\[0\]\.observation"):
        _report(query_set, (broken,))


def test_partial_report_cannot_forge_its_suite_from_unevaluated_queries() -> None:
    """A partial run may not relabel an unevaluated answerable query as a trap."""
    query_set = _query_set()
    partial = _report(
        query_set,
        tuple(
            record for record in _baseline_records(query_set) if record.result.query_id == "atq-027"
        ),
    )
    forged = ("atq-001", "atq-027")

    with pytest.raises(ValueError, match="suite_query_ids"):
        replace(partial, suite_query_ids=forged)


def test_suite_must_equal_every_trap_in_the_recorded_query_set() -> None:
    query_set = _query_set()
    partial = _report(
        query_set,
        tuple(
            record for record in _baseline_records(query_set) if record.result.query_id == "atq-027"
        ),
    )

    with pytest.raises(ValueError, match="suite_query_ids"):
        replace(partial, suite_query_ids=("atq-027", "atq-028", "atq-029"))


def test_recorded_categories_must_cover_the_universe_and_match_the_rows() -> None:
    query_set = _query_set()
    report = _report(query_set, _baseline_records(query_set))
    categories = dict(report.query_set_categories)

    missing_one = {k: v for k, v in categories.items() if k != "atq-013"}
    with pytest.raises(ValueError, match="query_set_categories"):
        replace(report, query_set_categories=missing_one)
    with pytest.raises(ValueError, match="query_set_categories"):
        replace(report, query_set_categories={**categories, "atq-099": QueryCategory.SINGLE_HOP})
    with pytest.raises(TypeError, match="query_set_categories"):
        replace(
            report,
            query_set_categories={**categories, "atq-013": "single_hop"},  # type: ignore[dict-item]
        )
    with pytest.raises(ValueError, match="category does not match"):
        replace(
            report,
            query_set_categories={**categories, "atq-013": QueryCategory.PROVENANCE},
        )
