# Project status — 2026-11-05

**Summary**: Implementation V1 has a complete deterministic S4 vertical slice through Stage 10 persistence and the shared S1–S4 evaluation-harness contract. The evaluation milestone is next; Issue #33 (anomaly-triage dataset governance and query set) is the dependency-ready gate for the metric suite, pilot, and benchmark.

**Sources**: Live Git/GitHub state checked 2026-11-05 (HEAD `7bb2f4c`, branch `feat/implementation-v1` in sync with origin, no open PRs); GitHub Issues #31, #32 closed, #33–#54 open; `src/mfg_agentgraph/`; `docs/implementation-v1-issue-workflow.md`.

**Last updated**: 2026-11-05.

**Thesis relevance**: RQ1 / RQ2 / RQ3 / RQ4.

---

## Completed and verified

**S4 vertical slice (deterministic, fail-closed)** — all ten Architecture V1 stages are implemented and integrated on `feat/implementation-v1`:

- request/run identity (#10), terminal states and stage instrumentation (#11), evidence identifiers (#12), candidate-action JSON boundary (#13), entity resolver (#14);
- SHACL validation loop and RDF action mapping (#22, #72, #74), bounded repair, ten-stage orchestrator (#23), fail-closed acceptance tests (#24), demo CLI (#25);
- service adapters: Fuseki/SPARQL structured retrieval (#27), Qdrant procedural retrieval (#28), SOP chunking and indexing (#29), fail-closed Ollama adapter (#30), durable Fuseki PROV-O persistence (#31).

**Evaluation infrastructure** — Issue #32 added the shared immutable S1–S4 record contract in `src/mfg_agentgraph/evaluation_harness.py`: controlled strategy configuration, run manifest, raw output, typed errors, canonical JSON, and explicit artifact applicability (`present` / `not_applicable`). This is R6 comparability infrastructure only — no dataset, metrics, strategy implementations, or results exist yet.

**Fixtures** — `tests/fixtures/pump_12`, `sop`, `fuseki`, `qdrant`. There is no query dataset and no metric implementation in the repository.

## Live state

- Branch `feat/implementation-v1` at `7bb2f4c`, equal to `origin/feat/implementation-v1`; working tree clean except today's automated wiki-health refresh (`wiki/log.md`, `wiki/wiki-health.md`).
- No open pull requests.
- Wiki inconsistency: this page and `wiki/index.md` supersede the 2026-09-05 status page, which still names Issue #11 as next.

## Next unit of work

Superseded on 2026-11-06: Issues #33 and #34 are integrated (`15c86d6`, `6ee628c`). The next unit per [[evaluation-roadmap]] is **Issue #38 — register S4 KG-Agent in the shared harness**, followed by #35, #76, #37, #36, #79, #80, #39, #40.

**Issue #33 — anomaly-triage dataset governance and query set** (`type:experiment`, priority high, size M).

It defines stable query IDs and categories, expected evidence/gold labels, a dataset card with leakage notes, a dataset version/hash recorded in run manifests, and trap cases (unsupported/unsafe requests). It unblocks #34 (metric suite), #36 (S2 baseline), and every experiment from #39 onward. Plan comment and explicit approval are required before any tracked edit.

Dependency-ready in parallel once #33 lands: #35 (S1 naive RAG; needs only harness + Qdrant adapter, already available), #38 (register S4 KG-Agent; needs only the vertical slice + harness), #37 (S3; needs Fuseki + Qdrant adapters). They remain one-issue-at-a-time by workflow rule.

## Remaining evaluation chain

| Issue | Work | Depends on |
| --- | --- | --- |
| #33 | dataset governance and query set | #32 (done) |
| #34 | RQ metric suite + evaluator fixtures | #33 |
| #35 | S1 naive RAG baseline | #32, Qdrant adapter (available) |
| #36 | S2 GraphRAG-style baseline | #33 |
| #37 | S3 ontology-grounded baseline | #32, adapters (available) |
| #38 | register S4 strategy | #32, vertical slice (done) |
| #39 | 5-query S1–S4 pilot, go/no-go | #33–#38 |
| #40 | full 30-query benchmark | #39 |
| #41–#48 | per-type analysis, ablations, failure stress, latency, provenance audit, repair budget, ontology gaps, failure synthesis | #40 |
| #49–#54 | RQ synthesis, Architecture V2 delta, thesis tables/figures, threats to validity | experiments |

Independent research backlog (no code dependency): #76 OG-RAG ingest (high), #75 ToG 2.0 ingest and citation resolution (high), #77 KG-Agent precedent, #78 SAREF/SAREF4INMA, #79 independent human gold annotation (high; aligns with #33 artifacts), #80 abstention/unanswerable suite (needs #33 + #34). Low-priority chores: #82 Windows CI leg, #83 branch/manuscript consolidation.

## Related pages

- [[architecture-v1-rage-kg-2026]]
- [[implementation-decisions]]
- [[project-status-2026-09-05]]
- [[research-questions]]
