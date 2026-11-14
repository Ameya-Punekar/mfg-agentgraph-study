# Project Status — 2026-07-20

**Summary**: Current RAGE-KG 2026 submission-candidate status: retained V1/V2 comparison, validated CEUR-ART package, publication architecture work, open human metadata, closed PR state, and Hermes thesis-agent environment.

**Sources**: `concept-paper/publication/rage-kg-2026/README.md`; `concept-paper/publication/rage-kg-2026/manuscript.md`; `concept-paper/publication/rage-kg-2026/manuscript-v2.md`; `concept-paper/publication/rage-kg-2026/revision-justification.md`; `concept-paper/publication/rage-kg-2026/submission-checklist.md`; `concept-paper/publication/rage-kg-2026/latex/ceurart-main.pdf`; RAGE-KG 2026 call for papers at https://2026.rage-kg.org/; local Git/config/validation checks on 2026-07-20.

**Last updated**: 2026-07-20.

**Thesis relevance**: RQ1 / RQ2 / RQ3 / RQ4.

---

## Executive status

The MFG-AgentGraph RAGE-KG 2026 submission candidate is content-complete and locally buildable. The registered abstract remains unchanged. The manuscript specifies an architecture and falsifiable evaluation protocol; it does not claim completed empirical findings. `manuscript.md` preserves the pre-review V1 baseline, `manuscript-v2.md` preserves the reviewed submission candidate, and the generated LaTeX source reflects V2. (source: `concept-paper/publication/rage-kg-2026/manuscript.md`; `concept-paper/publication/rage-kg-2026/manuscript-v2.md`; `concept-paper/publication/rage-kg-2026/revision-justification.md`)

The CEUR-ART PDF builds successfully, has 12 A4 pages, embeds all fonts, contains no Type 3 fonts, and has no unresolved citations or cross-references in the final pass. The citation audit resolves all 32 cited keys. (source: local `build_ceur_pdf.py`, `audit_citations.py`, `check_braces.py`, `pdfinfo`, and `pdffonts` runs on 2026-07-20)

## Venue, deadline, and track

- Venue: RAGE-KG 2026, co-located with ISWC 2026 in Bari, Italy, 25–26 October 2026. (source: https://2026.rage-kg.org/)
- Abstract deadline: 17 July 2026 AoE; the abstract is recorded as registered. (source: task context; `concept-paper/publication/rage-kg-2026/README.md`)
- Paper deadline: 24 July 2026 AoE. (source: https://2026.rage-kg.org/)
- Notification: 17 August 2026; camera-ready: 1 September 2026. (source: https://2026.rage-kg.org/)
- The call lists full research papers at 7–12 pages and short research papers at 3–6 pages. The current comprehensive 12-page PDF is therefore labeled **full research paper**. (source: https://2026.rage-kg.org/; `concept-paper/publication/rage-kg-2026/latex/ceurart-main.pdf`)
- The EasyChair record must be checked before upload. If it is locked to short paper, a separate 3–6-page cut is required. [NEEDS VERIFICATION]

## Canonical submission artifacts

- Package root: `concept-paper/publication/rage-kg-2026/`.
- Comparison baseline: `manuscript.md` (pre-review V1).
- Current submission candidate: `manuscript-v2.md` (reviewed V2).
- Expert review: `expert-review-v2-2026-07-20.md`.
- Review response: `revision-justification.md`.
- Generated CEUR source: `latex/ceurart-main.tex`.
- Validated PDF: `latex/ceurart-main.pdf`.
- Reproducible build: `scripts/build_ceur_pdf.py`.
- Readiness record: `submission-checklist.md`.

## Review findings resolved

The final candidate addresses the expert review's main methodological risks. SHACL validity is scoped to encoded structural/evidence constraints rather than truth or safety; provenance-write failure is fail-closed; PROV-O remains the trace contract while PROV-AGENT-style concepts are optional specializations; S1–S4 differences are interpreted as approximate incremental evidence rather than causal proof; RQ3 is expert-assessed auditability rather than operational trust; and planned dataset sizes are targets rather than empirical facts. (source: `concept-paper/publication/rage-kg-2026/revision-justification.md`; [[shacl-validation]]; [[strategy-comparison]]; [[prov-o]])

PROV-AGENT is conservatively cited as arXiv:2508.02866. Unverified IEEE proceedings metadata was removed from the submission bibliography rather than asserted. (source: `concept-paper/publication/rage-kg-2026/source/references.bib`)

## Work completed on 2026-07-20

Four commits were created and pushed on `rage-kg-deep-eval-fixes`:

1. `df62b1d` added the expert-reviewed V2 manuscript.
2. `56b64b0` finalized and validated the RAGE-KG package: review reports, revision justification, 12-page CEUR-ART PDF, reproducible build scripts, self-contained submission archive, citation fixes, checklist, and this dated wiki status page.
3. `d1da8f9` restored a visible V1-versus-V2 comparison instead of overwriting the baseline manuscript.
4. `20f8e67` added the publication architecture figure in editable SVG plus print PDF/PNG/HTML and a detailed flow specification.

A later visual-refinement pass remains local and uncommitted: `latex/figure-architecture.tex` and `visuals/fig1_architecture.png` are modified, while three SVG variants are untracked. These edits must be reviewed, validated in the rebuilt PDF, and either committed or discarded before the branch is considered clean. (source: local Git status and log on 2026-07-20)

## Remaining human-supplied blockers

1. Confirm that EasyChair uses the full-research-paper track. [NEEDS VERIFICATION]
2. Obtain verified e-mail addresses for Ameya Punekar and Juergen Bock. [NEEDS VERIFICATION]
3. Add verified ORCID iDs if available. [NEEDS VERIFICATION]
4. Authors confirm name spelling/order, affiliation, and corresponding-author assignment. Faizan Ali is currently marked corresponding author using the e-mail already present in project source. [NEEDS VERIFICATION]
5. Perform a final human visual read and inspect the PDF downloaded back from EasyChair after upload.

## Scope deliberately deferred

Diagram redesign, visual restyling, and Canva work were explicitly deferred and were not performed in this completion pass. Existing figure sources were not edited. The PDF builder uses temporary build-only float-placement substitutions solely to compile the existing figures with the local CEUR/TeX toolchain. (source: user instruction; `concept-paper/publication/rage-kg-2026/scripts/build_ceur_pdf.py`)

## S1–S4 consistency

- S1 = [[naive-rag]]: vector-only retrieval plus LLM generation; no graph, agent loop, SHACL, or provenance.
- S2 = [[graphrag]]: LLM-built graph/community-summary retrieval; no expert ontology, SHACL, or provenance.
- S3 = [[og-rag]]: expert ontology / ontology-guided retrieval baseline; no agentic validation loop or PROV-O evidence package.
- S4 = [[kg-agent-s4]]: proposed KG-agent with SPARQL + vector retrieval, SHACL validation/repair, and PROV-O / PROV-AGENT-style traces.

This consistency matters across RQ1–RQ4: retrieval and answer quality (RQ1), ontology/SHACL contribution (RQ2), auditability and provenance usability (RQ3), and local deployment viability (RQ4). (source: [[strategy-comparison]]; [[research-questions]])

## Wiki health today

The automated audit checked 56 wiki pages and found zero missing fields, RQ-tag issues, broken wikilinks, orphan/index-coverage issues, or stale dates. It flagged 79 `raw/` files solely because their worktree timestamps are recent; `git status -- thesis-wiki/raw` is empty, so no tracked raw source was modified in this worktree. Treat this as a worktree-metadata false positive rather than content mutation. (source: `wiki/wiki-health.md`; local Git status on 2026-07-20)

## Agent environment status

The active thesis profile currently uses `openai-codex` / `gpt-5.6-sol` for the main agent, `gpt-5.5` for delegation and heavier auxiliary work, and `gpt-5.4-mini` for lighter session-search, skills, approval, MCP, and title tasks. Its ordered continuity fallbacks are OpenAI Codex `gpt-5.5` then `gpt-5.4-mini`. The `context-mode` MCP server is enabled and its server/SQLite FTS5 tests pass, but the installed v1.0.162 is behind v1.0.169 and its Claude-style `PreToolUse` hook check fails because `~/.claude/settings.json` is absent; this does not block the currently exposed MCP tools. (source: active thesis `config.yaml` and `context-mode doctor` on 2026-07-20)

## Repository identity hygiene

A Git audit found inconsistent commit-embedded identities: 12 reachable commits use the reversed name `Punekar Ameya` with a placeholder `example.com` address, one verified main-branch commit uses `Ameya Punekar`, and seven commits named `Faizan Ali` use the `Ameya-Punekar` GitHub noreply address and are therefore attributed by GitHub to the `Ameya-Punekar` account. The WSL global and repository-local identity is now set to the canonical `Ameya Punekar` name with the GitHub-linked noreply address for future commits. Existing commit objects were not rewritten because rewriting published history changes hashes and requires force-pushing; the intended ownership of the seven `Faizan Ali` commits must be confirmed before any historical correction. (source: local `git log --all`, `git config --show-origin`, and GitHub commit API on 2026-07-20)

## Branch and PR

The branch `rage-kg-deep-eval-fixes` is pushed through commit `20f8e67`. GitHub PR #3, which targeted the long-running `evaluation` branch, is currently **closed**. No replacement PR has been created. The worktree is not clean because the later figure-refinement files and this status refresh are still uncommitted. (source: local Git and GitHub PR metadata on 2026-07-20)

## Related pages

- [[index]]
- [[research-questions]]
- [[strategy-comparison]]
- [[naive-rag]]
- [[graphrag]]
- [[og-rag]]
- [[kg-agent-s4]]
- [[shacl-validation]]
- [[prov-o]]
- [[wiki-health]]
- [[project-status-2026-06-22]]
