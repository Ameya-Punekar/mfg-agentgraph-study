# Retrieval-Augmented Generation: A Comprehensive Survey of Architectures, Enhancements, and Robustness Frontiers

**Summary**: A 2025 survey by Sharma that categorizes RAG architectures into retriever-centric, generator-centric, hybrid, and robustness-oriented designs. It provides a taxonomy of RAG enhancements including adaptive retrieval and noise-adaptive training objectives.

**Sources**: `raw/converted/RAG_Architectures_Robustness_Survey_2025.md`

**Last updated**: 2026-05-11.

**Thesis relevance**: RQ1 (Method comparison), RQ4 (Local deployment).

---

## Key Takeaways

The survey provides a taxonomy categorizing RAG frameworks based on their primary architectural orientation:

1. **Retriever-Based Systems**: Focus on query enhancement (e.g., query expansion, rewriting), retriever adaptation, and granularity optimization.
2. **Generator-Based Systems**: Assume retrieved content is sufficiently relevant, shifting the burden of factual grounding to the language model via faithfulness-aware decoding, context compression, and retrieval-guided control.
3. **Hybrid RAG Systems**: Tightly couple the retriever and generator for joint optimization, utilizing iterative or multi-round retrieval and dynamic triggering (e.g., FLARE, CRAG).
4. **Robustness-Oriented Systems**: Designed to preserve output quality in the face of noisy or adversarial retrieval contexts via noise-adaptive training and hallucination-aware decoding constraints.

## Relationship to the Thesis

- **S4 (MFG-AgentGraph) Placement**: The S4 architecture uses a SHACL-driven self-correction loop, which closely maps to the **Hybrid RAG Systems** and **Robustness-Oriented** paradigms outlined in the survey, specifically acting as an iterative retrieval-generation feedback loop.
- **Evaluation framing**: The discussion on robustness provides a useful theoretical framework for validating the SHACL constraint checker as a noise-filtering/robustness-enhancing mechanism.

## Related pages

- [[strategy-comparison]]
- [[kg-agent-s4]]
- [[rag-comprehensive-survey-2024]]
