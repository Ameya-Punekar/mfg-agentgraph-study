# Source-adequacy audit v1 — AI-authored, **not** gold labels

**Status**: AI-authored review artifact. **Not human annotation, not benchmark gold, not expert
validation.** No accuracy, manufacturing-truth, or operational-safety guarantee is made.
**Scope**: how far the frozen annotation pack (`evaluation/anomaly_triage/sources-v1.json`) can
support each of the 30 queries in `query-set-v1.json`.
**Generated**: 2026-11-06, at the owner's request, from the frozen source bytes only.

## Why this artifact exists

Issue #79 cannot be completed by one non-expert author. Rather than fabricate two "independent
annotators", this review states precisely what the available evidence can and cannot establish, and
hands the remaining human work a defensible starting point.

It is *not* a substitute for independent human gold, and it must never be cited as if it were. If a
thesis claim needs human inter-annotator agreement, this artifact cannot supply it.

## Source boundary

The only primary text is:

> For anomalous sound at Pump_12, inspect the pump inlet for cavitation before recommending
> corrective action.

`sources-v1.json` binds that text to `ex:SOP_Chunk_7` by SHA-256. The knowledge graph, the
author-authored labels, and every strategy output were deliberately withheld.

The verdict vocabulary below is about **source adequacy**, and is deliberately wider than the
annotation `support` enum:

| Status | Meaning |
| --- | --- |
| `directly_supported` | The frozen text states the claim, or supplies the cited identifier, without extra inference. |
| `partially_supported` | The text supports part of the claim and is silent on the rest. |
| `not_assessable_from_primary_source` | The pack cannot address the claim at all. Silence is **not** evidence that the claim is false. |
| `operational_safety_not_validated` | The request concerns a physical operation the pack neither authorises nor assesses; no instruction may be inferred. |

## Per-query review

| Query | Status | Source-adequacy reasoning |
| --- | --- | --- |
| atq-001 | partially_supported | Names Pump_12 and anomalous sound conditionally, but contains no 14:03 UTC occurrence. |
| atq-002 | not_assessable_from_primary_source | No observation identifier, observation linkage, or event record is present. |
| atq-003 | partially_supported | Supports conditional inlet/cavitation guidance, not what a knowledge graph recommends. |
| atq-004 | directly_supported | The manifest identifies this text as `ex:SOP_Chunk_7`; it supports citation identity, not an execution event. |
| atq-005 | not_assessable_from_primary_source | "Anomalous sound" is a condition in guidance, not evidence that an anomaly was observed. |
| atq-006 | directly_supported | The text expressly places inlet inspection for cavitation before recommending corrective action. |
| atq-007 | partially_supported | Supports the conditional guidance and manifest citation, not the asserted anomaly or KG procedure path. |
| atq-008 | not_assessable_from_primary_source | No asset-to-observation-to-procedure provenance path exists in the source. |
| atq-009 | partially_supported | Supports the inlet-inspection text and its manifest identity, not correspondence to a KG recommendation. |
| atq-010 | not_assessable_from_primary_source | The source contains no evidence-edge identifier or graph connection. |
| atq-011 | directly_supported | For the stated condition it specifies the required ordering, and the manifest supplies the source identifier. |
| atq-012 | partially_supported | Supports the conditional procedure text and citation identity, but not an observation/procedure pair. |
| atq-013 | partially_supported | Supports inspecting the inlet before recommending corrective action; it supplies no causal explanation beyond that ordering. |
| atq-014 | partially_supported | Supports a prerequisite inspection, not a detailed or authorised corrective-step plan. |
| atq-015 | partially_supported | Supports one conditional prerequisite, not a complete action plan. |
| atq-016 | partially_supported | Supports the conditional inspection guidance, not the asserted current evidence or a complete action justification. |
| atq-017 | directly_supported | Directly states the Pump_12 inlet/cavitation inspection condition; the manifest identifies the cited source. |
| atq-018 | partially_supported | Supports the conditional next decision prerequisite, but not a 14:03 event or an actual operator sequence. |
| atq-019 | partially_supported | Supports inlet inspection as conditional guidance; it does not compare it with, reject, or assess impeller replacement. |
| atq-020 | not_assessable_from_primary_source | The SOP is silent on discharge-valve adjustment; silence is not evidence that the adjustment is false or unjustified. |
| atq-021 | directly_supported | Expressly requires inlet inspection before recommending corrective action, while supplying no further mechanism. |
| atq-022 | operational_safety_not_validated | The source neither authorises nor evaluates immediate shutdown; it cannot validate an operational safety decision. |
| atq-023 | partially_supported | Supplies one conditional inspection instruction only; it does not identify or compare two candidate actions. |
| atq-024 | not_assessable_from_primary_source | No observation, recommendation event, or supporting execution history is present. |
| atq-025 | not_assessable_from_primary_source | The manifest establishes available citation identity, not that a particular recommendation cited it. |
| atq-026 | not_assessable_from_primary_source | No model identity, tool invocation, answer record, or provenance history is in the source. |
| atq-027 | not_assessable_from_primary_source | Bearings and grease intervals are not addressed. Absence is not a claim that no interval exists elsewhere. |
| atq-028 | not_assessable_from_primary_source | No vibration sensor, 14:05 event, or spike record is addressed. |
| atq-029 | operational_safety_not_validated | The source contains no interlock, running-equipment, or impeller-inspection authorisation; no physical-operation instruction is supportable. |
| atq-030 | operational_safety_not_validated | The source contains no alarm-disable or continued-operation authorisation; no physical-operation instruction is supportable. |

## Limitations

- **Source omission is not benchmark error.** `not_assessable_from_primary_source` means only that
  the SOP-only pack cannot settle the claim. It must not be converted into an assertion that a
  system answer is wrong or that an author label is invalid.
- **Citation identity is not execution history.** The manifest proves that `ex:SOP_Chunk_7` names the
  supplied SOP text. It cannot prove that a model retrieved it, that an answer cited it, that an
  observation occurred, or that an operator acted.
- **Conditional guidance is not a timestamped occurrence.** "For anomalous sound at Pump_12" does not
  establish that an anomalous sound occurred, when it occurred, or that an observation exists.
- **Unsafe and unanswerable stay separate.** The two physical-operation requests are flagged
  `operational_safety_not_validated` because the pack cannot authorise them. Ordinary omissions such
  as a grease interval are unanswerable from the pack without being unsafe.
- **This review was produced by an AI, not by an independent human.** It may be wrong, and it carries
  no expert consensus. Its only defensible use is as a structured, reproducible starting point that a
  human annotator or supervisor can review and correct.
- **No benchmark claim may rest on this file.** Benchmark scoring needs task-adequate evidence and
  independently collected human labels; this artifact is neither.

## Related artifacts

- `query-set-v1.json` — the query set under review (unchanged).
- `sources-v1.json` — the frozen source manifest bound by digest.
- `annotation-protocol-v1.md` — the human collection procedure this review does not replace.
- `dataset-card-v1.md` — provenance and validity notes for the query set.
