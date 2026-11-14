"""S2 GraphRAG-style baseline: a document-built graph, communities, and map-reduce.

The index is built from the documents alone — no expert ontology, no SHACL, no
PROV-O. Content-term extraction and connected components stand in for GraphRAG's
LLM entity extraction and hierarchical Leiden detection at fixture scale, so the
arm demonstrates graph-and-summary structure and build-cost accounting rather
than the paper's reported global-sensemaking gains.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from time import perf_counter
from typing import Any

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
from mfg_agentgraph.s1_naive_rag import (
    S1Chunk,
    build_s1_index,
    split_sentences,
    tokenize_text,
)
from mfg_agentgraph.stage_instrumentation import TerminalStatus

S2_INDEX_CONTRACT_VERSION = "mfg-agentgraph-s2-index-v1"
_MODEL_CONFIGURATION_ID = "extractive-fixture-v1"
_RETRIEVAL_CONFIGURATION_ID = "community-summary-mapreduce-v1"
_ONTOLOGY_FREE_REASON = "S2 builds its graph from documents; there is no SHACL gate"
_NO_PROVENANCE_REASON = "S2 emits no PROV-O package"
_MIN_TERM_LENGTH = 4
_MAX_TEXT_BYTES = 8_192
_SHA256_HEX_LENGTH = 64
_LOWERCASE_HEX = frozenset("0123456789abcdef")


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


def _require_digest(value: object, field_name: str) -> str:
    digest = _require_text(value, field_name, maximum_bytes=_SHA256_HEX_LENGTH)
    if len(digest) != _SHA256_HEX_LENGTH or any(
        character not in _LOWERCASE_HEX for character in digest
    ):
        raise ValueError(f"{field_name} must be 64 lowercase hexadecimal characters")
    return digest


def _require_sequence(values: object, expected: type[Any], field_name: str) -> tuple[Any, ...]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise TypeError(f"{field_name} must be a sequence of {expected.__name__} instances")
    normalized = tuple(values)
    if not all(isinstance(value, expected) for value in normalized):
        raise TypeError(f"{field_name} must be a sequence of {expected.__name__} instances")
    return normalized


@dataclass(frozen=True, slots=True)
class S2Entity:
    """One content term standing in for an LLM-extracted GraphRAG entity."""

    term: str
    occurrence_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "term", _require_text(self.term, "term", maximum_bytes=256))
        object.__setattr__(
            self,
            "occurrence_count",
            _require_positive_int(self.occurrence_count, "occurrence_count"),
        )


@dataclass(frozen=True, slots=True)
class S2Claim:
    """One sentence-level claim and the content terms it mentions."""

    chunk_evidence_id: str
    sentence_index: int
    text: str
    entity_terms: Sequence[str]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "chunk_evidence_id",
            _require_text(self.chunk_evidence_id, "chunk_evidence_id", maximum_bytes=8_192),
        )
        if not isinstance(self.sentence_index, int) or isinstance(self.sentence_index, bool):
            raise TypeError("sentence_index must be an integer")
        if self.sentence_index < 0:
            raise ValueError("sentence_index must be non-negative")
        object.__setattr__(
            self, "text", _require_text(self.text, "text", maximum_bytes=_MAX_TEXT_BYTES)
        )
        terms = _require_sequence(self.entity_terms, str, "entity_terms")
        object.__setattr__(self, "entity_terms", tuple(terms))


@dataclass(frozen=True, slots=True)
class S2Community:
    """One detected community, its extractive summary, and its source chunks."""

    community_id: str
    entity_terms: Sequence[str]
    summary_sentences: Sequence[str]
    evidence_ids: Sequence[str]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "community_id",
            _require_text(self.community_id, "community_id", maximum_bytes=256),
        )
        terms = _require_sequence(self.entity_terms, str, "entity_terms")
        if not terms:
            raise ValueError("entity_terms must not be empty")
        object.__setattr__(self, "entity_terms", tuple(terms))
        sentences = _require_sequence(self.summary_sentences, str, "summary_sentences")
        if not sentences:
            raise ValueError("summary_sentences must not be empty")
        object.__setattr__(self, "summary_sentences", tuple(sentences))
        evidence_ids = _require_sequence(self.evidence_ids, str, "evidence_ids")
        if not evidence_ids:
            raise ValueError("evidence_ids must not be empty")
        object.__setattr__(self, "evidence_ids", tuple(evidence_ids))


@dataclass(frozen=True, slots=True)
class S2IndexBuildCost:
    """Measured index-build cost, kept out of query latency."""

    build_duration_ms: float
    index_bytes: int
    entity_count: int
    claim_count: int
    edge_count: int
    community_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.build_duration_ms, (int, float)) or isinstance(
            self.build_duration_ms, bool
        ):
            raise TypeError("build_duration_ms must be a finite number")
        duration = float(self.build_duration_ms)
        if not math.isfinite(duration):
            raise ValueError("build_duration_ms must be finite")
        if duration < 0.0:
            raise ValueError("build_duration_ms must be non-negative")
        object.__setattr__(self, "build_duration_ms", duration)
        for field_name in (
            "index_bytes",
            "entity_count",
            "claim_count",
            "edge_count",
            "community_count",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"{field_name} must be an integer")
            if value < 0:
                raise ValueError(f"{field_name} must be non-negative")


@dataclass(frozen=True, slots=True)
class S2Index:
    """Immutable, rebuildable GraphRAG-style index with a canonical digest."""

    contract_version: str
    chunks: Sequence[S1Chunk]
    entities: Sequence[S2Entity]
    claims: Sequence[S2Claim]
    edges: Sequence[tuple[str, str, int]]
    communities: Sequence[S2Community]
    index_sha256: str
    index_bytes: int
    cost: S2IndexBuildCost

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "contract_version",
            _require_text(self.contract_version, "contract_version", maximum_bytes=256),
        )
        object.__setattr__(self, "chunks", _require_sequence(self.chunks, S1Chunk, "chunks"))
        object.__setattr__(self, "entities", _require_sequence(self.entities, S2Entity, "entities"))
        object.__setattr__(self, "claims", _require_sequence(self.claims, S2Claim, "claims"))
        edges = _require_sequence(self.edges, tuple, "edges")
        for edge in edges:
            if len(edge) != 3 or not isinstance(edge[2], int):
                raise TypeError("edges must contain (left, right, weight) integer triples")
        object.__setattr__(self, "edges", edges)
        object.__setattr__(
            self, "communities", _require_sequence(self.communities, S2Community, "communities")
        )
        object.__setattr__(self, "index_sha256", _require_digest(self.index_sha256, "index_sha256"))
        if not isinstance(self.index_bytes, int) or isinstance(self.index_bytes, bool):
            raise TypeError("index_bytes must be an integer")
        if self.index_bytes < 0:
            raise ValueError("index_bytes must be non-negative")
        if not isinstance(self.cost, S2IndexBuildCost):
            raise TypeError("cost must be an S2IndexBuildCost")
        if self.cost.index_bytes != self.index_bytes:
            raise ValueError("index_bytes must equal cost.index_bytes")


def _resolve_build_duration(build_duration_ms: object) -> float | None:
    if build_duration_ms is None:
        return None
    if not isinstance(build_duration_ms, (int, float)) or isinstance(build_duration_ms, bool):
        raise TypeError("build_duration_ms must be a finite number or None")
    duration = float(build_duration_ms)
    if not math.isfinite(duration):
        raise ValueError("build_duration_ms must be finite")
    if duration < 0.0:
        raise ValueError("build_duration_ms must be non-negative")
    return duration


def _content_terms(sentence: str) -> tuple[str, ...]:
    return tuple(
        sorted({token for token in tokenize_text(sentence) if len(token) >= _MIN_TERM_LENGTH})
    )


def _claim_texts(claims: Sequence[S2Claim], members: frozenset[str]) -> list[S2Claim]:
    selected = [claim for claim in claims if members.intersection(claim.entity_terms)]
    selected.sort(
        key=lambda claim: (
            -len(members.intersection(claim.entity_terms)),
            claim.chunk_evidence_id,
            claim.sentence_index,
        )
    )
    return selected


def _canonical_digest(
    contract_version: str,
    entities: Sequence[S2Entity],
    claims: Sequence[S2Claim],
    edges: Sequence[tuple[str, str, int]],
    communities: Sequence[S2Community],
) -> tuple[str, int]:
    payload: dict[str, object] = {
        "claims": [
            [claim.chunk_evidence_id, claim.sentence_index, claim.text, list(claim.entity_terms)]
            for claim in claims
        ],
        "communities": [
            [
                community.community_id,
                list(community.entity_terms),
                list(community.summary_sentences),
                list(community.evidence_ids),
            ]
            for community in communities
        ],
        "contract_version": contract_version,
        "edges": [[left, right, weight] for left, right, weight in edges],
        "entities": [[entity.term, entity.occurrence_count] for entity in entities],
    }
    canonical = json.dumps(
        payload, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    encoded = canonical.encode("utf-8")
    return hashlib.sha256(encoded).hexdigest(), len(encoded)


def build_s2_index(
    chunks: Sequence[S1Chunk],
    *,
    build_duration_ms: float | None = None,
    max_summary_sentences: int = 3,
    contract_version: str = S2_INDEX_CONTRACT_VERSION,
) -> S2Index:
    """Build the document-derived graph, communities, and summaries from one corpus."""
    validated = build_s1_index(chunks).chunks
    if not validated:
        raise ValueError("chunks must not be empty")
    declared_duration = _resolve_build_duration(build_duration_ms)
    version = _require_text(contract_version, "contract_version", maximum_bytes=256)
    summary_limit = _require_positive_int(max_summary_sentences, "max_summary_sentences")

    started = perf_counter()
    occurrences: dict[str, int] = {}
    claims: list[S2Claim] = []
    for chunk in validated:
        for sentence_index, sentence in enumerate(split_sentences(chunk.text)):
            terms = _content_terms(sentence)
            claims.append(
                S2Claim(
                    chunk_evidence_id=chunk.evidence_id,
                    sentence_index=sentence_index,
                    text=sentence,
                    entity_terms=terms,
                )
            )
            for term in terms:
                occurrences[term] = occurrences.get(term, 0) + 1

    entities = tuple(
        S2Entity(term=term, occurrence_count=count) for term, count in sorted(occurrences.items())
    )
    edge_weights: dict[tuple[str, str], int] = {}
    for claim in claims:
        claim_terms = claim.entity_terms
        for left_index, left in enumerate(claim_terms):
            for right in claim_terms[left_index + 1 :]:
                pair = (left, right) if left < right else (right, left)
                edge_weights[pair] = edge_weights.get(pair, 0) + 1
    edges = tuple((left, right, weight) for (left, right), weight in sorted(edge_weights.items()))

    communities = _detect_communities(entities, claims, max_summary_sentences=summary_limit)
    duration = (
        declared_duration
        if declared_duration is not None
        else ((perf_counter() - started) * 1_000.0)
    )
    digest, index_bytes = _canonical_digest(version, entities, claims, edges, communities)
    cost = S2IndexBuildCost(
        build_duration_ms=duration,
        index_bytes=index_bytes,
        entity_count=len(entities),
        claim_count=len(claims),
        edge_count=len(edges),
        community_count=len(communities),
    )
    return S2Index(
        contract_version=version,
        chunks=validated,
        entities=entities,
        claims=tuple(claims),
        edges=edges,
        communities=communities,
        index_sha256=digest,
        index_bytes=index_bytes,
        cost=cost,
    )


def _detect_communities(
    entities: Sequence[S2Entity],
    claims: Sequence[S2Claim],
    *,
    max_summary_sentences: int,
) -> tuple[S2Community, ...]:
    adjacency: dict[str, set[str]] = {entity.term: set() for entity in entities}
    for claim in claims:
        for term in claim.entity_terms:
            adjacency[term].update(claim.entity_terms)
    for term, neighbours in adjacency.items():
        neighbours.discard(term)

    remaining = set(adjacency)
    components: list[tuple[str, ...]] = []
    while remaining:
        seed = min(remaining)
        stack = [seed]
        component: set[str] = set()
        while stack:
            current = stack.pop()
            if current in component:
                continue
            component.add(current)
            stack.extend(sorted(adjacency[current] - component))
        remaining -= component
        components.append(tuple(sorted(component)))

    components.sort(key=lambda members: (-len(members), members[0]))
    communities: list[S2Community] = []
    for ordinal, members in enumerate(components):
        member_set = frozenset(members)
        candidates = _claim_texts(claims, member_set)[:max_summary_sentences]
        evidence_ids: list[str] = []
        for claim in candidates:
            if claim.chunk_evidence_id not in evidence_ids:
                evidence_ids.append(claim.chunk_evidence_id)
        communities.append(
            S2Community(
                community_id=f"community-{ordinal:03d}",
                entity_terms=members,
                summary_sentences=tuple(claim.text for claim in candidates),
                evidence_ids=tuple(evidence_ids),
            )
        )
    return tuple(communities)


def build_s2_run_configuration(
    query_set: QuerySet,
    index: S2Index,
    *,
    top_k_communities: int = 2,
    max_sentences: int = 2,
    random_seed: int = 0,
) -> EvaluationRunConfiguration:
    """Build the controlled S2 configuration bound to one index and query set."""
    if not isinstance(query_set, QuerySet):
        raise TypeError("query_set must be a QuerySet")
    if not isinstance(index, S2Index):
        raise TypeError("index must be an S2Index")
    return EvaluationRunConfiguration(
        strategy=EvaluationStrategy.S2,
        dataset_id=query_set.dataset_id,
        query_set_id=query_set.query_set_id,
        model_configuration_id=_MODEL_CONFIGURATION_ID,
        retrieval_configuration_id=_RETRIEVAL_CONFIGURATION_ID,
        random_seed=random_seed,
        parameters={
            "dataset_sha256": query_set.document_sha256,
            "dataset_version": query_set.version,
            "index_contract_version": index.contract_version,
            "index_sha256": index.index_sha256,
            "max_sentences": _require_positive_int(max_sentences, "max_sentences"),
            "top_k_communities": _require_positive_int(top_k_communities, "top_k_communities"),
        },
    )


@dataclass(frozen=True, slots=True)
class S2QueryEvaluation:
    """One S2 query: the comparable record and its metric observation."""

    result: EvaluationResult
    observation: MetricObservation

    def __post_init__(self) -> None:
        if not isinstance(self.result, EvaluationResult):
            raise TypeError("result must be an EvaluationResult")
        if not isinstance(self.observation, MetricObservation):
            raise TypeError("observation must be a MetricObservation")


def _parameter_int(configuration: EvaluationRunConfiguration, name: str) -> int:
    value = configuration.parameters.get(name)
    if value is None:
        raise ValueError(f"configuration parameters must include {name}")
    return _require_positive_int(value, name)


def _parameter_digest(configuration: EvaluationRunConfiguration, name: str) -> str:
    value = configuration.parameters.get(name)
    if value is None:
        raise ValueError(f"configuration parameters must include {name}")
    return _require_digest(value, name)


def _artifacts(
    *,
    released: bool,
    answer: str,
    status: TerminalStatus,
    evidence_ids: Sequence[str],
) -> tuple[EvaluationArtifact, ...]:
    return (
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
            reason=_ONTOLOGY_FREE_REASON,
        ),
        EvaluationArtifact(
            kind=ArtifactKind.PROVENANCE_TRACE,
            applicability=ArtifactApplicability.NOT_APPLICABLE,
            value=None,
            reason=_NO_PROVENANCE_REASON,
        ),
    )


def _index_cost_payload(index: S2Index) -> dict[str, object]:
    return {
        "index_build_duration_ms": index.cost.build_duration_ms,
        "index_bytes": index.index_bytes,
        "index_claim_count": index.cost.claim_count,
        "index_community_count": index.cost.community_count,
        "index_edge_count": index.cost.edge_count,
        "index_entity_count": index.cost.entity_count,
        "index_sha256": index.index_sha256,
    }


def _ranked_communities(
    index: S2Index, query_tokens: frozenset[str], top_k: int
) -> tuple[tuple[int, S2Community], ...]:
    scored: list[tuple[int, S2Community]] = []
    for community in index.communities:
        vocabulary = set(community.entity_terms)
        vocabulary.update(tokenize_text(" ".join(community.summary_sentences)))
        score = len(query_tokens & vocabulary)
        if score:
            scored.append((score, community))
    scored.sort(key=lambda item: (-item[0], item[1].community_id))
    return tuple(scored[:top_k])


def _map_reduce(
    index: S2Index,
    query_tokens: frozenset[str],
    selected: Sequence[tuple[int, S2Community]],
    max_sentences: int,
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    mapped: list[tuple[int, str, int, str]] = []
    for _, community in selected:
        member_set = frozenset(community.entity_terms)
        best: tuple[int, str, int, str] | None = None
        for claim in index.claims:
            if not member_set.intersection(claim.entity_terms):
                continue
            overlap = len(query_tokens & set(claim.entity_terms))
            if not overlap:
                continue
            candidate = (overlap, claim.chunk_evidence_id, claim.sentence_index, claim.text)
            if best is None or (-candidate[0], candidate[1], candidate[2]) < (
                -best[0],
                best[1],
                best[2],
            ):
                best = candidate
        if best is not None:
            mapped.append(best)
    mapped.sort(key=lambda item: (-item[0], item[1], item[2]))
    reduced = mapped[:max_sentences]
    answer = " ".join(item[3] for item in reduced)
    evidence_ids: list[str] = []
    for item in reduced:
        if item[1] not in evidence_ids:
            evidence_ids.append(item[1])
    return answer, tuple(evidence_ids), tuple(community.community_id for _, community in selected)


def run_s2_query(
    query: QueryRecord,
    configuration: EvaluationRunConfiguration,
    *,
    index: S2Index,
    harness_version: str,
    repository_revision: str,
    latency_ms: float | None = None,
    peak_memory_mb: float | None = None,
) -> S2QueryEvaluation:
    """Answer one query by map-reducing over the indexed community summaries."""
    if not isinstance(query, QueryRecord):
        raise TypeError("query must be a QueryRecord")
    if not isinstance(configuration, EvaluationRunConfiguration):
        raise TypeError("configuration must be an EvaluationRunConfiguration")
    if configuration.strategy is not EvaluationStrategy.S2:
        raise ValueError("configuration must target the S2 strategy")
    if not isinstance(index, S2Index):
        raise TypeError("index must be an S2Index")

    bound_index = _parameter_digest(configuration, "index_sha256")
    if bound_index != index.index_sha256:
        raise ValueError("configuration index_sha256 must match the supplied index")
    top_k = _parameter_int(configuration, "top_k_communities")
    max_sentences = _parameter_int(configuration, "max_sentences")

    query_tokens = frozenset(tokenize_text(query.text))
    selected = _ranked_communities(index, query_tokens, top_k) if query_tokens else ()
    answer, evidence_ids, community_ids = _map_reduce(index, query_tokens, selected, max_sentences)
    if not answer:
        status = TerminalStatus.INSUFFICIENT_EVIDENCE
        errors: tuple[EvaluationError, ...] = (
            EvaluationError(
                code="insufficient_evidence",
                field="query_text",
                message="no indexed community matched the query above the threshold",
            ),
        )
        released = False
    else:
        status = TerminalStatus.PASSED
        errors = ()
        released = True

    raw_output: dict[str, object] = {
        "answer": answer,
        "constraint_validated": False,
        "evidence_ids": list(evidence_ids),
        "provenance_id": None,
        "query_latency_ms": latency_ms,
        "selected_community_ids": list(community_ids),
        "terminal_status": status.value,
    }
    raw_output.update(_index_cost_payload(index))
    result = EvaluationResult(
        configuration=configuration,
        manifest=EvaluationRunManifest(
            run_id=f"run:s2:{query.query_id}",
            repository_revision=repository_revision,
            harness_version=harness_version,
            dataset_sha256=dataset_sha256_from_configuration(configuration),
        ),
        query_id=query.query_id,
        raw_output=raw_output,
        errors=errors,
        artifacts=_artifacts(
            released=released,
            answer=answer,
            status=status,
            evidence_ids=evidence_ids,
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
    return S2QueryEvaluation(result=result, observation=observation)


def summarize_index_build(index: S2Index) -> Mapping[str, object]:
    """Return the recorded build cost so experiments keep it beside query latency."""
    if not isinstance(index, S2Index):
        raise TypeError("index must be an S2Index")
    return _index_cost_payload(index)
