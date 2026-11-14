"""Score a strategy run against the versioned synthetic reference.

This is the consumer for `mfg-agentgraph-synthetic-reference-v2`. It does not reimplement
any metric: per-query values come from `compute_query_metrics` and run-level values from
`summarize_run`, both of which the shared S1–S4 harness already uses.

What it adds is the reference gate and the honest scope statement:

- a run whose recorded dataset digest does not match the reference's query set is refused,
  so numbers can never be attributed to a reference describing different queries;
- when a reference entry's citations are not anchored in the frozen artefacts, the
  reference-dependent metrics become not-applicable with a stated reason instead of scoring
  a caller against a broken reference;
- metrics measured from the run itself — SHACL validation, repair, provenance completeness,
  latency, memory — are never suppressed, because the reference has no bearing on them;
- a partial run is supported, so a five-query pilot reports what it measured and names the
  queries it did not, rather than implying full coverage;
- the artifact states that the reference is single-author, AI-assisted, and not
  independently validated.

Absence of a value is always reported as not-applicable with a reason, never as zero.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from mfg_agentgraph.annotation_sources import canonical_json
from mfg_agentgraph.anomaly_triage_dataset import QueryRecord, QuerySet
from mfg_agentgraph.evaluation_harness import (
    EvaluationRunConfiguration,
    dataset_sha256_from_configuration,
)
from mfg_agentgraph.evaluation_metrics import (
    MetricApplicability,
    MetricName,
    MetricObservation,
    MetricSummary,
    MetricValue,
    compute_query_metrics,
    summarize_run,
)
from mfg_agentgraph.synthetic_reference import (
    ReferenceStrength,
    SyntheticReference,
    SyntheticReferenceEntry,
)

REFERENCE_SCORE_CONTRACT_VERSION = "mfg-agentgraph-reference-score-v1"

# Metrics that compare a run against the reference label itself. Everything else is measured
# from the run, or — for the expected terminal status — fixed by the dataset contract.
REFERENCE_DEPENDENT_METRICS: tuple[MetricName, ...] = (
    MetricName.HITS_AT_ANY,
    MetricName.EVIDENCE_SUPPORT_COVERAGE,
    MetricName.EVIDENCE_CITATION_PRECISION,
    MetricName.ANSWER_ACTION_EXACT_MATCH,
    MetricName.ANSWER_ACTION_TOKEN_F1,
)

# Everything the reference cannot influence: measured from the run itself.
RUN_MEASURED_METRICS: tuple[MetricName, ...] = tuple(
    name for name in MetricName if name not in REFERENCE_DEPENDENT_METRICS
)

_SCOPE = (
    "Single-author, AI-assisted synthetic reference. Scores describe software behaviour "
    "against frozen scenario fixtures: they are not independently validated, not expert "
    "reviewed, and carry no inter-annotator agreement. Reference-dependent metrics are "
    "reported as not-applicable where the citation is not anchored, and must never be "
    "scored as a false answer. Label-derived run summaries cover only anchored entries, and "
    "their applicable_count states that coverage."
)


@dataclass(frozen=True, slots=True)
class ReferenceScore:
    """One strategy run scored against the synthetic reference."""

    strategy: str
    query_set_id: str
    model_configuration_id: str
    retrieval_configuration_id: str
    random_seed: int
    reference_sha256: str
    query_set_sha256: str
    scenario_sha256: str
    authoring: Mapping[str, object]
    original_requirement_status: str
    per_query: Mapping[str, Mapping[MetricName, MetricValue]]
    summary: Mapping[MetricName, MetricSummary]
    observed_query_ids: Sequence[str]
    not_evaluated_query_ids: Sequence[str]
    suppressed_query_ids: Sequence[str]
    contract_version: str = REFERENCE_SCORE_CONTRACT_VERSION

    def __post_init__(self) -> None:
        for field_name in ("reference_sha256", "query_set_sha256", "scenario_sha256"):
            digest = getattr(self, field_name)
            if len(digest) != 64 or any(
                character not in "0123456789abcdef" for character in digest
            ):
                raise ValueError(f"{field_name} must be 64 lowercase hexadecimal characters")
        if not self.per_query:
            raise ValueError("per_query must not be empty")
        for field_name in (
            "observed_query_ids",
            "not_evaluated_query_ids",
            "suppressed_query_ids",
        ):
            object.__setattr__(self, field_name, tuple(getattr(self, field_name)))
        overlap = set(self.observed_query_ids) & set(self.not_evaluated_query_ids)
        if overlap:
            raise ValueError(
                f"query {sorted(overlap)[0]!r} cannot be both observed and not evaluated"
            )

    def to_document(self) -> dict[str, object]:
        return {
            "authoring": dict(self.authoring),
            "contract_version": self.contract_version,
            "model_configuration_id": self.model_configuration_id,
            "not_evaluated_query_ids": list(self.not_evaluated_query_ids),
            "observed_query_count": len(self.observed_query_ids),
            "observed_query_ids": list(self.observed_query_ids),
            "original_requirement_status": self.original_requirement_status,
            "per_query": {
                query_id: {name.value: value.to_dict() for name, value in metrics.items()}
                for query_id, metrics in self.per_query.items()
            },
            "query_set_id": self.query_set_id,
            "query_set_sha256": self.query_set_sha256,
            "random_seed": self.random_seed,
            "reference_sha256": self.reference_sha256,
            "retrieval_configuration_id": self.retrieval_configuration_id,
            "scenario_sha256": self.scenario_sha256,
            "scope": _SCOPE,
            "strategy": self.strategy,
            "summary": {name.value: value.to_dict() for name, value in self.summary.items()},
            "suppressed_query_ids": list(self.suppressed_query_ids),
        }

    def to_json(self) -> str:
        """Return canonical JSON for a persisted scoring report."""
        return canonical_json(self.to_document())

    @property
    def document_sha256(self) -> str:
        """Return the SHA-256 of the canonical scoring report bytes."""
        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()


def _suppressed(metric: MetricName, entry: SyntheticReferenceEntry) -> MetricValue:
    unresolved = ", ".join(entry.unresolved_evidence_refs)
    return MetricValue(
        metric=metric,
        value=None,
        applicability=MetricApplicability.NOT_APPLICABLE,
        reason=(
            "reference citation is not anchored in the frozen artifacts "
            f"({unresolved}); the reference cannot settle this query"
        ),
    )


def _metrics_for(
    observation: MetricObservation,
    query: QueryRecord,
    entry: SyntheticReferenceEntry,
) -> Mapping[MetricName, MetricValue]:
    """Return the shared engine's values, suppressing reference metrics when unanchored."""
    base = dict(compute_query_metrics(observation, query))
    if entry.strength is ReferenceStrength.UNANCHORED:
        for metric in REFERENCE_DEPENDENT_METRICS:
            base[metric] = _suppressed(metric, entry)
    return MappingProxyType(base)


def _summarize(
    *,
    observations: Sequence[MetricObservation],
    observed: Sequence[QueryRecord],
    observed_ids: Sequence[str],
    suppressed_ids: Sequence[str],
) -> Mapping[MetricName, MetricSummary]:
    """Aggregate run-measured metrics over every observation, label metrics over anchored ones.

    Suppressing a per-query value is pointless if the run summary recomputes it from the
    original query label, so label-derived metrics are aggregated only from anchored entries.
    Run-measured metrics keep covering every observed query, including suppressed ones.
    """
    run_summary = summarize_run(observations, observed)
    anchored_ids = set(observed_ids) - set(suppressed_ids)
    if anchored_ids:
        anchored_observations = [
            observation for observation in observations if observation.query_id in anchored_ids
        ]
        anchored_queries = [query for query in observed if query.query_id in anchored_ids]
        label_summary = summarize_run(anchored_observations, anchored_queries)
    else:
        label_summary = {}
    merged: dict[MetricName, MetricSummary] = {}
    for name in MetricName:
        if name in REFERENCE_DEPENDENT_METRICS:
            merged[name] = label_summary.get(
                name,
                MetricSummary(
                    metric=name,
                    rq=run_summary[name].rq,
                    value=None,
                    applicable_count=0,
                    undefined_count=len(observed_ids),
                    reason=(
                        "no observed query has an anchored reference entry, so "
                        "reference-derived metrics are not applicable"
                    ),
                ),
            )
        else:
            merged[name] = run_summary[name]
    return MappingProxyType(merged)


def score_reference_run(
    *,
    configuration: EvaluationRunConfiguration,
    query_set: QuerySet,
    reference: SyntheticReference,
    observations: Sequence[MetricObservation],
) -> ReferenceScore:
    """Score one run against the reference, failing closed on any provenance mismatch."""
    if not isinstance(configuration, EvaluationRunConfiguration):
        raise TypeError("configuration must be an EvaluationRunConfiguration")
    if not isinstance(query_set, QuerySet):
        raise TypeError("query_set must be a QuerySet")
    if not isinstance(reference, SyntheticReference):
        raise TypeError("reference must be a SyntheticReference")
    if isinstance(observations, (str, bytes, bytearray)) or not isinstance(observations, Sequence):
        raise TypeError("observations must be a sequence of MetricObservation instances")
    if not observations:
        raise ValueError("at least one observation is required")

    dataset_digest = dataset_sha256_from_configuration(configuration)
    if dataset_digest != reference.query_set_sha256:
        raise ValueError(
            "run dataset_sha256 does not match the reference query set: "
            f"run {dataset_digest}, reference {reference.query_set_sha256}"
        )
    if query_set.document_sha256 != reference.query_set_sha256:
        raise ValueError(
            "query set does not match the reference query set: "
            f"query set {query_set.document_sha256}, reference {reference.query_set_sha256}"
        )

    queries = {query.query_id: query for query in query_set.queries}
    entries = {entry.query_id: entry for entry in reference.entries}
    per_query: dict[str, Mapping[MetricName, MetricValue]] = {}
    observed_ids: list[str] = []
    suppressed_ids: list[str] = []
    for observation in observations:
        query = queries.get(observation.query_id)
        if query is None:
            raise ValueError(f"observation query_id {observation.query_id!r} has no matching query")
        if observation.query_id in per_query:
            raise ValueError(f"duplicate observation for query_id {observation.query_id!r}")
        entry = entries[observation.query_id]
        per_query[observation.query_id] = _metrics_for(observation, query, entry)
        observed_ids.append(observation.query_id)
        if entry.strength is ReferenceStrength.UNANCHORED:
            suppressed_ids.append(observation.query_id)

    observed = [query for query in query_set.queries if query.query_id in set(observed_ids)]
    summary = _summarize(
        observations=observations,
        observed=observed,
        observed_ids=observed_ids,
        suppressed_ids=suppressed_ids,
    )
    missing = [query.query_id for query in query_set.queries if query.query_id not in per_query]

    return ReferenceScore(
        strategy=configuration.strategy.value,
        query_set_id=configuration.query_set_id,
        model_configuration_id=configuration.model_configuration_id,
        retrieval_configuration_id=configuration.retrieval_configuration_id,
        random_seed=configuration.random_seed,
        reference_sha256=reference.document_sha256,
        query_set_sha256=reference.query_set_sha256,
        scenario_sha256=reference.scenario_sha256,
        authoring=reference.authoring,
        original_requirement_status=reference.original_requirement_status,
        per_query=MappingProxyType(per_query),
        summary=summary,
        observed_query_ids=observed_ids,
        not_evaluated_query_ids=missing,
        suppressed_query_ids=suppressed_ids,
    )
