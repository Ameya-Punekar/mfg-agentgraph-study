# OG-RAG — Ontology-Grounded RAG (Strategy 3)

**Summary**: A pre-existing domain ontology grounds retrieval: documents are mapped onto ontology facts, those facts are flattened into a hypergraph, and retrieval greedily selects the fewest hyperedges that cover the query-relevant facts. The S3 baseline in the four-strategy comparison.

**Sources**: `concept-paper/sources/2412.15235.pdf` (Sharma, Kumar & Li, Microsoft Research, arXiv:2412.15235v1, 2024). See [[og-rag-2024]] for the full source summary.

**Last updated**: 2026-11-06.

**Thesis relevance**: RQ1, RQ2.

---

## What it is

OG-RAG anchors retrieval in an expert ontology instead of embedding-similarity chunking. The ontology defines entities and attributes; documents supply the values the ontology leaves open; each ontology-mapped factual block becomes a hyperedge of key-value hypernodes; retrieval returns a minimal set of hyperedges that covers the query's relevant facts, and the LLM answers from that compact context. (source: 2412.15235 §4)

## Mechanism in four steps

1. **Ontology mapping.** Prompt an LLM to extract attribute values from domain documents into JSON-LD factual blocks that follow the ontology (source: 2412.15235 §4.1.1).
2. **Flattening.** Resolve nested entity references so every fact becomes a set of `(subject ⊕ attribute ⊕ … , value)` pairs (source: 2412.15235 §4.1.2, Algorithm 1).
3. **Hypergraph.** Hyperedges are flattened factual blocks; hypernodes are key-value pairs. One hyperedge can express a multi-entity fact, unlike pairwise graphs (source: 2412.15235 §4.1.2, Definitions 3–4).
4. **Retrieval and generation.** Take the top-`k` hypernodes by key similarity and top-`k` by value similarity, then greedily add the hyperedge covering the most uncovered relevant nodes until coverage completes or `L` hyperedges are reached; pass those hyperedges to the LLM as line-separated context (source: 2412.15235 §4.2, Algorithm 2).

## Reported results

On two proprietary agriculture corpora and one public news corpus, across GPT-4o-mini, GPT-4o, Llama-3.1-8B, and Llama-3.1-70B, against RAG, RAPTOR, and GraphRAG:

- +55% context recall of correct claims and +110% context entity recall (source: 2412.15235 §6.1.2);
- +40% answer correctness and +16% answer relevance (source: 2412.15235 §6.1.3);
- at most about 2 seconds more query time than simple RAG, with lower preprocessing time than RAPTOR and GraphRAG (source: 2412.15235 §6.1.4);
- 30% faster, better attribution in a user study, and +27% correctness on a deductive-reasoning task (source: 2412.15235 Abstract; Table 5).

These are the authors' numbers on their own datasets, not an independent replication.

## What OG-RAG does not do (the gap S4 fills)

- **No schema or constraint validation.** Hyperedges are retrieved, not validated; nothing rejects a recommendation that violates domain constraints (source: 2412.15235 §4; Algorithm 2 contains no validation step).
- **No repair loop.** If the generated action is invalid, there is no bounded correction mechanism.
- **No audit-grade provenance.** Attribution means "these hyperedges supported the answer"; there is no PROV-O activity/agent/entity trace of retrieval, generation, validation, and writing.
- **No manufacturing evaluation.** The paper motivates industrial workflows but evaluates agriculture and news; no anomaly-triage or sensor-evidence setting appears (source: 2412.15235 §1, §5).

That last point is why S3 in this thesis is a *transfer* of the method to Pump_12 anomaly triage, not a reproduction of a published manufacturing result.

## How S3 uses this in the thesis

S3 keeps the ontology-grounded retrieval mechanism and drops the validation, repair, and provenance layers, which isolates what expert-ontology grounding alone buys over LLM-built graph structure (S2) and text retrieval (S1). The Pump_12 ontology takes the place of the agriculture ontology, SOP chunks supply the values, and the deterministic fixture path mirrors the paper's two-stage structure: ontology-mapped facts, then greedy hyperedge coverage. Implementation is Issue #37: `mfg_agentgraph.s3_ontology_rag` provides the factual-block model, scope filtering by asset/procedure, key-side and value-side relevance, and bounded greedy coverage, and records the answer with validation and provenance artifacts marked `not_applicable`. `check_s3_candidate_post_hoc` runs the package SHACL gate afterwards without changing the record. The deterministic fixture equivalent substitutes lexical query-token overlap for embedding similarity, so it must not claim the paper's reported gains; the same page records that limitation.

## Source discrepancy

The thesis pitch attributes `arXiv:2412.15235` to "Soman et al., EMNLP 2025". The file at that identifier is the Sharma, Kumar, and Li preprint (Microsoft Research, December 2024, `A PREPRINT`) summarised in [[og-rag-2024]]. The pitch and the `idea-and-concept/` manuscripts are author-owned and were not edited; this page records the contradiction.

[NEEDS VERIFICATION] A separate EMNLP 2025 OG-RAG paper by Soman et al. may exist. If it does, it needs its own arXiv/DOI record before any thesis citation; the repository contains no such source.

## Related pages

- [[og-rag-2024]] — source summary and full evaluation detail
- [[strategy-comparison]]
- [[graphrag]]
- [[naive-rag]]
- [[kg-agent-s4]]
- [[ssn-sosa]]
- [[unifying-llms-kgs]]
