# GraphRAG: Local to Global (Microsoft, 2024)

**Summary**: Edge et al.'s GraphRAG paper — a two-stage pipeline that uses an LLM to build an entity-relationship knowledge graph from a corpus, partitions it with Leiden community detection, generates hierarchical community summaries at indexing time, and answers global sensemaking queries via map-reduce over those summaries at query time. The peer-reviewed basis for [[graphrag]] (S2 baseline).

**Sources**: `GraphRAG_Local_to_Global_Microsoft_2024.pdf` (arXiv:2404.16130, Edge, Trinh, Cheng, Bradley, Chao, Mody, Truitt, Metropolitansky, Ness, Larson — Microsoft Research; Feb 2025 v2).

**Last updated**: 2026-04-27.

**Thesis relevance**: RQ1 (S2 method definition), RQ2 (LLM-built graph vs. expert ontology comparison), RQ4 (token cost and indexing latency).

---

## Problem framing

Vector RAG fails on **global sensemaking** queries — questions that require understanding the *entire* corpus, e.g., *"What are the main themes?"* or *"How are scientific discoveries influenced by interdisciplinary research?"*. These are query-focused summarization (QFS) tasks, not retrieval tasks. Prior QFS methods don't scale to RAG-sized corpora. GraphRAG combines the two by indexing a graph of communities and summarizing them. (source: arXiv:2404.16130 §1)

## Indexing pipeline (Figure 1)

Six steps, all performed at indexing time:

1. **Source documents → text chunks.** Default chunk size 600 tokens with 100-token overlap. Smaller chunks recover more entities (600 ≈ 2× the entities of 2400) at higher LLM cost. (source: arXiv:2404.16130 §3.1.1, §A.2)
2. **Text chunks → entities & relationships.** A multipart LLM prompt extracts named entities (name, type, description) and the relationships between them (source, target, description, strength), plus optional **claims** (factual statements about entities). Default entity types are generic "named entities" — domain-specific few-shot exemplars improve specialized domains. (source: arXiv:2404.16130 §3.1.2, §E.1)
3. **Self-reflection "gleaning" loop.** After extraction, the LLM is asked whether entities were missed (logit-bias-forced yes/no); if yes, a continuation prompt encourages another pass. This lets larger chunk sizes work without recall loss. (source: arXiv:2404.16130 §A.2)
4. **Entities & relationships → KG.** Multiple instances of the same entity are merged by **exact string matching**; relationships aggregate with edge weights = duplicate count. The paper acknowledges softer entity matching is possible but unused here. (source: arXiv:2404.16130 §3.1.3)
5. **KG → graph communities.** Hierarchical **Leiden community detection** via the `graspologic` library — recursively detects sub-communities until leaves can't be partitioned further. Each level is a mutually exclusive, collectively exhaustive partition. (source: arXiv:2404.16130 §3.1.4, §4.1.3)
6. **Communities → community summaries.** Bottom-up: leaf-level summaries pack element descriptions (nodes, edges, claims) prioritized by combined source+target degree until the token limit; higher-level summaries substitute sub-community summaries for element summaries when the combined element list overflows. (source: arXiv:2404.16130 §3.1.5, §E.2)

## Query pipeline (map-reduce)

For a user query at a chosen community level:

1. **Prepare**: shuffle community summaries; chunk to a pre-specified token size.
2. **Map**: each chunk independently produces a partial answer plus a 0-100 helpfulness score; score-0 answers are filtered out.
3. **Reduce**: sort partials by descending helpfulness, pack into a new context until the token limit, generate final global answer. (source: arXiv:2404.16130 §3.1.6, §E.3, §E.4)

## Evaluation method (no ground truth)

Because global sensemaking has no gold answers, the authors design an LLM-as-judge head-to-head:

- **Adaptive benchmarking**: an LLM is given a corpus description, generates K=5 user personas × N=5 tasks per persona × M=5 questions per (user, task) → 125 questions per dataset, all requiring corpus-wide understanding. (source: arXiv:2404.16130 §3.2)
- **Three target criteria**: *Comprehensiveness* (detail/coverage), *Diversity* (variety of perspectives), *Empowerment* (helps reader make informed judgements). Plus a **control criterion** *Directness* (concision) that is "effectively in opposition" to comprehensiveness/diversity — used as a sanity check. (source: arXiv:2404.16130 §3.3, §F.2)
- **The authors explicitly call RAGAS' faithfulness, context relevance, and answer relevance "not relevant to global sensemaking"** — important signal for [[ragas-metrics]]. (source: arXiv:2404.16130 §2.4)
- Each pairwise comparison is run **5 times** and averaged to handle LLM stochasticity.

A second experiment validates Comprehensiveness and Diversity with **Claimify**-extracted factual claims (Metropolitansky & Larson 2025): comprehensiveness = average claims per answer; diversity = average ROUGE-L cluster count per answer. LLM-as-judge agreed with claim-based labels in 78% of comprehensiveness comparisons and 69-70% of diversity comparisons. (source: arXiv:2404.16130 §4.2, §5.2)

## Six experimental conditions

| Condition | What it uses |
|---|---|
| **C0** | Root-level community summaries (fewest) |
| **C1** | High-level community summaries |
| **C2** | Intermediate-level community summaries |
| **C3** | Low-level community summaries (most) |
| **TS** | Map-reduce over raw source-text chunks (no graph) |
| **SS** | Vector RAG semantic search baseline |

(source: arXiv:2404.16130 §4.1.2)

## Key results

Two datasets, ~1M tokens each: *Behind the Tech* podcast transcripts (1669 chunks) and a 2013-2023 news-articles corpus (3197 chunks). GPT-4-turbo, 8k context window for query-time, 600-token chunks. (source: arXiv:2404.16130 §4.1.1, §4.1.3)

- **All graph conditions C0-C3 beat vector RAG SS** on Comprehensiveness (72-83% win rate, p<.001) and Diversity (62-82%, p<.001 to p<.01). (source: arXiv:2404.16130 §5.1)
- **Token efficiency**: C0 (root) requires 9-43× fewer tokens than C3 (leaf), and ~97% fewer than TS (text summarization). For modest performance loss, C0 retains a 72% comprehensiveness and 62% diversity win over vector RAG. (source: arXiv:2404.16130 §5.1, Table 2)
- **Empowerment** showed *mixed* results — GraphRAG vs. SS not significantly better in all cases. The authors attribute this to the need for "specific examples, quotes, and citations" which their default extraction prompt does not optimize for.
- **Indexing cost**: 281 minutes for the 1M-token Podcast corpus on a 16GB-RAM Xeon VM using a `gpt-4-turbo` endpoint at 2M TPM / 10k RPM. The Podcast graph: 8,564 nodes, 20,691 edges. (source: arXiv:2404.16130 §4.1.3, §5.1)
- **Context window**: surprisingly, **8k beats 16k/32k/64k** universally on comprehensiveness (58.1% win) and ties on diversity/empowerment — the "lost in the middle" effect (Liu et al. 2023). The authors fixed 8k for all conditions. (source: arXiv:2404.16130 §C)

## What GraphRAG explicitly does *not* do

These omissions are exactly the gap S3 ([[og-rag]]) and S4 ([[kg-agent-s4]]) fill:

- **No ontology**. Entities are LLM-extracted with a generic "named entity" prompt; types are inferred per-chunk. (source: arXiv:2404.16130 §3.1.2, §E.1)
- **No constraint validation** (no [[shacl-validation]] equivalent). Extracted relationships are accepted as-is.
- **No provenance** (no [[prov-o]] equivalent). The output cites "Reports" and entity/relationship IDs by community summary, but there is no audit trail of *which model version, when, with what inputs* produced the answer.
- **No relational reasoning over the graph itself**. Retrieval is over *summaries of community subgraphs*, not over edges/paths. There is no SPARQL or path-walking step.
- **Exact-string entity matching only** — duplicate-entity surface forms across documents are merged only if literally identical.

## Limitations stated by the authors

- Tested only on ~1M-token corpora; generalization to larger or domain-specialized corpora is not demonstrated.
- No fabrication-rate analysis (suggests SelfCheckGPT for future work).
- Claim-based metrics agree with LLM-as-judge only ~70-78% of the time. (source: arXiv:2404.16130 §6.1)

## Future-work suggestions relevant to S4

The authors propose two extensions that anticipate [[think-on-graph-2]]-style hybrid retrieval and the S4 design:

1. **Hybrid local + global**: embedding-based matching of the user query to graph annotations *before* community-summary generation — i.e., a more local "drill down" mechanism that follows the information scent of higher-level summaries. This is structurally similar to [[kg-agent-s4]]'s plan→KG-retrieve→vector-retrieve flow. (source: arXiv:2404.16130 §6.2)
2. **Just-in-time community report generation** — defer summary generation until query time for the relevant communities only.

This validates that GraphRAG's authors themselves see the local/global split as an open problem; S4's hybrid retrieval is a defensible extension, not an unmotivated change.

## Implementation notes for the thesis

- Open-source software at `github.com/microsoft/graphrag` (MIT). LangChain, LlamaIndex, NebulaGraph, and Neo4j all ship GraphRAG variants. (source: arXiv:2404.16130 §1)
- For RQ4 budget: a 1M-token MIMII manifest + SOPs corpus indexed with `gpt-4-turbo` would cost ~5 hours of LLM-bound indexing. Local-LLM substitution will likely lengthen this — flag for [[local-deployment]] feasibility analysis.
- The Leiden community detection step is local CPU work (graspologic) and not the bottleneck.

## Related pages

- [[graphrag]]
- [[og-rag]]
- [[kg-agent-s4]]
- [[strategy-comparison]]
- [[ragas-metrics]]
- [[rag-comprehensive-survey-2024]]
- [[local-deployment]]
- [[research-questions]]
