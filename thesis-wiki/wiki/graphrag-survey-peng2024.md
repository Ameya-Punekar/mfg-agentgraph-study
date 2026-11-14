# Graph Retrieval-Augmented Generation: A Survey

**Summary**: A comprehensive 2024 survey by Peng et al. that formalizes GraphRAG into three stages (G-Indexing, G-Retrieval, G-Generation) and reviews the core technologies, training methods, downstream tasks, and industrial applications of Graph-augmented LLM systems.

**Sources**: `raw/converted/GraphRAG_Survey_Peng2024.md`

**Last updated**: 2026-05-11.

**Thesis relevance**: RQ1 (GraphRAG landscape and S2 alternatives), RQ2 (Graph-based Indexing technologies).

---

## Key Takeaways

The survey proposes a formal definition of GraphRAG and structures its workflow into three canonical phases:

1. **Graph-Based Indexing (G-Indexing)**: Selecting or constructing a graph database (open-source knowledge graphs or self-constructed textual graphs) and establishing indices. It addresses the representation of graphs as Text-Attributed Graphs (TAGs).
2. **Graph-Guided Retrieval (G-Retrieval)**: Extracting relevant elements (nodes, triples, paths, subgraphs) from the graph database given a user query. This stage incorporates mechanisms to narrow down the search space efficiently.
3. **Graph-Enhanced Generation (G-Generation)**: Synthesizing the final response by integrating the retrieved graph data with the prompt, often converting graph representations into natural language or other patterns the LLM generator can process.

## Relationship to the Thesis

- **S2 baseline context**: The survey places the [[graphrag-microsoft-2024]] (Microsoft GraphRAG) approach within a broader taxonomy of GraphRAG variants, reinforcing the validity of using community-based map-reduce methods as a strong baseline.
- **Alternative Retrieval Paradigms**: Highlights various graph traversal and retrieval techniques (e.g., GNNs, path-based retrieval) which contrast with the [[kg-agent-s4]] strategy of using an LLM-agent tool-caller for SPARQL execution.
- **Training Methodologies**: Discusses both training-free and fine-tuned paradigms for GraphRAG. The thesis adopts a training-free (plug-and-play) approach for S4, aligning with the survey's discussion on utilizing frozen generative pre-trained models.

## Open Questions
- Can the G-Indexing categorization (e.g., open-source KGs vs self-constructed graphs) help frame the difference between S3 (expert ontology) and S2 (LLM-built)?
- Are there specific evaluation metrics highlighted for the G-Retrieval stage that should be incorporated into the [[ragas-metrics]] suite?

## Related pages

- [[graphrag]]
- [[graphrag-microsoft-2024]]
- [[kg-agent-s4]]
- [[rag-comprehensive-survey-2024]]
