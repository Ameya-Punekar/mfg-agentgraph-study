# MFG-AgentGraph

**A recommendation an operator can check before acting on it.**

At 14:03 a pump station starts making an unusual noise. An operator asks: *what should I inspect
first, and why?* A general-purpose language model answers fluently, but fluency is not
accountability. The operator still needs to know which machine the advice is for, which observation
triggered it, which procedure supports it, whether the action is even valid for that asset, and how
the answer was put together.

MFG-AgentGraph is my master's thesis research on that gap. The design rule is blunt: **a
recommendation must be machine-checkable and evidence-backed before a person acts on it.**
This repository is the software that implements the rule.

---

## Why this repository is public

I built the project inside a private repository. It holds research material that cannot be
published: working copies of third-party manuals and papers that were never cleared for
redistribution, unfinished drafts under review, and my own development journal. Opening that
repository would have leaked all of it.

So I did the boring, correct thing instead of the quick one. I built a reviewed snapshot — the
code, tests, documentation and evaluation artifacts that are mine to share — and published that.
The working repository stays private. The snapshot is what a reviewer needs to judge the engineering:
it runs, it is tested, and it says plainly what is finished and what is not.

The short version: **showing your work should not mean publishing other people's.** If you want the
longer story, [`PROCESS.md`](PROCESS.md) describes how the work was actually carried out — the
planning, the review gates, the failures and the corrections.

## The problem

Manufacturing anomaly triage is a decision problem with consequences. When an unexpected sound,
vibration or reading appears, someone has to choose the next inspection step, and the cost of being
wrong is a wasted shift or a damaged machine. A language model can produce a convincing checklist in
seconds. It cannot tell you that the checklist is about the *wrong pump*, or that no procedure
supports the third step, or where any of it came from.

Three requirements follow:

- **Grounding.** The answer has to be attached to a specific asset, sensor and observation, not to a
  mood.
- **Validity.** The proposed action has to satisfy domain rules the operator can inspect and, if
  necessary, contest.
- **Traceability.** The system has to show which documents, graph statements and model calls produced
  the recommendation.

Most retrieval-augmented systems do the first badly and skip the other two.

## What I built

A ten-stage pipeline that treats those three requirements as gates rather than aspirations:

1. **Resolve** the request to a known asset and sensor in the knowledge graph.
2. **Retrieve twice** — SPARQL over an SSN/SOSA-aligned RDF graph for structured facts, and vector
   search over procedure text for procedural context.
3. **Generate** candidate actions as strict JSON. By design the model may only *select* among
   retrieved identifiers; it never invents one.
4. **Validate** the candidate with SHACL after converting it to RDF. If it fails, the violation
   report goes back to the model as a repair signal under a bounded retry budget. If the budget runs
   out, the system says so — it asks the operator, or returns *insufficient evidence*. It does not
   show an unvalidated recommendation.
5. **Assemble** an evidence package — target asset, supporting graph statements, document citations,
   validation status — and write a PROV-O trace of the activities, prompts, model and retrieved
   resources behind it.

If you want to evaluate what was built rather than read a description:

| Start here | Why |
|---|---|
| `uv run mfg-agentgraph-demo` | Runs the whole pipeline and prints all ten stage outcomes |
| `src/mfg_agentgraph/shacl_validation.py`, `bounded_repair.py` | The validation gate and its repair loop |
| `src/mfg_agentgraph/provenance.py`, `fuseki_provenance_store.py` | The audit trail, and how it is persisted |
| `src/mfg_agentgraph/pump12_orchestrator.py` | The composition of everything above |
| `tests/` | The behaviour the system is actually held to |
| [`THIRD_PARTY.md`](THIRD_PARTY.md) | Where every quoted document came from, and under what terms |

### One deliberate limit

Passing the gate means the recommendation satisfies the SHACL constraints encoded here and that the
pipeline produced the evidence and provenance those constraints demand. It does **not** mean the
advice is true, correct, optimal or safe. A shape checks an encoding, not reality. Being explicit
about that line is the point — an operator tool that overstates its own guarantees is worse than no
tool.

## Current progress

**Working today**

- The ten-stage pipeline, orchestrated end to end.
- The SHACL gate, the bounded repair controller, and the explicit fallback states.
- The evidence package and the deterministic PROV-O trace, with a Fuseki persistence adapter.
- All four comparison arms (S1 naive RAG, S2 GraphRAG-style, S3 ontology-grounded, S4 agent) on one
  immutable, digest-bound run record.
- A pinned local stack — Fuseki 6.2.0, Qdrant 1.19.2, Ollama 0.23.2 — with `bootstrap`/`doctor`
  preflight, verified against the real images.
- A versioned scenario corpus: 49 document artifacts across 48 families, 528 source-located chunks,
  8 assets, 1,604 observations, 19,521 triples, all digest-pinned and rebuildable.
- **2,215 passing tests at 92.3% coverage**, against a 90% floor enforced in CI.

**Still being built**

- Model-backed strategies and repair against a live local runtime. The demo runs on a deterministic
  fixture, and says so in its own output.
- The batch runner and the measured, comparable benchmark.
- The service API and the operator interface.
- The held-out query packet and independent annotation.

The ordering, the dependencies and the claims each milestone unlocks are in
[`thesis-wiki/wiki/delivery-roadmap.md`](thesis-wiki/wiki/delivery-roadmap.md).

## Try it

```bash
uv sync --locked
uv run mfg-agentgraph-demo
```

```text
MFG-AgentGraph deterministic S4 demo
terminal_status: passed
recommendation: Inspect the pump inlet of Pump_12 for cavitation
evidence_package_id: ex:EvidencePackage_Pump12_001
provenance_id: ex:ProvenanceTrace_Pump12_001
stages:
01. entity_asset_resolution: passed
...
10. prov_o_trace_writing: passed
```

Verify the frozen corpus without any service:

```bash
uv run mfg-agentgraph-corpus verify evaluation/scenario-corpus-v4/corpus-v4.json
```

**What the demo does not show.** It makes no network, model, Fuseki or Qdrant call, and the trace is
kept in memory rather than persisted. Corpus values are synthetic scenario readings, not
measurements. What it proves is that the composition works and that release is all-or-nothing — not
that the recommendation is good.

## How I work

The process matters more than any single file, so it is written down rather than implied:

- **One issue at a time, plan before code.** Every change starts with a written plan naming the
  files, the test strategy, the alternatives considered and the rollback, and it waits for approval.
  Silence is not approval.
- **Test first.** A failing behaviour test, then the smallest change that passes it.
- **Deterministic by default.** Unit tests never touch the network. Live services are exercised by
  gated integration tests that *fail* rather than skip when unconfigured, because a skipped
  integration test is a claim nobody checked.
- **Contracts carry their identity.** Query sets, runs, corpus releases and manifests carry SHA-256
  digests that are re-verified on load; a digest mismatch is a refusal, not a warning.
- **Shortfalls are recorded, not smoothed over.** When I could not meet a requirement — an
  independent two-annotator gold set, for example — the artifact says so in its own metadata and the
  affected metrics report *not applicable* with a reason. No metric is invented to fill a table.
- **Research notes are linted, not just kept.** The wiki holding the literature review, the decision
  record and the derivation records is checked structurally by `scripts/wiki_health.py`, so broken
  links and drift are caught by a command rather than by memory.

Details: [`PROCESS.md`](PROCESS.md), [`docs/engineering-standards.md`](docs/engineering-standards.md),
and [`thesis-wiki/wiki/implementation-decisions.md`](thesis-wiki/wiki/implementation-decisions.md).

## Research basis

> Faizan Ali, Ameya Punekar, Juergen Bock. *MFG-AgentGraph: SHACL-Validated and PROV-O-Traceable LLM
> Agents for Manufacturing Anomaly Triage.* RAGE-KG 2026 (co-located with ISWC 2026), Bari, Italy.
> [Paper (PDF)](https://2026.rage-kg.org/papers/2026/paper19.pdf) · CC BY 4.0

The paper is the framework half: it specifies the architecture and a falsifiable four-strategy
protocol, and reports a 32-query pilot. Its proof-of-concept artifact is a **different** repository —
[`faizan8201/mfg-agentgraph`](https://github.com/faizan8201/mfg-agentgraph), archived at
[doi:10.5281/zenodo.22083418](https://doi.org/10.5281/zenodo.22083418). This repository is the
companion implementation study: turning that specification into tested software and measuring it.

The thesis is organised around four questions:

| RQ | Question | Where it lives |
|---|---|---|
| RQ1 | How do the four retrieval strategies compare on answer quality? | `thesis-wiki/wiki/strategy-comparison.md` |
| RQ2 | Does ontology grounding plus SHACL validation catch invalid recommendations? | `thesis-wiki/wiki/shacl-validation.md` |
| RQ3 | Does provenance make a recommendation auditable to an engineer? | `thesis-wiki/wiki/prov-o.md` |
| RQ4 | Can any of it run inside a factory network on free hardware? | `thesis-wiki/wiki/local-deployment.md` |

## Technical reference

The component contracts — evaluation harness, annotation boundary, metric suite, retrieval adapters,
SHACL report format, repair policy, evidence package and provenance writer — are in
[`docs/implementation-reference.md`](docs/implementation-reference.md).

## Licence and third-party material

The code, tests and author-written documentation here are © the authors, and **no open-source licence
is offered**; rights are reserved. The published paper is separately available under CC BY 4.0.

The corpus quotes 49 third-party documents. Each keeps its own licence — CC0, CC BY-SA, CC BY-NC-SA,
GPL-3.0, OGL, US federal works, and bespoke permissions — recorded per document with the source's own
wording in [`THIRD_PARTY.md`](THIRD_PARTY.md), with copyleft texts in [`LICENSES/`](LICENSES). If you
want to reuse an excerpt, its licence governs, not this repository's notice.

Deliberately **absent**: source PDFs and their full-text conversions, institutional templates,
credentials, unpublished drafts, reviewer correspondence, and the private issue history.
