# SHACL Validation

**Summary**: Shapes Constraint Language — a W3C Recommendation for validating RDF graphs against shape constraints. In MFG-AgentGraph, SHACL is the gate of the S4 self-correction loop and the hard contract that prevents "explainability theater".

**Sources**: `thesis-pitch-v2.md` §2.3, §6 step 4, §10, §14; `raw/w3c-shacl-spec.md`. W3C spec [NEEDS VERIFICATION] — not yet ingested.

**Last updated**: 2026-05-04.

**Thesis relevance**: RQ2 (primary).

---

## What it is

W3C Recommendation defining a language for describing constraints (shapes) that an RDF graph must satisfy. A SHACL validator (e.g., `pyshacl`) reports per-shape pass/fail and a structured validation report. (source: thesis-pitch-v2.md §7)

## Use in MFG-AgentGraph

Inside the S4 [[langgraph-agent|LangGraph]] agent loop:

1. The LLM proposes an action plan with a candidate evidence package.
2. SHACL shapes validate the plan: e.g., every action must reference a real `sosa:FeatureOfInterest`; maintenance steps must follow defined ordering constraints.
3. If validation fails, the agent self-corrects — queries the KG for missing information and regenerates.
4. If validation passes, the SHACL report becomes part of the evidence package returned to the operator.

(source: thesis-pitch-v2.md §6 step 4)

## Why it matters for the thesis

- **Hard contract:** SHACL rejects plans without asset references — this is the structural defense against fluent-but-ungrounded LLM output ("explainability theater"). (source: thesis-pitch-v2.md §10, §14)
- **Measurable RQ2 metrics:** SHACL pass rate, % plans that needed self-correction, ontology coverage — all fall directly out of the validation report. See [[research-questions|RQ2]].
- **Hypothesis H3:** the thesis predicts SHACL self-correction fires on >30% of initially invalid plans — establishing measurable safety value. (source: thesis-pitch-v2.md §9.4)

## Peer-reviewed precedent

SHACL has been used for FMEA graph validation and manufacturing digital twins (cited as DigitalTwinKG 2025 in the pitch). (source: thesis-pitch-v2.md §2.3)

## Anchor in the Pan 2024 roadmap

§7.1 of [[unifying-llms-kgs|Pan 2024]] *KGs for Hallucination Detection in LLMs* argues that *"in order to gain the public's trust and border applications, it is imperative to detect and assess instances of hallucination in LLMs ... existing methods strive to detect hallucination by training a neural classifier on a small set of documents, which are neither robust nor powerful to handle ever-growing LLMs. Recently, researchers try to use KGs as an external source to validate LLMs."* (source: Pan2024 §7.1)

SHACL is the **structural** instantiation of this future direction: instead of training a neural hallucination classifier, S4 uses ontology-defined shapes to reject ungrounded plans. The thesis can frame the SHACL self-correction loop as a concrete answer to Pan §7.1 — useful for the related-work / contributions chapter.

## External-Planner-Aided framing (Huang et al. 2024)

[[understanding-planning-llm-agents-2024|Huang et al. 2024]] §5 places LLM+P (PDDL/Fast-Downward), LLM+PDDL (LPG), LLM+ASP (CLINGO) in a single family — **External Planner-Aided** — where the LLM works alongside a deterministic symbolic planner. **SHACL in S4 inhabits this family**, but inverts the direction: in LLM+P the LLM formalises the task and the symbolic planner synthesises the plan; in S4 the LLM synthesises the SPARQL plan + answer and the symbolic engine (SHACL) **validates** it.

§5.3 closes the section with: "The advantages brought by symbolic systems include theoretical completeness, stability, and interpretability. The combination of statistical AI with LLM is poised to become a major trend." §9 elevates this to a future-direction recommendation: "**Connecting LLM with symbolic planning models without altering LLM itself is a promising future direction.**" Both quotes are direct citations supporting the thesis's no-fine-tuning + symbolic-validator design. (source: arXiv:2402.02716 §5.3, §9)

## Tooling

- `pyshacl` (Apache-2.0) — Python SHACL validator. (source: thesis-pitch-v2.md §7)
- Apache Jena Fuseki supports SHACL inference natively. (source: thesis-pitch-v2.md §7)

## Open questions for ingest

- What shapes should the minimal manufacturing ontology include for the thesis (Phase 1, Week 4 deliverable)?
- How are SHACL violations best reported back to the LLM for self-correction (text? JSON? structured tool output)?
- What SHACL features (SPARQL-based constraints, inference) are needed beyond the core?

## Related pages

- [[ssn-sosa]]
- [[kg-agent-s4]]
- [[fuseki-triplestore]]
- [[unifying-llms-kgs]]
- [[research-questions]]
- [[understanding-planning-llm-agents-2024]]
- [[beyond-chain-of-thought-2024]]
