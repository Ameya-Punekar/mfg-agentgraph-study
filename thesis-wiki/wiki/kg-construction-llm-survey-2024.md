# LLM-Empowered KG Construction Survey (Bian 2025)

**Summary**: Survey of LLM-driven knowledge graph construction across the classical three-layer pipeline — **Ontology Engineering → Knowledge Extraction → Knowledge Fusion**. Provides the taxonomy that situates the thesis's mostly-curated SSN/SOSA-grounded KG (top-down ontology + schema-based extraction). §6.4 ("KGs beyond RAG") and §6.2 ("Dynamic Knowledge Memory for Agentic Systems") supply direct framings for S4's KG-as-cognitive-substrate role.

**Sources**: `raw/KG_Construction_from_Text_LLM_Survey_2024.pdf` (Bian — Xidian University, conference paper at ICAIS 2025, arXiv:2510.20345v1, 23 Oct 2025).

**Last updated**: 2026-05-04.

**Thesis relevance**: RQ2 (ontology engineering pattern + schema-based extraction precedents), RQ3 (KG-as-agent-memory pattern), RQ4 (none direct).

---

## The three-layer pipeline (§2)

Bian organises the field around the classical KG-construction pipeline (source: arXiv:2510.20345 §2):

| Layer | What it does | Pre-LLM tooling | LLM-era shift |
|---|---|---|---|
| **Ontology Engineering** | Formal specification of concepts, relationships, constraints | Protégé, METHONTOLOGY, On-To-Knowledge | LLMs as ontology co-modellers (top-down) or schema-inducers (bottom-up) |
| **Knowledge Extraction** | Identify entities, relations, attributes from text | BiLSTM-CRF, Transformer-based RE | Schema-based vs. schema-free LLM extraction |
| **Knowledge Fusion** | Integrate heterogeneous sources, resolve duplication/conflict | Lexical/embedding entity alignment | Schema-level, instance-level, hybrid LLM fusion |

(source: arXiv:2510.20345 §2.1-§2.3, Fig. 1)

## Where MFG-AgentGraph sits in the taxonomy

| Layer | Bian's sub-paradigm | Thesis choice | Closest precedent |
|---|---|---|---|
| Ontology Engineering | **Top-down (LLMs as Ontology Assistants)** — CQ-based (Ontogenia, CQbyCQ) or NL-based (LLMs4OL, NeOn-GPT, LLMs4Life) | Top-down: hand-authored SSN/SOSA + manufacturing ontology, **optionally** assisted by CQ-based LLM prompts at ontology-design time | NeOn-GPT (Fathallah et al. 2025, ESWC), LLMs4Life for life-sciences |
| Knowledge Extraction | **Schema-based / Static** — ontology fixed, LLM populates ABox under strict supervision | Static schema-driven extraction from SOPs and maintenance records into SSN/SOSA + asset ontology | **Kommineni et al. 2024**, **Feng et al. 2024** (ontology-grounded two-step extraction), **KARMA** (Lu & Wang 2025, multi-agent schema-guided) |
| Knowledge Fusion | **Schema-level: Ontology-driven consistency** | Manual canonical concept set; minimal cross-source fusion (single ontology) | Kommineni 2024 (schema-level alignment) |

(source: arXiv:2510.20345 §3.1, §4.1.1, §5.1)

The thesis is **not** doing autonomous LLM ontology induction (bottom-up GraphRAG/OntoRAG/EDC/AutoSchemaKG style) — that path conflicts with the [[ssn-sosa]] commitment to a peer-reviewed core ontology. Bian's taxonomy lets the thesis state the choice explicitly: "we adopt the top-down + static-schema-based combination, the most semantically conservative cell of Bian's taxonomy."

## §6.4 KGs beyond RAG — the cleanest framing for S4

> "Beyond their use as retrieval backbones in RAG systems, Knowledge Graphs (KGs) are increasingly envisioned as a **cognitive middle layer** bridging raw input and LLM reasoning. In this paradigm, KGs provide a structured scaffold for **querying, planning, and decision-making**, enabling more interpretable and grounded generation. Recent studies illustrate this shift. CogER formulates recommendation as cognition-aware KG reasoning... PKG-LLM employs domain KGs for knowledge augmentation and predictive modeling in mental health diagnostics." (source: arXiv:2510.20345 §6.4)

**This is the cleanest one-paragraph framing of S4 in the literature**: S4 treats the KG not as a document store (S1 [[naive-rag]]) or community-summary index ([[graphrag|S2]]) but as the cognitive substrate over which the agent plans, retrieves, validates, and explains. Cite §6.4 in the thesis introduction to position MFG-AgentGraph against pure-RAG baselines.

## §6.2 Dynamic Knowledge Memory for Agentic Systems — direct support for thesis PROV-O memory

> "Achieving autonomy in LLM-powered agents requires overcoming the limits of finite context windows through **persistent, structured memory**. Recent architectures envision the knowledge graph (KG) as a **dynamic memory substrate**, evolving continuously with agent interactions rather than storing static histories. Frameworks such as **A-MEM** (Xu et al. 2025) model memory as interconnected 'notes' enriched with contextual metadata, enabling continual reorganization and growth. Similarly, **Zep** (Rasmussen et al. 2025) employs a **temporal knowledge graph (TKG)** to manage fact validity and support time-aware reasoning and updates." (source: arXiv:2510.20345 §6.2)

Maps directly to the thesis [[fuseki-triplestore]] + [[prov-o]] design — Fuseki holds the static SSN/SOSA-typed observation history, PROV-O records the agent's per-run interactions. **Zep's temporal KG pattern is worth chasing** as a related-work reference for time-stamped sensor observations and PROV provenance.

Also confirms (independent of [[understanding-planning-llm-agents-2024|Huang et al. 2024]] §7) that **KG-as-RAG-memory** is the recognised future direction for agent memory — fourth independent placement of the thesis's design.

## §6.3 Multimodal KG construction — flagged for MIMII future work

Bian §6.3 mentions VaLiK (Liu et al. 2025, Vision-aligned-to-Language integrated KG) and KG-MRI (Lu et al. 2024) for multimodal KG construction. The thesis currently flattens MIMII audio → text features (already noted in [[understanding-planning-llm-agents-2024]] and [[beyond-chain-of-thought-2024]] open questions). VaLiK is the named precedent if the thesis ever extends to direct audio→KG construction. (source: arXiv:2510.20345 §6.3)

## Schema-based KE precedents worth chasing

For the thesis's SOP/maintenance-record → SSN/SOSA ABox extraction (Phase 1-2 deliverable), Bian flags four named precedents:

| Method | What it does | Thesis applicability |
|---|---|---|
| **Kommineni et al. 2024** | LLM generates CQs, builds TBox, then performs ABox population under strict schema supervision | **Closest match** — full-pipeline schema-based extraction with CQ scoping |
| **KARMA** (Lu & Wang 2025) | Multi-agent architecture; specialist agents handle entity normalisation, relation classification under fixed ontological boundary | If thesis ever splits the agent into planner+extractor+normaliser, this is the precedent |
| **Feng et al. 2024** | Two-step "ontology-grounded extraction" — first generate domain-specific ontology from text, then extract RDF triples directively | Useful if thesis needs to backfill missing ontology classes from SOP corpus |
| **ODKE+** (Khorshidi et al. 2025) | Ontology snippets — dynamically selected ontology subsets to construct context-aware prompts per entity | Efficiency lever for the thesis if context-window pressure on the local LLM becomes a bottleneck |

(source: arXiv:2510.20345 §4.1.1, §4.1.2)

## Pull-quotes worth saving

> "KGs provide a structured scaffold for querying, planning, and decision-making, enabling more interpretable and grounded generation." (source: arXiv:2510.20345 §6.4)

> "Recent architectures envision the knowledge graph (KG) as a dynamic memory substrate, evolving continuously with agent interactions rather than storing static histories." (source: arXiv:2510.20345 §6.2)

> "The focus evolves from 'LLMs for Ontology Engineering' to 'Ontologies and KGs for LLMs'. Whereas the top-down trajectory emphasises semantic modelling, logical consistency, and expert-guided alignment ... the bottom-up trajectory prioritises automatic extraction, schema induction, and dynamic evolution." (source: arXiv:2510.20345 §3.2)

## Open questions raised

1. **CQ-based LLM-assisted ontology refinement** — could the thesis use Ontogenia or CQbyCQ to validate the manually-authored manufacturing ontology against a generated CQ set? Cheap pre-Phase-1 sanity check.
2. **Zep TKG vs. PROV-O** — Zep's temporal-KG architecture handles fact validity; the thesis uses PROV-O timestamps. Worth comparing whether a time-aware KG layer adds anything beyond PROV.
3. **Bian §6.4 cited as the literature framing for S4** — should be the lead reference in the introduction's "what is MFG-AgentGraph" paragraph.

## Related pages

- [[mfg-agentgraph]] — §6.4 "cognitive middle layer" is the literature framing for the system
- [[ssn-sosa]] — top-down ontology engineering choice; Bian §3.1 puts this in "LLMs as Ontology Assistants"
- [[shacl-validation]] — ontology-driven consistency in Bian's §5.1 schema-level fusion
- [[fuseki-triplestore]], [[prov-o]] — KG-as-agent-memory framing from §6.2
- [[graphrag-microsoft-2024]] — Bian places GraphRAG in bottom-up ontology induction; thesis takes the opposite (top-down) path
- [[understanding-planning-llm-agents-2024]] — independent placement of KG-as-memory pattern
