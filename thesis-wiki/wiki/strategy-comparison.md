# S1–S4 Strategy Comparison

**Summary**: The four KG–LLM integration strategies compared in the thesis, arranged so each adds one capability over the previous. This is the spine of [[research-questions|RQ1]].

**Sources**: `thesis-pitch-v2.md` §5.

**Last updated**: 2026-04-27.

**Thesis relevance**: RQ1 (primary), RQ2, RQ4.

---

## The four strategies

| Property | S1: [[naive-rag]] | S2: [[graphrag]] | S3: [[og-rag]] | S4: [[kg-agent-s4]] |
|---|---|---|---|---|
| KG source | None | LLM-built (from documents) | Expert ontology (SSN/SOSA + domain) | Expert ontology |
| Retrieval | Vector only | Community summaries | Ontology-hypergraph | SPARQL + vector |
| Agent loop | No | No | No | Yes ([[langgraph-agent]]) |
| SHACL validation | No | No | No | **Yes** |
| Provenance ([[prov-o]]) | No | No | No | **Yes** |
| Local deployment | Yes | Yes | Yes | Yes |
| Fine-tuning needed | No | No | No | No |
| [[unifying-llms-kgs\|Pan 2024]] paradigm | 1 (KG-enhanced LLM Inference) | 1 + 2 (Inference + KG Construction) | 1 (KG Instruction-tuning + Inference) | **3 (Synergized / LLMs-as-Agents Reasoning)** |
| Closest cited cousin in Pan 2024 | Lewis 2020 RAG | (no direct cousin — straddles paradigms) | OntoPrompt (Ye 2022) | ToG, RoG, StructGPT |
| Prior work venue | NeurIPS 2020 (Lewis RAG) | arXiv 2024 (Edge et al., Microsoft) | arXiv 2024 preprint (Sharma, Kumar & Li, Microsoft Research) | This thesis |

(source: thesis-pitch-v2.md §5.5)

## Why this design

Each strategy isolates one design dimension so RQ1 can attribute differences to specific causes:

- **S1 → S2** isolates the value of *having any graph structure at all* over flat vector retrieval.
- **S2 → S3** isolates *expert ontology vs. LLM-constructed graph* (informs RQ2's H2 hypothesis).
- **S3 → S4** isolates *agent loop + SHACL validation + provenance* (informs RQ2's H3 and RQ3's H4).

(source: thesis-pitch-v2.md §5)

## Peer-reviewed basis (per strategy)

- **S1** — Lewis et al., 2020, NeurIPS (original RAG). Evaluated by [[ragas-metrics]]. See [[naive-rag]].
- **S2** — Edge et al., 2024, arXiv:2404.16130 (Microsoft GraphRAG). MIT-licensed implementation `microsoft/graphrag`. See [[graphrag]].
- **S3** — Sharma, Kumar & Li, 2024, arXiv:2412.15235 (Microsoft Research preprint, *verified against `concept-paper/sources/2412.15235.pdf`*); method supported by DeBellis et al., Applied Ontology 2024. See [[og-rag]] and [[og-rag-2024]]. Reported +55% context recall, +40% answer correctness, and +110% context entity recall across four LLMs on agriculture and news corpora. The pitch's "Soman et al., EMNLP 2025" attribution does not match the file — see [[og-rag-2024]].
- **S4** — Built on the **"LLM ⊗ KG" tight-coupling paradigm** from Think-on-Graph (Sun et al., ICLR 2024, arXiv:2307.07697 — see [[think-on-graph]], **verified, the most direct S4 precedent**): three-phase Init → Explore (Search+Prune over relations+entities, beam search) → Reason loop, training-free, plug-and-play across LLMs. Augmented with: plan-as-relation-path from RoG (Luo et al., ICLR 2024, arXiv:2310.01061 — see [[reasoning-on-graphs]], verified) adapted *without fine-tuning* (RoG's 38h LLaMA2-Chat-7B fine-tuning replaced by schema-constrained prompting); hybrid KG+corpus retrieval from ToG 2.0 (Sun et al., ICLR 2025, arXiv:2407.10805 — see [[think-on-graph-2]]); ontology backbone from OG-RAG; SHACL repair from Digital-Twin KG practice; PROV-O audit from Dibowski 2024 (FOIS) and Lavrinovics et al. 2025 (J. Web Semantics); SSN/SOSA modelling from Janowicz 2018.

(source: thesis-pitch-v2.md §5.4)

## Same agent harness, four configs

All four strategies run inside the same Python harness so outputs are directly comparable. The harness is invoked as `mfg-agentgraph run-agent --strategy {s1|s2|s3|s4}` with a shared query set. (source: thesis-pitch-v2.md §12)

## Expected outcomes (hypotheses)

- **H1** — S4 > S1/S2/S3 on RAGAS faithfulness and groundedness.
- **H2** — S3 > S2 on multi-hop relational queries.
- **H3** — SHACL self-correction fires on >30% of S4 plans.

(source: thesis-pitch-v2.md §9.4)

## Related pages

- [[research-questions]]
- [[unifying-llms-kgs]]
- [[ragas-metrics]]
- [[anomaly-triage]]
- [[mimii-dataset]]
