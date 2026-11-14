# MFG-AgentGraph Wiki — Index

**Summary**: Table of contents for the thesis wiki. Pages are organized by topic and tagged to research questions (RQ1–RQ4).

**Sources**: Maintained wiki pages in `wiki/` and source summaries derived from `raw/` / `raw/converted/`.

**Last updated**: 2026-11-09.

**Thesis relevance**: RQ1 / RQ2 / RQ3 / RQ4.

---

## How to navigate

- Start with [[thesis-pitch]] for the project overview.
- [[research-questions]] anchors all other pages to RQ1–RQ4.
- [[strategy-comparison]] is the spine of RQ1 (the four-way method comparison).
- See [[log]] for the append-only edit history.

## Project spine

- [[implementation-study-protocol-v1]] — **Frozen implementation-study protocol (2026-11-07)**: deployment envelope, executable S1–S4 definitions, two study tracks, data lineage, human-evidence gates, claims table and licence manifest. Every result must cite it.
- [[delivery-roadmap]] — **Authoritative delivery order (clarified 2026-11-08)**: core backend and evaluation components before API/UI, then controlled experiments and a packaged demo; supersedes the measurement phase of [[evaluation-roadmap]] and lists the prohibited-claims gates.
- [[scenario-corpus-v1]] — **Versioned four-class corpus release (2026-11-09)**: 28 licensed documents, 292 chunks, 8 assets, 64 SSN/SOSA sensors, 1,612 observations (4 MIMII-derived), 12,413 triples, development split only; records the ~50-document shortfall, the missing industrial slide sources, and a post-freeze acquisition record for the 13 blocked identities (11 complete, 2 partial Navy manuals).
- [[scenario-corpus-v2]] — **Additive corpus successor (2026-11-10)**: v1's frozen evidence layer plus the 11 previously unreachable documents (nine NRC valve reports, CDC/NIOSH 2019-124, USACE 2020), giving 39 artifacts / 38 families, 418 chunks, 13,405 triples; superseded by v3.
- [[scenario-corpus-v3]] — **Corpus release (2026-11-13), superseded by v4**: v2's evidence layer plus ten verified families (SKAT India Mark II/III, PRACTICA rope pump, three NAVEDTRA courses, Voron, LulzBot, FarmBot, PrintNC) at 49 artifacts / 48 families, 528 chunks, 14,761 triples; corrects the authored layer so recipes and queries cite entailing chunks, publishes provenance plus a derivation record for each derived source into the graph, and records that the triple count is multiplicity-driven.
- [[scenario-corpus-v4]] — **Current corpus release (2026-11-13)**: v3's evidence and authored layers unchanged, with the observation layer rebuilt so 1,600 authored records each state a value in their sensor's unit, a scenario instant and an operating state; 1,604 observations at 49 artifacts / 48 families, 528 chunks and 19,521 triples, with zero identifier-only records (v3 had 1,608) and a recorded scale-only reading of the triple count.

- [[evaluation-roadmap]] — Dependency-ordered sequence for the remaining evaluation issues (#35–#54) plus the review-driven validity gates (#79, #80); historical after the 2026-11-07 delivery audit.
- [[project-status-2026-11-05]] — Current Implementation V1 snapshot: complete deterministic S4 slice through Stage 10, shared S1–S4 harness contract (#32), and Issue #33 as the next dependency-ready evaluation gate.
- [[project-status-2026-09-05]] — Historical snapshot: Issue #10 complete, verified baseline, branch divergence, and the Issue #11 plan/approval gate.
- [[architecture-v1-rage-kg-2026]] — **Frozen Architecture V1 and Implementation V1 contract**, derived from the exact final RAGE-KG 2026 submission (`submission/rage-kg-2026`, commit `59b2796`).
- [[implementation-decisions]] — Append-only Implementation V1 decision and Architecture V1 deviation record, including the shared immutable S1–S4 evaluation-record contract, the versioned anomaly-triage query set with a required manifest dataset digest, the RQ-mapped deterministic metric suite, deterministic service-backed retrieval; versioned SOP chunk/index planning; stable evidence/point identity; and validation, repair, evidence-package, and provenance contracts; plus the S4, S1, S3, and S2 strategy registrations with their capability boundaries, the blinded independent gold-annotation boundary for reviewer-flagged label bias, and the 2026-11-06 scope revision that leaves the two-annotator requirement unmet while shipping a digest-pinned, explicitly non-independent synthetic reference; plus the 2026-11-07 abstention suite that measures, from harness evaluation records, correct, wrong-reason, and false-answer trap outcomes plus over-abstention per strategy, with capability-gated refusal recall; and the 2026-11-09 correction of the free local deployment envelope after running it live — Ollama's in-container bind, read-only Fuseki configuration seeding instead of a mount the image rewrites, Compose's nulled image CMD under an `entrypoint` override, one `deploy/.env` shared by Compose and the CLI, endpoints derived from published ports, a cold-pull timeout separate from readiness, and a transport that refuses redirects; plus the review-driven clarification that a Qdrant collection's identity is its width and distance, and that loopback publication excludes remote hosts but not other local processes.
- [[project-status-2026-07-20]] — Historical pre-submission snapshot: validated RAGE-KG 2026 candidate, V1/V2 comparison, 12-page CEUR-ART build, author metadata, figure work, and then-current branch/PR state.
- [[project-status-2026-06-22]] — Prior status snapshot: thesis/wiki progress, concept-paper artifacts, lint results, venue path, and next actions.
- [[thesis-pitch]] — Master thesis pitch v2 summary (problem, RQs, S1–S4, evaluation, timeline).
- [[mfg-agentgraph]] — The proposed system: architecture, stack, deliverables.
- [[research-questions]] — RQ1 (methods), RQ2 (ontology), RQ3 (provenance/trust), RQ4 (local deployment).

## Method strategies (RQ1)

- [[strategy-comparison]] — Side-by-side matrix of S1–S4.
- [[naive-rag]] — S1 baseline: vector retrieval only, no KG.
- [[graphrag]] — S2 baseline: Microsoft GraphRAG, LLM-built community-summary graph.
- [[og-rag]] — S3 baseline: expert-ontology-grounded retrieval (verified mechanism: ontology-mapped factual blocks → hypergraph → greedy minimal-hyperedge context).
- [[kg-agent-s4]] — S4 proposed: SPARQL agent + SHACL + PROV-O.

## Ontology and standards (RQ2)

- [[ssn-sosa]] — W3C sensor/observation vocabulary.
- [[shacl-validation]] — Constraint validation and self-correction loop.
- [[prov-o]] — Provenance for AI agents (RQ3 also).

## Evaluation (RQ1)

- [[ragas-metrics]] — RAGAS framework: faithfulness, answer relevance, context precision/recall, noise sensitivity, Nvidia metrics, agent evaluation.
- [[faithfulness]] — Specific construct definition.
- [[groundedness]] — Specific construct definition.

## Manufacturing domain

- [[mimii-dataset]] — Public industrial machine sound dataset.
- [[anomaly-triage]] — The primary scenario (pump station case).

## Infrastructure (RQ4)

- [[local-deployment]] — Docker, Ollama, vLLM, llama.cpp.
- [[langgraph-agent]] — Agent framework.
- [[fuseki-triplestore]] — Apache Jena Fuseki SPARQL store (TDB2, Docker, SHACL on-demand).

## Alternative RAG paradigms

- [[pageindex]] — Vectorless, reasoning-based RAG via hierarchical tree indexing + LLM tree search (VectifyAI, 2025). 98.7% on FinanceBench. Potential hybrid complement or comparison baseline.

## Bibliography

- [[references-master]] — Consolidated master reference collection: research papers, surveys, journals, conference papers, books, standards, GitHub repos, web articles, videos, podcasts.

## Wiki maintenance

- [[wiki-health]] — Automated structural health report for page format, RQ tags, wikilinks, index coverage, and stale pages. Structural review on 2026-11-09 found no defects; age-only warnings remain for content review.

## Supporting concepts and aliases

- [[think-on-graph-2]] — Placeholder for pending correct ToG 2.0 source; resolves legacy backlinks.
- [[reasoning-on-graphs-rog-2024]] — Alias page pointing to canonical [[reasoning-on-graphs]].
- [[bm25-dpr]] — Retrieval baseline concepts for sparse and dense retrieval.

## Additional source summaries

- [[graphrag-survey-peng2024]] — Survey of GraphRAG methods and graph-augmented retrieval; useful for positioning S2/S3/S4.
- [[kag-knowledge-augmented-generation-2024]] — Knowledge-Augmented Generation framing for combining LLMs with structured knowledge.
- [[fidelis-faithful-kg-reasoning-2024]] — Faithful KG reasoning precedent for grounded path reasoning.
- [[graph-constrained-reasoning-2024]] — Graph-constrained reasoning source relevant to S4 path constraints.
- [[rag-beyond-external-data-2024]] — RAG beyond external documents; useful for memory/tool/agentic retrieval framing.
- [[rag-architectures-robustness-survey-2025]] — Survey of robust RAG architectures and failure modes.
- [[rag-evaluation-llm-era-survey-2025]] — Survey of RAG evaluation in the LLM era; complements [[ragas-metrics]].
- [[llm-agent-methodology-survey-2025]] — Survey of LLM agent methodology; supports agent architecture choices.
- [[multi-agent-collaboration-mechanisms-survey-2025]] — Multi-agent collaboration mechanisms and trade-offs.
- [[react-yao2023]] — ReAct reasoning-acting paradigm; background for tool-using agents.
- [[ontology-llm-accuracy-sparql-qa-2024]] — Ontology and SPARQL QA accuracy; relevant to RQ2/RQ4.
- [[llms-for-manufacturing-survey-2024]] — Manufacturing-domain LLM survey; frames the industrial setting.
- [[llms-for-information-retrieval-survey-2023]] — LLMs for IR survey; background for retriever/reranker/reader pipelines.
- [[fraud-detection-ml-2025]] — Explicitly marked non-thesis-relevant mislabeled source retained for provenance.

## Source summaries

- [[rag-comprehensive-survey-2024]] — Gupta, Ranjan, Singh 2024 (arXiv:2410.12837). RAG landscape; canonical retriever/generator decomposition; recent variants.
- [[og-rag-2024]] — Sharma, Kumar & Li 2024 (arXiv:2412.15235, Microsoft Research preprint). OG-RAG method and evaluation detail; records the pitch's "Soman et al., EMNLP 2025" attribution as a source discrepancy.
- [[graphrag-microsoft-2024]] — Edge et al. 2024 (arXiv:2404.16130). Microsoft GraphRAG: Leiden communities + map-reduce community summaries for global sensemaking; the S2 method paper.
- [[unifying-llms-kgs]] — Pan et al. 2024 (IEEE TKDE, arXiv:2306.08302). The three-paradigm taxonomy paper (KG-enhanced LLMs / LLM-augmented KGs / Synergized) that anchors the thesis's literature positioning; places S4 in Synergized / LLMs-as-Agents Reasoning.
- [[reasoning-on-graphs]] — Luo et al., ICLR 2024 (arXiv:2310.01061). RoG: planning-retrieval-reasoning framework with KG-grounded relation paths as faithful plans; the S4 plan-as-relation-path basis. Plug-and-play planner (Table 3) shows the planner's value transfers to unmodified LLMs — defends S4's "no fine-tuning" choice.
- [[think-on-graph]] — Sun et al., ICLR 2024 (arXiv:2307.07697). ToG: introduces the "LLM ⊗ KG" tight-coupling paradigm — LLM as iterative agent over the KG via Search + Prune beam search, training-free, plug-and-play across LLMs. **The most direct S4 precedent**; supplies the prompts, SPARQL templates, and complexity analysis S4 inherits. Llama2-70B + ToG ≥ GPT-4 + CoT in some scenarios — empirical anchor for RQ4.
- [[prov-agent-souza2025]] — Souza et al., IEEE e-Science 2025 (arXiv:2508.02866). PROV-AGENT: W3C PROV extension for agentic workflows; concrete subclasses (`AIAgent`, `AgentTool`, `AIModelInvocation`, `Prompt`, `AIModel`, `ResponseData`) integrated via MCP. Self-described **first** provenance framework for agentic workflows. Resolves [NEEDS VERIFICATION] in [[prov-o]]. Five operator-trust queries adopted verbatim as RQ3 user-study test items.
- [[sosa-ssn-2018]] — Janowicz et al., *J. Web Semantics* 2018 (arXiv:1805.09979). The peer-reviewed reference for **SOSA**, the lightweight (13 classes, 21 properties, `ALI(D)`) W3C/OGC core ontology for sensors/observations/samples/actuators. Direct PROV-O alignment composes cleanly with PROV-AGENT. Resolves [NEEDS VERIFICATION] in [[ssn-sosa]]. Thesis-recommended adoption: SOSA core + PROV-O alignment, skip DUL/OBOE/full-SSN.
- [[multi-agent-systems-survey-2024b]] — Chen et al. 2024 (HIT, arXiv:2412.17481). Survey of 125 LLM-MAS papers (∗ACL/NeurIPS/AAAI/ICLR 2023-24); three-aspect taxonomy (task-solving / simulation / evaluation). Value to thesis is positional: §6.2 "efficiency explosion" is the citation justifying single-agent S4; §2.1 seven-component agent decomposition (LLM/Profile/Reasoning/Memory + Rules/Tools/Intervention) maps onto the LangGraph design; §3.1 self-refine family is the structural family S4's SHACL loop belongs to.
- [[agentigraph-2025]] — Zhao et al., CIKM 2025 (arXiv:2508.02999). AGENTiGraph: the **closest published architectural precedent** for MFG-AgentGraph — multi-agent KG-LLM system with 7 specialised agents targeting non-technical users. Same positioning but no SHACL, no PROV-O, no domain ontology. Llama-3.1-8b + agent ≥ GPT-4o zero-shot — second empirical anchor for RQ4 after ToG.
- [[beyond-chain-of-thought-2024]] — Xia et al. 2024 (arXiv:2404.15676). Generalises CoT to Chain-of-X (CoX); two-axis taxonomy (nodes × tasks) places S4 as Chain-of-Augmentation (KG retrievals) + Chain-of-Feedback (SHACL self-feedback). Table 1 lists ToG as S4's closest KG-based neighbour.
- [[kg-construction-llm-survey-2024]] — Bian 2025 (arXiv:2510.20345). Three-layer KG construction pipeline (Ontology Engineering → Knowledge Extraction → Knowledge Fusion). §6.4 "KGs beyond RAG" is the cleanest one-paragraph framing of S4. §6.2 "Dynamic Knowledge Memory" supports PROV-O memory design.
- [[llms-meet-kgs-qa-survey-2025]] — Ma et al., EDBT 2025 (arXiv:2505.20099). Three-role KG taxonomy (Background Knowledge / Reasoning Guidelines / Refiners and Validators). S4 is a hybrid inhabiting all three roles. AnsQ/RetQ/ReaQ evaluation triple extends RAGAS. §5 lightweight-validator opportunity is the published framing of SHACL self-correction.
- [[multi-agent-llm-survey-2024]] — Guo et al. 2024 (arXiv:2402.01680). Predecessor MAS survey; adds sharper communication-structure taxonomy, profile-method taxonomy, and feedback-source taxonomy. SHACL = Environment feedback in Guo's classification.
- [[understanding-planning-llm-agents-2024]] — Huang et al. 2024 (arXiv:2402.02716). Five-direction planning taxonomy; External Planner-Aided is the precedent paradigm for LLM + SHACL. §5.3 "combination of statistical AI with LLM is a major future trend" — direct citation supporting S4's design.

