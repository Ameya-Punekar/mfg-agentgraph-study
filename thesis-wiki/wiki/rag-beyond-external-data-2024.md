# RAG and Beyond: A Comprehensive Survey on How to Make your LLMs use External Data More Wisely

**Summary**: A 2024 survey by Zhao et al. (Microsoft Research) that categorizes RAG tasks into four query levels (Explicit Facts, Implicit Facts, Interpretable Rationales, Hidden Rationales) to systematize the development of data-augmented LLM applications.

**Sources**: `raw/converted/RAG_Beyond_External_Data_2024.md`

**Last updated**: 2026-05-11.

**Thesis relevance**: RQ1 (Methods comparison), RQ3 (Provenance).

---

## Key Takeaways

The survey addresses the challenge of building reliable domain-specific RAG applications by stratifying queries based on data dependency and reasoning complexity:

- **Level-1 (Explicit Facts)**: Queries targeting facts directly present in the text, requiring simple retrieval.
- **Level-2 (Implicit Facts)**: Queries requiring synthesis of facts spread across multiple segments or requiring basic logical deductions.
- **Level-3 (Interpretable Rationales)**: Queries requiring the LLM to comprehend and apply domain-specific rules, guidelines, or decision trees explicit in the external data (e.g., medical diagnostic manuals, FDA guidance).
- **Level-4 (Hidden Rationales)**: Queries where rationales must be inferred from unstructured historical data (e.g., IT operations incident logs).

## Relationship to the Thesis

- **Anomaly Triage (RQ1/RQ3)**: The thesis's primary scenario (anomaly triage on pump stations based on SOPs) is a textbook **Level-3 (Interpretable Rationales)** query. The system must navigate standard operating procedures to process conditions.
- **Evaluating Faithfulness**: The distinction between implicit facts and interpretable rationales highlights why evaluating RAG in expert domains (manufacturing) requires more than standard Q&A metrics—it requires verifying the reasoning path (provenance).

## Related pages

- [[anomaly-triage]]
- [[ragas-metrics]]
- [[kg-agent-s4]]
