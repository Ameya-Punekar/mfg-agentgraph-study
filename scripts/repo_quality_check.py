#!/usr/bin/env python3
"""Repository governance and safety checks for MFG-AgentGraph.

This check intentionally avoids third-party dependencies so it can run locally,
in WSL, and in GitHub Actions.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CODEOWNERS",
    "docs/repository-governance.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/feature_request.yml",
    ".github/ISSUE_TEMPLATE/research_task.yml",
    ".github/ISSUE_TEMPLATE/config.yml",
    ".github/workflows/repo-quality.yml",
    "scripts/wiki_health.py",
]

FORBIDDEN_TRACKED_PATTERNS = [
    re.compile(r"(^|/)\.env($|\.)"),
    re.compile(r"(^|/)auth\.json$"),
    re.compile(r"(^|/)id_rsa($|\.)"),
    re.compile(r"(^|/)id_ed25519($|\.)"),
]

SECRET_LINE_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|password|passwd|token)\s*[:=]\s*['\"]?[A-Za-z0-9_./+=:-]{12,}"),
    re.compile(r"ghp_[A-Za-z0-9_]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
]

TEXT_EXTENSIONS = {
    ".md", ".txt", ".py", ".yml", ".yaml", ".json", ".toml", ".ini", ".cfg",
    ".sh", ".bib", ".tex", ".rst",
}


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def tracked_files() -> list[str]:
    result = run(["git", "ls-files", "--cached", "--others", "--exclude-standard"])
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise SystemExit(result.returncode)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def check_required_files(errors: list[str]) -> None:
    for rel in REQUIRED_FILES:
        if not (ROOT / rel).is_file():
            errors.append(f"missing required repository governance file: {rel}")


def check_forbidden_tracked_files(files: list[str], errors: list[str]) -> None:
    for rel in files:
        normalized = rel.replace(os.sep, "/")
        for pattern in FORBIDDEN_TRACKED_PATTERNS:
            if pattern.search(normalized):
                errors.append(f"forbidden tracked credential/local file: {rel}")


def check_secret_like_lines(files: list[str], errors: list[str]) -> None:
    for rel in files:
        path = ROOT / rel
        if not path.is_file():
            # Tracked paths can be deleted in the working tree before the
            # deletion is staged; there is nothing to scan for those.
            continue
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        if "raw" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            for pattern in SECRET_LINE_PATTERNS:
                if pattern.search(stripped):
                    lowered = stripped.lower()
                    if any(word in lowered for word in ["example", "placeholder", "your-secret", "redacted", "<", "xxxx"]):
                        continue
                    errors.append(f"possible secret in {rel}:{i}: {stripped[:120]}")


def check_readme_content(errors: list[str]) -> None:
    readme_path = ROOT / "README.md"
    readme = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""
    required_terms = ["MFG-AgentGraph", "RQ1", "RQ2", "RQ3", "RQ4", "thesis-wiki", "wiki_health.py"]
    for term in required_terms:
        if term not in readme:
            errors.append(f"README.md missing required term: {term}")


def check_branch_name(errors: list[str]) -> None:
    branch = os.environ.get("GITHUB_HEAD_REF") or os.environ.get("GITHUB_REF_NAME")
    if not branch:
        result = run(["git", "branch", "--show-current"])
        branch = result.stdout.strip() if result.returncode == 0 else ""
    if not branch or branch in {"main", "HEAD"}:
        return
    allowed = re.compile(r"^(feat|fix|docs|research|experiment|ci|chore|refactor|test)/[a-z0-9][a-z0-9-]{1,80}$")
    if not allowed.match(branch):
        errors.append(
            "branch name does not match <type>/<kebab-case-description>; "
            f"got {branch!r}"
        )


def main() -> int:
    errors: list[str] = []
    files = tracked_files()
    check_required_files(errors)
    check_forbidden_tracked_files(files, errors)
    check_secret_like_lines(files, errors)
    check_readme_content(errors)
    check_branch_name(errors)

    if errors:
        print("Repository quality check failed:")
        for err in errors:
            print(f"- {err}")
        return 1

    print("Repository quality check passed.")
    print(f"Files scanned: {len(files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
