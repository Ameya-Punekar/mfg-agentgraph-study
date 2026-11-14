# FiDeLiS: Faithful Reasoning in Large Language Models for KG QA (2024)

**Summary**: A 2024 paper introducing FiDeLiS, a unified framework to improve the factuality of LLM responses in KG QA. It anchors answers to verifiable reasoning steps retrieved from a KG via Deductive-Verification Beam Search (DVBS) and Path-RAG.

**Sources**: `raw/converted/FiDeLiS_Faithful_KG_Reasoning_2024.md`

**Last updated**: 2026-05-11.

**Thesis relevance**: RQ3, RQ4.

---

## Key Takeaways

FiDeLiS balances the efficiency of retrieval-based methods and the faithfulness of agent-based methods:
1. **Path-RAG**: Iteratively pre-selects a smaller candidate set of entities and relations to reduce the search space, using both semantic similarity and structural connectivity.
2. **Deductive-Verification Beam Search (DVBS)**: Employs an LLM to build reasoning paths step-by-step. At each step, a deductive verification check ensures the accumulated reasoning logically supports the query. The search halts only when the query can be confidently deduced.

## Relationship to the Thesis

- **Reasoning Fidelity (RQ3)**: The emphasis on verifiable paths directly aligns with the thesis's focus on interpretable rationales for anomaly triage.
- **Architectural Efficiency (RQ4)**: The Path-RAG component addresses the latency bottlenecks of typical multi-agent or iterative single-agent approaches. This supports the thesis's design choice in using optimized retrieval (like page index or graph trie) before performing LLM reasoning.

## Related pages

- [[mfg-agentgraph]]
- [[reasoning-on-graphs-rog-2024]]
- [[kg-agent-s4]]
