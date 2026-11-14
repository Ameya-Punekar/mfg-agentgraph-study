"""S3 ontology-grounded hybrid retrieval registered in the shared harness.

The arm keeps the OG-RAG shape — ontology-mapped factual blocks, key/value
relevance, and greedy minimal-hyperedge coverage — and stops there. It has no
SHACL gate, no bounded repair, and no user-facing PROV-O package; the optional
post-hoc check runs after the S3 answer is recorded and cannot rewrite it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

from rdflib import URIRef

from mfg_agentgraph.anomaly_triage_dataset import QueryRecord, QuerySet
from mfg_agentgraph.candidate_action import CandidateAction, parse_candidate_actions
from mfg_agentgraph.evaluation_harness import (
    ArtifactApplicability,
    ArtifactKind,
    EvaluationArtifact,
    EvaluationError,
    EvaluationResult,
    EvaluationRunConfiguration,
    EvaluationRunManifest,
    EvaluationStrategy,
    dataset_sha256_from_configuration,
    errors_from_events,
)
from mfg_agentgraph.evaluation_metrics import MetricObservation
from mfg_agentgraph.fixture_model_adapter import (
    FixtureModelVariant,
    generate_fixture_candidate_actions,
)
from mfg_agentgraph.procedural_retrieval import ProceduralRetrievalResult
from mfg_agentgraph.recommended_action_rdf_assembly import assemble_recommended_action_rdf
from mfg_agentgraph.s1_naive_rag import tokenize_text
from mfg_agentgraph.shacl_validation import ShaclValidationResult, validate_recommended_action
from mfg_agentgraph.stage_instrumentation import StageEvent, TerminalStatus
from mfg_agentgraph.structured_retrieval import StructuredRetrievalResult

_MODEL_CONFIGURATION_ID = "fixture-model-pump12-v1"
_RETRIEVAL_CONFIGURATION_ID = "ontology-grounded-hybrid-v1"
_MAX_KEY_BYTES = 1_024
_MAX_VALUE_BYTES = 1_000_000
_MAX_EVIDENCE_ID_BYTES = 8_192
_ONTOLOGY_GROUNDED_REASON = "S3 has no online SHACL stage; post-hoc checks are reported separately"
_NO_PROVENANCE_REASON = "S3 emits no user-facing PROV-O package"


def _require_text(value: object, field_name: str, *, maximum_bytes: int) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be nonblank")
    if len(normalized.encode("utf-8")) > maximum_bytes:
        raise ValueError(f"{field_name} exceeds {maximum_bytes} UTF-8 bytes")
    return normalized


def _require_positive_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer")
    if value < 1:
        raise ValueError(f"{field_name} must be positive")
    return value


@dataclass(frozen=True, slots=True)
class S3Fact:
    """One ontology attribute/value pair inside a factual block."""

    key: str
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "key", _require_text(self.key, "key", maximum_bytes=_MAX_KEY_BYTES)
        )
        object.__setattr__(
            self, "value", _require_text(self.value, "value", maximum_bytes=_MAX_VALUE_BYTES)
        )


@dataclass(frozen=True, slots=True)
class S3FactualBlock:
    """One ontology-mapped factual block that acts as a hyperedge."""

    name: str
    asset_id: str
    procedure_id: str
    facts: Sequence[S3Fact]
    evidence_ids: Sequence[str]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "name", _require_text(self.name, "name", maximum_bytes=_MAX_KEY_BYTES)
        )
        object.__setattr__(
            self, "asset_id", _require_text(self.asset_id, "asset_id", maximum_bytes=_MAX_KEY_BYTES)
        )
        object.__setattr__(
            self,
            "procedure_id",
            _require_text(self.procedure_id, "procedure_id", maximum_bytes=_MAX_KEY_BYTES),
        )
        if isinstance(self.facts, (str, bytes, bytearray)) or not isinstance(self.facts, Sequence):
            raise TypeError("facts must be a sequence of S3Fact instances")
        normalized_facts = tuple(self.facts)
        if not normalized_facts:
            raise ValueError("facts must not be empty")
        if not all(isinstance(fact, S3Fact) for fact in normalized_facts):
            raise TypeError("facts must be a sequence of S3Fact instances")
        object.__setattr__(self, "facts", normalized_facts)
        if isinstance(self.evidence_ids, (str, bytes, bytearray)) or not isinstance(
            self.evidence_ids, Sequence
        ):
            raise TypeError("evidence_ids must be a sequence of strings")
        normalized_ids = tuple(
            _require_text(value, "evidence_ids", maximum_bytes=_MAX_EVIDENCE_ID_BYTES)
            for value in self.evidence_ids
        )
        if not normalized_ids:
            raise ValueError("evidence_ids must not be empty")
        if len(set(normalized_ids)) != len(normalized_ids):
            raise ValueError("evidence_ids must be unique within a factual block")
        object.__setattr__(self, "evidence_ids", normalized_ids)


def _normalize_blocks(blocks: object) -> tuple[S3FactualBlock, ...]:
    if isinstance(blocks, (str, bytes, bytearray)) or not isinstance(blocks, Sequence):
        raise TypeError("blocks must be a sequence of S3FactualBlock instances")
    normalized = tuple(blocks)
    if not all(isinstance(block, S3FactualBlock) for block in normalized):
        raise TypeError("blocks must be a sequence of S3FactualBlock instances")
    seen: set[str] = set()
    for block in normalized:
        if block.name in seen:
            raise ValueError(f"duplicate factual block {block.name!r}")
        seen.add(block.name)
    return normalized


def _rank_nodes(
    blocks: Sequence[S3FactualBlock],
    query_tokens: frozenset[str],
    side: str,
    top_k: int,
) -> tuple[tuple[str, int], ...]:
    scored: list[tuple[int, str, int]] = []
    for block in blocks:
        for index, fact in enumerate(block.facts):
            text = fact.key if side == "key" else fact.value
            overlap = len(query_tokens & set(tokenize_text(text)))
            if overlap:
                scored.append((overlap, block.name, index))
    scored.sort(key=lambda item: (-item[0], item[1], item[2]))
    return tuple((name, index) for _, name, index in scored[:top_k])


def retrieve_ontology_grounded(
    blocks: Sequence[S3FactualBlock],
    query_text: str,
    *,
    asset_id: str,
    procedure_id: str | None = None,
    top_k: int = 3,
    max_blocks: int = 3,
) -> tuple[S3FactualBlock, ...]:
    """Select the fewest ontology-applicable blocks covering the query-relevant facts."""
    normalized = _normalize_blocks(blocks)
    normalized_asset = _require_text(asset_id, "asset_id", maximum_bytes=_MAX_KEY_BYTES)
    normalized_procedure = (
        None
        if procedure_id is None
        else _require_text(procedure_id, "procedure_id", maximum_bytes=_MAX_KEY_BYTES)
    )
    limit = _require_positive_int(top_k, "top_k")
    block_limit = _require_positive_int(max_blocks, "max_blocks")
    if type(query_text) is not str:
        raise TypeError("query_text must be a string")
    query_tokens = frozenset(tokenize_text(query_text))
    if not query_tokens:
        return ()
    applicable = tuple(
        block
        for block in normalized
        if block.asset_id == normalized_asset
        and (normalized_procedure is None or block.procedure_id == normalized_procedure)
    )
    if not applicable:
        return ()
    relevant = set(_rank_nodes(applicable, query_tokens, "key", limit))
    relevant.update(_rank_nodes(applicable, query_tokens, "value", limit))
    if not relevant:
        return ()

    selected: list[S3FactualBlock] = []
    selected_names: set[str] = set()
    covered: set[tuple[str, int]] = set()
    while len(selected) < block_limit and len(covered) < len(relevant):
        best: S3FactualBlock | None = None
        best_gain = 0
        for block in applicable:
            if block.name in selected_names:
                continue
            gain = len(
                {
                    (block.name, index)
                    for index in range(len(block.facts))
                    if (block.name, index) in relevant and (block.name, index) not in covered
                }
            )
            if gain == 0:
                continue
            if gain > best_gain or (
                gain == best_gain and best is not None and block.name < best.name
            ):
                best, best_gain = block, gain
        if best is None:  # pragma: no cover - unreachable while relevant nodes stay uncovered
            break
        selected.append(best)
        selected_names.add(best.name)
        covered.update(
            (best.name, index) for index in range(len(best.facts)) if (best.name, index) in relevant
        )
    return tuple(selected)


def build_s3_run_configuration(
    query_set: QuerySet,
    *,
    top_k: int = 3,
    max_blocks: int = 3,
    random_seed: int = 0,
) -> EvaluationRunConfiguration:
    """Build the controlled S3 configuration for one query set."""
    if not isinstance(query_set, QuerySet):
        raise TypeError("query_set must be a QuerySet")
    return EvaluationRunConfiguration(
        strategy=EvaluationStrategy.S3,
        dataset_id=query_set.dataset_id,
        query_set_id=query_set.query_set_id,
        model_configuration_id=_MODEL_CONFIGURATION_ID,
        retrieval_configuration_id=_RETRIEVAL_CONFIGURATION_ID,
        random_seed=random_seed,
        parameters={
            "dataset_sha256": query_set.document_sha256,
            "dataset_version": query_set.version,
            "max_blocks": _require_positive_int(max_blocks, "max_blocks"),
            "top_k": _require_positive_int(top_k, "top_k"),
        },
    )


@dataclass(frozen=True, slots=True)
class S3QueryEvaluation:
    """One S3 query: comparable record, metric observation, and post-hoc inputs."""

    result: EvaluationResult
    observation: MetricObservation
    candidate: CandidateAction | None
    structured_result: StructuredRetrievalResult
    procedural_result: ProceduralRetrievalResult

    def __post_init__(self) -> None:
        if not isinstance(self.result, EvaluationResult):
            raise TypeError("result must be an EvaluationResult")
        if not isinstance(self.observation, MetricObservation):
            raise TypeError("observation must be a MetricObservation")
        if self.candidate is not None and not isinstance(self.candidate, CandidateAction):
            raise TypeError("candidate must be a CandidateAction or None")
        if not isinstance(self.structured_result, StructuredRetrievalResult):
            raise TypeError("structured_result must be a StructuredRetrievalResult")
        if not isinstance(self.procedural_result, ProceduralRetrievalResult):
            raise TypeError("procedural_result must be a ProceduralRetrievalResult")


_T = TypeVar("_T")


def _single_record(records: Sequence[_T], field_name: str) -> _T:
    """Return the only record of a validated sequence, failing closed otherwise."""
    if len(records) != 1:  # pragma: no cover - passed retrieval results carry exactly one
        raise ValueError(f"{field_name} must contain exactly one record")
    return records[0]


def _factual_blocks(
    structured: StructuredRetrievalResult,
    procedural: ProceduralRetrievalResult,
) -> tuple[S3FactualBlock, ...]:
    observation = _single_record(structured.observations, "structured_result.observations")
    structured_support = _single_record(
        structured.support_records, "structured_result.support_records"
    )
    procedural_support = _single_record(
        procedural.support_records, "procedural_result.support_records"
    )
    kg_block = S3FactualBlock(
        name="kg-evidence",
        asset_id=structured.asset.asset_id,
        procedure_id=structured_support.procedure_id,
        facts=(
            S3Fact("asset", structured.asset.asset_id),
            S3Fact("procedure", structured_support.procedure_id),
            S3Fact("anomaly", observation.anomaly),
            S3Fact("signal", observation.signal),
        ),
        evidence_ids=(structured_support.evidence_id,),
    )
    document_block = S3FactualBlock(
        name="document-evidence",
        asset_id=structured.asset.asset_id,
        procedure_id=procedural_support.related_procedure,
        facts=(
            S3Fact("procedure", procedural_support.related_procedure),
            S3Fact("text", procedural_support.text),
        ),
        evidence_ids=(procedural_support.evidence_id,),
    )
    return (kg_block, document_block)


def _record(
    query: QueryRecord,
    configuration: EvaluationRunConfiguration,
    *,
    status: TerminalStatus,
    answer: str,
    evidence_ids: tuple[str, ...],
    errors: tuple[EvaluationError, ...],
    harness_version: str,
    repository_revision: str,
    latency_ms: float | None,
    peak_memory_mb: float | None,
    candidate: CandidateAction | None,
    structured: StructuredRetrievalResult,
    procedural: ProceduralRetrievalResult,
) -> S3QueryEvaluation:
    released = status is TerminalStatus.PASSED
    result = EvaluationResult(
        configuration=configuration,
        manifest=EvaluationRunManifest(
            run_id=f"run:s3:{query.query_id}",
            repository_revision=repository_revision,
            harness_version=harness_version,
            dataset_sha256=dataset_sha256_from_configuration(configuration),
        ),
        query_id=query.query_id,
        raw_output={
            "constraint_validated": False,
            "evidence_ids": list(evidence_ids),
            "provenance_id": None,
            "recommendation": answer if released else None,
            "terminal_status": status.value,
        },
        errors=errors,
        artifacts=(
            EvaluationArtifact(
                kind=ArtifactKind.ANSWER,
                applicability=ArtifactApplicability.PRESENT,
                value={"released": released, "text": answer if released else status.value},
                reason=None,
            ),
            EvaluationArtifact(
                kind=ArtifactKind.RETRIEVED_CONTEXT,
                applicability=ArtifactApplicability.PRESENT,
                value={"evidence_ids": list(evidence_ids)},
                reason=None,
            ),
            EvaluationArtifact(
                kind=ArtifactKind.VALIDATION_REPORT,
                applicability=ArtifactApplicability.NOT_APPLICABLE,
                value=None,
                reason=_ONTOLOGY_GROUNDED_REASON,
            ),
            EvaluationArtifact(
                kind=ArtifactKind.PROVENANCE_TRACE,
                applicability=ArtifactApplicability.NOT_APPLICABLE,
                value=None,
                reason=_NO_PROVENANCE_REASON,
            ),
        ),
    )
    observation = MetricObservation(
        query_id=query.query_id,
        predicted_answer=answer if released else "",
        cited_evidence_refs=evidence_ids if released else (),
        terminal_status=status,
        latency_ms=latency_ms,
        peak_memory_mb=peak_memory_mb,
    )
    return S3QueryEvaluation(
        result=result,
        observation=observation,
        candidate=candidate,
        structured_result=structured,
        procedural_result=procedural,
    )


def _failed_evaluation(
    query: QueryRecord,
    configuration: EvaluationRunConfiguration,
    *,
    status: TerminalStatus,
    event: StageEvent | None,
    field: str,
    message: str,
    harness_version: str,
    repository_revision: str,
    latency_ms: float | None,
    peak_memory_mb: float | None,
    structured: StructuredRetrievalResult,
    procedural: ProceduralRetrievalResult,
) -> S3QueryEvaluation:
    errors = errors_from_events((event,)) if event is not None else ()
    if not errors:
        errors = (EvaluationError(code="insufficient_evidence", field=field, message=message),)
    return _record(
        query,
        configuration,
        status=status,
        answer="",
        evidence_ids=(),
        errors=errors,
        harness_version=harness_version,
        repository_revision=repository_revision,
        latency_ms=latency_ms,
        peak_memory_mb=peak_memory_mb,
        candidate=None,
        structured=structured,
        procedural=procedural,
    )


def run_s3_query(
    query: QueryRecord,
    configuration: EvaluationRunConfiguration,
    *,
    scenario: Mapping[str, Any],
    structured_result: StructuredRetrievalResult,
    procedural_result: ProceduralRetrievalResult,
    harness_version: str,
    repository_revision: str,
    latency_ms: float | None = None,
    peak_memory_mb: float | None = None,
) -> S3QueryEvaluation:
    """Retrieve ontology-grounded context for one query and record it without a gate."""
    if not isinstance(query, QueryRecord):
        raise TypeError("query must be a QueryRecord")
    if not isinstance(configuration, EvaluationRunConfiguration):
        raise TypeError("configuration must be an EvaluationRunConfiguration")
    if configuration.strategy is not EvaluationStrategy.S3:
        raise ValueError("configuration must target the S3 strategy")
    if not isinstance(scenario, Mapping):
        raise TypeError("scenario must be a mapping")
    if not isinstance(structured_result, StructuredRetrievalResult):
        raise TypeError("structured_result must be a StructuredRetrievalResult")
    if not isinstance(procedural_result, ProceduralRetrievalResult):
        raise TypeError("procedural_result must be a ProceduralRetrievalResult")

    common: dict[str, Any] = {
        "harness_version": harness_version,
        "repository_revision": repository_revision,
        "latency_ms": latency_ms,
        "peak_memory_mb": peak_memory_mb,
        "structured": structured_result,
        "procedural": procedural_result,
    }
    for retrieval, event_name in (
        (structured_result, "structured_result"),
        (procedural_result, "procedural_result"),
    ):
        if retrieval.status is not TerminalStatus.PASSED:
            return _failed_evaluation(
                query,
                configuration,
                status=retrieval.status,
                event=retrieval.event,
                field=f"{event_name}.status",
                message=f"{event_name} did not pass",
                **common,
            )
    if structured_result.asset.asset_id != query.asset_id:
        return _failed_evaluation(
            query,
            configuration,
            status=TerminalStatus.INSUFFICIENT_EVIDENCE,
            event=None,
            field="asset_id",
            message="retrieved asset does not match the query asset",
            **common,
        )
    if procedural_result.asset.asset_id != structured_result.asset.asset_id:
        # Both adapters are Pump_12-specific today, so this can only fire once an
        # adapter returns another asset; the guard keeps such a pairing fail-closed.
        return _failed_evaluation(  # pragma: no cover
            query,
            configuration,
            status=TerminalStatus.INSUFFICIENT_EVIDENCE,
            event=None,
            field="procedural_result.asset",
            message="retrieval arms disagree on the asset identity",
            **common,
        )

    top_k = _require_positive_int(configuration.parameters.get("top_k"), "top_k")
    max_blocks = _require_positive_int(configuration.parameters.get("max_blocks"), "max_blocks")
    selected = retrieve_ontology_grounded(
        _factual_blocks(structured_result, procedural_result),
        query.text,
        asset_id=query.asset_id,
        top_k=top_k,
        max_blocks=max_blocks,
    )
    evidence_ids = tuple(evidence_id for block in selected for evidence_id in block.evidence_ids)
    if not selected:
        return _failed_evaluation(
            query,
            configuration,
            status=TerminalStatus.INSUFFICIENT_EVIDENCE,
            event=None,
            field="query_text",
            message="no ontology-grounded factual block matched the query",
            **common,
        )

    generation = generate_fixture_candidate_actions(
        scenario=scenario,
        structured_result=structured_result,
        procedural_result=procedural_result,
        generation_run_id=f"run:s3:{query.query_id}",
        query_id=query.query_id,
        variant=FixtureModelVariant.REPAIRED,
    )
    plan = parse_candidate_actions(
        generation.raw_json,
        known_assets={query.asset_id},
        evidence_catalog=generation.evidence_catalog,
    )
    candidate = plan.ranked_actions[0]
    cited = tuple(reference.stable_id for reference in candidate.support_evidence)
    if set(cited) - set(evidence_ids) or candidate.target_asset != query.asset_id:
        return _failed_evaluation(
            query,
            configuration,
            status=TerminalStatus.INSUFFICIENT_EVIDENCE,
            event=None,
            field="support_evidence",
            message="candidate cites support outside the retrieved ontology context",
            **common,
        )

    return _record(
        query,
        configuration,
        status=TerminalStatus.PASSED,
        answer=candidate.action,
        evidence_ids=evidence_ids,
        errors=(),
        candidate=candidate,
        **common,
    )


def check_s3_candidate_post_hoc(
    evaluation: S3QueryEvaluation,
    *,
    action_iri: URIRef,
    resource_iris: Mapping[str, URIRef],
    anomaly_window_start: str,
    anomaly_window_end: str,
    report_uri: URIRef,
) -> ShaclValidationResult:
    """Validate the recorded S3 candidate offline without changing the S3 record."""
    if not isinstance(evaluation, S3QueryEvaluation):
        raise TypeError("evaluation must be an S3QueryEvaluation")
    if evaluation.candidate is None:
        raise ValueError("evaluation has no candidate to check post hoc")
    assembled = assemble_recommended_action_rdf(
        evaluation.candidate,
        action_iri=action_iri,
        resource_iris=resource_iris,
        anomaly_window_start=anomaly_window_start,
        anomaly_window_end=anomaly_window_end,
        structured_result=evaluation.structured_result,
        procedural_result=evaluation.procedural_result,
    )
    return validate_recommended_action(
        assembled.action_graph,
        action_uri=action_iri,
        support_graph=assembled.support_graph,
        report_uri=report_uri,
        run_id=evaluation.result.manifest.run_id,
    )
