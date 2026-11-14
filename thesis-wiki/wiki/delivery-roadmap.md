# Delivery roadmap — free local application, measurement, and demonstration

**Summary**: Dependency-ordered plan to finish the deliverable the thesis actually needs: a free-only
local implementation of the concept-paper architecture, a working backend and interface, a controlled
S1–S4 benchmark with reproducible artifacts, and a packaged demonstration. It supersedes the ordering
in [[evaluation-roadmap]] for everything after the strategy registrations.

**Sources**: Delivery audit of 2026-11-07 at integration commit `380197b`; frozen baseline
[[architecture-v1-rage-kg-2026]]; `concept-paper/publication/rage-kg-2026/manuscript.md` (frozen at
`59b2796`); GitHub issues #113–#133; existing issues #33–#54, #75–#83.

**Last updated**: 2026-11-08.

**Thesis relevance**: RQ1 / RQ2 / RQ3 / RQ4.

---

## Goal restated

Build the concept paper's architecture as a runnable local system, measure the four strategies
honestly, and demonstrate both through an interface — with no paid services, so a student can run,
reproduce and defend it.

## Verified state at `380197b`

| Capability | Reality |
|---|---|
| Ten-stage S4 pipeline | Implemented and orchestrated, but every retrieval/generation stage is a deterministic fixture; provenance is a callback; repair runs with `retry_budget=0` |
| S1 / S2 / S3 / S4 harness arms | Registered and unit-tested as deterministic substitutes, not the paper's methods |
| Fuseki / Qdrant / Ollama adapters | Implemented and unit-tested, but wired into nothing |
| Embeddings | Absent — vectors are caller-supplied (`caller_supplied`), no text→vector path |
| Dataset | 30 queries over one asset, one SOP sentence, one KG edge; no independent annotation |
| Reference labels | Digest-pinned, explicitly non-independent synthetic reference |
| Batch runner / results | Absent — no driver, no persisted artifact, no measured latency/memory |
| API / UI / deployment | Absent — no server, routes, frontend, compose file or bootstrap |
| Acceptance checklist | Two stale strict xfails still mark undelivered behaviour |

The demonstration today is `mfg-agentgraph-demo`: ten fixture stages, a canned recommendation, an
in-memory trace.

## Two tracks, one roadmap

The frozen paper specifies a study at a scale and human-evidence bar that the current repository cannot
supply: one asset, one SOP sentence, one KG edge, 30 queries, an author-derived reference, and no
participants. The roadmap therefore separates two named tracks and forbids silent substitution (issue
`#113`, protocol `implementation-study-protocol-v1`):

- **Track A — original-method study**: ~50 documents, four MIMII machine types, 10^4–10^5-style
  triples, ≥100 held-out questions, two independent annotators with agreement and adjudication before
  scoring.
- **Track B — limited student feasibility study**: explicitly fixture/synthetic context, no
  topical-breadth, industrial decision-quality, independent-gold or trust claims.

Both tracks share the same pipeline, artifacts and interface. Only the corpus, labels and admissible
claims differ.

## Serial order (one issue finished before the next starts)

Scheduling clarification (2026-11-08): finish the core backend and evaluation components before
building the UI. The local judge (`#123`) therefore precedes the API (`#124`) and UI (`#125`);
this is a scheduling choice, not a new architectural dependency. Human studies and final
end-to-end checks still follow their required inputs.

| # | Issue | Work | Depends on |
|---|---|---|---|
| 1 | `#113` | Freeze the study protocol, licence manifest, RQ3 crosswalk, two-track scope | — |
| 2 | `#114` | Local service substrate: compose, healthchecks, volumes, preflight | `#113` |
| 3 | `#115` | Versioned corpus + development split, with MIMII-vs-synthetic lineage | `#113`, `#114` |
| 4 | `#116` | Remove Pump_12-only assumptions from evidence contracts | `#113`, `#115` |
| 5 | `#117` | Real local embeddings for corpus and query retrieval | `#114`, `#115`, `#116` |
| 6 | `#131` | Measure and freeze the hardware envelope (or record RQ4 unmet) | `#114`, `#117` |
| 7 | `#130` | Shared local model invocation contract | `#114`, `#115` |
| 8 | `#118` | Live model-backed S4 with real bounded repair and durable provenance | `#114`, `#117`, `#116`, `#130`, `#131` |
| 9 | `#119` | Model-backed vector+LLM S1 | `#117`, `#116`, `#130` |
| 10 | `#120` | Model-backed ontology-grounded S3 | `#117`, `#116`, `#130`, `#119` |
| 11 | `#121` | S2 with local LLM extraction, communities and query-time generation parity | `#114`, `#115`, `#130`, `#119` |
| 12 | `#133` | Run-artifact bundle, catalog and offline replay | `#113` |
| 13 | `#122` | Batch runner, measured runs and stage-correlated resource sampling | `#118`–`#121`, `#133` |
| 14 | `#123` | Pinned local judge with preregistered calibration | `#122`, `#133`, `#130`, `#113` |
| 15 | `#124` | FastAPI service over the shared execution path | `#118`, `#133` |
| 16 | `#125` | Operator and results interface | `#124`, `#133` |
| 17 | `#48` | **Re-scoped pre-pilot** live failure/release gate across runner, API and UI | `#122`, `#124`, `#125`, `#123` |
| 18 | `#39` | Development pilot and go/no-go (no label-dependent held-out scores) | strategy + app + gate rows above |
| 19 | `#40` | Held-out benchmark, per protocol track | `#39`, and `#126` for label-dependent claims |
| 20 | `#41`, `#43`, `#45`, `#44`, `#47`, `#46`, `#42` | Analyses, ablations, profiling, provenance audit | `#40` |
| 21 | `#127` | Exploratory expert auditability review | `#125`, `#40`, `#46` |
| 22 | `#49`–`#53` | Ontology gaps, failure synthesis, RQ4 synthesis, V2 delta, thesis tables | analyses |
| 23 | `#129` | Packaged cold-start demonstration | `#125`, `#114`, `#53` |
| 24 | `#54` | Reproducibility and threats-to-validity audit **of the delivered package** | `#129`, `#53` |

Independent, schedulable any time after their inputs exist: `#126` (independent annotation, after
`#132`), `#132` (blinded held-out packet, after `#115`), `#128` (acceptance-test honesty, after the
owning runnable paths), `#75`, `#77`, `#78`, `#82`, `#83`.

## Interface and evidence contract

- `#133` defines what a run bundle contains: raw records, metrics, aggregates, SHACL report graph,
  support graph, provenance trace, repair history, stage-correlated resource samples, and environment
  identity digests.
- `#124` and `#125` read those bundles; they never recompute metrics or fabricate values.
- `#129` ships the cold-start package, including the fixture data the demo needs (the wheel currently
  ships only `src/mfg_agentgraph`, so packaging must change).

## Prohibited claims until their gate lands

| Claim | Gate |
|---|---|
| "S1 is vector RAG / any arm uses an LLM" | `#119`–`#121`, `#130` |
| "S4 is the deployed local KG-agent" | `#118` |
| Any latency, throughput, memory or stage-cost number | `#122`, `#133`, `#131` |
| Faithfulness / answer relevance figures | `#123` |
| Independent gold labels or inter-annotator agreement | `#126` |
| Operator trust, usability, safety or field effectiveness | `#127` measures auditability only; trust study unmet |
| Topical breadth or global sensemaking from one scenario | Track A corpus `#115`, `#132` |
| "Reproducible" before a cold-start package exists | `#129`, then `#54` |

## Status of the pre-existing evaluation order

[[evaluation-roadmap]] remains a correct record of how the strategy registrations were sequenced
(`#38` → `#35` → `#76` → `#37` → `#36` → `#79` → `#80`). Its measurement phase is superseded: `#39`
and `#40` are blocked until the rows above land, `#48` moves before the pilot, and `#54` moves after
the packaged demonstration.

## Related pages

- [[evaluation-roadmap]]
- [[architecture-v1-rage-kg-2026]]
- [[implementation-decisions]]
- [[research-questions]]
- [[local-deployment]]
- [[project-status-2026-11-05]]
