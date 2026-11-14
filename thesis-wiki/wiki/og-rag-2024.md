# OG-RAG (Sharma, Kumar & Li, arXiv:2412.15235, 2024)

**Summary**: Microsoft Research preprint describing OG-RAG, an ontology-grounded retrieval method that maps documents onto a domain ontology, flattens the mapped facts into a hypergraph, and retrieves a minimal set of hyperedges as compact, attributable LLM context. The method paper behind the S3 baseline.

**Sources**: `concept-paper/sources/2412.15235.pdf` (text extraction: `concept-paper/sources/2412.15235.txt`).

**Last updated**: 2026-11-06.

**Thesis relevance**: RQ1, RQ2.

---

## Citation record

- **Title**: OG-RAG: Ontology-Grounded Retrieval-Augmented Generation for Large Language Models.
- **Authors**: Kartik Sharma, Peeyush Kumar, Yunqing Li (Microsoft Research, Seattle).
- **Venue**: arXiv preprint 2412.15235v1, submitted 12 December 2024; the PDF is marked `A PREPRINT`. No peer-reviewed venue is stated in the document.
- **Code**: no repository or artifact link appears in the ingested text. Replication from the paper description is the only route established here.

[NEEDS VERIFICATION] The thesis pitch attributes this arXiv ID to "Soman et al., EMNLP 2025". That attribution does not match the file (see **Source discrepancy** below). Whether a separate 2025 OG-RAG paper by Soman et al. exists is unresolved in this repository.

## Problem the paper targets

Domain-specific question answering needs precise, rule-following facts, not general embeddings. Plain RAG chunks documents arbitrarily, so retrieved context is hard to attribute to facts and cannot support deductive reasoning over a domain's rules (source: 2412.15235 §1). The paper argues ontologies supply the structure that chunking loses.

## Method

1. **Ontology-mapped factual blocks.** Given an ontology `O` of triples `(s, a, v)` where `v` is either another entity or a domain value, an LLM prompts values out of the documents for attributes the ontology leaves open, producing self-contained factual blocks in JSON-LD (source: 2412.15235 §4.1.1, Definition 2; Appendix B.1).
2. **Flattening.** Nested blocks are expanded into flattened key-value facts by following entity references, so each fact is a set of `(concatenated subject-attributed path, value)` pairs (source: 2412.15235 §4.1.2, Algorithm 1).
3. **Hypergraph.** Each flattened factual block becomes a hyperedge whose hypernodes are key-value pairs, so one hyperedge encodes a multi-entity fact that pairwise graphs cannot express (source: 2412.15235 §4.1.2, Definitions 3–4).
4. **Retrieval.** For a query, the method takes the top-`k` hypernodes by embedding similarity of the key `s ⊕ a` and the top-`k` by similarity of the value `v`, then greedily adds the hyperedge covering the most uncovered relevant nodes until all are covered or `L` hyperedges are selected. The paper argues this greedy coverage is optimal because the objective is linear under a matroid constraint (source: 2412.15235 §4.2, Algorithm 2).
5. **Generation.** The selected hyperedges are passed line-separated as context with the query, and the LLM answers as a list of facts in dictionary format (source: 2412.15235 §4.2.3).

## Evaluation setup

- **Domains**: two agriculture datasets (85 documents prepared by agriculture experts, soybean and wheat cultivation in India; proprietary) and one news dataset (149 long-form articles over 2,000 words from a Multi-hop RAG dataset; public) (source: 2412.15235 §5, Datasets).
- **Ontologies**: a proprietary ontology-learning module reviewed by crop-cultivation experts for agriculture; a trimmed Simple News and Press (SNaP) ontology for news (source: 2412.15235 §5, Ontology).
- **Models**: GPT-4o-mini, GPT-4o, Llama-3.1-8B, Llama-3.1-70B; zero-shot, 4,096 completion tokens, temperature 0 (source: 2412.15235 §5, LLMs).
- **Baselines**: RAG, RAPTOR, GraphRAG (source: 2412.15235 §5, Baselines; Table 1).
- **Metrics**: context recall (C-Rec), context entity recall (C-ERec), answer correctness (A-Corr), answer similarity (A-Sim), answer relevance (A-Rel), plus a user study on attribution speed and a deductive-reasoning task over predefined rules (source: 2412.15235 §6).

## Reported results

- Context recall of correct claims: +55%; context entity recall: +110% (source: 2412.15235 §6.1.2). The news dataset ties RAPTOR on context recall.
- Answer correctness: +40%; answer relevance: +16% (source: 2412.15235 §6.1.3). The paper notes answer relevance can dip on wheat/soybean with GPT-4o and Llama-3-70B because broad context adds extraneous information.
- Efficiency: query-time overhead of at most about 2 seconds versus simple RAG, and lower preprocessing time than RAPTOR and GraphRAG (source: 2412.15235 §6.1.4).
- Attribution: a user study finds attributing responses to retrieved context 30% faster and better (source: 2412.15235 Abstract, §1).
- Deductive reasoning: +27% correctness when applying predefined rules over OG-RAG context (source: 2412.15235 Abstract, Table 5).

All numbers are as reported by the authors on their own datasets; they are not independently replicated here.

## Stated and apparent limitations

- Domain ontologies "may not always be available or sufficiently comprehensive"; the authors are developing ontology learning to mitigate this (source: 2412.15235 §4.1.1).
- The agriculture corpora are proprietary, so exact replication on those numbers is not possible from this repository.
- No manufacturing or industrial anomaly evaluation appears in the paper, despite the framing of "industrial workflows" (source: 2412.15235 §1, §5).
- There is no schema/constraint validation, no repair loop, and no provenance trace: context attribution is over hyperedges, not an audit-grade PROV record (source: 2412.15235 §4; no such component appears in Algorithm 2).

## Source discrepancy

The thesis pitch (`raw/thesis-pitch-v2.md` §5.3 and its reference list) attributes `arXiv:2412.15235` to **Soman et al. (2025, EMNLP)**. The file at that arXiv ID is the Sharma, Kumar, and Li preprint above: different authors, different venue status (preprint, not EMNLP). The pitch and the `idea-and-concept/` copies are left unchanged because they are author-owned source and derivative manuscripts; this page and [[og-rag]] record the contradiction.

[NEEDS VERIFICATION] If the thesis intends to cite an EMNLP 2025 OG-RAG paper by Soman et al., it must be located and cited with its own identifier. The repository currently contains no such source.

## Related pages

- [[og-rag]] — the S3 strategy page built from this source
- [[strategy-comparison]]
- [[graphrag]]
- [[kg-agent-s4]]
- [[unifying-llms-kgs]]
