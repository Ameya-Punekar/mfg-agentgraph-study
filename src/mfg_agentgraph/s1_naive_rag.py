"""S1 naive-RAG baseline: lexical procedure retrieval plus an extractive answer."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass

from mfg_agentgraph.anomaly_triage_dataset import QueryRecord, QuerySet
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
)
from mfg_agentgraph.evaluation_metrics import MetricObservation
from mfg_agentgraph.stage_instrumentation import TerminalStatus

_MAX_TEXT_BYTES = 8_192
_TOKEN_PATTERN = re.compile(r"[^0-9a-z]+")
_SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s+")
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "at",
        "be",
        "before",
        "by",
        "do",
        "does",
        "for",
        "from",
        "how",
        "if",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "should",
        "than",
        "that",
        "the",
        "then",
        "there",
        "these",
        "this",
        "to",
        "was",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
    }
)
_MODEL_CONFIGURATION_ID = "extractive-fixture-v1"


def _require_text(value: object, field_name: str, *, maximum_bytes: int = _MAX_TEXT_BYTES) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be nonblank")
    if len(normalized.encode("utf-8")) > maximum_bytes:
        raise ValueError(f"{field_name} exceeds {maximum_bytes} UTF-8 bytes")
    return normalized


@dataclass(frozen=True, slots=True)
class S1Chunk:
    """One indexed procedure paragraph with its canonical evidence identity."""

    evidence_id: str
    document: str
    text: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", _require_text(self.evidence_id, "evidence_id"))
        object.__setattr__(self, "document", _require_text(self.document, "document"))
        object.__setattr__(self, "text", _require_text(self.text, "text"))


@dataclass(frozen=True, slots=True)
class S1Index:
    """Immutable corpus for the naive baseline."""

    chunks: Sequence[S1Chunk]

    def __post_init__(self) -> None:
        if isinstance(self.chunks, (str, bytes, bytearray)) or not isinstance(
            self.chunks, Sequence
        ):
            raise TypeError("chunks must be a sequence of S1Chunk instances")
        normalized = tuple(self.chunks)
        if not all(isinstance(chunk, S1Chunk) for chunk in normalized):
            raise TypeError("chunks must be a sequence of S1Chunk instances")
        seen: set[str] = set()
        for chunk in normalized:
            if chunk.evidence_id in seen:
                raise ValueError(f"duplicate evidence_id {chunk.evidence_id!r}")
            seen.add(chunk.evidence_id)
        object.__setattr__(self, "chunks", normalized)


@dataclass(frozen=True, slots=True)
class S1RetrievedChunk:
    """One ranked retrieval hit with its deterministic overlap score."""

    chunk: S1Chunk
    score: float


def tokenize_text(text: str) -> tuple[str, ...]:
    """Split text into lowercase alphanumeric tokens without English function words."""
    return tuple(
        token for token in _TOKEN_PATTERN.split(text.lower()) if token and token not in _STOPWORDS
    )


def build_s1_index(chunks: Sequence[S1Chunk]) -> S1Index:
    """Validate and freeze a naive-RAG corpus."""
    return S1Index(chunks)


def build_s1_index_from_document(
    text: str,
    *,
    document: str,
    first_chunk_index: int,
    evidence_id_prefix: str = "ex:SOP_Chunk_",
) -> S1Index:
    """Split one procedure document into paragraph chunks with stable IDs."""
    if not isinstance(first_chunk_index, int) or isinstance(first_chunk_index, bool):
        raise TypeError("first_chunk_index must be an integer")
    if first_chunk_index < 1:
        raise ValueError("first_chunk_index must be positive")
    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n", _require_text(text, "text"))
        if paragraph.strip()
    ]
    chunks = tuple(
        S1Chunk(
            evidence_id=f"{evidence_id_prefix}{first_chunk_index + offset}",
            document=document,
            text=paragraph,
        )
        for offset, paragraph in enumerate(paragraphs)
    )
    return S1Index(chunks)


def _require_score(value: object, field_name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be a finite number")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    return normalized


def retrieve_naive(
    index: S1Index,
    query_text: str,
    *,
    top_k: int = 3,
    minimum_score: float = 0.0,
) -> tuple[S1RetrievedChunk, ...]:
    """Rank chunks by query-token coverage, breaking ties by evidence ID."""
    if not isinstance(index, S1Index):
        raise TypeError("index must be an S1Index")
    if not isinstance(top_k, int) or isinstance(top_k, bool):
        raise TypeError("top_k must be an integer")
    if top_k < 1:
        raise ValueError("top_k must be positive")
    threshold = _require_score(minimum_score, "minimum_score")
    if threshold < 0.0 or threshold > 1.0:
        raise ValueError("minimum_score must be between 0 and 1")
    query_tokens = set(tokenize_text(_require_text(query_text, "query_text")))
    if not query_tokens:
        return ()
    ranked: list[S1RetrievedChunk] = []
    for chunk in index.chunks:
        overlap = len(query_tokens & set(tokenize_text(chunk.text)))
        if not overlap:
            continue
        score = overlap / len(query_tokens)
        if score < threshold:
            continue
        ranked.append(S1RetrievedChunk(chunk=chunk, score=score))
    ranked.sort(key=lambda ranked_chunk: (-ranked_chunk.score, ranked_chunk.chunk.evidence_id))
    return tuple(ranked[:top_k])


def _extractive_answer(chunk: S1Chunk) -> str:
    return split_sentences(chunk.text)[0].rstrip(".!?").strip()


def split_sentences(text: str) -> tuple[str, ...]:
    """Split text into trimmed sentences on terminal punctuation."""
    return tuple(
        sentence.strip()
        for sentence in _SENTENCE_PATTERN.split(_require_text(text, "text"))
        if sentence.strip()
    )


def build_s1_run_configuration(
    query_set: QuerySet,
    *,
    top_k: int = 3,
    minimum_score: float = 0.0,
    random_seed: int = 0,
) -> EvaluationRunConfiguration:
    """Build the controlled S1 configuration for one query set."""
    if not isinstance(query_set, QuerySet):
        raise TypeError("query_set must be a QuerySet")
    if not isinstance(top_k, int) or isinstance(top_k, bool):
        raise TypeError("top_k must be an integer")
    if top_k < 1:
        raise ValueError("top_k must be positive")
    threshold = _require_score(minimum_score, "minimum_score")
    return EvaluationRunConfiguration(
        strategy=EvaluationStrategy.S1,
        dataset_id=query_set.dataset_id,
        query_set_id=query_set.query_set_id,
        model_configuration_id=_MODEL_CONFIGURATION_ID,
        retrieval_configuration_id=f"lexical-overlap-top{top_k}",
        random_seed=random_seed,
        parameters={
            "dataset_sha256": query_set.document_sha256,
            "dataset_version": query_set.version,
            "minimum_score": threshold,
            "top_k": top_k,
        },
    )


@dataclass(frozen=True, slots=True)
class S1QueryEvaluation:
    """One S1 query: the comparable record and its metric observation."""

    result: EvaluationResult
    observation: MetricObservation

    def __post_init__(self) -> None:
        if not isinstance(self.result, EvaluationResult):
            raise TypeError("result must be an EvaluationResult")
        if not isinstance(self.observation, MetricObservation):
            raise TypeError("observation must be a MetricObservation")


def _parameter(configuration: EvaluationRunConfiguration, name: str) -> object:
    value = configuration.parameters.get(name)
    if value is None:
        raise ValueError(f"configuration parameters must include {name}")
    return value


def run_s1_query(
    query: QueryRecord,
    configuration: EvaluationRunConfiguration,
    *,
    index: S1Index,
    harness_version: str,
    repository_revision: str,
    latency_ms: float | None = None,
    peak_memory_mb: float | None = None,
) -> S1QueryEvaluation:
    """Retrieve procedure chunks for one query and answer extractively."""
    if not isinstance(query, QueryRecord):
        raise TypeError("query must be a QueryRecord")
    if not isinstance(configuration, EvaluationRunConfiguration):
        raise TypeError("configuration must be an EvaluationRunConfiguration")
    if configuration.strategy is not EvaluationStrategy.S1:
        raise ValueError("configuration must target the S1 strategy")
    if not isinstance(index, S1Index):
        raise TypeError("index must be an S1Index")

    top_k = _parameter(configuration, "top_k")
    minimum_score = _parameter(configuration, "minimum_score")
    if not isinstance(top_k, int) or isinstance(top_k, bool):
        raise TypeError("top_k parameter must be an integer")
    if not isinstance(minimum_score, (int, float)) or isinstance(minimum_score, bool):
        raise TypeError("minimum_score parameter must be a finite number")
    dataset_sha256 = dataset_sha256_from_configuration(configuration)

    ranked = retrieve_naive(index, query.text, top_k=top_k, minimum_score=float(minimum_score))
    evidence_ids = tuple(hit.chunk.evidence_id for hit in ranked)
    if ranked:
        terminal_status = TerminalStatus.PASSED
        answer = _extractive_answer(ranked[0].chunk)
        errors: tuple[EvaluationError, ...] = ()
    else:
        terminal_status = TerminalStatus.INSUFFICIENT_EVIDENCE
        answer = ""
        errors = (
            EvaluationError(
                code="insufficient_evidence",
                field="query_text",
                message="no procedure chunk matched the query above the configured threshold",
            ),
        )

    result = EvaluationResult(
        configuration=configuration,
        manifest=EvaluationRunManifest(
            run_id=f"run:s1:{query.query_id}",
            repository_revision=repository_revision,
            harness_version=harness_version,
            dataset_sha256=dataset_sha256,
        ),
        query_id=query.query_id,
        raw_output={
            "answer": answer,
            "retrieved": [
                {"evidence_id": hit.chunk.evidence_id, "score": hit.score} for hit in ranked
            ],
            "terminal_status": terminal_status.value,
        },
        errors=errors,
        artifacts=(
            EvaluationArtifact(
                kind=ArtifactKind.ANSWER,
                applicability=ArtifactApplicability.PRESENT,
                value={
                    "released": bool(ranked),
                    "text": answer if ranked else terminal_status.value,
                },
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
                reason="S1 has no SHACL validation stage",
            ),
            EvaluationArtifact(
                kind=ArtifactKind.PROVENANCE_TRACE,
                applicability=ArtifactApplicability.NOT_APPLICABLE,
                value=None,
                reason="S1 emits no provenance trace",
            ),
        ),
    )
    observation = MetricObservation(
        query_id=query.query_id,
        predicted_answer=answer,
        cited_evidence_refs=evidence_ids,
        terminal_status=terminal_status,
        latency_ms=latency_ms,
        peak_memory_mb=peak_memory_mb,
    )
    return S1QueryEvaluation(result=result, observation=observation)
