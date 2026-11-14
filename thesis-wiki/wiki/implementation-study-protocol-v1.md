# Implementation study protocol — v1

**Summary**: The versioned, free-only contract that fixes what the implementation study will run and what it may claim, before any result is collected. It names two study tracks (the frozen paper-scale study and a limited student feasibility study) so neither can be silently substituted for the other.

**Sources**: `concept-paper/publication/rage-kg-2026/manuscript.md` (frozen at `59b2796`, §4); [[research-questions]]; [[architecture-v1-rage-kg-2026]]; [[delivery-roadmap]]; GitHub issue #113.

**Last updated**: 2026-11-07.

**Thesis relevance**: RQ1 / RQ2 / RQ3 / RQ4.

---

## Protocol identity

- **Protocol ID**: `implementation-study-protocol-v1`
- **Frozen**: 2026-11-07
- **Status**: proposed and approved for issue #113; the first block in the delivery order.
- **Rule**: no result artifact may cite a protocol version other than the one its run was executed under. A change that alters scope, dataset, metrics, labels, or deployment is a new protocol version and a new approval.

## Two tracks, one pipeline

The frozen paper specifies a study whose scale and human-evidence bar exceed what a single student can currently supply. The protocol therefore freezes **two named tracks**; a result must state which track produced it.

### Track A — original-method study (paper scale)

- ~50 SOP/manual documents across four MIMII machine types (pumps, fans, sliders, valves).
- A knowledge graph on the order of 10^4–10^5 triples with multiple asset instances per machine type.
- ≥100 held-out queries across the five difficulty tiers in the frozen paper (single-hop facts, multi-hop paths, action plans, contrastive, provenance).
- Gold first-inspection actions authored by **two independent domain annotators** working from the SOP corpus, with inter-annotator agreement reported and disagreements adjudicated **before** held-out scoring.
- Admissible claims: the full RQ1–RQ4 comparison with gold-label accuracy, and the operator-trust/auditability study only if actually executed.
- **Freeze gate**: Track A cannot be declared complete, or its held-out scores reported, by running the 30-query single-asset fixture set or by promoting the author-derived synthetic reference to gold.

### Track B — limited student feasibility study (current capability)

- Corpus is the frozen fixture scenario (one asset, one SOP sentence, one KG support edge) and 30 behavioural queries — explicitly fixture/synthetic.
- Reference is `synthetic-reference-v2`: 26 `fixture_anchored`, 4 `not_applicable`, `independent_annotation: false`, no IAA.
- Admissible claims: scenario-level software conformance, mechanism demonstration, fail-closed and abstention-status behaviour. This is what the deterministic arms and demo currently support.
- **Prohibited claims**: topical breadth, industrial decision quality, independent-gold validation, operator trust, safety or field effectiveness, any latency/memory value before the measured envelope exists.

A run's manifest records which track it belongs to and the corpus, split and reference digests it binds.

## Deployment envelope

The paper fixes the deployment so the strategy is the only variable. The protocol distinguishes what is fixed now from what is measured later.

**Fixed by this protocol (candidate identities and licences, subject to the `#131` envelope gate):**

| Component | Version / identity | Licence |
|---|---|---|
| KG store | Apache Jena Fuseki 6.2.0 (`jena-6.2.0`) | Apache-2.0 (one BSD-style bundled component) |
| Vector store | Qdrant 1.19.2 (`v1.19.2`) | Apache-2.0 |
| Model runtime | Ollama 0.23.2 (`v0.23.2`, observed installed) | MIT |
| Generation model | `qwen2.5:7b-instruct-q4_K_M` (Qwen2.5-7B-Instruct, Apache-2.0); registry manifest digest `sha256:845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e`, model layer `sha256:2bada8a7450677000f678be90653b85d364de7db25eb5ea54136ada5f3933730` (4.68 GB); runtime verification frozen by `#131` | Apache-2.0 |
| Embedding model | `nomic-embed-text` v1.5, 137M F16 (Apache-2.0); installed digest `0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f` | Apache-2.0 |
| MIMII audio source | Zenodo record 3384388, Hitachi Ltd., CC BY-SA 4.0 | CC BY-SA 4.0 |

**Not fixed yet — measured by `#131` before the pilot.** The observed workstation (Linux 6.6, WSL2; RTX 5070 Laptop 8151 MiB; 23.5 GiB RAM) is recorded for planning only. The installed `qwen3:1.7b` is **not** evidence for the paper's 7–13B assumption. The envelope gate must select and freeze a feasible generation model, quantisation, context and output limits, or record RQ4 as unmet. No latency, memory, throughput or model-suitability claim may be made until that gate lands.

The paper holds context length, output length and retrieval top-k fixed without stating values. Those
three parameters are therefore selected together with the model by the `#131` envelope gate and
recorded verbatim in every run manifest; until then no strategy may treat any value as frozen.

## Executable strategy definitions

Each strategy shares one corpus, one query set, one local deployment envelope and one scoring path. Where a registered arm is currently a deterministic substitute, that is stated, and the substitute must not be reported as the method.

| Strategy | Executable definition (paper) | Current registered arm |
|---|---|---|
| S1 | Vector retrieval over the corpus + local LLM answer generation; no KG, SHACL, repair or provenance | Lexical token-coverage + extractive sentence — **test fixture only** |
| S2 | Local-LLM graph extraction + a declared community-detection algorithm + LLM community summaries + map-reduce answering, with indexing cost reported separately | Term claims + connected components + extractive summaries — **test fixture only** |
| S3 | Ontology-mapped factual blocks/hyperedges + hybrid KG/document retrieval + local generation; post-hoc SHACL is diagnostic, non-gating | Hand-built blocks over the fixture + fixture candidate generator — **test fixture only** |
| S4 | Full architecture: entity resolution, hybrid retrieval, local generation, SHACL gate, bounded repair, evidence package, PROV-O trace | Fixture retrievers + fixture candidate + `retry_budget=0` + callback provenance — **test fixture only** |

Cross-cutting rules:

- Model access for every arm goes through the shared invocation contract (`#130`); no arm owns a private model client, prompt, or fallback.
- S1/S3/S4 share the same query-time generator, prompt/output schema, decoder settings and retrieval budget; S2 answers with the same query-time generator and reports its build-time extraction/summarisation model and cost separately.
- Every strategy output is recorded through the shared harness record; validation and provenance fields are `not_applicable` with a reason where the strategy has no gate or trace.

## Data scope and lineage

- **MIMII supplies acoustic events only** — not an asset hierarchy, maintenance history, SOP corpus, or validated KG (frozen paper §4). The benchmark combines MIMII-derived events with authored synthetic context.
- Every dataset element must be labelled **MIMII-derived** or **authored/curated**, with per-record lineage (source recording/label/version, transformation/detector identity, generation rules) and attribution. The synthetic-context schema and generation rules are published so acoustic-event grounding is separable from plant decision-support performance.
- Results must be described as **"MIMII-event-grounded synthetic-context" evaluation**, never as MIMII maintenance decision support.
- Leakage prevention: the synthetic KG and SOP corpus are authored before and independently of any strategy output, and frozen before S1–S4 run; no strategy is tuned against the split it is scored on.
- Held-out integrity: references are produced only by `#126` from a blinded packet (`#132`) that carries no gold evidence, action or rubric. Run manifests bind corpus, split and reference digests; a run whose selection/prompt/index tuning touched the held-out split is invalid.

## Human evidence

| Requirement | Owner | Status |
|---|---|---|
| Two independent domain annotators, IAA reported, disagreements adjudicated before scoring | `#126` | **Unmet** — the synthetic reference is not gold and never substitutes |
| Blinded held-out packet without references | `#132` | Planned |
| Exploratory expert auditability review (5–10 domain engineers, provenance-query tasks) | `#127` | **Unmet** — no participants exist; unavailable reviewers are recorded as unmet |

The RQ3 crosswalk is explicit: the executable study measures **provenance/auditability task performance only**. The original operator-trust/usability study (SUS, Likert, interviews) remains unmet, and no operational, safety, or clinical conclusion follows from the auditability result.

## Metrics and claims

Deterministic metrics are computed by the existing metric suite; judge metrics by `#123`; unavailable values carry a reason, never a fabricated number.

| Class | Metrics | Notes |
|---|---|---|
| Deterministic | `hits_at_any`, `evidence_support_coverage`, `evidence_citation_precision`, `answer_action_exact_match`, `answer_action_token_f1` (over the 12 queries with an expected action), `terminal_status_match`; S4-only: `initial_shacl_pass`, `final_shacl_pass`, `repair_iterations`, `repair_succeeded_after_failure`, `provenance_completeness` | Anchored against `synthetic-reference-v2` with its `scope` and `original_requirement_status` reported verbatim |
| Judge-derived | RAGAS faithfulness, answer relevancy, context precision/recall | Pin model/prompt/seed; preregister a calibration set disjoint from the scored split; descriptive only until the human-label gate (`#126`) is met; reported beside, never as the headline, gold accuracy |
| Not-applicable | Latency, throughput, memory, build-cost | Until `#122`/`#133`/`#131` measure them |
| Prohibited | Topical breadth from one scenario; independent-gold; operator trust/safety/effectiveness; "S1 is vector RAG" before `#119`; "S4 is the deployed KG-agent" before `#118`; reproducibility before a cold-start package exists | Each has a named gate in [[delivery-roadmap]] |

## Reproducibility and artifact contract

- `#133` defines the run bundle: raw records, metrics, aggregates, SHACL report graph, support graph, provenance trace, repair history, stage-correlated resource samples, and environment identity digests. API and UI read the bundle; they never recompute metrics.
- Offline replay must reproduce stored aggregates from raw artifacts, or report the mismatch.
- Failure is a first-class result: SHACL rejections, repair failures, incomplete traces and envelope violations are reported, not suppressed.

## Licence and terms manifest

| Item | Licence | Redistribution | Network |
|---|---|---|---|
| MIMII (Zenodo 3384388) | CC BY-SA 4.0 (Hitachi Ltd.) | Share-alike; attribute | bootstrap download |
| Qwen2.5-7B-Instruct | Apache-2.0 | Permitted | bootstrap pull |
| nomic-embed-text v1.5 | Apache-2.0 | Permitted | bootstrap pull |
| Apache Jena Fuseki | Apache-2.0 | Permitted | bootstrap pull |
| Qdrant | Apache-2.0 | Permitted | bootstrap pull |
| Ollama | MIT | Permitted | bootstrap pull |

A mandatory paid account, cloud endpoint, or incompatible licence blocks freeze. The full per-package manifest (frontend and API dependencies included) is completed by `#114`, `#115`, `#117`, `#124`, `#130` and verified again in the `#54` audit.

## Related pages

- [[delivery-roadmap]]
- [[evaluation-roadmap]]
- [[research-questions]]
- [[architecture-v1-rage-kg-2026]]
- [[implementation-decisions]]
- [[local-deployment]]
- [[mimii-dataset]]
