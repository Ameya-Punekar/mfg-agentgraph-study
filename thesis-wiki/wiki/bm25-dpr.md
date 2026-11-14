# BM25 and DPR

**Summary**: Retrieval baseline concepts for sparse lexical search (BM25) and dense passage retrieval (DPR), used as background for naive RAG and RAG evaluation.

**Sources**: `wiki/rag-comprehensive-survey-2024.md`; `wiki/naive-rag.md`.

**Last updated**: 2026-05-15.

**Thesis relevance**: RQ1 — retrieval baselines for comparing S1 vector RAG, S2 GraphRAG, S3 ontology-grounded retrieval, and S4 KG-Agent reasoning.

---

BM25 is a sparse lexical retrieval baseline that ranks documents by term matching and length-normalized term statistics. DPR is a dense retrieval family that embeds queries and passages into a vector space for semantic nearest-neighbor retrieval. In this thesis wiki, both terms are background baselines for understanding [[naive-rag]] and the broader RAG evaluation literature (source: `wiki/rag-comprehensive-survey-2024.md`).

## Related pages

- [[naive-rag]]
- [[rag-comprehensive-survey-2024]]
- [[ragas-metrics]]
- [[strategy-comparison]]
