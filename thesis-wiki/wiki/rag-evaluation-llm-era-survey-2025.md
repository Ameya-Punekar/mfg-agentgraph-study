# RAG Evaluation in the Era of LLMs: A Comprehensive Survey

**Summary**: A 2025 survey by Gan et al. outlining RAG evaluation methodologies. It divides evaluation into internal (component-level: retrieval vs. generation) and external (system-level: safety, efficiency) domains, detailing specific metrics like MRR, NDCG, and LLM-as-a-judge patterns.

**Sources**: `raw/converted/RAG_Evaluation_LLM_Era_Survey_2025.md`

**Last updated**: 2026-05-11.

**Thesis relevance**: RQ1 (Evaluation methodology), RQ2.

---

## Key Takeaways

The survey structures RAG evaluation along a bipartite framework:

1. **Internal Evaluation**: Assesses component-level performance:
   - **Retrieval Target**: Evaluates *Relevance* (Retrieved Docs ↔ Query) and *Comprehensiveness* (Coverage). Employs IR metrics like Hit@K, MRR, NDCG, and MAP.
   - **Generation Target**: Evaluates *Relevance* (Response ↔ Query), *Faithfulness* (Response ↔ Retrieved Docs), and *Correctness* (Response ↔ Ground Truth). Uses NLG metrics like EM, ROUGE, BLEU, and LLM-based metrics.
2. **External Evaluation**: Examines system-wide factors such as safety, hallucination rates, and computational efficiency.

## Relationship to the Thesis

- **RQ1 Evaluation Design**: Validates the use of RAGAS metrics (Faithfulness, Answer Relevance, Context Precision) which are aligned with the internal evaluation targets described in the survey.
- **RAGAS Integration**: Reinforces the decision to utilize multifaceted LLM-driven evaluation frameworks for the S1–S4 baseline comparison.

## Related pages

- [[ragas-metrics]]
- [[faithfulness]]
- [[groundedness]]
