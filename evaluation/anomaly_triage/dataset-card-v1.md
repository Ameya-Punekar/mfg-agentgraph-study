# Dataset card — anomaly-triage query set v1

**Contract**: `mfg-agentgraph-anomaly-triage-dataset-v1`
**Dataset ID**: `mimii-pump12`
**Query-set ID**: `anomaly-triage-v1`
**Version**: `v1`
**Status**: versioned evaluation input for Implementation V1; no results reported.

## What this dataset is

Thirty operator questions about one anomaly-triage scenario at Pump Station 12, each with a
stable identifier, a difficulty category, expected evidence references, an expected action where
one is justified, and a one-line gold rubric. Four queries are traps: two request information the
corpus cannot support, and two request unsafe corrective action.

The query set is the unit of comparability for S1–S4. Every evaluation record must name the
dataset hash of the exact query-set bytes it ran against.

## Composition

| Category | Count | What it probes |
| --- | --- | --- |
| `single_hop` | 6 | direct asset, observation, procedure, and document facts |
| `multi_hop` | 6 | asset → observation → procedure → chunk paths |
| `action_plan` | 6 | what to inspect first and why, with expected support |
| `counterfactual` | 5 | why one action is preferred, and whether an alternative is supported |
| `provenance` | 3 | which observation, chunk, and invocation supported the answer |
| `trap_unsupported` | 2 | answerable-looking questions with no KG or SOP support |
| `trap_unsafe` | 2 | requests for unsafe or out-of-scope corrective action |

Gold labels are rubrics plus evidence references, not model answers: scoring decides whether an
answer satisfies the rubric and cites the expected evidence, not whether it matches a string.

## Provenance and source material

- **Anomaly source**: MIMII industrial machine-sound dataset (pump class) motivates the anomaly
  event; this version does not embed audio. The event is the frozen `Pump_12` fixture observation
  at `2026-05-18T14:03:00Z`.
- **Knowledge graph**: `tests/fixtures/fuseki/pump12.trig` — one asset, one observation, one
  procedure, one support edge (`ex:EvidenceEdge_001`), plus the SHACL-facing resource mappings.
- **Procedural corpus**: `tests/fixtures/sop/pump12-sop.txt` — one indexed chunk
  (`ex:SOP_Chunk_7`) from `SOP-PUMP-OPS-2026`.
- **Gold labels**: authored by the thesis author against those two artifacts.

## Leakage and validity notes

- The corpus is deliberately minimal: one SOP sentence and one KG edge. Category variety is
  therefore **behavioural** — phrasing, entity resolution, evidence demand, provenance demand,
  and traps — not topical. Thirty queries over one scenario is a pilot-scale set, not a benchmark
  of topical breadth.
- Because the labels were authored against the same artifacts the strategies retrieve, they are
  not independent. Issue #79 adds independent human annotation keyed by `query_id`; until then,
  gold agreement is author-defined.
- **Current status of independent annotation: not yet collected.** The collection procedure,
  blinding rules, submission contract, and pre-adjudication agreement reporting are defined in
  `annotation-protocol-v1.md` and implemented by `mfg_agentgraph.gold_annotation` plus the
  `mfg-agentgraph-annotate` CLI. Having the protocol is not evidence: no annotator submission or
  agreement report exists yet, and none may be simulated, model-generated, or author-authored.
  `query-set-v1.json` is unchanged by annotation work, and agreement is always reported against
  the exact `document_sha256` above.
- Evidence citations are validated against the frozen manifest at
  `evaluation/anomaly_triage/sources-v1.json`: the manifest digest is carried through packet,
  submission, agreement report, and gold artifact, and a citation outside its vocabulary is rejected.
- The manifest deliberately excludes this KG fixture, so an SOP-only pack judges source adequacy
  rather than the benchmark key. A KG-derived claim the pack cannot address is **not assessable**
  from it; that is not evidence that the claim is false or that an author label is wrong, and such
  judgments are not promoted to gold for KG-dependent queries. The gold artifact states this in
  `label_scope` and records the author view only in `author_label_cross_check`.
- `source-adequacy-audit-v1.md` is an **AI-authored** source-adequacy review, not human gold and not
  expert validation; it exists so the pack's limits are recorded rather than implied.
- **Reference labels in this version**: every query's reference label is recorded in
  `synthetic-reference-v2.json` (`mfg-agentgraph-synthetic-reference-v2`), which binds the query set,
  the source manifest, and the scenario fixture by digest. The 26 citable queries are
  `fixture_anchored`; the 4 trap queries cite nothing by contract and are `not_applicable`; none is
  `unanchored`. The artifact states `independent_annotation: false`. Anchoring is a provenance
  property, not evidence of correctness: it shows the citation exists, not that the fixture answers
  the query. A query citing an identifier that is referenced but never declared — a predicate name,
  for instance — does not anchor.
- Trap queries are genuine absences, not invented ones: their key terms appear nowhere in the SOP
  text or the KG fixture, and the loader requires traps to carry no evidence references.
- The four traps are also the **abstention suite**. `mfg_agentgraph.abstention_suite` derives them
  from this file rather than restating them, and reports per strategy whether a trap ended in the
  expected status (`correct_abstention`), in a different non-`passed` status (`wrong_abstention`),
  or `passed` (`false_answer`), plus over-abstention on the 26 answerable queries. Four queries is
  pilot scale: it probes whether abstention is measured and whether the failure is visible, not how
  a strategy behaves across adversarial phrasing breadth. A `correct_abstention` is a match on
  this dataset's expected status, not proof that a strategy recognised the request as unanswerable
  or unsafe, and `unsafe_refusal_recall` is only scored for arms with a validation gate. Growing
  the suite means a new query-set version, not an edit here.
- The unsafe traps expect `validation_failed_closed`, the V1 terminal status for an action that
  cannot pass validation and cannot be repaired within budget. This is the dataset's expected
  outcome, not a claim about any strategy's behavior.

## Versioning

- Any query text, category, label, or count change requires a new `version` and a new file
  (`query-set-v2.json`); files are never edited in place after a benchmark run cites them.
- The dataset hash is the SHA-256 of the canonical JSON document (sorted keys, compact
  separators), so reformatting the file does not change the hash but changing any value does.
- `EXPECTED_CATEGORY_COUNTS` and the trap terminal-status mapping live in
  `src/mfg_agentgraph/anomaly_triage_dataset.py`; loading a set with a different composition
  fails closed until the approved composition is updated deliberately.

## How to load

```python
from pathlib import Path

from mfg_agentgraph.anomaly_triage_dataset import load_query_set

query_set = load_query_set(Path("evaluation/anomaly_triage/query-set-v1.json"))
print(query_set.document_sha256)
```
