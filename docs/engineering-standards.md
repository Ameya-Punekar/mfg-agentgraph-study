# Engineering Standards

These standards apply to Implementation V1 code and its supporting automation. They are intentionally small: add a tool or abstraction only when it closes a demonstrated quality gap.

## Reuse-first ladder

Before writing code, stop at the first option that fully satisfies the requirement:

1. Does the change need to exist? If not, do not build it.
2. Does the repository already provide it? Reuse or extend that implementation.
3. Can the Python standard library solve it clearly? Prefer the standard library.
4. Can a native platform or protocol feature solve it? Use that feature.
5. Is an approved dependency already installed? Reuse it.
6. Is the correct solution genuinely small? Keep it small.
7. Only then add the minimum new implementation required.

Minimal does not mean careless. Never remove validation, deterministic failure handling, security controls, accessibility, evidence capture, tests, or Architecture V1 conformance to reduce line count.

This policy adapts the reuse-first reasoning in [Ponytail](https://github.com/DietrichGebert/ponytail). Ponytail is guidance, not a project dependency.

## Python baseline

- Python: 3.11 or newer.
- Environment and lock file: [uv](https://github.com/astral-sh/uv).
- Lint and format: [Ruff](https://github.com/astral-sh/ruff).
- Static types: strict [mypy](https://github.com/python/mypy).
- Tests: [pytest](https://github.com/pytest-dev/pytest).
- Coverage: branch coverage through [coverage.py](https://github.com/coveragepy/coveragepy), with a 90% minimum for `src/mfg_agentgraph` **and** a required per-file floor for `src/mfg_agentgraph/fixture_model_adapter.py` (90%). Check the module with:

  ```bash
  uv run coverage report --include=src/mfg_agentgraph/fixture_model_adapter.py
  ```

- Local staged checks: [pre-commit](https://github.com/pre-commit/pre-commit).
- Workflow security: [zizmor](https://github.com/zizmorcore/zizmor).

Historical paper and wiki utilities are outside the product-package coverage and strict-type gates. Code intended for runtime use belongs under `src/mfg_agentgraph`; tests belong under `tests`.

## Required local checks

Set up once:

```bash
uv sync --locked
uv run pre-commit install
```

Before pushing:

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy
uv run pytest
uv run coverage report --include=src/mfg_agentgraph/fixture_model_adapter.py
uv run zizmor .github/workflows
python3 scripts/wiki_health.py
python3 scripts/repo_quality_check.py
```

Do not lower a quality threshold merely to make a change pass. Fix the code or record a justified policy change.

## Test and coverage policy

- Write a failing behavior test before implementation code.
- Keep unit tests deterministic and independent of external services.
- Put service-dependent tests behind explicit integration markers when those services are introduced.
- Coverage is a floor, not a quality score by itself. Assertions must test behavior and failure cases rather than execute lines mechanically.
- Every bug fix must include a regression test.
- Product-code changes and their tests belong in the same pull request.

## Architecture and documentation

The frozen baseline is `thesis-wiki/wiki/architecture-v1-rage-kg-2026.md`.

- Map implementation changes to a V1 requirement, pipeline stage, or acceptance criterion.
- Record material implementation decisions and all V1 deviations in `thesis-wiki/wiki/implementation-decisions.md`.
- Do not silently rewrite Architecture V1 to match an implementation shortcut.
- Update README, contributor guidance, maintained wiki pages, and exact commands in the same pull request when behavior changes.
- Add a new documentation generator only when the existing Markdown/wiki workflow cannot meet a concrete publishing need. MkDocs is deliberately deferred.

## Pull requests

- Keep one purpose per pull request and prefer fewer than 500 changed lines excluding lock files and generated artifacts.
- Use the pull-request template completely.
- Required checks are `repo-quality` and `code-quality`.
- Merge only by squash after all required checks and conversations are resolved.
- Do not commit generated PDFs, archives, figures, or unrelated thesis artifacts with implementation work unless the pull request explicitly owns them.

## Dependency policy

- Start with no runtime dependency.
- Add a dependency only when the standard library and installed dependencies do not meet a concrete requirement.
- Explain the dependency, license, maintenance signal, and removal cost in the pull request.
- Commit `uv.lock` and let Dependabot propose grouped weekly updates.
- Never auto-merge a dependency update before the complete required-check set passes.
