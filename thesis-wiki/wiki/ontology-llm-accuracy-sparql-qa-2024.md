# Increasing the LLM Accuracy for QA: Ontologies to the Rescue (2024)

**Summary**: A 2024 technical report by Allemang and Sequeda demonstrating that checking and repairing LLM-generated SPARQL queries against an ontology significantly improves QA accuracy over relational databases (Text-to-SPARQL).

**Sources**: `raw/converted/Ontology_LLM_Accuracy_SPARQL_QA_2024.md`

**Last updated**: 2026-05-11.

**Thesis relevance**: RQ2, RQ4.

---

## Key Takeaways

The approach uses determinism from ontologies to fix LLM errors:
1. **Ontology-based Query Check (OBQC)**: A deterministic module that checks if an LLM-generated SPARQL query conforms to the structural rules of the ontology (e.g., checking `rdfs:domain` and `rdfs:range` rules to ensure proper relationship directions).
2. **LLM Repair**: When OBQC flags an error, it returns an explicit natural language explanation of the rule violation. The LLM is then reprompted with this explanation to repair the SPARQL query.
3. **Results**: Combining knowledge graph context with OBQC and LLM repair increased overall QA accuracy to 72% (from 16% in pure Text-to-SQL setups).

## Relationship to the Thesis

- **SHACL Self-Correction (S4 / RQ4)**: This report perfectly mirrors the thesis methodology. While the authors use `rdfs:domain`/`range` rule checking, the thesis uses SHACL shape validation to provide explicit error feedback for the LangGraph agent to self-correct its SPARQL generation.
- **Accuracy Improvement**: Provides empirical backing that ontology-guided error correction loops yield substantial performance gains in enterprise setups.

## Related pages

- [[mfg-agentgraph]]
- [[shacl-validation]]
- [[kg-agent-s4]]
