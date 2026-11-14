# Evaluation roadmap — S1–S4 execution order

**Summary**: Dependency-ordered sequence for the remaining Implementation V1 evaluation issues, decided 2026-11-05/06 after Issues #31–#34 were integrated. Sequencing follows the GitHub dependency sections plus two review-driven gaps (#79, #80) that must land before measured results are claimed.

**Sources**: GitHub Issues #35–#54, #75–#83; `docs/implementation-v1-issue-workflow.md`; [[architecture-v1-rage-kg-2026]]; [[implementation-decisions]]; [[project-status-2026-11-05]].

**Last updated**: 2026-11-06.

**Thesis relevance**: RQ1 / RQ2 / RQ3 / RQ4.

**Status (2026-11-07)**: historical for its measurement phase. The strategy-registration order below is
what actually happened. [[delivery-roadmap]] now governs sequencing: `#39`/`#40` are blocked until the
live methods, embeddings, hardware envelope, artifact runner, interface and local judge exist; the
failure gate `#48` moves before the pilot; and `#54` moves after the packaged demonstration. This page
is kept for the dependency reasoning recorded at the time.

---

## Why this order

Three rules decide the sequence:

1. **Nothing measured before it is comparable.** A strategy registration may land as soon as the harness (#32), query set (#33) and metrics (#34) exist; a benchmark may not start until all four strategies run through the same path.
2. **Bias and abstention are measured, not assumed.** Reviewers flagged author-derived gold labels (#79) and missing abstention evaluation (#80); both must be in place before the pilot and benchmark, or the results are attackable on validity grounds.
3. **Cheap proof first.** The S4 registration (#38) is the smallest runnable strategy because the deterministic vertical slice already exists; it proves the harness → dataset → metrics triple end to end before four baselines are built.

## Phase 1 — runnable strategies

| Order | Issue | Work | Why here |
| --- | --- | --- | --- |
| 1 | #38 | Register S4 KG-Agent in the shared harness | Needs only the vertical slice + harness; validates the dataset/metric path with existing code |
| 2 | #35 | S1 naive RAG baseline | Simplest baseline; first cross-strategy contrast |
| 3 | #76 | Ingest OG-RAG (S3 method paper) | Research gate for the S3 design; high priority |
| 4 | #37 | S3 ontology-grounded RAG | Needs the OG-RAG method understanding from #76 |
| 5 | #36 | S2 GraphRAG-style baseline | Medium priority; independent of #37 beyond shared adapters |

## Phase 2 — validity and coverage before measurement

| Order | Issue | Work | Why here |
| --- | --- | --- | --- |
| 6 | #79 | Reference-label scope: **revised 2026-11-06** from independent human gold to a synthetic reference (≥2 annotators remains unmet) | Reviewer-flagged label bias. Independent human annotation is unavailable (single non-expert author), so the branch ships a digest-pinned, explicitly non-independent reference instead and records the limitation; it does **not** clear the bias objection |
| 7 | #80 | Abstention / unanswerable-query suite | Reviewer-suggested; measures fail-closed behavior instead of assuming it |

## Phase 3 — measurement

| Order | Issue | Work | Why here |
| --- | --- | --- | --- |
| 8 | #39 | 5-query S1–S4 pilot and go/no-go | Gate before spending a full benchmark |
| 9 | #40 | Full 30-query controlled benchmark | Every later analysis depends on it |

## Phase 4 — analysis (all need #40)

| Order | Issue | Work | Note |
| --- | --- | --- | --- |
| 10 | #41 | Results by query type and strategy boundary | Frames every later analysis |
| 11 | #43 | S4 no-repair ablation | Must precede #45 |
| 12 | #45 | Repair-budget sensitivity | Needs #43 |
| 13 | #44 | KG-only, vector-only, hybrid ablation | Retrieval attribution |
| 14 | #47 | Latency, memory, per-stage profiling | RQ4 |
| 15 | #46 | Provenance completeness and evidence-package usefulness | RQ3 |
| 16 | #42 | S2 global-sensemaking sub-evaluation | Needs the S2 baseline |
| 17 | #48 | Failure-mode and fail-closed stress test | Pairs with #80 |

## Phase 5 — synthesis

| Order | Issue | Work |
| --- | --- | --- |
| 18 | #49 | Ontology and SHACL coverage gaps |
| 19 | #50 | Prompt and generation failure synthesis |
| 20 | #51 | RQ4 local-deployment viability |
| 21 | #52 | Architecture V2 candidate delta matrix |
| 22 | #53 | Thesis-ready tables, figures, validity notes |
| 23 | #54 | Reproducibility and threats-to-validity audit |

## Independent work (no experiment dependency)

| Issue | Work | Placement |
| --- | --- | --- |
| #75 | Ingest ToG 2.0 and resolve `[NEEDS VERIFICATION]` citations | Any time; strengthens S4 positioning |
| #77 | Ingest KG-Agent (arXiv:2402.11163) as direct S4 precedent | Any time |
| #78 | Add SAREF/SAREF4INMA source | Before #49/#52 so the ontology choice is defensible |
| #82 | Windows/Python 3.12 CI leg, Ruff S/PTH rules | Low-risk filler |
| #83 | Consolidate divergent branches and manuscript copies | Low-risk filler; needs an inventory first |

## Rules that do not change with the order

- One short-lived branch and one focused PR per issue; never stack an unintegrated branch.
- Plan comment and explicit approval before any tracked edit.
- `finish` gates: pytest (≥90% branch), Ruff, strict mypy, zizmor, wiki health, repository quality, raw-source and journal-privacy checks.
- The private journal records each issue; the tracked wiki records only public-safe decisions.

## Related pages

- [[project-status-2026-11-05]]
- [[architecture-v1-rage-kg-2026]]
- [[implementation-decisions]]
- [[research-questions]]
