# Scenario corpus v2

**Summary**: The additive successor to [[scenario-corpus-v1]]: the same frozen v1 evidence layer with the 11 documents v1 recorded as unreachable appended, giving 39 document artifacts (38 families), 418 source-located chunks and 13,405 triples, still development-split only and still short of the protocol's ~50-document target.

**Sources**: `evaluation/scenario-corpus-v2/corpus-v2.json`, `corpus-v2.trig`, `sources-v2.json`, `dataset-card-v2.md`; `evaluation/scenario-corpus-v1/acquisition-v1.json`; `scripts/build_scenario_corpus.py`; [[scenario-corpus-v1]]; [[implementation-study-protocol-v1]]; GitHub issue #115.

**Last updated**: 2026-11-10.

**Thesis relevance**: RQ1 / RQ2 (RQ3 provenance and RQ4 local reproduction as prerequisites).

---

## What v2 is, and what it deliberately is not

v2 is **additive, not a rewrite**. The builder loads the frozen v1 release
(`load_corpus_release`) and appends supplemental documents declared in
`sources-v2.json`; the v1 documents, chunks, assets, sensors, observations, procedures and
development queries are reused verbatim. A v2 measurement therefore cites v1 evidence that
cannot drift underneath it, and `--version v1 --verify` still reproduces the v1 digest
`16a956886bc1ac0c64cd3a1861bcf14421b964dae0d0c880454784406ad936ad`.

| Element | v1 | v2 |
|---|---|---|
| Documents | 28 | 39 (38 families) |
| Chunks | 292 | 418 |
| Assets / sensors | 8 / 64 | 8 / 64 |
| Observations | 1,612 (4 `mimii_derived`) | 1,612 (4 `mimii_derived`) |
| Procedures / queries | 4 / 10 | 4 / 10 |
| Triples | 12,413 | 13,405 |
| Release digest | `16a9568…` | `91f48943414bb886e167924aca8caa2f9108e0d52f103f56eab90bbadd7ced76` |

The contract identifier stays `mfg-agentgraph-scenario-corpus-v1`; only the release version and
corpus id (`mimii-synthetic-context-v2`) move, because the document schema did not change.

## The 11 added documents

Nine NRC valve reports (NUREG/CR-4819 V1, CR-6478, CR-4692, CR-6819 V2, NUREG-1296, CR-4302
V1+V2, CR-5515, CR-5583), CDC/NIOSH 2019-124 (fan), and USACE EM 1110-2-3105 **2020** (pump).
All 9 NRC entries use the **NRC site permission**, not blanket federal authorship, because
contractor-prepared NUREG/CR reports can carry approved third-party material; only text is used
and figures, photos and quoted industry standards are excluded. CDC's copy states it is public
domain and may be freely copied; the USACE manual states unlimited distribution.

`doc:nrc-nureg-cr-6478` was image-only from both the NRC URL and its OSTI mirror, so a text layer
was produced by real OCR (tesseract 5.5.0 at 300 dpi, text laid over the untouched 55-page scan
with PyMuPDF in a throwaway environment, no project runtime dependency). It contributes 12
chunks, and its text is machine-OCR, so a quoted clause must be checked against the page image.

## Counting discipline

39 artifacts is **38 document families**, because `doc:usace-em-1110-2-3105-2020` supersedes the
1994 edition v1 already bundles. Neither number is "39 independent sources", and ~50 is **still
unmet**. The two Navy manuals stay out because they are incomplete (14265A part 1 to Ch 9;
14264A Ch 9 only), and linear slides still rest entirely on open-hardware documentation.

## Reproducing it

```bash
uv run python scripts/build_scenario_corpus.py --version v2           # build from the frozen v1 release
uv run python scripts/build_scenario_corpus.py --version v2 --verify  # JSON bytes + TriG graph isomorphism
uv run mfg-agentgraph-corpus load evaluation/scenario-corpus-v2/corpus-v2.json
```

The v2 build verifies the pinned SHA-256 of every supplemental artifact on every run (cached or
not), refuses a cached byte mismatch, refuses a supplemental document that yields no procedural
chunk, and refuses to overwrite a divergent versioned release. TriG is verified as a parsed graph
because rdflib does not serialise triples in a stable wire order.

## Prohibited claims

Track A completeness; "39 independent sources"; industrial decision quality, safety, operator
trust or field effectiveness; topical breadth beyond the listed documents; a complete
re-publication of any source manual; any held-out score before the blinded packet and independent
annotation exist.

## Related pages

- [[scenario-corpus-v1]]
- [[implementation-study-protocol-v1]]
- [[implementation-decisions]]
- [[mimii-dataset]]
- [[anomaly-triage]]
- [[delivery-roadmap]]
