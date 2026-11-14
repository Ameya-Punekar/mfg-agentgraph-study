# PageIndex: Vectorless Reasoning-Based RAG

**Summary**: PageIndex is a vectorless, reasoning-based RAG framework that replaces chunking→embedding→vector-similarity with hierarchical tree indexing + LLM-guided tree search. Achieves 98.7% on FinanceBench (SOTA). Relevant as an alternative retrieval paradigm and a potential comparison baseline or hybrid component for MFG-AgentGraph.

**Sources**: `raw/pageindex-readme.md`, `raw/pageindex-study-notes.md` (Zhang, Tang & VectifyAI Team, 2025; MIT License; github.com/VectifyAI/PageIndex, 25.8k stars).

**Last updated**: 2026-05-11.

**Thesis relevance**: RQ1 (alternative RAG paradigm for S1 baseline comparison), RQ4 (no vector DB infrastructure — simpler local deployment).

---

## Core Insight: Similarity ≠ Relevance

Traditional vector RAG retrieves by cosine similarity in embedding space. PageIndex argues that what matters is **relevance**, and relevance requires **reasoning** — not pattern matching. When working with professional documents demanding domain expertise and multi-step reasoning, similarity search falls short. (source: pageindex-readme.md)

Inspired by **AlphaGo's Monte Carlo Tree Search**: just as AlphaGo navigates a game tree, PageIndex uses LLM-guided tree search to navigate a document's hierarchical structure. (source: pageindex-study-notes.md)

## Two-Phase Pipeline

### Phase 1 — Tree Index Construction

PageIndex transforms PDF documents into a semantic **tree structure** (a "Table of Contents" optimized for LLMs). Three modes, chosen automatically:

| Mode | Trigger | Process |
|---|---|---|
| **A: ToC with page numbers** | Document has table of contents with page refs | Extract ToC → JSON → calculate page offset → verify via LLM |
| **B: ToC without page numbers** | ToC exists but no page numbers | Extract ToC → JSON → LLM locates physical start pages → verify |
| **C: No ToC** | No detectable table of contents | Divide pages into token-limited groups → LLM generates hierarchical structure |

After initial construction, nodes exceeding thresholds (default: 10 pages / 20,000 tokens) are **recursively split**. (source: pageindex-study-notes.md §3.2)

### Phase 2 — Retrieval via Tree Search

Three retrieval tools exposed to LLM agents:
1. **`get_document(doc_id)`** → metadata (name, description, page count)
2. **`get_document_structure(doc_id)`** → tree structure (without text, to save tokens)
3. **`get_page_content(doc_id, pages)`** → actual page text for specified pages

The retrieval flow: Query → LLM reads tree structure → Reasons about relevant section → Requests page content → Extracts answer. (source: pageindex-study-notes.md §3.4)

## Self-Correction Loop

Verification and cascading fallback ensure robustness:
```
verify_toc() → checks every entry against actual page content
  ├── accuracy ≥ 100% → return as-is
  ├── accuracy > 60%  → fix_incorrect_toc_with_retries() (up to 3x)
  └── accuracy ≤ 60%  → fallback to less-informed mode:
                         with_page_numbers → no_page_numbers → no_toc
```

This pattern is **structurally analogous** to S4's [[shacl-validation|SHACL]] self-correction loop: both use a deterministic check (page-content verification / SHACL engine) to trigger iterative LLM regeneration. Fourth independent instance of the generate-validate-retry pattern (after [[multi-agent-systems-survey-2024b|Chen et al. §3.1]], [[understanding-planning-llm-agents-2024|Huang et al. §5-6]], [[beyond-chain-of-thought-2024|Xia et al. §3.3]]). (source: pageindex-study-notes.md §5.4)

## Comparison: PageIndex vs. MFG-AgentGraph

| Aspect | MFG-AgentGraph (S4) | PageIndex |
|---|---|---|
| Knowledge structure | Knowledge Graph (RDF/OWL) | Document tree (JSON) |
| Data source | Manufacturing sensor data, metadata | PDF documents |
| Query language | SPARQL | Natural language → tree navigation |
| Reasoning | KG path traversal (ToG/RoG) | LLM tree search |
| Scope | Multi-document knowledge base | Single/few document analysis |
| Validation | SHACL shape conformance | ToC page-mapping verification |
| Infrastructure | Fuseki triplestore | No vector DB, no external infra |

(source: pageindex-study-notes.md §9)

## Thesis Integration Points

1. **Hybrid retrieval**: Use PageIndex for **document-level** retrieval over manufacturing manuals/SOPs, combined with KG retrieval for structured sensor data. This is the hybrid text+KG retrieval pattern that [[graphrag-microsoft-2024|GraphRAG §6.2]] and [[think-on-graph|ToG]] independently propose as future work.
2. **Agentic tool pattern**: PageIndex's three retrieval tools follow the same LangGraph tool-use pattern as S4's SPARQL tools — could be integrated as additional [[langgraph-agent]] tool nodes.
3. **Comparison baseline**: PageIndex could serve as an alternative to S1 ([[naive-rag]]) — reasoning-based vectorless retrieval vs. similarity-based vector retrieval, both without KG.
4. **No vector DB**: Aligns with [[local-deployment]] / RQ4 emphasis on minimal infrastructure. (source: pageindex-study-notes.md §9)

## Strengths and Limitations

**Strengths**: no vector DB required; explainable retrieval (traceable to pages/sections); handles complex/long documents; preserves document hierarchy; 98.7% accuracy on FinanceBench.

**Limitations**: high LLM cost (dozens of calls per document for indexing); slow indexing vs. vector embeddings; requires capable LLM (GPT-4o class); not ideal for short documents; no fuzzy semantic search capability. (source: pageindex-study-notes.md §8)

## Open questions raised

1. **Hybrid KG + PageIndex retrieval**: could S4's SPARQL-retrieved subgraph be combined with PageIndex-retrieved SOP sections in the same answer generation step? Worth prototyping in Phase 3.
2. **Local LLM for tree indexing**: PageIndex defaults to GPT-4o — does it degrade gracefully with quantized local models? Directly relevant to RQ4.
3. **Manufacturing document quality**: SOPs and maintenance manuals are often poorly formatted PDFs — does the cascading fallback (Mode A → B → C) handle these adequately?

## Related pages

- [[naive-rag]] — PageIndex is the reasoning-based alternative to vector-similarity S1
- [[shacl-validation]] — structural parallel: deterministic-check → self-correction loop
- [[local-deployment]] — no vector DB aligns with minimal infrastructure goal
- [[langgraph-agent]] — PageIndex tools follow the same agentic tool-use pattern
- [[graphrag-microsoft-2024]] — §6.2 proposes hybrid text+KG retrieval that PageIndex could enable
- [[kg-agent-s4]] — potential hybrid: KG reasoning for structured data + tree reasoning for documents
