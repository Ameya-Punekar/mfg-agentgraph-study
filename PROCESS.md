# How this project is built

The process is part of the work, so it is visible here rather than described in a pitch. This
describes how the work was carried out in the original private repository, at source commit
`6b0823560882`. The workflow below is that project's own policy as it stood: it is recorded here as
context for the snapshot, not as a request that anyone working with the snapshot adopt, enforce or
change it.

## One issue at a time, plan approved before code

Every change starts as a written plan and stops for approval before any implementation file is
edited. The plan has to name the technical concept, why the work comes now, the exact files and
modules, how it will be tested, what already exists (so new code or a dependency is justified), the
risks and rollback, and what evidence the work should produce. If discovery changes the scope
materially, the plan is revised and approved again.

The rule that makes this useful is the negative one: silence is not approval, and approval of a
different issue, or of a branch, is not approval of the implementation. It is written down in
[`docs/implementation-v1-issue-workflow.md`](docs/implementation-v1-issue-workflow.md).

## Test-first, then the smallest correct change

A failing behaviour test comes first, then the implementation that makes it pass. The gate is not
advisory:

```bash
uv run pytest                      # 2215 passed, 2 strict xfails; 92.30% combined branch-aware coverage
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy
python3 scripts/repo_quality_check.py
python3 scripts/wiki_health.py
```

The coverage floor is 90% with branch measurement enabled (`pyproject.toml`, over
`src/mfg_agentgraph`), so a regression fails the build rather than being noticed later. The two
expected-failure tests are strict xfails pending an acceptance-test reconciliation.

## Deterministic by default

Unit tests never touch the network. Live services are exercised only by separately gated
integration tests that **fail rather than skip** when unconfigured, because a silently skipped
integration test is a claim nobody checked. Local endpoints are constructed in exactly one place
(`stack_config.py`), which rejects non-loopback hosts.

## Contracts carry their own identity

Frozen artifacts are addressed by content digest, so a claim can name the exact bytes it was
measured on: the query set, the run manifest, the corpus release, the annotation packet and the
source manifest all carry SHA-256 digests that are re-verified on load. A run whose dataset digest
does not match is refused rather than scored.

## Scope is reduced loudly, never quietly

When a requirement turned out to be unmeetable, the repository recorded the shortfall instead of
substituting a weaker claim. The independence requirement for gold labels is the clearest case: one
annotator was available, not two, so the artifact ships as an explicitly non-independent synthetic
reference that states the unmet requirement in its own metadata. Where a reference entry cites
something that does not resolve against the frozen fixture or the source manifest, the metrics that
depend on that label are reported `not_applicable` with a reason rather than as numbers; metrics the
run itself measures — SHACL pass, repair iterations, provenance completeness, latency, memory — are
never suppressed.

Prohibited claims are tracked against the gate that would unlock them, so "planned" and "measured"
cannot be confused. See
[`docs/engineering-standards.md`](docs/engineering-standards.md).

## Research and implementation stay in one repository

Literature notes, decision records and derivation records live in a maintained wiki
(`thesis-wiki/wiki/`), structurally linted by `scripts/wiki_health.py`. Material implementation
decisions and deviations from the frozen architecture are appended to
`thesis-wiki/wiki/implementation-decisions.md` before merge, so the reasoning survives the code.

---

*This repository is a curated snapshot, taken at source commit `6b0823560882`, of an active private
working repository. It contains the implementation, tests, documentation and evaluation artifacts —
not the private development journal, the issue and review history, institutional material, or
third-party sources that are not redistributable.*
