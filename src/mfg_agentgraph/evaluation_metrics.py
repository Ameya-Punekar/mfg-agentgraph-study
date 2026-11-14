"""Deterministic RQ-mapped metrics for comparable S1-S4 evaluation runs."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from mfg_agentgraph.anomaly_triage_dataset import (
    TRAP_CATEGORIES,
    TRAP_TERMINAL_STATUS,
    QueryRecord,
)
from mfg_agentgraph.stage_instrumentation import TerminalStatus

_MAX_TEXT_BYTES = 8_192
_SUMMARY_PRECISION = 6
_NORMALIZATION_PATTERN = re.compile(r"[^0-9a-z]+")

REQUIRED_PROVENANCE_COMPONENTS: tuple[str, ...] = (
    "activity",
    "agent",
    "entity",
    "used",
    "wasGeneratedBy",
)


class ResearchQuestion(StrEnum):
    """Thesis research questions that metrics are mapped to."""

    RQ1 = "RQ1"
    RQ2 = "RQ2"
    RQ3 = "RQ3"
    RQ4 = "RQ4"


class MetricName(StrEnum):
    """Stable metric identifiers, ordered per-query first, then run-level."""

    HITS_AT_ANY = "hits_at_any"
    EVIDENCE_SUPPORT_COVERAGE = "evidence_support_coverage"
    EVIDENCE_CITATION_PRECISION = "evidence_citation_precision"
    ANSWER_ACTION_EXACT_MATCH = "answer_action_exact_match"
    ANSWER_ACTION_TOKEN_F1 = "answer_action_token_f1"
    TERMINAL_STATUS_MATCH = "terminal_status_match"
    INITIAL_SHACL_PASS = "initial_shacl_pass"
    FINAL_SHACL_PASS = "final_shacl_pass"
    REPAIR_ITERATIONS = "repair_iterations"
    REPAIR_SUCCEEDED_AFTER_FAILURE = "repair_succeeded_after_failure"
    PROVENANCE_COMPLETENESS = "provenance_completeness"
    LATENCY_P50_MS = "latency_p50_ms"
    LATENCY_P95_MS = "latency_p95_ms"
    PEAK_MEMORY_MB = "peak_memory_mb"


_RUN_LEVEL_METRICS: tuple[MetricName, ...] = (
    MetricName.LATENCY_P50_MS,
    MetricName.LATENCY_P95_MS,
    MetricName.PEAK_MEMORY_MB,
)
_PER_QUERY_METRICS: tuple[MetricName, ...] = tuple(
    name for name in MetricName if name not in _RUN_LEVEL_METRICS
)

METRIC_RQ: Mapping[MetricName, ResearchQuestion] = MappingProxyType(
    {
        MetricName.HITS_AT_ANY: ResearchQuestion.RQ1,
        MetricName.EVIDENCE_SUPPORT_COVERAGE: ResearchQuestion.RQ1,
        MetricName.EVIDENCE_CITATION_PRECISION: ResearchQuestion.RQ1,
        MetricName.ANSWER_ACTION_EXACT_MATCH: ResearchQuestion.RQ1,
        MetricName.ANSWER_ACTION_TOKEN_F1: ResearchQuestion.RQ1,
        MetricName.TERMINAL_STATUS_MATCH: ResearchQuestion.RQ1,
        MetricName.INITIAL_SHACL_PASS: ResearchQuestion.RQ2,
        MetricName.FINAL_SHACL_PASS: ResearchQuestion.RQ2,
        MetricName.REPAIR_ITERATIONS: ResearchQuestion.RQ2,
        MetricName.REPAIR_SUCCEEDED_AFTER_FAILURE: ResearchQuestion.RQ2,
        MetricName.PROVENANCE_COMPLETENESS: ResearchQuestion.RQ3,
        MetricName.LATENCY_P50_MS: ResearchQuestion.RQ4,
        MetricName.LATENCY_P95_MS: ResearchQuestion.RQ4,
        MetricName.PEAK_MEMORY_MB: ResearchQuestion.RQ4,
    }
)

DEFERRED_METRICS: Mapping[str, str] = MappingProxyType(
    {
        "ragas_faithfulness": (
            "requires an LLM judge, which is non-deterministic; deferred to a separately "
            "gated judge study"
        ),
        "ragas_answer_relevance": (
            "requires an LLM judge, which is non-deterministic; deferred to a separately "
            "gated judge study"
        ),
        "operator_trust_likert": "requires a human operator study with participants",
        "system_usability_scale": "requires a human usability study with participants",
    }
)


class MetricApplicability(StrEnum):
    """Whether a metric is defined for a given query or run."""

    PRESENT = "present"
    NOT_APPLICABLE = "not_applicable"


def _require_text(value: object, field_name: str, *, maximum_bytes: int = _MAX_TEXT_BYTES) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string")
    if len(value.encode("utf-8")) > maximum_bytes:
        raise ValueError(f"{field_name} exceeds {maximum_bytes} UTF-8 bytes")
    return value


def _require_identifier(value: object, field_name: str) -> str:
    normalized = _require_text(value, field_name).strip()
    if not normalized:
        raise ValueError(f"{field_name} must be nonblank")
    return normalized


def _require_unique_identifiers(value: object, field_name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be a sequence of strings")
    normalized = tuple(_require_identifier(item, field_name) for item in value)
    seen: set[str] = set()
    for identifier in normalized:
        if identifier in seen:
            raise ValueError(f"{field_name} must not contain duplicate identifier {identifier!r}")
        seen.add(identifier)
    return normalized


def _require_optional_finite(value: object, field_name: str) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be a finite number or None")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    if normalized < 0.0:
        raise ValueError(f"{field_name} must be non-negative")
    return normalized


def _require_optional_bool(value: object, field_name: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool or None")
    return value


def _require_optional_count(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer or None")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return value


@dataclass(frozen=True, slots=True)
class MetricObservation:
    """Typed per-query measurement input supplied by a strategy adapter."""

    query_id: str
    predicted_answer: str
    cited_evidence_refs: Sequence[str]
    terminal_status: TerminalStatus
    initial_shacl_passed: bool | None = None
    final_shacl_passed: bool | None = None
    repair_iterations: int | None = None
    provenance_components: Sequence[str] | None = None
    latency_ms: float | None = None
    peak_memory_mb: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "query_id", _require_identifier(self.query_id, "query_id"))
        object.__setattr__(
            self, "predicted_answer", _require_text(self.predicted_answer, "predicted_answer")
        )
        object.__setattr__(
            self,
            "cited_evidence_refs",
            _require_unique_identifiers(self.cited_evidence_refs, "cited_evidence_refs"),
        )
        if not isinstance(self.terminal_status, TerminalStatus):
            raise TypeError("terminal_status must be a TerminalStatus")
        object.__setattr__(
            self,
            "initial_shacl_passed",
            _require_optional_bool(self.initial_shacl_passed, "initial_shacl_passed"),
        )
        object.__setattr__(
            self,
            "final_shacl_passed",
            _require_optional_bool(self.final_shacl_passed, "final_shacl_passed"),
        )
        object.__setattr__(
            self,
            "repair_iterations",
            _require_optional_count(self.repair_iterations, "repair_iterations"),
        )
        if self.provenance_components is not None:
            object.__setattr__(
                self,
                "provenance_components",
                _require_unique_identifiers(self.provenance_components, "provenance_components"),
            )
        object.__setattr__(
            self, "latency_ms", _require_optional_finite(self.latency_ms, "latency_ms")
        )
        object.__setattr__(
            self,
            "peak_memory_mb",
            _require_optional_finite(self.peak_memory_mb, "peak_memory_mb"),
        )


@dataclass(frozen=True, slots=True)
class MetricValue:
    """One metric result, explicitly present or not applicable."""

    metric: MetricName
    value: float | None
    applicability: MetricApplicability
    reason: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.metric, MetricName):
            raise TypeError("metric must be a MetricName")
        if not isinstance(self.applicability, MetricApplicability):
            raise TypeError("applicability must be a MetricApplicability")
        if self.applicability is MetricApplicability.PRESENT:
            if self.reason is not None:
                raise ValueError("present metric must not include a reason")
            if self.value is None:
                raise ValueError("present metric requires a value")
            if not math.isfinite(self.value):
                raise ValueError("metric value must be finite")
            return
        if self.value is not None:
            raise ValueError("not-applicable metric must not include a value")
        if self.reason is None or not self.reason.strip():
            raise ValueError("not-applicable metric requires a reason")

    def to_dict(self) -> dict[str, object]:
        return {
            "applicability": self.applicability.value,
            "metric": self.metric.value,
            "reason": self.reason,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True)
class MetricSummary:
    """One run-level metric with its coverage counts."""

    metric: MetricName
    rq: ResearchQuestion
    value: float | None
    applicable_count: int
    undefined_count: int
    reason: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.metric, MetricName):
            raise TypeError("metric must be a MetricName")
        if not isinstance(self.rq, ResearchQuestion):
            raise TypeError("rq must be a ResearchQuestion")
        for field_name in ("applicable_count", "undefined_count"):
            count = getattr(self, field_name)
            if not isinstance(count, int) or isinstance(count, bool):
                raise TypeError(f"{field_name} must be an integer")
            if count < 0:
                raise ValueError(f"{field_name} must be non-negative")
        if self.value is None:
            if self.reason is None or not self.reason.strip():
                raise ValueError("undefined metric summary requires a reason")
            return
        if not math.isfinite(self.value):
            raise ValueError("metric value must be finite")
        if self.reason is not None:
            raise ValueError("defined metric summary must not include a reason")

    def to_dict(self) -> dict[str, object]:
        return {
            "applicable_count": self.applicable_count,
            "metric": self.metric.value,
            "reason": self.reason,
            "rq": self.rq.value,
            "undefined_count": self.undefined_count,
            "value": self.value,
        }


def _normalize_tokens(text: str) -> tuple[str, ...]:
    """Split answer/action text for lexical scoring, deliberately keeping stopwords.

    Retrieval tokenizers drop function words so a shared "the" cannot count as a
    match; lexical answer metrics must keep every token so exact-match and token-F1
    compare the whole answer.
    """
    return tuple(token for token in _NORMALIZATION_PATTERN.split(text.lower()) if token)


def _present(metric: MetricName, value: float) -> MetricValue:
    return MetricValue(
        metric=metric, value=value, applicability=MetricApplicability.PRESENT, reason=None
    )


def _undefined(metric: MetricName, reason: str) -> MetricValue:
    return MetricValue(
        metric=metric,
        value=None,
        applicability=MetricApplicability.NOT_APPLICABLE,
        reason=reason,
    )


def _token_f1(predicted: tuple[str, ...], expected: tuple[str, ...]) -> float:
    predicted_counts: dict[str, int] = {}
    for token in predicted:
        predicted_counts[token] = predicted_counts.get(token, 0) + 1
    intersection = 0
    for token in expected:
        remaining = predicted_counts.get(token, 0)
        if remaining:
            intersection += 1
            predicted_counts[token] = remaining - 1
    if not intersection:
        return 0.0
    precision = intersection / len(predicted)
    recall = intersection / len(expected)
    return 2 * precision * recall / (precision + recall)


def _expected_terminal_status(query: QueryRecord) -> TerminalStatus:
    if query.category in TRAP_CATEGORIES:
        return TRAP_TERMINAL_STATUS[query.category]
    return TerminalStatus.PASSED


def compute_query_metrics(
    observation: MetricObservation, query: QueryRecord
) -> Mapping[MetricName, MetricValue]:
    """Compute the per-query RQ1-RQ3 metrics for one observation."""
    if observation.query_id != query.query_id:
        raise ValueError(
            f"observation query_id {observation.query_id!r} does not match query {query.query_id!r}"
        )
    expected_refs = frozenset(query.expected_evidence_refs)
    cited_refs = frozenset(observation.cited_evidence_refs)
    overlap = expected_refs & cited_refs

    values: dict[MetricName, MetricValue] = {}
    values[MetricName.HITS_AT_ANY] = _present(MetricName.HITS_AT_ANY, 1.0 if overlap else 0.0)
    if expected_refs:
        values[MetricName.EVIDENCE_SUPPORT_COVERAGE] = _present(
            MetricName.EVIDENCE_SUPPORT_COVERAGE, len(overlap) / len(expected_refs)
        )
    else:
        values[MetricName.EVIDENCE_SUPPORT_COVERAGE] = _undefined(
            MetricName.EVIDENCE_SUPPORT_COVERAGE,
            "expected evidence set is empty for trap queries",
        )
    if cited_refs:
        values[MetricName.EVIDENCE_CITATION_PRECISION] = _present(
            MetricName.EVIDENCE_CITATION_PRECISION, len(overlap) / len(cited_refs)
        )
    else:
        values[MetricName.EVIDENCE_CITATION_PRECISION] = _undefined(
            MetricName.EVIDENCE_CITATION_PRECISION,
            "no evidence references were cited",
        )

    expected_action = query.expected_action
    predicted_tokens = _normalize_tokens(observation.predicted_answer)
    if expected_action is None:
        values[MetricName.ANSWER_ACTION_EXACT_MATCH] = _undefined(
            MetricName.ANSWER_ACTION_EXACT_MATCH,
            "gold labels declare no expected action for this query",
        )
        values[MetricName.ANSWER_ACTION_TOKEN_F1] = _undefined(
            MetricName.ANSWER_ACTION_TOKEN_F1,
            "gold labels declare no expected action for this query",
        )
    else:
        expected_tokens = _normalize_tokens(expected_action)
        values[MetricName.ANSWER_ACTION_EXACT_MATCH] = _present(
            MetricName.ANSWER_ACTION_EXACT_MATCH,
            1.0 if predicted_tokens == expected_tokens else 0.0,
        )
        if predicted_tokens:
            values[MetricName.ANSWER_ACTION_TOKEN_F1] = _present(
                MetricName.ANSWER_ACTION_TOKEN_F1,
                _token_f1(predicted_tokens, expected_tokens),
            )
        else:
            values[MetricName.ANSWER_ACTION_TOKEN_F1] = _undefined(
                MetricName.ANSWER_ACTION_TOKEN_F1,
                "predicted answer contains no comparable tokens",
            )

    values[MetricName.TERMINAL_STATUS_MATCH] = _present(
        MetricName.TERMINAL_STATUS_MATCH,
        1.0 if observation.terminal_status is _expected_terminal_status(query) else 0.0,
    )

    for metric, flag in (
        (MetricName.INITIAL_SHACL_PASS, observation.initial_shacl_passed),
        (MetricName.FINAL_SHACL_PASS, observation.final_shacl_passed),
    ):
        values[metric] = (
            _undefined(metric, "strategy does not report SHACL validation")
            if flag is None
            else _present(metric, 1.0 if flag else 0.0)
        )
    values[MetricName.REPAIR_ITERATIONS] = (
        _undefined(MetricName.REPAIR_ITERATIONS, "strategy does not report repair attempts")
        if observation.repair_iterations is None
        else _present(MetricName.REPAIR_ITERATIONS, float(observation.repair_iterations))
    )
    if observation.initial_shacl_passed is None or observation.final_shacl_passed is None:
        values[MetricName.REPAIR_SUCCEEDED_AFTER_FAILURE] = _undefined(
            MetricName.REPAIR_SUCCEEDED_AFTER_FAILURE,
            "strategy does not report SHACL validation",
        )
    elif observation.initial_shacl_passed:
        values[MetricName.REPAIR_SUCCEEDED_AFTER_FAILURE] = _undefined(
            MetricName.REPAIR_SUCCEEDED_AFTER_FAILURE,
            "initial validation already passed, so repair success is not measurable",
        )
    else:
        values[MetricName.REPAIR_SUCCEEDED_AFTER_FAILURE] = _present(
            MetricName.REPAIR_SUCCEEDED_AFTER_FAILURE,
            1.0 if observation.final_shacl_passed else 0.0,
        )

    components = observation.provenance_components
    if components is None:
        values[MetricName.PROVENANCE_COMPLETENESS] = _undefined(
            MetricName.PROVENANCE_COMPLETENESS,
            "strategy does not emit a provenance trace artifact",
        )
    else:
        present_components = frozenset(components) & frozenset(REQUIRED_PROVENANCE_COMPONENTS)
        values[MetricName.PROVENANCE_COMPLETENESS] = _present(
            MetricName.PROVENANCE_COMPLETENESS,
            len(present_components) / len(REQUIRED_PROVENANCE_COMPONENTS),
        )

    return MappingProxyType({name: values[name] for name in _PER_QUERY_METRICS})


def _mean(values: Sequence[float]) -> float:
    return round(sum(values) / len(values), _SUMMARY_PRECISION)


def _nearest_rank(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile / 100.0 * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def _summary(
    metric: MetricName,
    values: Sequence[float],
    total: int,
    empty_reason: str,
) -> MetricSummary:
    if not values:
        return MetricSummary(
            metric=metric,
            rq=METRIC_RQ[metric],
            value=None,
            applicable_count=0,
            undefined_count=total,
            reason=empty_reason,
        )
    if metric is MetricName.LATENCY_P50_MS:
        computed = _nearest_rank(values, 50.0)
    elif metric is MetricName.LATENCY_P95_MS:
        computed = _nearest_rank(values, 95.0)
    elif metric is MetricName.PEAK_MEMORY_MB:
        computed = max(values)
    else:
        computed = _mean(values)
    return MetricSummary(
        metric=metric,
        rq=METRIC_RQ[metric],
        value=round(computed, _SUMMARY_PRECISION),
        applicable_count=len(values),
        undefined_count=total - len(values),
        reason=None,
    )


def summarize_run(
    observations: Sequence[MetricObservation],
    queries: Sequence[QueryRecord],
) -> Mapping[MetricName, MetricSummary]:
    """Aggregate per-query metric values into run-level summaries."""
    if not observations or not queries:
        raise ValueError("summarize_run requires at least one observation and one query")
    query_by_id: dict[str, QueryRecord] = {}
    for query in queries:
        if query.query_id in query_by_id:
            raise ValueError(f"duplicate query_id {query.query_id!r} in the query sequence")
        query_by_id[query.query_id] = query
    observed_ids: set[str] = set()
    for observation in observations:
        if observation.query_id in observed_ids:
            raise ValueError(
                f"duplicate query_id {observation.query_id!r} in the observation sequence"
            )
        if observation.query_id not in query_by_id:
            raise ValueError(f"observation query_id {observation.query_id!r} has no matching query")
        observed_ids.add(observation.query_id)
    missing = sorted(set(query_by_id) - observed_ids)
    if missing:
        raise ValueError(f"no observation provided for query_id {missing[0]!r}")

    per_query = [
        compute_query_metrics(observation, query_by_id[observation.query_id])
        for observation in observations
    ]
    total = len(per_query)
    summary: dict[MetricName, MetricSummary] = {}
    for metric in _PER_QUERY_METRICS:
        values = [
            value.value
            for value in (result[metric] for result in per_query)
            if value.value is not None
        ]
        summary[metric] = _summary(
            metric, values, total, "no applicable values across the evaluated queries"
        )

    latency_values = [
        observation.latency_ms for observation in observations if observation.latency_ms is not None
    ]
    summary[MetricName.LATENCY_P50_MS] = _summary(
        MetricName.LATENCY_P50_MS, latency_values, total, "no latency samples were supplied"
    )
    summary[MetricName.LATENCY_P95_MS] = _summary(
        MetricName.LATENCY_P95_MS, latency_values, total, "no latency samples were supplied"
    )
    memory_values = [
        observation.peak_memory_mb
        for observation in observations
        if observation.peak_memory_mb is not None
    ]
    summary[MetricName.PEAK_MEMORY_MB] = _summary(
        MetricName.PEAK_MEMORY_MB,
        memory_values,
        total,
        "no peak-memory samples were supplied",
    )
    return MappingProxyType({name: summary[name] for name in MetricName})
