# PROV-O — Provenance for AI Agents

**Summary**: W3C Recommendation for representing provenance (who did what, when, with what data) as RDF. Used in MFG-AgentGraph to record an audit trail for every agent decision, supporting RQ3 (operator trust) and EU AI Act / GDPR Article 22 transparency requirements.

**Sources**: `thesis-pitch-v2.md` §2.3, §6 step 6; `raw/w3c-prov-o-spec.md`; `raw/w3c-prov-primer.md`; `raw/PROV_AGENT_Provenance_AI_Agents_2025.pdf` (**verified — see [[prov-agent-souza2025]]**). W3C specs themselves still [NEEDS VERIFICATION].

**Last updated**: 2026-04-27.

**Thesis relevance**: RQ3 (primary), RQ2.

---

## What it is

W3C Recommendation that defines an RDF/OWL vocabulary for describing provenance: `prov:Activity`, `prov:Entity`, `prov:Agent`, plus relations like `prov:wasGeneratedBy`, `prov:used`, `prov:wasAttributedTo`. (source: thesis-pitch-v2.md §7)

## Use in MFG-AgentGraph

Every agent run produces a PROV-O activity record stored back into the [[fuseki-triplestore|Fuseki]] KG, with:

- Data sources used (Fuseki graph URI, Qdrant collection).
- Model identifier (e.g., `llama3.2:3b`) and embedding model.
- Tools invoked (`sparql_query`, `vector_search`, `shacl_validate`).
- Timestamps.

(source: thesis-pitch-v2.md §6 step 6, §10)

## Why it matters for the thesis

- **Audit trail at the triple level** — directly supports EU AI Act transparency requirements and GDPR Article 22 right-to-explanation (cited as KGAudit 2024 in the pitch). (source: thesis-pitch-v2.md §2.3)
- **RQ3 hypothesis H4:** structured provenance + SHACL report should improve operator-perceived explainability and trust (Likert ≥ 4, SUS ≥ 68) compared to an equivalent agent without the structured evidence package. (source: thesis-pitch-v2.md §9.4)
- **Triple-level granularity** — every claim in S4's response can be traced to its evidence; this is what S1–S3 cannot do.

## Peer-reviewed basis

- **[[prov-agent-souza2025|PROV-AGENT]]** (Souza et al., IEEE e-Science 2025, arXiv:2508.02866) — **verified**. The first provenance framework specifically designed for agentic workflows. Defines concrete PROV subclasses (`AIAgent`, `AgentTool`, `AIModelInvocation`, `Prompt`, `AIModel`, `ResponseData`, `DomainData`/`SchedulingData`/`TelemetryData`), uses standard PROV relationships throughout (no new vocabulary), built on Model Context Protocol (MCP). Open-source impl: Flowcept (`github.com/ORNL/flowcept`). **S4's PROV-O record is fully expressible in PROV-AGENT vocabulary** plus one new subclass (`ValidationReport` for SHACL outputs).
- Dibowski 2024 (FOIS) — PROV-O for AI agent audit trails. Cited in pitch §5.4; not in `raw/`.
- Lavrinovics et al. 2025 (Journal of Web Semantics) — KG audit framework. Cited in pitch §5.4; not in `raw/`.

(source: thesis-pitch-v2.md §5.4; arXiv:2508.02866)

## The five operator-trust queries from PROV-AGENT (RQ3 spine)

PROV-AGENT §IV.B identifies five canonical queries enabled by an agentic-provenance graph. **These should appear verbatim in the thesis RQ3 evaluation** — they are the user-study questions:

1. **Q1**: Given an agent decision, what was the complete lineage until the first input data?
2. **Q2**: For iteration N, what was the agent decision, the available options, and the reasoning?
3. **Q3**: What was the LLM prompt and response when a *surprising* agent decision was identified? (the hallucination-debugging query)
4. **Q4**: How did an agent decision influence subsequent workflow activities?
5. **Q5**: Where did erroneous data originate, and how did it propagate?

(source: arXiv:2508.02866 §IV.B)

## Gap relative to Pan 2024 roadmap (additive contribution)

The [[unifying-llms-kgs|Pan 2024 roadmap]] discusses interpretability extensively (§4.4 KG-enhanced LLM Interpretability — KGs for LLM probing and analysis) but **does not cover provenance / audit trails at all**. Pan's interpretability framing is "use KGs to understand what an LLM knows", whereas PROV-O is "record what the agent did, with what inputs, when". These are orthogonal — one is static knowledge probing, the other is dynamic action auditing.

**This means the thesis's PROV-O contribution is genuinely additive vs. the cited literature spine.** Worth flagging in the contributions chapter as a gap the thesis fills relative to the canonical taxonomy paper. (source: Pan2024 §4.4 omission)

## Resolved: what PROV-AGENT proposes beyond stock PROV-O

After ingest of [[prov-agent-souza2025]]: PROV-AGENT introduces **concrete subclasses** for agentic concepts (`AIAgent`, `AgentTool`, `AIModelInvocation`, `Prompt`, `AIModel`, `ResponseData`) but uses **standard PROV relationships** (`used`, `wasGeneratedBy`, `wasAttributedTo`, `wasInformedBy`, `wasAssociatedWith`) — no new vocabulary. The contribution is the *taxonomy* and the MCP-integration pattern, not a new RDF vocabulary. S4 should adopt this taxonomy directly and add **one** new subclass (`ValidationReport`) for SHACL outputs.

The `wasInformedBy` edge from `AgentTool` → `AIModelInvocation` is the key wiring that captures "this tool's logic depended on what the model said" — distinct from `used`, which is reserved for entities. (source: arXiv:2508.02866 §III)

## Open questions for ingest

- PROV-STAR / extensions referenced in the literature index — which features are worth adopting?
- What SHACL shapes should validate that the PROV-O record is complete (e.g., every `AgentTool` activity must have a `wasAssociatedWith` edge to an `AIAgent`)?
- How is the provenance presented in the operator UI without overwhelming them? PROV-AGENT uses a Streamlit chat interface (Fig. 5B) — usable as a UI baseline, but a force-directed graph view may be more direct for operators.

## Related pages

- [[prov-agent-souza2025]]
- [[shacl-validation]]
- [[kg-agent-s4]]
- [[research-questions]]
- [[fuseki-triplestore]]
- [[unifying-llms-kgs]]
