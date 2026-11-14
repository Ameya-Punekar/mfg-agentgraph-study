# GraphRAG (Strategy 2)

**Summary**: Microsoft's GraphRAG: an LLM extracts an entity-relationship graph from documents at indexing time, then generates community summaries that serve as retrieval context at query time. The S2 baseline in the four-strategy comparison.

**Sources**: `thesis-pitch-v2.md` §5.2; `microsoft-graphrag-docs.md`; `GraphRAG_Local_to_Global_Microsoft_2024.pdf` (arXiv:2404.16130) — see [[graphrag-microsoft-2024]] for the full source page.

**Last updated**: 2026-11-06.

**Thesis relevance**: RQ1, RQ2.

---

## What it is

At indexing time, an LLM extracts an entity-relationship-claim graph from 600-token chunks (with a self-reflection "gleaning" loop that re-prompts the LLM to recover missed entities). The graph is partitioned hierarchically with **Leiden community detection** (Traag et al. 2019, via the `graspologic` library), and the LLM generates report-style **community summaries** bottom-up — each higher-level summary either packs element descriptions or substitutes sub-community summaries when the token budget overflows. At query time, a **map-reduce** procedure runs: each community summary at a chosen hierarchy level produces a partial answer with a 0-100 helpfulness score; top-ranked partials are reduced into the final global answer. (source: GraphRAG_Local_to_Global_Microsoft_2024.pdf §3.1, §3.1.6)

## Peer-reviewed basis

Edge, D., Trinh, H., Cheng, N., et al. (2024). *From Local to Global: A Graph RAG Approach to Query-Focused Summarization.* Microsoft Research. arXiv:2404.16130. Full ingest: [[graphrag-microsoft-2024]]. Open-source impl: `github.com/microsoft/graphrag` (MIT). (source: arXiv:2404.16130)

## Key design choice for the thesis

The graph in GraphRAG is *constructed by the LLM* from documents — no domain ontology is imposed. Including S2 in the comparison isolates the question: *can a free-form LLM-built graph match an expert ontology for manufacturing reasoning?* This directly informs RQ2's hypothesis H2. (source: thesis-pitch-v2.md §5.2)

## Expected strengths and weaknesses

- **Strength (verified):** rich global summaries for broad ("main themes") questions. On 1M-token corpora, all GraphRAG conditions beat vector RAG on Comprehensiveness (72-83% wins, p<.001) and Diversity (62-82%, p<.001 to p<.01). Root-level summaries (C0) achieve 72% comprehensiveness and 62% diversity wins over vector RAG using **97% fewer tokens than text-summarization map-reduce**. (source: arXiv:2404.16130 §5.1, Table 2)
- **Strength (verified):** the authors themselves note that GraphRAG is *designed for global sensemaking / query-focused summarization* and contrast with conventional "vector RAG" — useful framing for the S1 vs. S2 distinction in the thesis.
- **Weakness (verified):** no constraint validation, no provenance, **exact-string entity matching only** (cross-document entity merging fails on surface-form variation), and **the authors explicitly flag that RAGAS' faithfulness/relevance/context-relevance criteria are not relevant to global sensemaking** — meaning S2's strength does not directly translate to RQ1's chosen RAGAS metrics. This is a **significant evaluation tension** worth flagging in the thesis: S2 is optimized for criteria (comprehensiveness, diversity, empowerment) that the thesis does not measure. (source: arXiv:2404.16130 §2.4, §3.1.3, §3.3)
- **Weakness (verified):** Empowerment results vs. vector RAG were *mixed* — the default extraction prompt does not preserve "specific examples, quotes, and citations" well, which the authors identify as the root cause.

## Risk for the thesis

`microsoft/graphrag` introduces a heavy LLM indexing pipeline. Concrete cost from the paper: **281 minutes** to index a 1M-token corpus on a 16GB-RAM Xeon VM using a public `gpt-4-turbo` endpoint (2M TPM / 10k RPM). Resulting graph: 8,564 nodes, 20,691 edges. With local LLM substitution this will be slower — flag for [[local-deployment]] feasibility analysis. Mitigation per pitch: timebox integration to 3 days in Phase 4; if too complex, substitute with LightRAG (also MIT-licensed, simpler API). (source: arXiv:2404.16130 §4.1.3, §5.1; thesis-pitch-v2.md §14)

## Placement in Pan et al. 2024 taxonomy

In the [[unifying-llms-kgs|Pan 2024 roadmap]], S2 GraphRAG **straddles two paradigms simultaneously**:

- **Paradigm 1 (KG-enhanced LLMs)**, sub-category Inference / KGs Prompting (§4.2.2) — the community summaries are used as prompt context at query time.
- **Paradigm 2 (LLM-augmented KGs)**, sub-category KG Construction / End-to-End Construction (§5.3) — the LLM itself extracts the entity-relationship graph at indexing time.

This dual placement is what makes S2 the *uncontrolled* counterpart to S3: it tests "what happens when the same LLM both builds and uses the graph" with no expert ontology in between. Useful framing for **H2** (S3 > S2 on faithfulness because S3 uses an expert-curated KG instead of an LLM-built one). (source: Pan2024 §3.1.1, §3.1.2, §4.2.2, §5.3)

## Configuration notes from the paper

- **Context window size matters**: the authors tested 8k, 16k, 32k, 64k and found **8k universally best on comprehensiveness** (58.1% win rate over larger windows) due to "lost in the middle" effects. Adopt 8k as default if reproducing. (source: arXiv:2404.16130 §C)
- **Chunk size 600 tokens** detects ~2× the entity references vs. 2400 tokens at the cost of more LLM calls. (source: arXiv:2404.16130 §A.2)
- **Community level choice (C0-C3)**: C0 (root) is dramatically more token-efficient; C2 (intermediate) tended to win on comprehensiveness in the Podcast dataset; C1 won on the News dataset. The thesis should pick a level explicitly and justify it.

## Related variants surfaced by the RAG comprehensive survey

Two recent variants from the [[rag-comprehensive-survey-2024]] are close cousins:

- **CommunityKG-RAG** (Chang et al. 2024) — zero-shot integration of *KG community structures* into RAG via multi-hop connections. Closer in spirit to GraphRAG than RAPTOR, but uses pre-existing KGs rather than LLM-built ones; potentially a more honest comparator if S2 needs an alternative. (source: RAG_Comprehensive_Survey_2024.pdf §4)
- **RAPTOR** (Sarthi et al. 2024) — hierarchical *summary tree* via recursive embedding/clustering/summarisation; +20% on QuALITY with GPT-4. Alternative summary-graph structure; could serve as the LightRAG-style fallback if `microsoft/graphrag` proves too heavy. (source: RAG_Comprehensive_Survey_2024.pdf §4)

These are noted for awareness only — S2 in the thesis is fixed to Microsoft GraphRAG (or LightRAG fallback) per [[thesis-pitch]] §5.2 and §14.

## Resolved open questions (from initial stub)

- *Community detection algorithm* → **Hierarchical Leiden** via `graspologic`, recursive sub-community detection until leaves.
- *"Local" vs. "global" split* → The paper defines "local" as embedding-based query→graph-annotation matching (proposed only as **future work**; current GraphRAG is global-only via map-reduce on community summaries). This validates [[kg-agent-s4]]'s hybrid retrieval as a defensible extension rather than an unmotivated change.
- *Paper's own evaluation* → LLM-as-judge head-to-head on 125 persona-generated questions × 2 datasets × 5 replicates per criterion, with Claimify-based claim count/cluster validation. Criteria: Comprehensiveness, Diversity, Empowerment + control Directness — **explicitly avoiding RAGAS** as not relevant to global sensemaking.
- *Indexing cost* → ~5 hours of `gpt-4-turbo` time per 1M tokens (see Risk section).

## Open questions still relevant

- How will hierarchical Leiden behave on a small MIMII-derived corpus (likely <100k tokens)? Communities may be too few/coarse to give C0 meaningful structure.
- The default "named entity" prompt is generic. Can a manufacturing few-shot exemplar set match S3's expert ontology coverage? — directly relevant to **H2** (S3 > S2 on faithfulness).
- Is C2 or C1 the right level to fix for thesis evaluation (paper finds dataset-dependent winners)?

## Implementation status in this thesis

Issue #36 registers S2 in the shared harness as `mfg_agentgraph.s2_graphrag`. The arm reproduces the paper's *shape* — a graph built from the documents, communities over that graph, one summary per community, and map-reduce answering — with three documented deterministic substitutions: content-term extraction instead of LLM entity extraction, connected components instead of hierarchical Leiden, and extractive summaries instead of LLM reports. The index records its own build cost (duration, canonical bytes, entity/claim/edge/community counts) and an `index_sha256` over canonical index JSON, so a rebuild from documented inputs is verifiable and build cost is reported separately from query latency. It carries no ontology, no SHACL gate, and no PROV-O, which is what separates it from [[og-rag]] and [[kg-agent-s4]]. Because the substitutions change the graph builder and the summary writer, this arm cannot claim the paper's reported comprehensiveness or diversity gains; it establishes index structure, rebuildability, and cost accounting for RQ1 and RQ4.

## Related pages

- [[graphrag-microsoft-2024]]
- [[strategy-comparison]]
- [[og-rag]]
- [[unifying-llms-kgs]]
- [[research-questions]]
