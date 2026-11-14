# Graph-constrained Reasoning (2024)

**Summary**: A 2024 paper by Luo et al. introducing Graph-constrained Reasoning (GCR), a framework that ensures faithful reasoning on Knowledge Graphs by integrating the KG structure directly into the LLM decoding process using a trie-based index (KG-Trie).

**Sources**: `raw/converted/Graph_Constrained_Reasoning_2024.md`

**Last updated**: 2026-05-11.

**Thesis relevance**: RQ4.

---

## Key Takeaways

The GCR framework bridges structured knowledge with unstructured LLM reasoning through three components:
1. **KG-Trie Construction**: Converts reasoning paths in KGs into a structured index (Trie) that restricts LLM output tokens to valid prefixes.
2. **Graph-constrained Decoding**: A lightweight KG-specialized LLM is constrained by the KG-Trie to generate only valid, hallucination-free reasoning paths and hypothesis answers directly from the KG.
3. **Graph Inductive Reasoning**: A powerful general LLM processes multiple reasoning paths and hypothesis answers to deduce the final correct answer via inductive reasoning.

## Relationship to the Thesis

- **Graph Traversal vs SPARQL**: GCR offers an alternative to the thesis's tool-calling approach (where the agent writes SPARQL queries). By restricting the token generation process, GCR guarantees valid paths without the latency of iterative agent tool-use. 
- **SHACL Constraint Analogue**: While the thesis uses SHACL to enforce schema compliance dynamically, GCR enforces compliance at the decoding level. Comparing these two paradigms provides rich material for the RQ4 discussion on efficiency vs. accuracy tradeoffs.

## Related pages

- [[mfg-agentgraph]]
- [[kg-agent-s4]]
- [[reasoning-on-graphs-rog-2024]]
