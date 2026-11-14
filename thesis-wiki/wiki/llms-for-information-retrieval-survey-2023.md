# Large Language Models for Information Retrieval: A Survey (2023)

**Summary**: A comprehensive 2023 survey by Zhu et al. detailing the confluence of Large Language Models (LLMs) and Information Retrieval (IR) systems. It systematically reviews how LLMs are applied to core IR components including query rewriters, retrievers, rerankers, and readers, as well as the emerging paradigm of search agents.

**Sources**: `raw/converted/Think_on_Graph_2_Hybrid_RAG_2024.md` (Mislabeled file)

**Last updated**: 2026-05-11.

**Thesis relevance**: RQ1 — background for retrieval/reranking/reader pipelines and the search-agent framing behind S1–S4 comparisons.

---

## Key Takeaways

1. **IR Pipeline Enhancements**: LLMs can replace or augment specific modules within the traditional IR pipeline:
   - **Query Rewriters**: Refining or expanding user queries for better precision.
   - **Retrievers**: Assisting in generating better dense embeddings or capturing complex query-document semantic relationships.
   - **Rerankers**: Providing fine-grained, context-aware reordering of the initially retrieved candidate documents.
   - **Readers**: Summarizing retrieved documents into concise, natural language responses (similar to RAG).
2. **Search Agents**: The survey highlights a shift toward holistic "search agents" (like WebGPT) that autonomously interact with search engines, orchestrating the entire retrieval and reading loop.

## Relationship to the Thesis

- **Related Work Context**: Provides a broad taxonomy of how LLMs are transforming IR, grounding the thesis's specific focus on Knowledge Graph-augmented retrieval (S2/S3/S4) within the wider NLP literature.
- **Note on Mislabeled File**: This paper was originally provided under the filename `Think_on_Graph_2_Hybrid_RAG_2024.md`. It is an Information Retrieval survey, *not* the Think-on-Graph 2.0 paper by Sun et al. The actual ToG 2.0 paper is still pending.

## Related pages

- [[naive-rag]]
- [[strategy-comparison]]
- [[references-master]]
