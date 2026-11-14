# LLM Agent Methodology Survey (2025)

**Summary**: A comprehensive 2025 survey by Luo et al. detailing LLM-based intelligent agents through a methodology-centered taxonomy encompassing Construction, Collaboration, and Evolution.

**Sources**: `raw/converted/LLM_Agent_Methodology_Survey_2025.md`

**Last updated**: 2026-05-11.

**Thesis relevance**: RQ1, RQ4.

---

## Key Takeaways

The survey provides a "Build-Collaborate-Evolve" framework for LLM agent systems:

1. **Agent Construction**: 
   - *Profile Definition*: Human-curated static profiles vs. batch-generated dynamic profiles.
   - *Memory Mechanism*: Short-term (contextual), long-term (experience/skills), and Knowledge Retrieval as Memory (RAG, GraphRAG, IRCoT).
   - *Planning Capability*: Task decomposition strategies (single-path chain vs. multi-path tree expansion) and feedback-driven iteration.
   - *Action Execution*: Tool utilization and physical interaction.
2. **Agent Collaboration**:
   - Centralized Control vs. Decentralized Collaboration vs. Hybrid Architectures.
3. **Agent Evolution**:
   - Self-learning, multi-agent co-evolution, and evolution via external resources.

## Relationship to the Thesis

- **MFG-AgentGraph Profiling**: S4 utilizes a *Human-Curated Static Profile* defined for anomaly triage in manufacturing.
- **Tool Utilization**: S4 acts as an agent using SPARQL execution as its primary tool to interact with the external knowledge graph, fitting cleanly into the survey's "Action Execution via Tool Utilization" category.
- **Why Single-Agent**: Provides additional context for single-agent vs. multi-agent (collaboration) tradeoffs, complementing the rationale from [[multi-agent-systems-survey-2024b]].

## Related pages

- [[mfg-agentgraph]]
- [[langgraph-agent]]
- [[kg-agent-s4]]
- [[multi-agent-systems-survey-2024b]]
