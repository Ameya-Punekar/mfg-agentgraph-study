# ReAct: Synergizing Reasoning and Acting in Language Models (2023)

**Summary**: The foundational 2023 paper by Yao et al. that introduced the ReAct paradigm, enabling LLMs to generate both reasoning traces (thoughts) and task-specific actions in an interleaved manner.

**Sources**: `raw/converted/ReAct_Yao2023.md`

**Last updated**: 2026-05-11.

**Thesis relevance**: RQ3, RQ4 (Agentic baseline).

---

## Key Takeaways

1. **Interleaved Reasoning and Acting**: ReAct augments the action space of an LLM agent to include a "language" space. Thoughts (reasoning traces) help induce, track, and update action plans, while actions interact with the environment (e.g., Wikipedia API, WebShop) to gather information.
2. **Overcoming CoT Limitations**: Chain-of-Thought (CoT) prompting suffers from hallucination and error propagation due to lack of environmental grounding. ReAct overcomes this by injecting factual external observations into the reasoning loop.
3. **Interpretability**: The distinct "Thought -> Action -> Observation" loops provide a highly interpretable trace of the model's decision-making process.

## Relationship to the Thesis

- **Core Framework (S4)**: The LangGraph single-agent architecture (S4) proposed in the thesis fundamentally operates on the ReAct loop. The agent reasons about the user anomaly query, formulates a SPARQL query action, observes the triplestore output, and reasons again (evaluating SHACL validation errors) to iterate.
- **Agentic Foundations**: Validates the choice to ground LLM reasoning in external systems (the industrial Knowledge Graph) to avoid hallucination during pump station diagnostics.

## Related pages

- [[mfg-agentgraph]]
- [[kg-agent-s4]]
- [[understanding-planning-llm-agents-2024]]
