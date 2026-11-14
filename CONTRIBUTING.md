# Contributing and Repository Workflow

This repository uses a professional, lightweight trunk-based workflow suitable for a solo thesis project assisted by AI agents, while still keeping industry-style quality gates.

## Golden rules

1. `main` must stay releasable/readable.
2. Every meaningful change must be committed and pushed once the owner explicitly approves those actions.
3. Prefer pull requests for normal work; use direct `main` commits only when the owner explicitly asks for immediate changes.
4. Do not commit secrets, tokens, API keys, private credentials, or local machine caches.
5. Never modify `thesis-wiki/raw/` unless explicitly ingesting source material under owner direction.
6. Run validation before merge or direct push.

## Branch naming

Branches must be lower-case kebab-case and follow:

```text
<type>/<short-description>
```

Allowed types:

| Type | Use for | Example |
|---|---|---|
| `feat` | New product/research-code feature | `feat/prov-trace-export` |
| `fix` | Bug fix | `fix/wiki-health-paths` |
| `docs` | Documentation, README, paper text | `docs/concept-paper-trim` |
| `research` | Literature/wiki/research-note work | `research/tog-2-verification` |
| `experiment` | Evaluation harnesses, benchmarks, runs | `experiment/rq1-s1-s4-baseline` |
| `ci` | GitHub Actions, lint, automation | `ci/repo-quality-checks` |
| `chore` | Maintenance, config, cleanup | `chore/repo-labels` |
| `refactor` | Code restructuring without behavior change | `refactor/sparql-client` |
| `test` | Tests only | `test/wiki-health-regressions` |

Rules:

- Use ASCII lowercase letters, numbers, and hyphens.
- Keep names short but meaningful.
- Include an issue number when one exists: `fix/42-wiki-health-date-parser`.
- Avoid personal names, vague names, and long sentences.

## Commit messages

Use Conventional Commits:

```text
<type>(optional-scope): short imperative summary

Optional body explaining why the change was needed.
```

Recommended types: `feat`, `fix`, `docs`, `research`, `experiment`, `test`, `ci`, `chore`, `refactor`.

Examples:

```text
docs: add professional repository governance
research(rq3): summarize PROV-AGENT trust queries
experiment(rq1): add S1 baseline config
ci: run wiki health in pull requests
```

## Pull request workflow

1. Start from the updated base branch — `main` for general work, or `feat/implementation-v1` for Implementation V1 issues (see `docs/implementation-v1-issue-workflow.md`):

   ```bash
   git checkout main            # or: git checkout feat/implementation-v1
   git pull origin HEAD
   git checkout -b docs/example-change
   ```

2. Make focused changes.
3. Run local checks:

   ```bash
   uv sync --locked
   uv run ruff check src tests
   uv run ruff format --check src tests
   uv run mypy
   uv run pytest
   uv run zizmor .github/workflows
   python3 scripts/wiki_health.py
   python3 scripts/repo_quality_check.py
   ```

4. Commit and push when the owner approves:

   ```bash
   git add path/to/intended-file path/to/related-test
   git commit -m "docs: describe example change"
   git push -u origin HEAD
   ```

5. Open a PR into the same base branch (`main`, or `feat/implementation-v1` for Implementation V1 issues).
6. Fill every relevant section of the PR template. Start it with `Closes #<issue>` so the merge closes the issue; use `Maintenance only` when no issue applies.
7. Wait for checks to pass.
8. Squash merge. The head branch is deleted automatically by the repository's `delete_branch_on_merge` setting.

## PR size and review expectations

Keep PRs reviewable:

- Preferred: under 500 changed lines excluding generated artifacts.
- Separate literature/wiki updates from code implementation when possible.
- Separate large generated PDFs/images from source changes when possible.
- Every PR should explain thesis relevance: RQ1/RQ2/RQ3/RQ4 or project maintenance.

Review checklist:

- Scope is focused and matches title/body.
- No secrets or credentials are included.
- `thesis-wiki/raw/` is not modified unexpectedly.
- Wiki pages use required metadata, citations, RQ tags, and wikilinks.
- Claims are cited or marked `[NEEDS VERIFICATION]`.
- Concept-paper text does not imply completed empirical results unless backed by experiment artifacts.
- Validation commands were run and results are reported.
- New product behavior has a test that failed before the implementation was added.
- `src/mfg_agentgraph` branch coverage remains at least 90% without assertion-free coverage gaming.
- The change follows the reuse-first ladder in `docs/engineering-standards.md` and introduces no speculative abstraction or dependency.
- Material Implementation V1 decisions or deviations are recorded in `thesis-wiki/wiki/implementation-decisions.md`.

## Minimal implementation policy

Use the first option that fully meets the requirement: do nothing, reuse repository code, use the standard library, use a native platform feature, reuse an installed dependency, or add the minimum new code. Minimality never justifies dropping validation, security, deterministic failures, provenance evidence, tests, or Architecture V1 conformance.

Runtime implementation belongs under `src/mfg_agentgraph`; deterministic tests belong under `tests`. Historical paper and wiki utilities are not part of the product coverage gate. Add dependencies only for a concrete task, explain the trade-off in the PR, and commit the updated `uv.lock`.

The complete policy and commands are in `docs/engineering-standards.md`.

## Merge policy

- Default merge method: squash merge.
- Merge commits are disabled for normal work to keep history clean.
- Rebase merge is allowed only for maintainers when a linear history is useful.
- Head branches are deleted automatically on merge (`delete_branch_on_merge` is enabled for the repository).
- Auto-merge may be used after required checks pass.
- Required checks are `repo-quality` and `code-quality`; do not bypass them for normal work.

## Issue workflow

Use issues for non-trivial work items with labels such as `type:bug`, `type:feature`, `type:research`, `type:experiment`, `type:docs`, `priority:high`, `status:needs-triage`, and `rq:RQ1` through `rq:RQ4`.

Good issue titles:

```text
research: verify ToG 2.0 source and update S4 claims
experiment: implement RQ1 S1 baseline evaluation config
fix: prevent wiki health from accepting stale index entries
```

## Thesis wiki rules

For files under `thesis-wiki/wiki/`:

- Keep `Summary`, `Sources`, `Last updated`, and `Thesis relevance` metadata.
- Keep RQ mapping explicit.
- Cite source filenames and arXiv/DOI where possible.
- Use Obsidian wikilinks.
- Append `thesis-wiki/wiki/log.md` after material wiki changes.
- Run `python3 scripts/wiki_health.py`.

For files under `thesis-wiki/raw/`:

- Treat as immutable source evidence.
- Do not edit existing raw sources.
- Add new raw material only intentionally and preserve provenance.

## Experiments

For every experiment, record date, git commit, data/config, exact command, metrics, interpretation, and next steps.

Prefer reproducible scripts/configs over notebook-only work.

## Direct-to-main exception

Direct pushes to `main` are acceptable only when the repository owner explicitly requests immediate setup/checkpoint work. Even then:

1. run checks;
2. commit with a clear Conventional Commit message;
3. push immediately;
4. summarize exactly what changed and what validation passed.
