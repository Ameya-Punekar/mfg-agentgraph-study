# Repository Governance

This document defines the professional GitHub operating model for `mfg-agentgraph`.

## Operating model

The repository follows trunk-based development:

- `main` is the protected trunk.
- Work normally happens in short-lived topic branches.
- Pull requests are the default review and merge unit.
- Squash merge is the default merge strategy.
- Branches are deleted after merge.

Because this is also a solo thesis workspace, the owner may explicitly request direct commits to `main`. Those direct commits still require validation, clean commit messages, and immediate push.

Implementation V1 additionally follows the mandatory Definition of Ready, user plan-approval gate, Definition of Done, journal capture, and per-issue reporting workflow in [`implementation-v1-issue-workflow.md`](implementation-v1-issue-workflow.md).

## Branch policy

Pattern: `<type>/<kebab-case-description>`.

Allowed types: `feat`, `fix`, `docs`, `research`, `experiment`, `ci`, `chore`, `refactor`, `test`.

Protected names:

- `main` — stable trunk only.
- `release/*` — future release snapshots only.
- `archive/*` — historical preservation only.

## Pull request policy

Every PR must include summary, motivation, thesis relevance or maintenance reason, changed areas, validation evidence, risk/rollback notes, and linked issue when applicable.

PRs touching thesis claims must state whether claims are cited, verified, or marked `[NEEDS VERIFICATION]`.

PRs touching experiments must include exact commands, data/config, metrics, and interpretation.

## Required checks

The baseline quality gate is:

```bash
python3 scripts/wiki_health.py
python3 scripts/repo_quality_check.py
```

GitHub Actions runs these checks on pull requests and `main`.

## Branch protection target

Recommended `main` protection:

- require pull request before merging;
- require at least one approving review where practical;
- require conversation resolution;
- require status checks to pass;
- require branch to be up to date before merge;
- restrict force pushes and deletions;
- allow squash merge;
- delete head branches after merge;
- keep repository private.

For this single-owner private thesis repo, admin enforcement can remain off so emergency owner-directed direct commits are possible.

## Labels

Standard labels:

- `type:bug`, `type:feature`, `type:docs`, `type:research`, `type:experiment`, `type:ci`
- `priority:high`, `priority:medium`, `priority:low`
- `status:needs-triage`, `status:blocked`, `status:ready`, `status:in-progress`
- `rq:RQ1`, `rq:RQ2`, `rq:RQ3`, `rq:RQ4`

## Release/versioning policy

Until implementation stabilizes, use milestone tags rather than semantic product releases:

- `concept-paper-v0.x`
- `thesis-prototype-v0.x`
- `evaluation-harness-v0.x`
- `submission/<venue>-<year>` for paper submission snapshots if needed.

Do not create a public release while the repository is private/unpublished unless the owner explicitly approves.

## Secrets and generated artifacts

- Secrets must stay out of tracked files.
- Generated PDFs and figures may be tracked when they are thesis deliverables.
- Large/generated artifacts should be separated from source changes where possible.
- Do not modify `thesis-wiki/raw/` casually; raw sources are evidence, not editable notes.

## AI-agent contribution rules

AI agents working in this repository must read `AGENTS.md`, read `thesis-wiki/wiki/index.md` before thesis claims, use tools for file/git/system facts, avoid hallucinated citations, mark uncertain claims `[NEEDS VERIFICATION]`, run validation, and commit or push only when the owner explicitly authorizes that action.
