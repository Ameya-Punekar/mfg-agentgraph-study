# Naive RAG (Strategy 1)

**Summary**: Vector-similarity retrieval over document chunks, fed directly to an LLM with no graph, no agent loop, and no constraint validation. The S1 baseline in the four-strategy comparison.

**Sources**: `thesis-pitch-v2.md` §5.1; `RAG_Comprehensive_Survey_2024.pdf` (see [[rag-comprehensive-survey-2024]]). Lewis et al. 2020 (NeurIPS) original RAG paper itself is not in `raw/`, so attribution is via the Gupta et al. 2024 survey.

**Last updated**: 2026-04-27.

**Thesis relevance**: RQ1 (baseline), RQ4.

---

## What it is

Standard retrieval-augmented generation: a **retriever** fetches relevant documents from an external corpus, and a **generator** synthesises an answer from query + retrieved context. (source: RAG_Comprehensive_Survey_2024.pdf §1.2, §2.1, citing Lewis et al. 2020)

In MFG-AgentGraph S1:

1. Documents are chunked and embedded (sentence-transformers).
2. At query time, top-k chunks by cosine similarity over Qdrant are retrieved.
3. Chunks are concatenated into the LLM prompt.
4. The LLM generates an answer directly.

No knowledge graph, no agent loop, no SHACL validation, no provenance. (source: thesis-pitch-v2.md §5.1)

## Peer-reviewed basis

Lewis et al., 2020, NeurIPS — original RAG paper. Survey-mediated attribution via [[rag-comprehensive-survey-2024]]; Lewis 2020 itself is not in `raw/`. The survey identifies BM25 (Robertson 2009), DPR (Karpukhin et al. 2020) and REALM (Guu et al. 2020) as the canonical retrievers, and T5/BART as the canonical generators. (source: RAG_Comprehensive_Survey_2024.pdf §2.2, §2.3)

Evaluated by the [[ragas-metrics|RAGAS]] framework.

## Why include it

Represents the status quo in many industrial AI assistants — establishes the floor for the S1–S4 comparison and isolates how much benefit comes from *any* graph structure. (source: thesis-pitch-v2.md §5.1)

## Placement in Pan et al. 2024 taxonomy

In the [[unifying-llms-kgs|Pan 2024 roadmap]] taxonomy, S1 sits in **paradigm 1: KG-enhanced LLMs**, sub-category **Inference / Retrieval-Augmented Knowledge Fusion** (§4.2.1) — the same bucket as the original Lewis et al. 2020 RAG paper. Strictly speaking S1 is a *degenerate* member: it retrieves *text*, not KG facts, so the "KG-enhanced" label only applies if the corpus itself is treated as the knowledge source. This is the framing the thesis uses to justify including S1 as a non-KG floor. (source: Pan2024 §4.2.1)

## Expected limitations (in the manufacturing setting)

- Ungrounded hallucinations (no structured constraint).
- No relational context (asset hierarchy, maintenance history).
- No validation against domain rules.
- No provenance trail.

(source: thesis-pitch-v2.md §5.1)

## Implementation choice for the thesis baseline

The S1 baseline in MFG-AgentGraph uses dense retrieval (sentence-transformers + Qdrant) to match the [[og-rag|S3]] vector backbone, so S1↔S3 differences cannot be attributed to retriever choice. BM25 was considered as an alternative baseline but rejected to keep the comparison axis clean.

## Implementation note: this survey ≠ Gao et al. 2023

The popular "Naive RAG / Advanced RAG / Modular RAG" three-stage taxonomy comes from a different survey (Gao et al. 2023, not in `raw/` yet). The Gupta et al. 2024 [[rag-comprehensive-survey-2024|survey we have]] is flatter — it surveys 17 recent variants but does not adopt the three-stage framing. If thesis writing needs that taxonomy, that source must be added.

## Open questions for ingest

- Which RAGAS metrics best penalise S1's specific failure modes (irrelevant retrieval vs. ungrounded generation)?
- Whether to add Gao et al. 2023 to `raw/` for the three-stage taxonomy.

## Related pages

- [[strategy-comparison]]
- [[graphrag]]
- [[unifying-llms-kgs]]
- [[ragas-metrics]]
- [[faithfulness]]
- [[groundedness]]
