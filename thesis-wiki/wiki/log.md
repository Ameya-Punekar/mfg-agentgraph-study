# Wiki Operations Log

Append-only record of ingest, edits, and audits. Newest entries at the top.

---
## 2026-11-01 — Issue #31 Fuseki provenance M4 callback/live-proof boundary

- Added Stage 10 contract tests that pass the actual `FusekiProvenanceStore.persist` bound method unchanged, verify both stable IDs only after update/readback, and prove update/readback failures block IDs and trace evidence with `PROVENANCE_FAILED_CLOSED`.
- Added the non-default-collected, explicitly invoked `tests/integration/live_fuseki_provenance.py` proof with dedicated loopback endpoint/graph/trace variables, empty preflight, one persist, exact fresh-graph readback, exact canonical cleanup only after confirmed ownership, and post-cleanup emptiness verification. No live service was run, so no live proof is claimed.
- Documented the adapter contract and command in `README.md`; recorded the R5/Stage-10, RQ3-primary decision with R1/RQ4 deployment context and RQ1 reproducibility-only scope. Navigation, `thesis-wiki/raw/`, frozen architecture, dependencies, defaults, and signatures are unchanged; M4 full gate remains pending.

---

## 2026-10-31 — Issue #30 local Ollama model-adapter proof

- Added the explicit standard-library Ollama `/api/chat` adapter and a separately invoked, non-collected live proof for the canonical Pump_12 Stage 4 path.
- Added behavior-focused tests for import purity, sanitized missing configuration/result failure, exact one-call success, and filename collection boundaries; retained the fixture adapter as the default and kept runtime/model claims opt-in.
- Recorded the Issue #30 R1/R4/RQ4 decision with pending final validation/review evidence. Navigation is unchanged, `thesis-wiki/raw/` and the generated wiki-health report are unchanged.

- Corrected the Issue #30 wire schema after a real Ollama grammar-compilation failure: omitted string `maxLength` keywords while preserving schema structure and local fail-closed byte/character limits. Updated the README and implementation decision; no live service rerun was performed.
- Corrected the Issue #30 response boundary after a real HTTP 200 Ollama response used pretty-printed candidate JSON: legal JSON whitespace is now accepted outside strings, while disallowed controls and direct/escaped surrogates remain fail-closed as `response_json`. No live service call was made for this correction.
- Recorded the environment-specific live outcome for installed local `qwen3:1.7b`: parser-valid output omitted the prepared KG-edge reference, so the strict passed-result invariant caused a sanitized `internal` validation-failed-closed result with no retry. This is fail-closed environment evidence, not a product-defect or model-quality conclusion; no raw model output was printed or persisted.

---

## 2026-10-25 — Issue #29 deterministic SOP chunking and Qdrant indexing

- Added the versioned pure SOP/manual index-plan builder, strict source/config/vector boundaries, deterministic paragraph chunks, stable evidence IDs and UUIDv5 point IDs, complete citation/vector provenance payloads, canonical generated artifact, and direct-construction resource hardening.
- Added the explicit Qdrant 1.19.2 writer with immutable sanitized results, exact collection/vector and keyword-index compatibility checks, proxy/redirect refusal, bounded strict JSON, zero retries, waited writes, idempotent same-ID upsert, and conservative observable states for every partial or uncertain side effect. Production code has no delete/recreate path.
- Added focused RED–GREEN contract coverage plus a separately collected live test. The live test indexed the unchanged plan twice against the pinned upstream Qdrant 1.19.2 Linux binary, directly verified the same UUID, exact 15-field payload/vector and one-point count after each run, retrieved through the Issue #28 adapter, and removed the dedicated test collection.
- Recorded the accepted R3/R5, S4 stage-3, RQ1/RQ3 decision in `implementation-decisions.md` and refreshed existing index metadata; navigation structure and `raw/` remain unchanged. Final full-suite, review, commit, CI, and integration evidence is recorded at the Issue #29 lifecycle checkpoint.

---

## 2026-10-18 — Issue #28 Qdrant procedural-retrieval adapter

- Added the Pump_12-specific read-only Qdrant Query Points adapter behind the existing procedural result/evidence/stage contracts. It accepts only explicit trusted configuration and caller vectors, applies exact asset/type/procedure filters, preserves the returned score, and releases only the canonical stable SOP chunk.
- Added fail-closed coverage for unsafe configuration and vectors, redirects/proxies, connection and HTTP failures, timeout, media type and response cap, malformed or duplicate-key JSON, result cardinality, score threshold, payload shape, and every canonical semantic field. Failures return `UNSUPPORTED_LOWER_RANK` without support/evidence and never retry or call the fixture retriever.
- Added the deterministic Qdrant preload fixture and separately collected live tests. Two live tests passed against local Qdrant 1.19.2: the exact positive contract and a missing-collection failure. Docker was unavailable in WSL, so the pinned upstream Linux binary was used from profile-local scratch and stopped after verification.
- Documented the public contract and accepted R1/R3, S4 stage-3, RQ1/RQ4 decision in `README.md` and `implementation-decisions.md`. Navigation is unchanged, `raw/` is unchanged, and production indexing/embedding remains Issue #29. A preferred-model final review found parser acceptance of nonfinite JSON constants in ignored response fields; a nine-case RED preceded parser-level rejection, and redirect coverage now proves the target receives no request. Corrected validation passes 765 tests plus 2 intentional xfails at 92.52% package branch coverage, 100% Qdrant/Fuseki adapter coverage, Ruff, formatting, strict mypy, zizmor pedantic, repository quality, structural wiki health, raw-source protection, and diff checks.
- The preferred-model corrected exact-worktree rereview approved with no finding. Commit, push, PR, CI, merge, and issue closure remain separate approval/lifecycle gates.

---

## 2026-10-11 — Issue #24 end-to-end fail-closed Pump_12 paths

- Extended the deterministic Pump_12 orchestrator with minimal early exits for failed structured/procedural retrieval, the explicitly allow-listed unknown-evidence parser error, and non-passing SHACL/bounded-repair outcomes. Every blocked path retains only its real executed event prefix and exposes no action, evidence package, provenance/recommendation identity, or trace evidence.
- Added real-component negative-path coverage for retrieval failure, parser rejection without raw-payload leakage, unsupported SHACL policy, two-attempt bounded-repair exhaustion, Stage 9 evidence-package rejection, and Stage 10 provenance-write rejection. Activated the four Issue #9 fail-closed acceptance gaps and the two corresponding Architecture V1 paths; two unrelated Architecture V1 gaps remain intentional xfails.
- Kept the public orchestrator signature, dependencies, fixtures, workflows, frozen Architecture V1 baseline, and `raw/` unchanged. Narrow test-only call-through wrappers invoke the real parser, validator, repair controller, package assembler, and provenance writer rather than fabricating result records. No new material policy decision or Architecture V1 deviation was introduced, so `implementation-decisions.md` and wiki navigation are unchanged.
- Independent specification review passed. A quality/security review's two out-of-scope findings were rechecked against the approved plan and source; the reviewer then approved with no critical or important findings. Local validation passes 607 tests with 2 intentional xfails and 90.13% branch coverage, Ruff lint/format, and strict mypy.

---

## 2026-10-11 — Issue #23 deterministic Pump_12 orchestrator

- Added the service-free `run_pump12_orchestrator` boundary and focused contract tests. It composes the existing Pump_12 stages in the canonical ten-stage order, preserves one run/evidence identity, invokes the real SHACL/evidence/provenance contracts, and exposes action/package/provenance outputs only after the Stage 10 callback returns `None`.
- Activated the three Issue #23 Architecture V1 acceptance paths for ten-stage instrumentation, entity disambiguation, and SHACL-before-release behavior. The combined #23/#24 broad vertical-slice path remains intentionally pending for Issue #24.
- Documented the public contract in `README.md` and recorded the accepted R1–R5, S4 stages 1–10, RQ1–RQ4 implementation decision in `implementation-decisions.md`. No dependency, lockfile, fixture, workflow, live service, durable persistence adapter, broad failure matrix, or Architecture V1 deviation was added; navigation and `raw/` are unchanged.
- A failed delegated stub was discarded before the valid missing-module RED and real implementation. Independent specification review passed; an unsupported quality review citing nonexistent symbols was rejected, and source-grounded quality/security rereview approved. Final local validation passes locked sync, Ruff, format, strict mypy, 595 tests with 8 intentional xfails and 90.08% branch coverage, zizmor pedantic, wiki health with zero structural/raw issues, repository quality over 442 files, raw/privacy checks, and diff checks.

---

## 2026-10-03 — Issue #72 retrieval-bound RDF/SHACL seam

- Added `assemble_recommended_action_rdf` as the narrow retrieval-aware boundary that snapshots explicit resource mappings, validates one exact structured observation and one exact procedural support record, and emits the anomaly-window and typed observation/procedure support triples consumed by the existing action-scoped validator.
- Activated the Architecture V1 mapper-to-SHACL path without hand-added triples and documented the accepted R2/R3/R4/R5, S4 stage-5/6, RQ2/RQ3 decision in `implementation-decisions.md`; wiki navigation is unchanged, and `raw/` is unchanged.
- Review-driven RED–GREEN fixes covered stateful and hostile mappings, nested dataclass/scalar tampering, exact cardinality and identity, strict timezone-aware XSD `dateTime` lexical forms, sanitized exception handling, and deterministic graph assembly. Final independent adversarial review returned PASS.
- Final local validation passed 48 focused tests plus 9 intentional xfails and 544 full-suite tests plus 13 intentional xfails at 90.07% branch coverage, together with Ruff lint/format, strict mypy, zizmor, repository quality, static added-line security, and diff checks. Issue publication, CI, merge, and closure remain separate gates.

---

## 2026-10-02 — Issue #21 pre-release evidence package implementation

- Added the Stage 9 `EvidencePackage`/assembly contract, exact action-graph digest binding in `ShaclValidationResult`, and the narrow `INVALID_EVIDENCE_PACKAGE` stage error. The package binds one final passing action to its target asset, validated KG/document support, SHACL report, bounded-repair outcome, run identity, and deterministic RDF evidence while rejecting anonymous graph nodes and incomplete or inconsistent inputs.
- Review-driven RED–GREEN fixes added exact candidate label/rank binding, parser-equivalent candidate rank/action/target validation before RDFLib comparison, immutable tuple-only support evidence plus one-time graph/mapping/ID snapshots to prevent validation/package drift, no-repair and repaired report-chain validation, and exception-safe handling for malformed validation-report IDs. Failures return no package and a sanitized `VALIDATION_FAILED_CLOSED` event.
- Documented the public Stage 9 contract in `README.md` and the accepted R5/S4-09 decision in `implementation-decisions.md`. Navigation is unchanged, `raw/` is unchanged, and no dependency, provenance persistence, recommendation release, or Issue #23 orchestration was added.
- Final local validation passed 63 focused tests and 499 full-suite tests with 13 intentional Architecture V1 xfails and 90.29% branch coverage, plus locked sync, Ruff lint/format, strict mypy over 30 source files, zizmor, wiki health, repository quality, and diff checks. Publication/CI and integration remain separate gates.

---

## 2026-09-21 — Issue #20 bounded repair implementation/documentation

- Added the allow-listed bounded-repair controller without adding a new dependency, plus its contract tests, the narrow `REPAIR_ATTEMPT_FAILED` stage-error code, and the real Architecture V1 bounded-repair acceptance assertion. The controller maps same-class package SHACL violations to target, observation, or procedure repair intents and explicit class-specific fallbacks; generic, unknown, root, and cross-class violations fail closed.
- Documented the public S4 stage-7/8 contract in `README.md`; recorded the accepted policy, fresh-report identity, retry metric, fail-closed, and security decisions in `implementation-decisions.md`; updated the existing index description only, with no new navigation page.
- Review-driven RED–GREEN corrections closed additive report identity, malformed nested callback state and crashes, rejected-result retention, extra stage-event identity, RDF/object conformance drift, hostile graph/literal conversion, foreign violation focus, result-link/tuple cardinality drift, hidden validation-result nodes, and extra result-node predicates. Final bounded-repair validation passed 93 tests, and independent final specification plus adversarial security rereviews returned PASS.
- The implementation maps to Architecture V1 R4/R5, S4 stages 7–8, RQ2 primary, and RQ3 secondary. It adds no dependency and does not implement retrieval/model repair tools, evidence-package assembly, provenance writing, persistence, end-to-end orchestration, or recommendation release. Complete local validation passed 436 tests with 13 intentional Architecture V1 xfails and 90.72% branch coverage, plus Ruff lint/format, strict mypy over 27 source files, zizmor, wiki health (`fields=0`, `rq=0`, `links=0`, `index=0`, `orphans=0`, `raw_recent=0`; 52 nonblocking stale-date notices), repository quality over 433 files, and `git diff --check`.

---

## 2026-09-21 — Issue #19 SHACL validation implementation/documentation

- Added the package-owned recommended-action SHACL shapes, typed PySHACL adapter, deterministic violation records, stable RDF validation-report normalization, and stage-6 terminal-event mapping. Validation is scoped to the caller-selected action so unrelated recommended-action nodes cannot poison its report.
- Documented the public stage-6 contract and complete caller-supplied support vocabulary in `README.md`; recorded the accepted PySHACL, packaged-shape, stable-report, sensitive-value-omission, and action-scoping decisions in `implementation-decisions.md`; updated the existing index description only, with no new navigation page.
- The implementation maps to Architecture V1 R4/R5, S4 stage 6, RQ2 primary, and RQ3 secondary. It does not implement repair, evidence-package assembly, provenance, orchestration, persistence, or recommendation release, and SHACL conformance is not presented as a safety or optimality proof.
- Focused validation passed 40 contract tests after a review-driven RED–GREEN action-scoping fix. Independent specification review passed and final quality/security re-review approved. Locked sync, Ruff lint/format, strict mypy, 342-test full pytest with 14 intentional xfails and 91.01% branch coverage, zizmor pedantic, wiki health, repository quality, wheel resource/loading, privacy, scope, and raw-source checks passed. The generated wiki-health refresh was restored after recording its structural result (`fields=0`, `rq=0`, `links=0`, `index=0`, `orphans=0`, `raw_recent=0`; 52 date-staleness warnings remain) to avoid unrelated generated-report churn.

---

## 2026-09-18 — Issue #18 RDF action mapping implementation/documentation

- Activated the Architecture V1 schema-to-RDF acceptance test by replacing the Issue #13/#18 strict xfail with a structural Pump_12 test that derives the parser payload from the canonical repaired fixture candidate, validates it through `parse_candidate_actions`, and maps it to RDF with explicit `URIRef` resources.
- Documented the public RDF action mapping contract in `README.md`, including the RDFLib dependency range, internal namespace status, explicit resource mapping requirement, fail-closed typed errors, returned triples, and out-of-scope SHACL, persistence/Fuseki, evidence-package, provenance, and orchestration work.
- Recorded the accepted deterministic RDF action mapping decision in `implementation-decisions.md` and updated the existing index description only; no new wiki page was added.
- Complete Issue #18 scope adds `src/mfg_agentgraph/rdf_action_mapper.py`, `tests/test_rdf_action_mapper_contract.py`, the RDFLib dependency in `pyproject.toml`/`uv.lock`, Architecture acceptance activation, and README/wiki docs. No `thesis-wiki/raw/`, generated wiki-health report, workflow, SHACL, persistence, provenance, evidence-package, or orchestration implementation changed; private journal evidence remains excluded from the parent repository and was not promoted publicly. Final local validation passed with 302 tests, 14 intentional xfails, 91.19% branch coverage, locked sync, Ruff, strict mypy, zizmor pedantic, wiki health, repository quality, raw-source protection, and diff checks; independent specification and quality/security reviews approved the final worktree.

---

## 2026-09-18 — Issue #17 deterministic fixture model-adapter implementation

- Added the deterministic Pump_12 fixture adapter and contract tests, plus the approved public README and wiki documentation. The implementation maps to the R1 local-deployment precursor, R4 pre-validation candidate generation, S4 stage 4, and RQ4 reproducibility; it remains service-free and fixture-only. Raw sources, private journal material, fixtures, generated wiki-health output, dependencies, workflows, live-model behavior, RDF/SHACL, repair, and orchestration remain unchanged.

---

## 2026-09-09 — Issue #16 deterministic procedural-retrieval documentation

- Documented the public procedural-retrieval scaffold in `README.md`, including the Pump_12 usage example, validated SOP/document-chunk contract, EvidenceCatalog interoperability, contradiction-resistant invariants, fail-closed `UNSUPPORTED_LOWER_RANK` behavior, and explicit out-of-scope Qdrant/vector-production boundaries.
- Recorded the accepted deterministic Pump_12 procedural retrieval decision in `implementation-decisions.md` with Architecture V1 R3/R5, S4 stage 3, RQ1/RQ3 mapping, standard-library fixture composition, no new dependencies, consequences/risks, and focused evidence.
- Updated `index.md` metadata and existing `implementation-decisions` description only; navigation is unchanged and no new wiki page was added.
- This documentation step edited only `README.md`, `thesis-wiki/wiki/implementation-decisions.md`, `thesis-wiki/wiki/index.md`, and `thesis-wiki/wiki/log.md`; it did not edit `thesis-wiki/raw/`, private journal material, source, tests, fixtures, configuration, dependencies, workflows, or generated reports. Final Issue #16 validation includes 59 focused contract tests and a full suite with 257 passes, 15 intentional xfails, and 91.97% branch coverage.

---

## 2026-09-08 — Issue #15 deterministic structured-retrieval documentation

- Documented the public structured-retrieval scaffold in `README.md`, including the Pump_12 usage example, validated asset/observation/procedure/KG-edge contract, stable KG-edge-only support boundary, EvidenceCatalog interoperability, fail-closed behavior, and explicit out-of-scope boundaries.
- Recorded the accepted deterministic Pump_12 structured retrieval decision in `implementation-decisions.md` with Architecture V1 R2/R3/R5, S4 stage 2, RQ2/RQ3 mapping, and source/test/fixture evidence.
- Updated `index.md` metadata description only; navigation is unchanged and no new wiki page was added.
- The documentation work did not edit `raw/`, `private-development-journal/`, `wiki-health.md`, source, tests, fixtures, dependencies, workflows, or any generated report. Focused local validation is limited to the 37 structured-retrieval contract tests.

---

## 2026-09-08 — Issue #14 deterministic entity-resolution documentation

- Documented the public entity and asset resolution contract in `README.md`, including the `KnownAsset`/`AssetCatalog` Pump_12 example, exact canonical-ID semantics, label/alias normalization, fixed confidence priorities, fail-safe disambiguation behavior, and explicit out-of-scope boundaries.
- Recorded the accepted deterministic fail-safe entity resolver decision in `implementation-decisions.md` with Architecture V1 R2, S4 stage 1, and RQ2 mapping; noted no V1 deviation and preserved the Architecture acceptance placeholders.
- Updated `index.md` metadata and existing implementation-decisions description; navigation is unchanged and no new page link was added.
- The documentation work did not edit `raw/`, `private-development-journal/`, or `wiki-health.md`; the complete Issue #14 change also added the resolver module and its contract tests.

---

## 2026-09-05 — Stable evidence reference contract

- Added `tests/test_evidence_reference_contract.py` and `src/mfg_agentgraph/evidence_reference.py` for stable KG-resource, KG-edge, and document-chunk evidence references required by Issue #12.
- Documented the public evidence-reference contract in `README.md` and recorded the material decision in `implementation-decisions.md` without changing the frozen Architecture V1 baseline.
- Preserved existing wiki navigation because `implementation-decisions.md` is already indexed; no files under `raw/` or `private-development-journal/` were modified.

---

## 2026-09-05 — Typed S4 stage instrumentation contract

- Added `tests/test_stage_instrumentation_contract.py` and `src/mfg_agentgraph/stage_instrumentation.py` for the dependency-free typed stage-event contract required by Issue #11.
- Documented the public contract in `README.md` and recorded the material decision in `implementation-decisions.md` without changing the frozen Architecture V1 baseline.
- Preserved existing wiki navigation because `implementation-decisions.md` is already indexed; no files under `raw/` or `private-development-journal/` were modified.

---

## 2026-09-05 — Implementation V1 status refresh

- Added `project-status-2026-09-05.md` from live Git, GitHub, test, branch, and private-journal verification.
- Recorded Issue #10 as complete and Issue #11 as the next dependency-ready task, still blocked by its required plan-comment and explicit user-approval gate.
- Updated `index.md` navigation; no files under `raw/` were modified.

---

## 2026-08-23 — Operator request contract implementation

- Added `tests/test_operator_request_contract.py` and `src/mfg_agentgraph/operator_request.py` for the dependency-free operator request normalization boundary.
- Documented the public interface decision in `implementation-decisions.md` and added README usage notes that later S4 stages are not implemented in this change.
- Preserved existing wiki navigation because these pages were already indexed; no files under `raw/` or `private-development-journal/` were modified.

---

## 2026-08-16 — Lean Implementation V1 quality foundation

- Added `implementation-decisions.md` as the append-only decision/deviation record linked to the frozen Architecture V1 baseline.
- Established a reuse-first engineering policy, locked Python environment, strict lint/type/test gates, 90% product branch-coverage floor, workflow security audit, and weekly dependency updates.
- Deliberately deferred MkDocs, formal ADR tooling, external coverage upload, broad linting of historical scripts, and speculative runtime dependencies.
- Updated `index.md` navigation; no files under `raw/` were modified.

---

## 2026-08-16 — Architecture V1 baseline and persistent thesis retrieval

- Designated the exact RAGE-KG 2026 final submission (`submission/rage-kg-2026`, commit `59b2796f8adceebbee61a896e689f265a5d36c2a`) as the frozen MFG-AgentGraph Architecture V1 baseline.
- Added `architecture-v1-rage-kg-2026.md` with immutable artifact provenance, V1 requirements, normative pipeline, component/interface map, bounded repair and fail-closed contracts, first vertical slice, RQ mapping, and implementation acceptance checklist.
- Linked the baseline from `index.md` and `mfg-agentgraph.md`; Architecture V1 changes must now be recorded as explicit deviations or a later architecture version.
- Raised Hermes context compression from 50% to 75% of the active Codex model window and increased the compression-call timeout to 300 seconds.
- Rebuilt and validated the semantic thesis-wiki index for persistent retrieval.
- No files under `raw/` were modified.

---

## 2026-08-03 — Weekly wiki structural curation

- Re-ran `python3 scripts/wiki_health.py`; `wiki-health.md` now reports 56 pages checked, with 0 missing fields, 0 RQ-tag issues, 0 broken wikilinks, 0 index/orphan issues, and 0 recent raw-folder changes.
- Flagged 31 stale `Last updated` fields for future content review; dates were not changed because refreshing them without reviewing page content would not be a safe deterministic fix.
- No safe deterministic structural repairs were required, and no files under `raw/` were modified.

---

## 2026-07-20 — Main-wiki status synchronization and repository identity audit

- Synchronized `project-status-2026-07-20.md` from the active RAGE-KG publication worktree into the main thesis wiki.
- Updated `index.md` so the current 2026-07-20 project snapshot is the first Project spine entry; retained the 2026-06-22 snapshot as historical context.
- Audited all reachable Git author/committer identities and GitHub attribution. The inconsistent displayed names come from commit-embedded metadata and changing Git configurations, not from the GitHub profile name itself.
- Historical commit metadata was not rewritten because that would change commit hashes and require coordinated force-pushing of published branches.
- Corrected the WSL global and repository-local identity for future commits to the canonical `Ameya Punekar` name and the GitHub-linked noreply address; enabled `user.useConfigOnly` globally to prevent Git from silently guessing another identity.
- No files under `raw/` were modified.

---

## 2026-07-20 — RAGE-KG submission status refresh and wiki lint

- Created `project-status-2026-07-20.md` covering the current RAGE-KG 2026 target, canonical submission artifacts, validated 12-page CEUR-ART package, remaining EasyChair/author-metadata blockers, figure-refinement state, and branch/PR status.
- Recorded the four publication commits completed on 2026-07-20 and the retained V1-versus-V2 comparison.
- Re-ran automated wiki structural lint with `python3 scripts/wiki_health.py`; see `wiki-health.md` for the generated report.
- No files under `raw/` were modified.

---

## 2026-07-20 — End-of-day publication status refresh

- Confirmed that the RAGE-KG submission candidate remains a validated 12-page full-paper package.
- Recorded that final EasyChair track confirmation, verified author metadata, human visual proof, and disposition of the local figure-refinement pass remain open.
- Recorded that `rage-kg-deep-eval-fixes` is pushed through `20f8e67`, PR #3 remains closed, and no replacement PR has been created.

---

## 2026-06-22 — European venue shortlist refresh

- Refreshed `concept-paper/conference-targets-2026.md` with additional reputable Europe-based upcoming opportunities for the current concept/position/short/WIP version of MFG-AgentGraph.
- Added GLOW@ISWC 2026, KG-NeSy 2026, KGMDSE 2026, EKAW 2026 Posters/Demos, and KGSWC 2026 Posters/Demos to the active venue ladder; retained EAIT 2026 as a non-European fallback only.
- Updated `project-status-2026-06-22.md` venue/status planning to reflect the expanded July-to-September submission path and official CFP links.

---

## 2026-06-22 — Professional GitHub repository governance setup

- Added industry-style repository governance for `mfg-agentgraph`: README, CONTRIBUTING workflow, SECURITY policy, CODEOWNERS, PR template, issue templates, and repository-governance documentation.
- Added GitHub Actions quality gate for `python3 scripts/wiki_health.py` and `python3 scripts/repo_quality_check.py`.
- Added `scripts/repo_quality_check.py` to enforce required governance files, branch naming, README anchors, forbidden tracked credential files, and simple secret-pattern scanning.
- Planned GitHub settings/protection now align with a private, trunk-based thesis repository: protected `main`, PR-first workflow, squash merge, branch cleanup, and labels for RQ/research/experiment tracking.

---

## 2026-06-22 — Ollama Cloud Qwen fallback ordering

- Updated the Hermes thesis profile fallback chain so `ollama-cloud` / `qwen3-coder:480b` is the first fallback and OpenRouter `cohere/north-mini-code:free` is the second fallback.
- Confirmed the first fallback is Ollama Cloud, not local Ollama; local Ollama remains non-active for Hermes fallback routing.
- Verified direct Hermes smoke tests for both fallback entries: `ollama-cloud-qwen-ok` from `ollama-cloud` / `qwen3-coder:480b`, and `cohere-second-fallback-ok` from OpenRouter `cohere/north-mini-code:free`.
- Re-ran the wiki health audit after documenting the fallback change; structural lint remained clean.

---

## 2026-06-22 — Free Hermes fallback routing refresh

- Replaced the paid/credit-consuming DeepSeek OpenRouter fallback chain with `cohere/north-mini-code:free`, the best free coding/tool-use fallback that passed live Hermes tests during this session.
- Confirmed `deepseek/deepseek-v4-flash` is a capable low-cost hosted fallback, but it is not free and can still fail under low OpenRouter credits.
- Confirmed `qwen/qwen3-coder:free` is listed on OpenRouter and is stronger/more agentic in principle, but repeated live Hermes tests returned upstream 429 after one successful smoke test, so it is not reliable enough as the active fallback right now.
- Confirmed Qwen3-Coder is available through Ollama (`qwen3-coder:30b`, `qwen3-coder:480b`); the local machine currently has only `nomic-embed-text` installed in Ollama, and `qwen3-coder:30b` would require roughly a 19 GB download and likely slow CPU/RAM-heavy execution on the current 8 GB VRAM / 23 GiB RAM host.
- Verified active free fallback with a direct smoke test and a forced fallback activation test.

---

## 2026-06-22 — Status refresh and wiki lint

- Created `project-status-2026-06-22.md` as a current thesis-brain status page covering completed wiki/literature work, concept-paper artifacts, venue path, lint results, unresolved verification flags, and next actions.
- Updated `index.md` to include the new status page under Project spine and bumped the index date.
- Re-ran the automated wiki health audit with `python3`; `wiki-health.md` reports zero structural issues after the status refresh.
- Patched `scripts/wiki_health.py` maintenance instructions from `python` to `python3` because this WSL environment does not provide a `python` executable.

---

## 2026-05-11 — Second Batch Ingest: Skipped and Pending Sources

- **New page**: `graph-constrained-reasoning-2024.md` — synthesized from `Graph_Constrained_Reasoning_2024.md` (ICML 2025). Explores integrating KG structure directly into LLM decoding using KG-Trie.
- **New page**: `fidelis-faithful-kg-reasoning-2024.md` — synthesized from `FiDeLiS_Faithful_KG_Reasoning_2024.md`. A framework improving factuality via Path-RAG and Deductive-Verification Beam Search (DVBS).
- **New page**: `kag-knowledge-augmented-generation-2024.md` — synthesized from `KAG_Knowledge_Augmented_Generation_2024.md` (Ant Group). Deep integration of KGs with RAG via logical form reasoning and mutual indexing.
- **New page**: `ontology-llm-accuracy-sparql-qa-2024.md` — synthesized from `Ontology_LLM_Accuracy_SPARQL_QA_2024.md`. Demonstrates error-checking and repairing LLM-generated SPARQL queries against an ontology.
- **New page**: `react-yao2023.md` — synthesized from `ReAct_Yao2023.md` (ICLR 2023). Foundational paradigm of interleaved reasoning and acting.
- **New page**: `llms-for-information-retrieval-survey-2023.md` — synthesized from `Think_on_Graph_2_Hybrid_RAG_2024.md`. This file was mislabeled in the dataset and actually contains an IR survey by Zhu et al., not ToG 2.0.
- **New page**: `fraud-detection-ml-2025.md` — synthesized from `Graphs_Meet_AI_Agents_Taxonomy_2025.md`. This file was mislabeled and contains an irrelevant credit card fraud detection paper. Included for absolute completeness of the `raw/` ingest.
- **Wiki stats**: All primary surveys, core literature, and even the mislabeled files from `raw/converted/` are now completely ingested into the wiki. 28/28 markdown files processed. The knowledge base is fully prepared for the thesis drafting phase.

---

## 2026-05-11 — Batch ingest: Markdown raw sources + enrichment pass

- **New page**: `pageindex.md` — synthesized from `raw/pageindex-readme.md` + `raw/pageindex-study-notes.md`. Covers the vectorless reasoning-based RAG framework: two-phase pipeline (tree indexing + LLM tree search), self-correction loop paralleling SHACL, comparison with MFG-AgentGraph, integration points for hybrid KG+document retrieval.
- **New page**: `references-master.md` — consolidated all 10 `raw/references-*.md` files into a single navigable master reference index with status tracking (✅ Ingested / 📋 Pending / Skipped) for each source. Covers: 11 research papers, 16 surveys, 9 journal articles, 7 conference papers, 5 books, 7 technical standards, 20 GitHub repos, 39 web articles, 24 videos, 9 podcasts.
- **Updated** `fuseki-triplestore.md`: enriched from `raw/apache-jena-fuseki-docs.md`. Resolved all three open questions: (1) TDB2 recommended over TDB1, (2) PROV-O stored in separate named graphs per agent run, (3) SHACL runs on demand via jena-shacl API. Added deployment modes, Docker recommendation, endpoint configuration, Python client pattern. Removed [NEEDS VERIFICATION] flag.
- **Updated** `ragas-metrics.md`: enriched from `raw/ragas-metrics-docs.md`. Added complete metric catalogue (6 RAG metrics + 3 Nvidia metrics + agent evaluation), AnsQ/RetQ/ReaQ augmentation from [[llms-meet-kgs-qa-survey-2025]], resolved all open questions. Removed [NEEDS VERIFICATION] flag.
- **Updated** `index.md`: added new sections (Alternative RAG paradigms, Bibliography), added all 6 source summaries from the 2026-05-04 Claude session that were missing (AGENTiGraph, Beyond CoT, KG Construction, LLMs Meet KGs, Multi-Agent LLM, Understanding Planning). Bumped date.
- **Retroactive log**: the following pages were created in a 2026-05-04 Claude session but not logged: `agentigraph-2025.md`, `beyond-chain-of-thought-2024.md`, `kg-construction-llm-survey-2024.md`, `llms-meet-kgs-qa-survey-2025.md`, `multi-agent-llm-survey-2024.md`, `understanding-planning-llm-agents-2024.md`. Now indexed and logged.
- **Raw sources NOT ingested** (PDF — cannot read): `Graph_Constrained_Reasoning_2024.pdf`, `LLM_Agent_Methodology_Survey_2025.pdf`, `LLM_Agents_Autonomous_Tool_Users_Review_2025.pdf`, `RAG_Architectures_Robustness_Survey_2025.pdf`, `RAG_Beyond_External_Data_2024.pdf`, `RAG_Evaluation_LLM_Era_Survey_2025.pdf`, `Graphs_Meet_AI_Agents_Taxonomy_2025.pdf`. These remain as 📋 Pending in [[references-master]].
- **Raw sources treated as reference-only** (no dedicated wiki page needed — content absorbed into existing pages or reference index): `raw/langgraph-docs.md` (empty redirect), `raw/microsoft-graphrag-docs.md` (scraped web chrome — key content in [[graphrag-microsoft-2024]]), `raw/ragas-metrics-docs.md` (absorbed into [[ragas-metrics]]), `raw/apache-jena-fuseki-docs.md` (absorbed into [[fuseki-triplestore]]), `raw/w3c-*.md` files (key content already in [[prov-o]], [[shacl-validation]], [[ssn-sosa]], [[sosa-ssn-2018]]).
- **Wiki stats**: 37 pages total (35 existing + 2 new). 21 source PDFs/docs fully ingested. 7 PDFs pending (require PDF-reading capability). 7 PDFs user-skipped.

---

## 2026-05-04 — Ingest batch: 6 source PDFs (Claude session — retroactive log)

- Read and created source pages for 6 PDFs in a single Claude session. Pages created: `agentigraph-2025.md` (AGENTiGraph, CIKM 2025), `beyond-chain-of-thought-2024.md` (CoX survey, Xia et al.), `kg-construction-llm-survey-2024.md` (KG Construction, Bian 2025), `llms-meet-kgs-qa-survey-2025.md` (LLMs Meet KGs QA, Ma et al. EDBT 2025), `multi-agent-llm-survey-2024.md` (LLM-MA Survey, Guo et al.), `understanding-planning-llm-agents-2024.md` (Planning survey, Huang et al.).
- Cross-references updated across existing pages (kg-agent-s4, shacl-validation, local-deployment, langgraph-agent, strategy-comparison, mfg-agentgraph, research-questions, etc.).
- Not logged at the time; retroactively logged 2026-05-11.

---

## 2026-05-04 — Ingest: Multi-Agent Systems Survey (Chen et al., HIT 2024)

- Read `Multi_Agent_Systems_Survey_2024b.pdf` end-to-end (arXiv:2412.17481v2, 13 pages — Chen, Liu, Han, Zhang, Liu — Harbin Institute of Technology).
- Created source page `multi-agent-systems-survey-2024b.md`. Value is **positional, not S4-precedent**: this is the cleanest published citation for staying single-agent and gives a survey-level vocabulary for the LangGraph design.
- Key takeaways captured: (1) Three-aspect LLM-MAS taxonomy (task-solving / simulation / evaluation) — thesis fits *none* directly. (2) **Seven-part agent decomposition** (LLM + Profile + Reasoning + Memory + Rules + Tools + Intervention) mapped onto MFG-AgentGraph component-by-component. (3) Three reasoning-framework families for task-solving (multi-stage / collective decision-making / self-refine) — **S4's SHACL loop is single-agent self-refine** with deterministic critic replacing LLM critic. (4) **§6.2 "efficiency explosion"** is the citation for why thesis stays single-agent (n-agent × ToG's ~10 LLM calls already breaches 30s p95 budget). (5) Companion challenge **"accumulative effect"** applies inside the SHACL self-refine loop — cap iteration count and report per-iteration faithfulness.
- Updated `langgraph-agent.md`: added the seven-component decomposition table mapping to MFG-AgentGraph; added the self-refine framing of S4's SHACL loop. Bumped Last updated.
- Updated `local-deployment.md`: added "Why single-agent: efficiency explosion" section citing Chen et al. §6.2 — supplies the published citation that protects RQ4 / H5 from "why didn't you do MAS?" defence questions. Bumped Last updated.
- Updated `index.md` with new source-summary entry. Bumped Last updated.
- **Open questions raised**: (1) consider a 2-agent ablation (planner + validator) as RQ4 efficiency-explosion comparator. (2) Profile authoring — hand-write SOP role prompt or extract from SOP text? (3) Long-context limit on growing PROV trace — plan compaction strategy before week-12 evaluation.
- **No content updates to** `naive-rag.md`, `graphrag.md`, `og-rag.md`, `kg-agent-s4.md`, `strategy-comparison.md`, `prov-o.md`, `ssn-sosa.md`, `shacl-validation.md` — survey is orthogonal to S1-S4 method mechanics.

---

## Skipped sources (running list)

User-directed skips during per-source ingest. Each entry records what was skipped and why, so re-ingest later is straightforward.

| Date | File | Reason | Status |
|---|---|---|---|
| 2026-04-27 | `Think_on_Graph_2_Hybrid_RAG_2024.pdf` | **Mislabeled** — file actually contains "Large Language Models for Information Retrieval: A Survey" (Zhu et al., arXiv:2308.07107v5), not ToG 2.0. Real ToG 2.0 (Sun et al., ICLR 2025, arXiv:2407.10805) missing from `raw/`. | Skipped; `[[think-on-graph-2]]` and citations of arXiv:2407.10805 remain `[NEEDS VERIFICATION]` in `strategy-comparison.md` and `kg-agent-s4.md`. |
| 2026-04-27 | `Ontology_LLM_Accuracy_SPARQL_QA_2024.pdf` | User-directed skip (no reason recorded). | Skipped. May revisit if RQ2 evaluation needs ontology-aware SPARQL benchmarks. |
| 2026-04-27 | `FiDeLiS_Faithful_KG_Reasoning_2024.pdf` | User-directed skip. | Skipped. Sibling to RoG/ToG; may revisit for related-work breadth. |
| 2026-04-27 | `KAG_Knowledge_Augmented_Generation_2024.pdf` | User-directed skip. | Skipped. Ant Group industrial KG-augmented generation framework; may revisit as competing-framework comparison. |
| 2026-04-27 | `LLMs_for_Manufacturing_Survey_2024.pdf` | Too big (~30 MB). | Skipped per the size-skip rule. Manufacturing-domain positioning survey; revisit when budget allows for a larger ingest. |
| 2026-04-27 | `GraphRAG_Survey_Peng2024.pdf` | User-directed skip. | Skipped. Broader GraphRAG landscape survey; may revisit for related-work breadth on S2 alternatives. |
| 2026-04-27 | `ReAct_Yao2023.pdf` | Borderline-too-big (33 pages, 633 KB). | Skipped per size-skip rule. Foundational agent paper (Yao et al., ICLR 2023); revisit for the related-work agent-foundations chapter when budget allows. |

---

## 2026-04-27 — Ingest: PROV-AGENT (Souza et al., IEEE e-Science 2025)

- Read `PROV_AGENT_Provenance_AI_Agents_2025.pdf` end-to-end (arXiv:2508.02866v3, 7 pages — Souza, Gueroudji, DeWitt, Rosendo, Ghosal, Ross, Balaprakash, Ferreira da Silva — Oak Ridge National Lab + Argonne National Lab).
- Created source page `prov-agent-souza2025.md` covering: the W3C PROV extension with concrete subclasses (`AIAgent`, `AgentTool`, `AIModelInvocation`, `Prompt`, `AIModel`, `ResponseData`, `DataObject` with subclasses `DomainData`/`SchedulingData`/`TelemetryData`); the standard PROV relationships used throughout (no new vocabulary — fully W3C-conformant); MCP integration as the agent-side instrumentation; the Flowcept open-source impl with `@flowcept_agent_tool` decorator + `FlowceptLLM` wrapper pattern; **the five operator-trust queries (Q1-Q5) that map directly to RQ3**; the additive-manufacturing use case at ORNL (metal 3D printer + HPC + cloud gpt-4o) which is structurally identical to the thesis's anomaly-triage scenario; the self-described "first provenance framework for agentic workflows" novelty claim; gaps relative to S4 (no SHACL, no domain ontology, cloud-LLM focus, observability-first not correctness-first).
- Updated `prov-o.md`: resolved `[NEEDS VERIFICATION]` flag for the PROV-AGENT PDF; added PROV-AGENT to the peer-reviewed-basis section as the verified primary reference; added the five operator-trust queries as the RQ3 spine; replaced the old "open question — what does PROV-AGENT propose?" with the resolved answer.
- Updated `kg-agent-s4.md`: added "PROV-AGENT framing" section with the **S4 = PROV-AGENT + `ValidationReport` + SSN/SOSA-typed `DomainData`** contribution claim — the cleanest statement of S4's novelty in the provenance literature; updated peer-reviewed-basis row to mark PROV-AGENT verified.
- Updated `research-questions.md`: added the five PROV-AGENT operator-trust queries as the user-study test items for RQ3 / H4.
- Updated `index.md` with new source-summary entry.
- **Open action item resolved**: the PROV-AGENT [NEEDS VERIFICATION] flag in `prov-o.md`.
- **New open questions raised**: (1) whether to adopt Flowcept directly or replicate the decorator pattern with a lighter Fuseki/SQLAlchemy backend (Flowcept's broker + Redis/Kafka may exceed the local-deployment footprint); (2) operationalize Q1-Q5 as concrete SPARQL queries against [[fuseki-triplestore]] for Phase 4; (3) provenance UI choice — PROV-AGENT's Streamlit chat interface vs. force-directed graph view.

## 2026-04-27 — Ingest: SOSA / SSN ontology paper (Janowicz et al., *J. Web Semantics* 2018)

- Read `SOSA_SSN_Ontology_Sensors_2018.pdf` end-to-end (arXiv:1805.09979v2, 10 pages — Janowicz, Haller, Cox, Le Phuoc, Lefrançois — UCSB / ANU / CSIRO / TU Berlin / Mines Saint-Étienne).
- Created source page `sosa-ssn-2018.md` covering: SOSA's three perspectives (observation, sampling, actuation) sharing a common core structure; the 13 classes and 21 properties; **direct PROV-O alignment** (Sensor/Sampler/Actuator ⊆ prov:Agent; Observation/Sampling/Actuation ⊆ prov:Activity; Procedure ⊆ prov:Plan; Result/FeatureOfInterest ⊆ prov:Entity) — the load-bearing edge that lets SOSA-typed data compose cleanly with PROV-AGENT; alignment with OGC O&M (`sosa:Observation ≡ om:Observation`); modular architecture (horizontal + vertical alignment modules); event-centric design (vs. old SSO situation-centric); concrete manufacturing-domain mapping for the PumpStation_12 scenario; the `Procedure` reproducibility argument as it applies to MIMII recording protocol; what SOSA delegates to other vocabularies (GeoSPARQL, QUDT, OWL-Time, DCAT, SKOS).
- Updated `ssn-sosa.md`: resolved [NEEDS VERIFICATION] flag for SOSA paper; added the PROV-O alignment table (the key compositional edge for S4 + PROV-AGENT); resolved the SSN-Lite vs. full SSN open question with a recommendation (SOSA core + PROV-O alignment only, skip DUL/OBOE/full-SSN to keep `ALI(D)` fragment); added the MIMII-protocol-as-Procedure modeling guidance.
- Updated `kg-agent-s4.md`: marked SSN/SOSA peer-reviewed-basis row as verified.
- Updated `index.md` with new source-summary entry.
- **Open action items resolved**: the SOSA paper [NEEDS VERIFICATION] in `ssn-sosa.md`; the "SSN-Lite vs. full SSN" open question.
- **New open questions raised**: (1) SAREF alignment for industrial settings (not covered by Janowicz et al.); (2) W3C-recommended SHACL shapes for SSN/SOSA validation (Phase 1 deliverable); (3) Fuseki support for QUDT custom datatypes (`cdt:pressure`) — paper notes these are "not yet recognized by current SPARQL engines" as of 2018, needs current verification.

## 2026-04-27 — Source 6 SKIPPED: file mislabel

- `raw/Think_on_Graph_2_Hybrid_RAG_2024.pdf` is mislabeled. File content is actually **"Large Language Models for Information Retrieval: A Survey"** by Zhu, Yuan, Wang, Liu, Liu, Deng, Chen, Liu, Dou, Wen — arXiv:2308.07107v5 (Renmin University + Beijing Academy of AI), 43 pages. **Not** the ToG 2.0 paper expected by the thesis pitch and current wiki citations.
- User chose to skip ingest rather than write up the IR survey under a different name.
- **Open action item**: download the actual ToG 2.0 PDF (Sun et al., ICLR 2025, arXiv:2407.10805 — "Think-on-Graph 2.0: Deep and Faithful Large Language Model Reasoning with Knowledge-guided Retrieval Augmented Generation") into `raw/` to resolve the [[think-on-graph-2]] forward-reference. Until then, citations of arXiv:2407.10805 in `strategy-comparison.md` and `kg-agent-s4.md` remain [NEEDS VERIFICATION].

## 2026-04-27 — Ingest: Think-on-Graph / ToG (Sun et al., ICLR 2024)

- Read `Think_on_Graph_Sun2023.pdf` end-to-end including all appendices (arXiv:2307.07697v6, 30 pages).
- Created source page `think-on-graph.md` covering: the three-paradigm framing **LLM-only / LLM ⊕ KG (loose) / LLM ⊗ KG (tight)** that anchors where S4 sits; the three-phase inference loop (Init → Explore via Search+Prune over relations+entities with LLM as scorer → Reason); the ToG-R variant trading entity-pruning for ~half the LLM calls; the **directly reusable SPARQL templates (Appendix E.1)** for relation/entity search and MID-to-label conversion; the **five reusable LLM prompts (Appendix E.3)** for relation prune / entity prune / sufficiency check / answer generation; headline results (ToG with GPT-4 beats fine-tuning SOTA on 6 of 9 datasets training-free); plug-and-play across LLMs (Llama2-70B +18.5%/+11.5%, ChatGPT +20.1%/+14.0%, GPT-4 +23.5%/+15.3% on CWQ/WebQSP over CoT) — **Llama2-70B + ToG ≥ GPT-4 + CoT in some scenarios**, the empirical anchor for [[local-deployment]] / RQ4; computational footprint (max 2ND+D+1 LLM calls; observed avg 8.7-14.3 on multi-hop datasets); pruning-tool ablation (LLM > BM25/SentenceBERT, but the latter cut calls from ~22 to ~4); knowledge traceability/correctability loop (Fig. 4) as the conceptual ancestor of SHACL self-correction + PROV-O; evidence-of-answers analysis (60-93% of correct answers come from KG paths only — strong faithfulness signal); path-overlap analysis (~25% of CWQ correct samples have 0 overlap with ground-truth paths — ToG explores alternative paths, robustness for incomplete KGs); naive-beam-search vs. ToG comparison.
- Updated `kg-agent-s4.md`: added the **"S4 = ToG + ontology + SHACL + PROV-O" framing** with a concrete component-by-component table; added ToG-vs-ToG-R recommendation for RQ4 (ToG-R as safer default for the 30s p95 budget); updated peer-reviewed-basis row to mark ToG as "verified, the most direct S4 precedent".
- Updated `strategy-comparison.md`: rewrote S4's peer-reviewed basis to lead with ToG (the "LLM ⊗ KG" paradigm) rather than RoG.
- Updated `local-deployment.md`: added the Llama2-70B+ToG ≥ GPT-4+CoT empirical anchor for H5; added per-query LLM-call budget analysis (~10 calls × 3s/call ≈ 30s with quantized local LLM) showing the budget is reachable but tight; flagged ToG-R + SentenceBERT pruning as the efficiency lever if needed.
- Updated `unifying-llms-kgs.md`: confirmed Pan §6.2's placement of ToG is exact — pure Agents Reasoning, no fine-tuning component. ToG is the cleanest paradigm-3 anchor available.
- Updated `index.md` with new source-summary entry.
- **Open questions raised**: (1) is the manufacturing KG large enough to make ToG-style exploration meaningful, or so small that a single SPARQL CONSTRUCT returns the full subgraph; (2) tune $N$/$D_\max$ for typical asset→component→fault→SOP query depth (~3-4 hops); (3) ToG-R vs. full ToG default for local deployment — run both as ablations; (4) interaction with [[og-rag|S3]]'s ontology-hypergraph retrieval — orthogonal or competing.

## 2026-04-27 — Ingest: Reasoning on Graphs / RoG (Luo et al., ICLR 2024)

- Read `Reasoning_on_Graphs_RoG_2024.pdf` end-to-end including appendices (arXiv:2310.01061v2, 24 pages).
- Created source page `reasoning-on-graphs.md` covering: the planning-retrieval-reasoning framework (Eq. 1, Fig. 2); the joint instruction-tuning objective (Eq. 7) with planning loss = KL divergence vs. shortest paths in KG; implementation footprint (LLaMA2-Chat-7B, 2× A100-80GB, **38 hours**, 216k+30k+2k instruction examples); headline results (Hits@1=85.7/F1=70.8 on WebQSP, beating prior SOTA DECAF by +4.4%; Hits@1=62.6/F1=56.2 on CWQ, beating UniKGQA by +22.3% Hits@1 and +14.4% F1); plug-and-play planner (Table 3) showing the frozen planner gives unmodified downstream LLMs +8.5% (ChatGPT) to +119.3% (Flan-T5-xl) Hits@1 — **the strongest finding for the thesis**, since it shows the planner's value transfers without LLM fine-tuning; ablations confirming both planning and reasoning modules are necessary; transfer-to-MetaQA finding (38h → 2h via Freebase-pretrained init); the constrained-BFS retrieval algorithm (Algorithm 1) and the three reusable prompts (planning, reasoning, explanation).
- Updated `kg-agent-s4.md`: resolved the open question "how does RoG's relation-path planning map onto our SPARQL-tool agent" with a concrete RoG → S4 mapping table; cited the Table-3 plug-and-play result as the empirical anchor for skipping fine-tuning; verified the peer-reviewed-basis row for RoG.
- Updated `strategy-comparison.md`: marked RoG citation as "verified" and noted that S4 explicitly replaces RoG's 38h fine-tuning with schema-constrained prompting + SHACL gating.
- Updated `unifying-llms-kgs.md`: confirmed Pan's dual placement of RoG (§4.1.3 instruction-tuning + §6.2 agents reasoning) is precise — RoG's training is paradigm-1, its inference is paradigm-3.
- Updated `index.md` with new source-summary entry.
- **Open questions raised**: (1) does prompt-only relation-path planning from a small manufacturing ontology actually match RoG's fine-tuned planner quality? Flag for Phase 4 prompt-engineering experiments; (2) keep RoG's K=3 default for top-K plans, or tune for the manufacturing setting; (3) **KG-Agent (Jiang et al. 2024, arXiv:2402.11163)** is cited by RoG as the named "agent over KG" framework — not in `raw/`, worth chasing as a more direct S4 precedent.

## 2026-04-27 — Ingest: Unifying LLMs and KGs Roadmap (Pan et al., IEEE TKDE 2024)

- Read `Unifying_LLMs_KGs_Roadmap_Pan2024.pdf` end-to-end (arXiv:2306.08302v3, 26 pages including bibliography).
- Created source page `unifying-llms-kgs.md` covering: the yin-yang LLM/KG pros/cons (Fig. 1) that underwrites the thesis's motivation; the three-paradigm taxonomy KG-enhanced / LLM-augmented / Synergized (§3.1, Fig. 6) and its sub-categories; the explicit mapping of thesis S1-S4 onto Pan's taxonomy (S1 = paradigm 1 / Retrieval-Augmented Knowledge Fusion; S2 = paradigms 1+2 straddle; S3 = paradigm 1 / KG Instruction-tuning + KGs Prompting, closest cited cousin OntoPrompt; S4 = paradigm 3 / LLMs-as-Agents Reasoning, same bucket as ToG/RoG/StructGPT/KSL/KD-CoT); the §6.2 contrast between LLM-KG Fusion Reasoning and LLMs-as-Agents Reasoning (the latter being defended as the right S4 anchor); the §7 future directions that justify thesis design choices (§7.1 hallucination → SHACL, §7.2 knowledge editing → KG layer, §7.5 LLMs poor at graph structure → tool-calling agent, §7.6 bidirectional reasoning → S4 plan-retrieve-reason-validate); the Stage-1/2/3 milestone roadmap (Fig. 26) with MFG-AgentGraph as a Stage-2 system; gaps the thesis fills (no PROV-O, no SHACL, no SSN/SOSA, no local-deployment angle in Pan).
- Updated `naive-rag.md`: added Pan-paradigm placement (1 / Retrieval-Augmented Knowledge Fusion, degenerate text-only case).
- Updated `graphrag.md`: added Pan-paradigm placement (1 + 2 straddle — LLM both builds and uses graph), framed for **H2** (S3 vs. S2 expert-vs-LLM-built ontology).
- Updated `og-rag.md`: added Pan-paradigm placement (1 / KG Instruction-tuning + KGs Prompting); flagged **OntoPrompt (Ye et al. 2022, WWW)** as the closest cited precedent if OG-RAG PDF stays missing — viable substitute peer-reviewed reference.
- Updated `kg-agent-s4.md`: added Pan-paradigm placement (3 / LLMs-as-Agents Reasoning, the paradigm-3 anchor) with §6.2 quote defending agents over fusion; added §7.5 anchor justifying the LangGraph + SPARQL-tool design.
- Updated `strategy-comparison.md`: added Pan-paradigm row + closest-cousin row to the S1-S4 matrix.
- Updated `mfg-agentgraph.md`: added position-in-broader-literature section calling MFG-AgentGraph a Stage-2 Synergized system per Pan Fig. 26.
- Updated `shacl-validation.md`: added Pan §7.1 hallucination-detection anchor — SHACL as the *structural* answer to Pan's open future direction.
- Updated `prov-o.md`: added gap-vs-Pan section noting that Pan covers static interpretability (§4.4) but **does not cover provenance / audit trails** — PROV-O is genuinely additive vs. the canonical taxonomy paper.
- Updated `index.md` with new source-summary entry.
- **Open questions raised**: (1) whether to adopt Pan's three-paradigm vocabulary in the thesis literature review or keep S1-S4 internal; (2) whether to chase OntoPrompt (Ye 2022, WWW) into raw/ as an OG-RAG substitute; (3) whether CoK chain-of-knowledge (Pan ref [117]) should be a fifth comparator.

## 2026-04-27 — Ingest: GraphRAG Local-to-Global (Edge et al., Microsoft 2024)

- Read `GraphRAG_Local_to_Global_Microsoft_2024.pdf` end-to-end including appendices (arXiv:2404.16130, 26 pages).
- Created source page `graphrag-microsoft-2024.md` covering the two-stage pipeline (LLM-extracted entity-relationship-claim graph → hierarchical Leiden communities → bottom-up community summaries → map-reduce query answering), six experimental conditions C0-C3 + TS + SS, the LLM-as-judge evaluation with comprehensiveness/diversity/empowerment/directness criteria, the 125-question persona-based adaptive benchmark, headline results (72-83% comprehensiveness wins over vector RAG, C0 root-level achieves this with 97% fewer tokens than text-summarization), and the explicit gaps that motivate S3/S4 (no ontology, no SHACL, no PROV-O, exact-string entity matching only).
- Updated `graphrag.md`: replaced [NEEDS VERIFICATION] block with verified pipeline description and Leiden community-detection details; replaced expected-strengths block with empirical results from the paper; added configuration notes (8k context window beats larger; 600-token chunks); added concrete indexing cost (281 min on 1M-token corpus with `gpt-4-turbo`); resolved four open questions and added new ones grounded in the paper.
- Updated `ragas-metrics.md`: added "Caveat raised by GraphRAG authors" section noting that Edge et al. explicitly call faithfulness/answer-relevance/context-relevance "not relevant to global sensemaking", with two suggestions for how the thesis writeup should handle this tension. **This is a non-trivial methodological flag for RQ1.**
- Updated `kg-agent-s4.md`: added "Hybrid retrieval precedent: GraphRAG's own future-work proposal" section showing that S4's plan→KG-retrieve→vector-retrieve flow is structurally what the GraphRAG authors themselves proposed as future work in §6.2 — useful framing to defend S4's design as the natural next step from S2.
- Updated `index.md` with new source-summary entry.
- **Open questions raised**: (1) hierarchical Leiden behavior on a small MIMII-derived corpus (likely <100k tokens) — communities may be too few/coarse; (2) whether a manufacturing few-shot exemplar set can match S3's expert ontology coverage (directly relevant to **H2**); (3) which community level (C0/C1/C2/C3) to fix for thesis evaluation given dataset-dependent winners in the paper.

## 2026-04-27 — Ingest: RAG Comprehensive Survey (Gupta, Ranjan, Singh 2024)

- Read `RAG_Comprehensive_Survey_2024.pdf` end-to-end (arXiv:2410.12837).
- Created source page `rag-comprehensive-survey-2024.md`.
- Updated `naive-rag.md`: replaced [NEEDS VERIFICATION] block with survey-mediated attribution; added BM25/DPR/REALM retriever taxonomy; added implementation note distinguishing this survey from Gao et al. 2023's three-stage taxonomy; revised open questions.
- Updated `graphrag.md`: added related-variants section flagging CommunityKG-RAG and RAPTOR as honest comparators / fallback options.
- Updated `kg-agent-s4.md`: added Self-RAG self-correction precedent linking the SHACL repair loop to a peer-reviewed antecedent.
- Updated `index.md` with new source-summary entry.
- **Open question raised:** consider adding Gao et al. 2023 RAG survey to `raw/` if the Naive/Advanced/Modular taxonomy is needed for thesis writing.

## 2026-04-26 — Wiki bootstrap

- Initialized empty wiki. Read `raw/thesis-pitch-v2.md` and `raw/master-literature-index.md` end-to-end as the foundation.
- Created scaffolding: `index.md`, `log.md`, `templates/page-template.md`.
- Created summary page: `thesis-pitch.md`.
- Created concept stubs (skeleton + claims sourced from the pitch only; deeper sources to be ingested per-paper):
  - `mfg-agentgraph.md`, `research-questions.md`, `strategy-comparison.md`
  - `naive-rag.md` (S1), `graphrag.md` (S2), `og-rag.md` (S3), `kg-agent-s4.md` (S4)
  - `ssn-sosa.md`, `shacl-validation.md`, `prov-o.md`
  - `ragas-metrics.md`, `faithfulness.md`, `groundedness.md`
  - `mimii-dataset.md`, `anomaly-triage.md`
  - `local-deployment.md`, `langgraph-agent.md`, `fuseki-triplestore.md`
- All concept pages flag deep claims as `[NEEDS VERIFICATION]` until the corresponding source PDF is read.
- Next: ingest sources in priority order — RAG_Comprehensive_Survey_2024 → GraphRAG_Local_to_Global_Microsoft_2024 → Unifying_LLMs_KGs_Roadmap_Pan2024 → Reasoning_on_Graphs_RoG_2024 → Think_on_Graph_Sun2023 → Think_on_Graph_2_Hybrid_RAG_2024 → OG-RAG (note: not yet in raw/, see [[og-rag]]).
- 2026-05-15: Ran automated wiki health audit; updated `wiki/wiki-health.md`.

- 2026-05-15: Added automated wiki health workflow (`scripts/wiki_health.py`), fixed index metadata and missing index coverage, created alias/concept pages `wiki/think-on-graph-2.md`, `wiki/reasoning-on-graphs-rog-2024.md`, and `wiki/bm25-dpr.md`, and verified wiki health at zero structural issues.
- 2026-05-18: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-06-05: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-06-09: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-06-14: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-06-22: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-06-30: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-07-20: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-07-23: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-07-24: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-07-27: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-07-31: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-08-03: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-08-16: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-08-26: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-09-05: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-09-07: Recorded the accepted Issue #13 strict candidate-action JSON boundary in [[implementation-decisions]], updated [[index]], and documented its R4/RQ2/RQ3 mapping and verified test evidence.
- 2026-09-08: Added the Issue #14 deterministic resolver and contract tests, documented the public contract in README and wiki decision/index/log pages, and left raw sources, the private journal, and wiki-health.md unchanged.
- 2026-09-09: Ran the automated wiki health audit for Issue #16 documentation; structural checks passed, and the generated `wiki/wiki-health.md` refresh was reverted to keep the feature diff in approved scope.
- 2026-09-18: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-09-21: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-09-22: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-09-25: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-09-28: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-10-02: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-10-03: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-10-04: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-10-05: Added the Issue #22 deterministic Stage 10 PROV-O trace/write gate, focused and Architecture V1 acceptance tests, public contract and retention/access limitations, and the corresponding implementation decision; no dependency, service adapter, orchestrator, raw source, or persistent-storage guarantee was added.
- 2026-10-05: Ran the automated wiki health audit for Issue #22 documentation; structural checks passed, and the generated `wiki/wiki-health.md` refresh was reverted to keep the feature diff in approved scope.
- 2026-10-11: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-10-17: Added the Issue #26 deterministic vertical-slice conformance checkpoint to [[implementation-decisions]], separating executable R1–R5 contract evidence from fixture/in-memory substitutes, keeping R6 and empirical claims open, and identifying Issue #27 as the next service-adapter milestone; no runtime code, dependency, fixture, workflow, architecture revision, or raw source changed.
- 2026-10-17: Added the Issue #27 read-only Fuseki/SPARQL structured-retrieval adapter, named-graph TriG fixture, deterministic HTTP/semantic failure tests, separately gated live-service test, README service/failure contract, and [[implementation-decisions]] record. The fixture retriever remains unchanged; no dependency, lockfile, orchestrator, write/persistence path, Qdrant integration, frozen architecture page, navigation, or raw source changed.
- 2026-10-19: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-10-20: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-10-23: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-10-24: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-10-25: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-10-31: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-11-01: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-11-02: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-11-03: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-11-03: Added the Issue #32 shared immutable S1–S4 evaluation-record contract: controlled strategy configuration, run manifest, raw output, typed errors, canonical JSON, and explicit artifact applicability. This establishes R6 comparison infrastructure only; no dataset, metric, strategy implementation, benchmark result, dependency, or Architecture V1 deviation was added.
- 2026-11-05: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-11-05: Added [[project-status-2026-11-05]] with the live Implementation V1 state (S4 slice through Stage 10, harness contract #32, #33 as next gate), refreshed [[index]] project-spine entry, and demoted the 2026-09-05 status page to historical.
- 2026-11-05: Added the Issue #33 versioned anomaly-triage query set (`evaluation/anomaly_triage/query-set-v1.json`, 30 queries across seven categories with gold rubrics, expected evidence, and unsupported/unsafe traps), its dataset card, the `mfg_agentgraph.anomaly_triage_dataset` loader/validator with canonical SHA-256, and the required `dataset_sha256` run-manifest field; documented in [[implementation-decisions]] and the README evaluation section.
- 2026-11-06: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-11-06: Added the Issue #34 deterministic RQ metric suite (`src/mfg_agentgraph/evaluation_metrics.py`): typed `MetricObservation` inputs, eleven per-query RQ1–RQ3 metrics, RQ4 latency/peak-memory aggregates with nearest-rank percentiles, explicit `not_applicable` values with reasons, `METRIC_RQ` mapping, and a `DEFERRED_METRICS` record for LLM-judge and human-study measures; documented in [[implementation-decisions]] and the README.
- 2026-11-06: Added [[evaluation-roadmap]] fixing the S1–S4 execution order after #31–#34: S4 registration (#38) → S1 (#35) → OG-RAG ingest (#76) → S3 (#37) → S2 (#36) → independent annotation (#79) → abstention suite (#80) → pilot (#39) → benchmark (#40) → analyses (#41, #43, #45, #44, #47, #46, #42, #48) → synthesis (#49–#54); recorded the review-driven validity gates and the independent research/CI backlog.
- 2026-11-06: Registered S4 in the shared evaluation harness (Issue #38): `src/mfg_agentgraph/s4_evaluation_strategy.py` drives the production orchestrator, emits the shared record plus metric observation, derives artifacts from SHACL/bounded-repair events and PROV triples, keeps fail-closed runs countable, and documents the fixed candidate-action identity and trap-honesty limitation; recorded in [[implementation-decisions]] and the README.
- 2026-11-06: Registered the S1 naive-RAG baseline (Issue #35): `src/mfg_agentgraph/s1_naive_rag.py` provides a canonical-evidence-ID chunk, deterministic stopword-filtered lexical retrieval with tie-breaking, extractive answers, explicit `not_applicable` validation/provenance artifacts, and `insufficient_evidence` abstention; documented the document-evidence coverage ceiling in [[implementation-decisions]] and the README.
- 2026-11-06: Ingested OG-RAG (Issue #76) from `concept-paper/sources/2412.15235.pdf`: added [[og-rag-2024]] with the verified method (ontology-mapped factual blocks, flattening, hypergraph, greedy minimal-hyperedge retrieval), evaluation setup (agriculture/news, four LLMs, RAG/RAPTOR/GraphRAG baselines), reported results, and limitations; rewrote [[og-rag]] as the S3 page with the S4 gap stated from the source; corrected the "Soman et al., EMNLP 2025" attribution in [[strategy-comparison]], [[kg-agent-s4]], [[mfg-agentgraph]], and [[references-master]], and recorded the unresolved contradiction with `raw/thesis-pitch-v2.md` (left unedited).
- 2026-11-06: Registered the S3 ontology-grounded RAG baseline (Issue #37): `src/mfg_agentgraph/s3_ontology_rag.py` provides ontology-mapped factual blocks, asset/procedure scope filtering, key-side and value-side query relevance, bounded greedy hyperedge coverage with deterministic tie-breaking, and shared-record emission with `not_applicable` validation/provenance artifacts plus undefined SHACL/repair/provenance metrics; `check_s3_candidate_post_hoc` reports package SHACL results after the fact without altering the record. Promoted the single stopword-filtered tokenizer (`s1_naive_rag.tokenize_text`) and two harness helpers (`errors_from_events`, `dataset_sha256_from_configuration`) instead of copying them; recorded in [[implementation-decisions]], [[og-rag]], and the README, including the lexical-overlap and single-scenario limitations.
- 2026-11-06: Registered the S2 GraphRAG-style baseline (Issue #36): `src/mfg_agentgraph/s2_graphrag.py` builds a document-derived term-claim graph, detects communities by connected components, writes extractive per-community summaries with source chunk IDs, records build cost (duration, canonical bytes, counts) separately from query latency, digests the canonical index, binds each run to that digest, and map-reduces community summaries while marking validation/provenance `not_applicable`; promoted `split_sentences` for S1/S2 parity and documented the three deterministic substitutions in [[graphrag]], [[implementation-decisions]], and the README.
- 2026-11-06: Added the Issue #79 independent gold-annotation boundary: `evaluation/anomaly_triage/annotation-protocol-v1.md` defines primary sources, blinding, the three-class support verdict, collection, pre-adjudication agreement, adjudication, and prohibited uses; `src/mfg_agentgraph/gold_annotation.py` provides the blinded packet (`query_id` and `text` only, bound to `query_set_sha256`), strict submission validation (contract version, dataset/packet digests, exact query coverage, evidence/action invariants) and pairwise raw-agreement/Cohen's-κ/evidence-set reporting with explicit undefined-κ reasons; `src/mfg_agentgraph/annotation_cli.py` adds the `mfg-agentgraph-annotate` `packet`/`agreement` commands. `query-set-v1.json` is unchanged, no independent human labels exist yet, and the dataset card plus README now state that author labels remain non-independent until real submissions and an external independence attestation exist. Promoted `require_text` and `reject_duplicate_json_keys` in `anomaly_triage_dataset` instead of copying them; recorded in [[implementation-decisions]].
- 2026-11-06: Corrected the Issue #79 annotation contract after two independent reviews. Evidence citations are now canonicalized as sorted sets (order no longer fabricates disagreement), `build_agreement_report(submissions, *, packet)` re-validates digests and full query coverage so a partial set cannot be reported, same-annotator pairwise comparison is rejected, and the `mfg-agentgraph-annotate` CLI creates files exclusively and refuses an `--output` path that is any input — a mistyped command previously truncated a submission or the query set. Docstrings and messages no longer claim to validate independence, and the protocol now records the real provenance of the SOP chunk identifier, names the two-identifier corpus vocabulary neutrally, and fixes verdict precedence (`unsafe_request` → `supported` → `unsupported`). `query-set-v1.json` unchanged; evidence-identifier membership in a versioned source manifest remains approval-gated follow-up. Recorded in [[implementation-decisions]].
- 2026-11-06: Closed both Issue #79 review blockers in the branch. Added `evaluation/anomaly_triage/sources-v1.json` and `mfg_agentgraph.annotation_sources` to freeze the permitted annotation sources by SHA-256 and path; the packet (`…-packet-v2`), submissions, agreement report, and gold artifact now carry the manifest digest, and citations outside the manifest vocabulary are rejected. The KG fixture is excluded from the manifest so KG-derived labels can only be a cross-check. Added `mfg_agentgraph.human_gold` with adjudication and `mfg-agentgraph-human-gold-v1`, which refuses to emit while a dispute is unadjudicated and records the author view only as `author_label_cross_check`; added the CLI `gold` subcommand and `--sources`/`--root`. Recorded in [[implementation-decisions]]; human annotation itself is still outstanding, so #79 remains open.
- 2026-11-06: Corrected Issue #79 annotation integrity after two read-only reviews. `SourceArtifact` now verifies that its declared SHA-256 covers the text it carries and the packet no longer whitespace-normalizes source views, closing two false-provenance paths. The protocol, README, and dataset card no longer claim KG-dependent queries become `unsupported`; an SOP-only pack judges source adequacy, an unaddressable claim is *not assessable* rather than false, and SOP-only judgments are not promoted to gold for KG-dependent queries. The gold artifact declares `label_scope`, and `evaluation/anomaly_triage/source-adequacy-audit-v1.md` records an explicitly AI-authored 30-query adequacy review (5 directly supported, 12 partial, 10 not assessable, 3 operational-safety-not-validated) that is not human annotation. #79 stays open. Recorded in [[implementation-decisions]].
- 2026-11-06: Revised Issue #79 scope at the owner's direction, because the thesis has one available human and no second annotator. The independent-annotation requirement is recorded as **unmet** rather than waived: `src/mfg_agentgraph/synthetic_reference.py` and the committed `evaluation/anomaly_triage/synthetic-reference-v1.json` (`mfg-agentgraph-synthetic-reference-v1`) record each reference label, resolve every citation against the frozen scenario fixture and source manifest, and declare `independent_annotation: false`, `inter_annotator_agreement: null` and an `original_requirement_status` naming the unmet requirement. All 30 citations anchor (30 fixture_anchored, 0 unanchored); anchoring proves the citation resolves, not that the label is correct, and author bias is not removed. `require_reference_matches_run` binds a scored run to the reference dataset digest, and a test fails if the committed artifact drifts from its inputs. Recorded in [[implementation-decisions]] and reflected in [[evaluation-roadmap]].
- 2026-11-06: Completed Issue #79 against the revised single-author criteria and superseded the reference contract with `mfg-agentgraph-synthetic-reference-v2`. The artifact now binds `scenario_sha256` over the fixture's canonical bytes, anchors only **declared** resources (a predicate name is reported as reference-only and cannot anchor), and classifies an empty citation set as `not_applicable` rather than vacuously anchored: 26 fixture_anchored, 4 not_applicable, 0 unanchored. Added `mfg_agentgraph.synthetic_evaluation.score_reference_run`, which reuses `compute_query_metrics`/`summarize_run` instead of reimplementing metrics, fails closed on a mismatched dataset digest or query set, suppresses only label-derived metrics for unanchored entries, never suppresses run-measured SHACL/provenance/latency values, keeps `terminal_status_match` because it is contract-derived, and supports partial runs with an explicit `not_evaluated_query_ids` list. Both modules are at 100% statement and branch coverage. The original two-annotator requirement remains unmet and is reported as a thesis limitation. Recorded in [[implementation-decisions]].
- 2026-11-07: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-11-07: Added the Issue #80 abstention suite (`src/mfg_agentgraph/abstention_suite.py`, `mfg-agentgraph-abstention-suite-v1`). It classifies each evaluated query three ways on the registered traps — `correct_abstention` (the dataset contract's status), `wrong_abstention` (any other non-`passed` status, e.g. `provenance_failed_closed`) and `false_answer` (`passed`) — plus `answered`/`over_abstained` on answerable queries, and reports six rates re-derived from its own rows with numerator, denominator and an explicit not-applicable reason. After two independent read-only reviews the measurement consumes the strategy evaluation records rather than bare observations, so a report cannot label S1 results as S4; it verifies the record configuration, manifest digest, query-ID pairing, and recorded terminal status, carries the dataset identity and the full query-set ID universe with recorded per-query categories, checked complement for unevaluated queries, and exact suite equality against the dataset's trap subset, rejects forged counts, rates, evaluated IDs, and suite IDs, and marks `unsafe_refusal_recall` not applicable for arms without a validation gate (S1/S2/S3) instead of scoring 0.0. A `correct_abstention` is a contract-status match, not proof of intent. Measured deterministic baselines: S4 declines 0 of 4 traps with 4 false answers and 0.0 unsafe-refusal recall over 2 rated unsafe traps; S1 also declines 0 of 4 but over-abstains on 2 of 26 answerable queries while its refusal recall is not applicable. Model-backed abstention remains unmeasured and needs an explicitly configured, pinned model-backed strategy run. Documented in the README, the dataset card, and [[implementation-decisions]]; no strategy, dataset, fixture, metric, dependency, or `MetricName` changed.
- 2026-11-07: Delivery audit at `380197b`. Verified that the ten-stage S4 pipeline, S1–S4 harness arms, adapters and metric suite exist but the S4 path is fixture-only (fixture retrieval/generation, `retry_budget=0`, callback provenance), S1/S2/S3 are deterministic substitutes, embeddings/API/UI/compose/batch-runner/persisted results are absent, and the dataset is 30 queries over one asset and one SOP sentence. Created issues #113–#133 for the missing work: protocol and two-track scope, local service substrate, corpus with MIMII-vs-synthetic lineage, Pump_12-agnostic contracts, real embeddings, shared model invocation contract, hardware envelope, live S4, model-backed S1/S3/S2, artifact bundle and catalog, batch runner with stage-correlated resource sampling, FastAPI service, interface, independent annotation, expert auditability, acceptance-test reconciliation, packaged delivery, blinded held-out packet. Added [[delivery-roadmap]] as the authoritative order, marked [[evaluation-roadmap]] historical for measurement, recorded the RQ3 scope change in [[research-questions]], and commented sequencing corrections on #39, #40, #48, #54, #46, #79, #33, #34, #35, #38, #4 and #47. No code changed; no issues closed.
- 2026-11-07: Issue #113 froze `implementation-study-protocol-v1`: two named study tracks (paper scale vs explicitly fixture/synthetic feasibility), the free deployment envelope with verified licences and model digests (MIMII CC BY-SA 4.0; Qwen2.5-7B Apache-2.0; nomic-embed-text v1.5 Apache-2.0; Fuseki/Qdrant Apache-2.0; Ollama MIT), executable S1–S4 definitions with fixture arms labelled test-only, MIMII-vs-authored lineage rules, unmet human-evidence gates (#126, #127), a determinism/claims table and a licence manifest. Also fixed the `#122`↔`#133` dependency cycle (artifacts now depend on `#113` only) and removed an unsupported "single student cannot execute" claim from [[delivery-roadmap]].
- 2026-11-08: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-11-08: Clarified [[delivery-roadmap]] at the owner's direction: core backend and evaluation components precede the UI. Moved the local judge (#123) ahead of API/UI (#124/#125), without adding an architectural dependency or changing the frozen study protocol. Updated [[index]]. GitHub issues and implementation code were unchanged.
- 2026-11-08: Added the Issue #114 free local deployment substrate: `deploy/compose.yaml` pinning `secoresearch/fuseki:6.2.0`, `qdrant/qdrant:v1.19.2` and `ollama/ollama:0.23.2` by manifest digest on loopback-only ports with named volumes and healthchecks; `src/mfg_agentgraph/stack_config.py` as the single validated endpoint constructor that rejects non-loopback hosts; `stack_preflight.py` (`doctor`) as the readiness gate that fails non-zero on any endpoint, version or digest mismatch; `stack_bootstrap.py` with idempotent graph/collection/model setup that refuses to replace divergent data without `--recreate`; and `stack_cli.py` exposing `mfg-agentgraph-stack doctor|bootstrap|status`. Rejected `stain/jena-fuseki` because its newest tag is `5.1.0` and cannot serve the protocol's Fuseki 6.2.0. Live acceptance (green `doctor` from a fresh clone, restart persistence, compose healthchecks) is recorded as **unmet pending a live run** because Docker Desktop's WSL integration was disabled in the authoring environment. Recorded in [[implementation-decisions]]; no dependency, dataset, strategy or fixture changed.
- 2026-11-08: Live-verified the Issue #114 envelope against the pinned images (compose project `mfg-issue114-live`, loopback ports 23030/23333/31434) and corrected four deployment contracts. Verified: `POST /ds/sparql` returns SPARQL-results JSON while `/ds/query` returns 405, so the query service name is now configuration (`MFG_FUSEKI_QUERY_SERVICE`, default `sparql`); `GET /$/ping` returns an ISO timestamp, not `pong`; `GET /$/server` returns 401 without credentials and 200 with basic auth, so `MFG_FUSEKI_ADMIN_PASSWORD` is now a configuration input and a missing credential is an explicit authentication failure; bootstrap compares graphs with `rdflib.compare.isomorphic` and reports parser failures as typed `FAILED` steps. Live outcomes: first `bootstrap` created the factory graph (18 triples), the shapes graph (103 triples) and collection `procedural` (size 768); the second run reported `already_present` for all three, proving idempotency including blank-node SHACL shapes that round-tripped through Fuseki; a force-recreated Fuseki and Qdrant preserved both an RDF provenance marker and a stored vector point. Recorded in [[implementation-decisions]].
- 2026-11-09: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-11-09: Corrected Issue #114 after running the documented commands instead of reading them, and recorded it in [[implementation-decisions]]. Both Ollama services now bind `0.0.0.0:11434` inside the container (an in-container `127.0.0.1` bind made the loopback-published port unreachable) while host publication stays `127.0.0.1`; `deploy/fuseki/` is mounted read-only at `/fuseki-config` and seeded into `/fuseki-base` by the compose entrypoint, so the image's `sed -i` rewrite no longer mutates tracked files — and because Compose nulls the image CMD when a service sets `entrypoint`, the pinned image's command is repeated under `command:`; `mfg-agentgraph-stack` reads `deploy/.env` (or `--env-file`) when no environment is supplied with real variables winning, and derives each endpoint from `MFG_*_PORT` when no URL is given; model pulls use `pull_timeout_seconds` (default 3600 s) instead of the 5 s readiness timeout; `UrllibTransport` now refuses to follow 30x as its docstring always claimed; and `admin_password` is `repr=False`. The documented order is now bootstrap → doctor, in `README.md` and [[local-deployment]]. Model pins were re-verified by recomputing the registry manifest digests for `qwen2.5:7b-instruct-q4_K_M` and `nomic-embed-text:v1.5`.
- 2026-11-09: Two read-only reviews of the committed Issue #114 change produced one correctness fix and one boundary statement, recorded in [[implementation-decisions]]. A Qdrant collection's identity is now its width **and** distance: `bootstrap` and `doctor` refuse/fail an existing collection whose reported `distance` is not `Cosine`, where a `Dot`/`Euclid` collection of the right width had been accepted as `already_present`. [[local-deployment]] now states that loopback excludes remote hosts but not other local processes, and that the pinned services are unauthenticated for data-plane access (Fuseki data write/update on, no Qdrant API key, Ollama has no authentication), so the envelope is a single-operator stack and `--recreate` is not an authorization boundary. Live `doctor` afterwards reported `collection procedural size 768 Cosine`.
- 2026-11-09: Added the Issue #115 versioned scenario corpus (`evaluation/scenario-corpus-v1/`, contract `mfg-agentgraph-scenario-corpus-v1`) and recorded it in [[implementation-decisions]]. Lineage is enforced structurally — a MIMII-derived observation must carry its recording identity and declare the dataset label, assets and sensors can never be MIMII-derived, and licence governs bundling and chunking — which is what keeps synthetic plant context separable from real acoustic evidence. Composition: 28 licensed documents (four machine classes, 3 share-alike), 292 source-located chunks, 8 assets, 64 SSN/SOSA sensors, 1,612 observations (exactly 4 MIMII-derived), 4 procedures, 10 development-only queries, 12,413 triples. MIMII recordings were read out of the remote ZIP by byte range and accepted only on CRC32 and size, so the 31.86 GB archive was never downloaded. **The protocol's ~50-document target is unmet at 28**: four hosts refuse programmatic download and archive.org/OSTI hold no copies, so it is recorded as a shortfall rather than waived — the card and the decision record both say a Track A completeness claim is false until those documents are acquired. Linear slides have no industrial source, only open-hardware documentation. Live proof: `load` created the corpus-context graph with 12,413 triples while the factory and provenance graphs were untouched, and SPARQL confirmed 2 assets per class, a 1,600-row asset→sensor→observation join, and exactly 4 MIMII-derived events.
- 2026-11-09: Weekly curation: ran `uv run python scripts/wiki_health.py` and reviewed [[wiki-health]] (64 pages; no missing fields, RQ tags, wikilink targets, index entries, or orphan pages; 51 age-only warnings; no recent raw-folder changes flagged). No structural repairs were needed. Updated [[index]] with the review date; left stale-page dates and research content unchanged pending substantive review. No files in `raw/` were modified.
- 2026-11-09: Re-attempted the 13 document identities that [[scenario-corpus-v1]] records as unreachable and recorded the outcome in `evaluation/scenario-corpus-v1/acquisition-v1.json` (committed) rather than committing ~104 MB of third-party PDFs to `.cache/scenario-corpus/acquired/` (gitignored). Result: 11 complete documents (nine NRC valve reports, CDC/NIOSH 2019-124, USACE EM 1110-2-3105 **2020**), 2 partial (NAVEDTRA 14265A part 1 through Chapter 9; NAVEDTRA 14264A Chapter 9 only), 1 duplicate (cleaner-OCR 1994 USACE edition) and 3 clearly-labelled optional candidates. Diagnosis: the four hosts reject this egress at the CDN edge — even their homepages return Akamai 403 to `89.245.181.195` (Düsseldorf), and a managed Chromium load fails identically — so no user-agent workaround exists; Wayback playback of the official URLs served the original bytes, while its raw-stream `id_` modifier is throttled to 429. Two captures truncated at exactly 5,242,880 B were rejected and re-fetched, and seven of the nine NRC files were cross-checked against OSTI report numbers. The frozen release is unchanged and still has 28 documents: ingestion needs an approved `SOURCES` extension plus the per-document licence check, and NAVEDTRA 14265A's copyright-for-record-purposes statement plus NUREG/CR-6478's absent text layer (image-only scan) are recorded hazards.
- 2026-11-10: Included the acquired documents as [[scenario-corpus-v2]] at the owner's direction, leaving v1 byte-identical. `scripts/build_scenario_corpus.py` now takes `--version {v1,v2}` (default v1); v2 loads the frozen v1 release and appends the 11 declared documents from `evaluation/scenario-corpus-v2/sources-v2.json`, reusing the v1 documents, chunks, assets, sensors, observations, procedures and development queries verbatim. Composition: 39 document artifacts / 38 families, 418 chunks (126 added), 1,612 observations unchanged with exactly 4 `mimii_derived`, 13,405 triples; release digest `91f4894…`, development digest `9c16742…`. `--version v1 --verify` still reproduces `16a9568…` and all four v1 artifacts kept their digests. Nine documents rest on the NRC site permission rather than blanket federal authorship (contractor NUREG/CR reports can embed approved third-party material; text-only extraction excludes figures and quoted standards), CDC's copy is stated public domain, and USACE 2020 states unlimited distribution. NUREG/CR-6478 was image-only on both the NRC URL and its OSTI mirror, so a text layer was produced by real OCR (tesseract 5.5.0, 300 dpi, PyMuPDF overlay in a throwaway environment, no project dependency); its text is machine OCR and a quoted clause must be checked against the page image. The ~50-document target is **still unmet**: the two Navy manuals remain excluded as incomplete and linear slides still have no industrial source.
- 2026-11-10: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-11-13: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
- 2026-11-13: Finished Issue #115 with [[scenario-corpus-v3]] (`evaluation/scenario-corpus-v3/`, digest `0d732475…`), keeping v1 and v2 byte-identical. v3 adds ten verified families (SKAT India Mark II and III, PRACTICA rope pump, NAVEDTRA 14075/14259/14057, Voron 2.4R2, LulzBot TAZ 6, FarmBot Genesis v1.8, PrintNC v4) to reach **49 artifacts / 48 families, 528 chunks, 14,745 triples**, and replaces the authored layer: every non-trap development query now cites observation + procedure + entailing chunk, every procedure cites chunks that state the action and its reason, and the builder enforces that each authored claim quotes its chunk verbatim. Eleven unsupportable claims (fan inlet/outlet, pump cavitation and recirculation, valve gland inspection and depressurisation, slider guide cleaning and carriage play) were dropped rather than written up. `provenance_profile: complete` publishes source, extraction and MIMII recording identity into the corpus graph, which previously stopped at the document. Owner decisions recorded: the two USBR FIST manuals stay excluded because their own statement limits them to internal Bureau use (48 families against an *approximately* 50 target), Voron's repo-level GPL-3.0 and LulzBot's BY/BY-SA ambiguity take the conservative share-alike reading, and the observation layer stays unchanged so the triple count is still multiplicity-driven (9,600 of 14,745 triples are 1,600 duplicated nominal records) with no Track A scale claim. Five defects found by review and by running the loader were fixed with regression tests: a 1 MiB response cap that truncated every corpus graph read into a turtle syntax error, `corpus load` also bootstrapping the shapes graph, chunk `text_sha256` never being compared with the text, `--version v1` overwriting the frozen release, and a bare DOI serialised as a `file://` IRI.
- 2026-11-13: A second independent review of the Issue #115 branch found three remaining defects; all three are fixed and [[scenario-corpus-v3]] is **re-frozen** with digest `0c11ebe5…` (was `0d732475…`) at 14,761 triples, v1 and v2 still byte-identical. (1) The two HTML captures were not reproducible from an empty cache: their `source_sha256` identified a local multi-page capture while `download_uri` served a 404 (FarmBot) or a single page (PrintNC). `evaluation/scenario-corpus-v3-derived/derived-inputs-v3.json` now declares each origin, the per-component page URLs with segment digests in assembly order, and a committed `*.visible-text.txt` snapshot whose digest the build verifies; a tampered capture or text fails closed. (2) The graph bound an OCR-artifact hash to the NRC URL. A document whose extracted artifact is not the bytes its origin serves now carries a `derivation` record (`derivationKind`, `originUri`, `originSha256`, `derivationManifest`, `derivationEntry`, `derivedArtifactSha256`) — NRC citation → OSTI scan `cb14029b…` → OCR artifact `98bb723e…` → committed text — emitted as explicit predicates for `complete` releases only, so the frozen releases keep their bytes. (3) An authored procedure could declare `mimii_derived` lineage, and `load_authored_v3` did not require a non-trap query's observation to exist or to belong to the cited procedure's asset. Both are now build failures. Cold-cache proof: `--version v3 --verify --cache-dir /tmp/corpus-cold-v3` from an empty directory reproduced `0c11ebe5…`.
- 2026-11-13: Fixed the limitations recorded when #115 closed, in [[scenario-corpus-v4]] (issue #137): 1,608 of v3's 1,612 observations stated nothing but their own identifier, so 9,640 of 14,761 triples were repetition and the protocol's meaningful 10^4-triple clause stayed unmet. v4 keeps v3's evidence and authored layers byte-identical and rebuilds only the observation layer: 1,600 authored readings, each with a value in its sensor's unit, a scenario instant and an operating state from `baseline | transient | anomaly | recovery`, plus the four MIMII events, which may carry neither a value nor a timestamp because the dataset supplies neither. `identifier_only_observation_ids` is now empty (v3: 1,608), the CLI prints that count and the v4 build refuses to publish otherwise, and TriG exports `corpus:value` / `corpus:observedAt` / `corpus:operatingState`. Composition: 49 artifacts / 48 families, 528 chunks, 1,604 observations, 19,521 triples, release digest `218300e2…`. The values are declared synthetic fixtures — no manufacturer limit, diagnostic threshold or measured behaviour — and the triple-order clause is met as a scale statement only, with independent gold labels still unmet (#132, #126).
- 2026-11-14: Ran automated wiki health audit; updated `wiki/wiki-health.md`.
