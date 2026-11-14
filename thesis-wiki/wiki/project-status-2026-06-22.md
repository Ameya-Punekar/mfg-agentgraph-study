# Project Status — 2026-06-22

**Summary**: Current status snapshot for MFG-AgentGraph thesis/wiki/concept-paper work as of 2026-06-22, including completed artifacts, live research position, wiki health, and next actions.

**Sources**: `wiki/index.md`; `wiki/log.md`; `wiki/wiki-health.md`; `concept-paper/2026-05-18_architecture-first_concept-paper_plan.md`; `concept-paper/draft/mfg-agentgraph-concept-paper-v0.2.md`; `concept-paper/review-pdf/mfg-agentgraph-review_v2.pdf`; `concept-paper/conference-targets-2026.md`; local session recall summaries.

**Last updated**: 2026-06-22.

**Thesis relevance**: RQ1 / RQ2 / RQ3 / RQ4.

---

## Executive status

The thesis brain is in a usable, structurally clean state. The wiki has a mature project spine, a complete S1–S4 method comparison scaffold, verified pages for the most important KG–LLM / GraphRAG / provenance / ontology sources, and an automated health checker. The concept paper has moved beyond planning into a review-draft stage, with architecture artifacts, a citation matrix, a related-work gap table, draft sections, a bibliography, a citation audit, and a built supervisor/review PDF v2. (source: `wiki/index.md`; `wiki/log.md`; `wiki/wiki-health.md`; `concept-paper/review-pdf/mfg-agentgraph-review_v2.pdf`)

## What has been done

### 1. Thesis wiki bootstrap and structure

- Created the thesis wiki as the durable research brain under `/mnt/d/master-thesis/thesis-wiki`, with immutable `raw/` sources and maintained `wiki/` pages. (source: `wiki/log.md`)
- Established the core thesis pages: [[thesis-pitch]], [[mfg-agentgraph]], [[research-questions]], [[strategy-comparison]], S1–S4 method pages, ontology/provenance pages, evaluation pages, manufacturing-domain pages, and infrastructure pages. (source: `wiki/index.md`; `wiki/log.md`)
- Added maintenance conventions: page metadata, RQ tagging, Obsidian wikilinks, append-only log, and automated health reporting. (source: `wiki/wiki-health.md`; `scripts/wiki_health.py`)

### 2. Research question and method spine

The thesis is organized around four research questions:

- RQ1 — compare retrieval/answer quality across S1–S4.
- RQ2 — evaluate ontology grounding and SHACL validation.
- RQ3 — evaluate provenance and operator trust.
- RQ4 — evaluate local deployment viability.

The method comparison is stable:

- S1: [[naive-rag]] — vector retrieval only.
- S2: [[graphrag]] — Microsoft GraphRAG-style LLM-built graph and community summaries.
- S3: [[og-rag]] — ontology-grounded RAG baseline.
- S4: [[kg-agent-s4]] — KG-Agent path reasoning using SPARQL, SHACL validation, and PROV-O / PROV-AGENT provenance.

This S1–S4 structure is the spine for RQ1 and also isolates RQ2/RQ3/RQ4 mechanisms. (source: [[strategy-comparison]]; [[research-questions]])

### 3. Literature and source ingestion progress

The wiki has ingested or summarized the main sources needed for the current concept-paper argument:

- RAG and GraphRAG grounding: [[rag-comprehensive-survey-2024]], [[graphrag-microsoft-2024]], [[graphrag-survey-peng2024]].
- KG–LLM taxonomy and reasoning: [[unifying-llms-kgs]], [[reasoning-on-graphs]], [[think-on-graph]], [[llms-meet-kgs-qa-survey-2025]], [[beyond-chain-of-thought-2024]], [[kg-construction-llm-survey-2024]].
- Agent and multi-agent positioning: [[multi-agent-systems-survey-2024b]], [[multi-agent-llm-survey-2024]], [[llm-agent-methodology-survey-2025]], [[understanding-planning-llm-agents-2024]], [[react-yao2023]].
- Ontology/provenance standards and precedents: [[sosa-ssn-2018]], [[ssn-sosa]], [[shacl-validation]], [[prov-o]], [[prov-agent-souza2025]].
- Manufacturing/domain/evaluation anchors: [[mimii-dataset]], [[anomaly-triage]], [[ragas-metrics]], [[faithfulness]], [[groundedness]].

The strongest current S4 support chain is: Pan taxonomy → RoG/ToG KG path reasoning → SOSA/SSN domain ontology → SHACL validation → PROV-O / PROV-AGENT provenance. (source: `wiki/index.md`; [[kg-agent-s4]]; [[strategy-comparison]])

### 4. Concept paper progress

A publishable concept/position paper workflow has been created and substantially executed:

- Architecture-first plan created at `concept-paper/2026-05-18_architecture-first_concept-paper_plan.md`.
- Architecture artifacts created under `concept-paper/architecture/`, including v1 and v2 figures.
- Literature support created:
  - `concept-paper/literature/citation-matrix.md`
  - `concept-paper/tables/related-work-gap-table.md`
  - `concept-paper/references.bib`
  - `concept-paper/citation-audit.md`
- Draft manuscript sections created under `concept-paper/draft/`, including v0.1 and v0.2 assembled drafts.
- Review PDF produced under `concept-paper/review-pdf/`.
- Review PDF v2 exists as `concept-paper/review-pdf/mfg-agentgraph-review_v2.pdf`; local PDF metadata shows the title as “MFG-AgentGraph: SHACL-Validated and PROV-O-Traceable LLM Agents for Manufacturing Anomaly Triage” and 23 pages. (source: local `pdfinfo` on `concept-paper/review-pdf/mfg-agentgraph-review_v2.pdf`)

### 5. Current paper positioning

The safe current claim is concept/architecture-stage, not completed empirical-results-stage:

MFG-AgentGraph is a locally deployable, ontology-grounded, provenance-traceable KG–LLM agent architecture for manufacturing anomaly triage. It combines SSN/SOSA-style RDF modelling, SPARQL retrieval over a triplestore, vector retrieval for SOP/manual evidence, SHACL-in-the-loop validation and bounded repair, and PROV-O / PROV-AGENT traces for auditable operator-facing evidence packages. (source: `concept-paper/conference-targets-2026.md`; [[mfg-agentgraph]]; [[kg-agent-s4]])

The novelty boundary remains conservative: do not claim “first KG–LLM agent” or “first GraphRAG system.” The defensible contribution is the particular combination of local manufacturing deployment, standards-based ontology grounding, SHACL validation in the agent loop, provenance packaging, and the planned S1/S2/S3/S4 evaluation harness. (source: `concept-paper/2026-05-18_architecture-first_concept-paper_plan.md`; `concept-paper/conference-targets-2026.md`)

### 6. Venue/status planning

The current target list prioritizes concept/position/short/WIP venues rather than full empirical-results venues. On 2026-06-22 it was refreshed with additional Europe-based opportunities and a clearer fallback ladder:

1. AIAA4KE 2026 — one-page position/vision/challenge statement, due 2026-07-24.
2. RAGE-KG 2026 — 4–6 page short paper, abstract 2026-07-17 and paper 2026-07-24.
3. GLOW@ISWC 2026 — discussion/position/system paper on graph-enhanced trustworthy LLMs, due 2026-07-14.
4. KG-NeSy 2026 — short paper / extended abstract on KG + neurosymbolic AI, due 2026-07-15.
5. Sci-K 2026 — 6-page vision/position/short paper, due 2026-07-24.
6. DMKG 2026 — short/position/demo paper, abstract 2026-07-10 and paper 2026-07-17.
7. KGMDSE 2026 — short position/vision paper on KG + model-driven systems engineering, due 2026-07-24.
8. EKAW 2026 Posters/Demos — late-breaking / ongoing KE/KM system work, due 2026-07-24 according to the updated official dates page.
9. KGSWC 2026 Posters/Demos — later-window European KG/Semantic Web backup, due 2026-09-18.
10. EAIT 2026 — non-European WIP fallback, due 2026-07-15.

(source: `concept-paper/conference-targets-2026.md`; official CFP pages linked there)

## Wiki lint status as of 2026-06-22

Automated structural lint passed after rerun:

- Required metadata fields: clean.
- RQ tags: clean.
- Wikilink targets: clean.
- Index coverage/orphans: clean.
- Stale dates: clean.
- Recent raw-folder mutation warnings: clean.

(source: `wiki/wiki-health.md`; `scripts/wiki_health.py`)

Manual content lint still identifies cleanup work:

- Several pages still contain `[NEEDS VERIFICATION]` flags, especially around ToG 2.0, MIMII dataset details, RAGAS faithfulness, OG-RAG claims, W3C PROV-O specs, and some standards/source-details. These are not structural failures, but they must be resolved before final thesis or submission-ready paper claims. (source: local wiki search on 2026-06-22)
- Many pages retain “Open questions” sections. That is acceptable for a research brain, but these should be triaged into: thesis experiment tasks, paper citation-audit tasks, and low-priority future work. (source: local wiki search on 2026-06-22)
- The concept-paper outputs are not yet fully reflected as first-class wiki navigation except through this status page. If the concept paper becomes the main short-term deliverable, add dedicated wiki pages for “concept-paper-status” and “venue-targets” or keep this status page updated. [NEEDS VERIFICATION]

## Immediate next actions

1. Choose paper target now: AIAA4KE one-pager vs RAGE-KG/Sci-K/DMKG 4–6 page short paper. The deadline path differs.
2. Cut the 23-page review PDF v2 into the chosen submission shape.
3. Remove or soften any text implying completed empirical results.
4. Resolve high-risk `[NEEDS VERIFICATION]` flags needed by the target version, especially OG-RAG, MIMII, RAGAS faithfulness, and ToG 2.0.
5. Produce venue-specific PDF and run a final citation/placeholder audit.
6. For thesis implementation, convert open questions into a concrete experiment backlog: data/KG build, S1–S4 harness, SHACL shapes, PROV trace store, local latency/resource benchmark.

## Agent operating environment update

The Hermes thesis profile now keeps `openai-codex` / `gpt-5.5` as the primary model and uses an ordered fallback chain: first `ollama-cloud` with `qwen3-coder:480b` via `https://ollama.com/v1`, then OpenRouter `cohere/north-mini-code:free` as the second fallback. The user explicitly preferred Ollama Cloud Qwen3-Coder over local Ollama for the first fallback. Earlier paid/credit-consuming OpenRouter fallbacks such as `deepseek/deepseek-v4-flash` remain inactive. On 2026-06-22, direct Hermes smoke tests passed for both `ollama-cloud` / `qwen3-coder:480b` (`ollama-cloud-qwen-ok`) and OpenRouter `cohere/north-mini-code:free` (`cohere-second-fallback-ok`). The OpenRouter `qwen/qwen3-coder:free` route remains documented as stronger on paper but unreliable in live tests because it returned upstream 429 after an initial success. Local Ollama still has only `nomic-embed-text` installed; local Qwen3-Coder is not the active plan. (source: local Hermes config check, direct Hermes provider smoke tests, OpenRouter `/api/v1/models`, Ollama model page and local `ollama list` on 2026-06-22)

## Related pages

- [[index]]
- [[wiki-health]]
- [[research-questions]]
- [[strategy-comparison]]
- [[mfg-agentgraph]]
- [[kg-agent-s4]]
- [[references-master]]
