# Implementation V1 Issue Workflow

This document defines the mandatory planning and completion gate for every MFG-AgentGraph Implementation V1 issue. It applies before code, tests, schemas, configuration, CI, evaluation, or maintained documentation are changed.

The purpose is to keep implementation aligned with the frozen Architecture V1 baseline, make one issue understandable at a time, and preserve reproducible thesis evidence.

## Operating rule

Implementation V1 proceeds sequentially:

1. Update `feat/implementation-v1` from its remote counterpart.
2. Select the next dependency-ready GitHub issue.
3. Create one short-lived issue branch from the current `feat/implementation-v1` commit.
4. Post the issue plan described below.
5. Wait for explicit user approval.
6. Implement only the approved scope.
7. Validate, review, document, and commit the focused change.
8. Request separate approval before creating or editing a pull request.
9. After the issue is integrated into `feat/implementation-v1`, create the next issue branch from that updated integration branch.

Do not stack a later issue on an unintegrated issue branch unless the user explicitly approves that dependency and workflow.

## Definition of Ready

An issue is ready for implementation only when all applicable items are true:

- [ ] The issue has one concrete outcome and acceptance criteria.
- [ ] Its prerequisite issues are complete, or the remaining dependency is explicitly accepted.
- [ ] The affected Architecture V1 requirements (`R1`–`R6`), S4 pipeline stages, and research questions are identified.
- [ ] In-scope and out-of-scope work are explicit.
- [ ] Likely files and modules have been inspected rather than guessed.
- [ ] The reuse-first ladder in `docs/engineering-standards.md` has been applied.
- [ ] The test-first or documentation-validation strategy is stated.
- [ ] Risks, rollback, and potential Architecture V1 deviations are identified.
- [ ] The private-journal record has been started and its parent-repository exclusion verified.
- [ ] A plan comment has been posted on the GitHub issue.
- [ ] The user has explicitly approved that plan.

If any required item is false, keep the issue in `status:planned` or `status:blocked`; do not make the tracked implementation change.

## Required issue plan comment

Post a concise comment containing all of the following sections:

```markdown
## Implementation plan — awaiting explicit user approval

### Concept this issue teaches
<Explain the technical or research concept in plain language.>

### Why this comes now
<Identify prerequisites and why this is the next dependency-ready issue.>

### Proposed focused changes
1. <Exact file/module and intended change.>
2. <Exact file/module and intended change.>

### Architecture V1 / RQ mapping
<Name affected R1-R6 requirements, S4 stages or comparison strategies, and RQ1-RQ4. State "No expected Architecture V1 deviation" or summarize the proposed deviation.>

### Test-first / validation strategy
<Failing behavior test first, or exact validation for documentation/config-only work.>

### Reuse-first / minimal-code decision
<State what already exists and why new code or a dependency is or is not necessary.>

### Risk and rollback
<State likely failure modes, scope boundaries, and how to revert safely.>

### Private journal capture
<State the decisions, commands, failures, tests, metrics, and RQ/chapter evidence to record.>

**Approval gate:** no tracked implementation files will be edited until the user explicitly approves this plan.
```

The plan must name exact files where inspection makes that possible. If discovery changes the scope materially, stop, revise the issue plan, and obtain approval again.

## What counts as approval

Approval must clearly authorize the posted plan, for example:

- `Approve issue #12 plan.`
- `Proceed with the plan you posted on issue #12.`
- `Approved, including the proposed dependency.`

The following do not approve implementation:

- silence or lack of response;
- a request to explain the issue;
- approval of a different issue or earlier plan;
- a generic backlog priority decision;
- approval to create a branch, commit, push, or open a pull request when the implementation plan itself has not been approved.

Approval applies only to the posted scope. A material scope, architecture, dependency, data-contract, evaluation, or risk change requires a revised plan and renewed approval.

## Rules while implementation is in progress

- Keep one issue branch and one focused change set.
- Explain meaningful checkpoints to the user: what changed, why, evidence, and next action.
- For behavior changes, follow red-green-refactor: first demonstrate a failing behavior test, then implement the minimum passing behavior.
- Keep product code and its tests in the same issue.
- Do not add a dependency unless the approved plan justifies why repository code, the Python standard library, platform features, and installed dependencies are insufficient.
- Do not silently alter Architecture V1 to fit an implementation shortcut.
- Record failures as `observed failure → root cause → fix → verification → lesson` in the private journal.
- Never place private-journal content, secrets, credentials, or private reasoning in public issues, commits, PRs, or tracked repository files.
- Never modify `thesis-wiki/raw/` as part of implementation work.

## Architecture V1 decisions and deviations

Update `thesis-wiki/wiki/implementation-decisions.md` before merge when a change affects a material implementation choice or deviates from the frozen Architecture V1 contract.

A material decision includes changes to:

- component or stage boundaries;
- public interfaces or persisted contracts;
- candidate-action schemas, RDF mappings, ontology use, or SHACL behavior;
- bounded repair, terminal states, or fail-closed behavior;
- evidence-package or provenance requirements;
- evaluation comparability, metrics, datasets, or deployment assumptions;
- security, privacy, reproducibility, or local-deployment guarantees.

A deviation record must state the Architecture V1 expectation, implemented behavior, reason, alternatives, risks, RQ impact, evidence, and whether Architecture V2 should revisit it. An unapproved deviation blocks completion.

Mechanical formatting, typo fixes, and implementation details that preserve the approved public contract can remain in the issue and private session record.

## Definition of Done

An issue is done only when all applicable items are true:

- [ ] Every acceptance criterion is satisfied with evidence.
- [ ] The final diff contains only the approved issue scope.
- [ ] New behavior was test-driven and regression cases cover discovered failures.
- [ ] Relevant tests, formatting, linting, typing, branch coverage, repository checks, and workflow security checks pass.
- [ ] Architecture V1 requirement, pipeline-stage, and RQ mappings are visible in the issue/PR evidence.
- [ ] Material decisions and Architecture V1 deviations are documented and approved.
- [ ] No unnecessary dependency, abstraction, or speculative feature was added.
- [ ] No secret or credential was added.
- [ ] `thesis-wiki/raw/` is unchanged.
- [ ] The private session record contains branch and commit identity, commands, results, failures/fixes, limitations, and next step.
- [ ] The private version/evidence pages are updated when the work yields milestone or thesis evidence.
- [ ] The private journal is committed only in its local nested repository, has no unapproved remote, and remains absent from parent Git status.
- [ ] The focused parent-repository commit is identified.
- [ ] CI is verified for the exact pushed commit when the branch is pushed.
- [ ] The user receives a completion report before work begins on the next issue.

## Validation matrix

Run only applicable checks, but explain every omission:

```bash
python3 scripts/wiki_health.py
python3 scripts/repo_quality_check.py
git diff --check
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy
uv run pytest
uv run zizmor .github/workflows
```

`scripts/wiki_health.py` updates maintained health artifacts. Review any generated diff and either include it as explicitly approved scope or restore it before completion; validation must not smuggle unrelated generated changes into an issue.

Always verify the immutable-source and privacy boundaries:

```bash
git status --short -- thesis-wiki/raw
git check-ignore -v thesis-wiki/private-development-journal/index.md
test -z "$(git ls-files thesis-wiki/private-development-journal)"
git status --short --branch
if git -C thesis-wiki/private-development-journal rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git -C thesis-wiki/private-development-journal remote -v
else
  printf '%s\n' 'Private journal is not present in this checkout.'
fi
```

Documentation-only work may omit product-code checks when no code, test, Python configuration, dependency, or workflow file changed. The completion report must say which checks were omitted and why.

## Completion report to the user

After each issue, report:

1. the concept implemented;
2. branch and final commit;
3. exact files changed;
4. behavior or process now available;
5. tests/checks and concise results;
6. Architecture V1 and RQ impact;
7. private-journal record and privacy verification;
8. known limitations or deferred work;
9. the next dependency-ready issue and its plan gate status.

Do not create a pull request, merge, delete a branch, or start the next issue merely because implementation was approved. Follow the repository's separate authorization boundaries for those actions.
