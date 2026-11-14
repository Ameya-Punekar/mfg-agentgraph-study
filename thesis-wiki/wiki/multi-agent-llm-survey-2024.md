# LLM-MA Survey (Guo et al. 2024)

**Summary**: Predecessor LLM-MA survey to [[multi-agent-systems-survey-2024b|Chen et al. HIT 2024]]. Organises the field around four dimensions — Agents-Environment Interface, Agents Profiling, Agents Communication, Capabilities Acquisition — rather than the three-aspect application taxonomy that Chen et al. later adopt. **High overlap** with the HIT survey; ingested for completeness and for two finer-grained taxonomies (profile-method and feedback-source) that Chen et al. omit.

**Sources**: `raw/Multi_Agent_LLM_Survey_2024.pdf` (Guo, Chen, Wang, Chang, Pei, Chawla, Wiest, Zhang — Notre Dame + KAUST + SUSTech + UMass Boston, arXiv:2402.01680v2, 19 Apr 2024).

**Last updated**: 2026-05-04.

**Thesis relevance**: RQ1 (related-work breadth — *positional, duplicative with Chen et al. 2024*).

---

## Why this is a short page

[[multi-agent-systems-survey-2024b|Chen et al. 2024]] §1 names Guo et al. 2024 as the prior work whose framework they extend. The two surveys cover the same 100+ paper corpus from different organising principles. This page records only what Guo et al. **add** beyond Chen et al.; the central single-agent-justification argument lives in [[multi-agent-systems-survey-2024b]].

## What Guo et al. 2024 add over Chen et al. 2024

### (1) Sharper communication-structure taxonomy (Fig. 3)

Four typical structures for inter-agent communication:

| Structure | Pattern | Example |
|---|---|---|
| **Layered** | Hierarchical, agents at each level interact within or with adjacent layers | DyLAN — dynamic LLM-Agent Network with inference-time agent selection |
| **Decentralised** | Peer-to-peer, agents directly communicate with each other | Common in world-simulation applications |
| **Centralised** | Central agent (or group) coordinates communication; others interact via this hub | — |
| **Shared Message Pool** | Agents publish messages and subscribe to relevant ones based on profiles | MetaGPT — improves efficiency by avoiding broadcast |

(source: arXiv:2402.01680 §3.3, Fig. 3)

**Thesis use**: irrelevant for single-agent S4. If a future ablation introduces a planner+validator two-agent setup (per [[multi-agent-systems-survey-2024b]] open question), the **Shared Message Pool** is the lowest-overhead structure for two agents that both need access to the [[fuseki-triplestore]] subgraph and SHACL report.

### (2) Profile-method taxonomy (§3.2)

Three methods for defining agent profiles:

| Method | Mechanism | Thesis applicability |
|---|---|---|
| **Pre-defined** | Profiles explicitly defined by system designer | **What thesis uses** — hand-authored SOP-derived role prompt |
| **Model-Generated** | Profiles created by an LLM | Could be used to bootstrap multiple operator personas for RQ3 user-study mock data |
| **Data-Derived** | Profiles constructed from pre-existing datasets | E.g. from real operator logs — out of scope |

(source: arXiv:2402.01680 §3.2, Table 1)

This taxonomy is **finer than Chen et al.'s "Profile" component description** and worth citing when the thesis architecture chapter explains the role-prompt design choice.

### (3) Feedback-source taxonomy (§3.4)

Four sources of feedback that drive agent capability acquisition:

| Source | What it is | S4 mapping |
|---|---|---|
| **Environment** | Real or simulated environment outputs (e.g. code interpreter, sensor reading) | **SHACL validation report ≈ Environment feedback** (deterministic engine return) |
| **Agent interaction** | Judgements from other agents | Not used (single-agent) |
| **Human** | Operator override, correction, RLHF | Operator-escalation step in [[anomaly-triage]] |
| **None** | No feedback (analysis-only simulation) | Not applicable |

(source: arXiv:2402.01680 §3.4)

**Thesis claim made cleaner**: S4's SHACL self-correction loop is **single-agent + Environment feedback** — the deterministic-validator special case of Guo's Environment-feedback class. This is the third independent placement of S4's SHACL loop after Chen et al. §3.1 self-refine and Huang et al. §6 reflection-and-refinement. Each survey lands on a slightly different framing; cite all three for breadth in the thesis related-work chapter.

## Three named open-source frameworks (§5.1)

Guo et al. flag three frameworks that recur across the surveyed papers:

| Framework | Distinguishing trait | Relevance |
|---|---|---|
| **MetaGPT** (Hong et al. 2023) | Encodes SOPs into role prompts for software-development agents (CTO/PM/coder) | **Closest naming-pattern precedent** for thesis SOP-as-role-prompt design |
| **CAMEL** (Li et al. 2023b) | "Inception prompting" for autonomous role-play cooperation | Out of scope |
| **AutoGen** (Wu et al. 2023a) | Customisable agents via natural language + code | LangGraph alternative if LangChain stack proves limiting; both are MIT-licensed |

(source: arXiv:2402.01680 §5.1)

## Challenges (§6) — same as Chen et al., re-confirmed

§6 lists six open challenges:
1. Multi-modal environment — same as [[understanding-planning-llm-agents-2024]] §9
2. Hallucination — with **cascading effect** (Chen et al. call this "accumulative effect")
3. Acquiring collective intelligence
4. **Scaling up** — computational complexity per agent (= Chen et al.'s "efficiency explosion")
5. Evaluation and benchmarks
6. Applications and beyond

(source: arXiv:2402.01680 §6)

The two key citations for thesis defensibility (single-agent justification: efficiency + cascading hallucination) are present in both surveys; the Chen et al. 2024 quotes are sharper.

## Open questions raised — none that aren't already in Chen et al.

This survey did not raise new thesis-relevant questions beyond what [[multi-agent-systems-survey-2024b]] already captured.

## Related pages

- [[multi-agent-systems-survey-2024b]] — successor survey; primary single-agent-justification citation
- [[langgraph-agent]] — Pre-defined profile method anchors role-prompt design
- [[shacl-validation]] — Environment-feedback class anchors deterministic-validator framing
- [[anomaly-triage]] — Human feedback class anchors operator-escalation step
