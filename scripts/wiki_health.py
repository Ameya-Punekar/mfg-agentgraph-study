#!/usr/bin/env python3
"""Health audit for the MFG-AgentGraph thesis wiki.

Checks page format, RQ tagging, wikilink targets, orphan pages, stale update dates,
raw-folder safety, and index coverage. Writes wiki/wiki-health.md and exits 0 even
when issues are found so scheduled jobs can report without failing noisily.
"""
from __future__ import annotations

import datetime as dt
import os
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WIKI = ROOT / "thesis-wiki" / "wiki"
RAW = ROOT / "thesis-wiki" / "raw"
INDEX = WIKI / "index.md"
LOG = WIKI / "log.md"
OUT = WIKI / "wiki-health.md"
TODAY = dt.date.today().isoformat()
REQUIRED_FIELDS = ["**Summary**:", "**Sources**:", "**Last updated**:", "**Thesis relevance**:"]
RQ_RE = re.compile(r"RQ[1-4]")
LINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
DATE_RE = re.compile(r"\*\*Last updated\*\*:\s*([0-9]{4}-[0-9]{2}-[0-9]{2})")


def slugify_link(link: str) -> str:
    # Some older pages accidentally escaped wikilinks before the closing brackets
    # (e.g. [[prov-o\]]). Treat that as [[prov-o]] for linting rather than
    # creating a false missing-target issue.
    link = link.strip().replace("\\", "")
    if link.endswith(".md"):
        link = link[:-3]
    return link


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    pages = sorted(p for p in WIKI.glob("*.md") if p.name != OUT.name)
    page_names = {p.stem for p in pages} | {OUT.stem}
    contents = {p: read(p) for p in pages}
    index_text = read(INDEX) if INDEX.exists() else ""

    format_issues: list[str] = []
    rq_issues: list[str] = []
    stale_issues: list[str] = []
    missing_targets: dict[str, set[str]] = defaultdict(set)
    backlinks: dict[str, set[str]] = defaultdict(set)
    outgoing: dict[str, set[str]] = defaultdict(set)
    index_missing: list[str] = []
    raw_mutation_warnings: list[str] = []

    for p, text in contents.items():
        stem = p.stem
        if p.name in {"log.md"}:
            continue
        missing_fields = [f for f in REQUIRED_FIELDS if f not in text]
        if missing_fields:
            format_issues.append(f"{p.name}: missing {', '.join(missing_fields)}")
        # RQ mapping is required except index/log/references-master if broad bibliography.
        explicit_non_relevant = "**Thesis relevance**: None" in text
        if p.name not in {"index.md", "references-master.md"} and not explicit_non_relevant and not RQ_RE.search(text):
            rq_issues.append(f"{p.name}: no RQ1/RQ2/RQ3/RQ4 tag found")
        m = DATE_RE.search(text)
        if m:
            try:
                age = (dt.date.today() - dt.date.fromisoformat(m.group(1))).days
                if age > 90:
                    stale_issues.append(f"{p.name}: Last updated {m.group(1)} ({age} days old)")
            except ValueError:
                stale_issues.append(f"{p.name}: invalid Last updated date")
        elif p.name not in {"log.md"}:
            stale_issues.append(f"{p.name}: no parseable Last updated date")
        for raw_link in LINK_RE.findall(text):
            target = slugify_link(raw_link)
            outgoing[stem].add(target)
            if target in page_names:
                backlinks[target].add(stem)
            else:
                missing_targets[stem].add(target)
        if p.name != "index.md" and f"[[{stem}]]" not in index_text:
            index_missing.append(p.name)

    orphan_pages = []
    for p in pages:
        if p.name in {"index.md", "log.md"}:
            continue
        if not backlinks.get(p.stem) and f"[[{p.stem}]]" not in index_text:
            orphan_pages.append(p.name)

    # Raw folder should be immutable; flag markdown files modified recently as a review signal only.
    if RAW.exists():
        now = dt.datetime.now().timestamp()
        for p in RAW.rglob("*"):
            if p.is_file() and now - p.stat().st_mtime < 24 * 3600:
                raw_mutation_warnings.append(str(p.relative_to(ROOT / "thesis-wiki")))

    def section(title: str, items: list[str], ok: str) -> str:
        if not items:
            return f"## {title}\n\n{ok}\n"
        body = "\n".join(f"- {x}" for x in items[:80])
        more = f"\n- ... {len(items)-80} more" if len(items) > 80 else ""
        return f"## {title}\n\n{body}{more}\n"

    missing_lines = [f"{src}.md -> [[{t}]]" for src, tgts in sorted(missing_targets.items()) for t in sorted(tgts)]
    report = f"""# Wiki Health Report

**Summary**: Automated structural health audit for the MFG-AgentGraph thesis wiki.

**Sources**: Local markdown files in `wiki/`; raw source tree metadata only.

**Last updated**: {TODAY}.

**Thesis relevance**: RQ1 / RQ2 / RQ3 / RQ4.

---

## Snapshot

- Wiki pages checked: {len(pages)}
- Missing required field issues: {len(format_issues)}
- RQ tag issues: {len(rq_issues)}
- Missing wikilink targets: {len(missing_lines)}
- Orphan/index coverage issues: {len(orphan_pages) + len(index_missing)}
- Stale date issues: {len(stale_issues)}
- Recent raw-folder file changes flagged: {len(raw_mutation_warnings)}

"""
    report += section("Missing required page fields", format_issues, "No missing required field issues found.") + "\n"
    report += section("Missing RQ tags", rq_issues, "All checked pages contain at least one RQ tag.") + "\n"
    report += section("Missing wikilink targets", missing_lines, "All wikilinks resolve to existing wiki pages.") + "\n"
    report += section("Pages missing from index", index_missing, "All pages appear to be linked from the index.") + "\n"
    report += section("Orphan pages", orphan_pages, "No orphan pages detected by this structural check.") + "\n"
    report += section("Stale or invalid Last updated fields", stale_issues, "No stale/invalid Last updated fields detected.") + "\n"
    report += section("Recent raw-folder changes to review", raw_mutation_warnings, "No raw-folder files changed in the last 24 hours.") + "\n"
    report += """## Recommended maintenance workflow

1. Fix missing required fields before content expansion.
2. Add index entries for important pages not currently linked from `wiki/index.md`.
3. Create missing concept pages only when the concept is thesis-relevant; otherwise remove accidental wikilinks.
4. Re-run this script after edits:

```bash
python3 /mnt/d/master-thesis/scripts/wiki_health.py
```

## Related pages

- [[index]]
- [[research-questions]]
- [[strategy-comparison]]
"""
    OUT.write_text(report, encoding="utf-8")

    log_entry = f"\n- {TODAY}: Ran automated wiki health audit; updated `wiki/wiki-health.md`.\n"
    if LOG.exists():
        log_text = read(LOG)
        if log_entry.strip() not in log_text:
            LOG.write_text(log_text.rstrip() + log_entry, encoding="utf-8")

    print(f"Wrote {OUT}")
    print(f"Issues: fields={len(format_issues)} rq={len(rq_issues)} links={len(missing_lines)} index={len(index_missing)} orphans={len(orphan_pages)} stale={len(stale_issues)} raw_recent={len(raw_mutation_warnings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
