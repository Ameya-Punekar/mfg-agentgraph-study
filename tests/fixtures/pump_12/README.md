# Pump_12 deterministic fixture contract

This directory contains the issue #8 deterministic Pump_12 fixture contract used by tests only.
It introduces fixture JSON for a frozen Pump Station 12 vertical-slice scenario without defining or
changing product code.

## Files

- `scenario.json` is the canonical valid/repair flow fixture.
- `failure_scenarios.json` lists deterministic invalid variants and their expected Architecture V1
  fallback intents.
- `README.md` documents the fixture contract and its boundary.

## Stable IDs

The scenario intentionally freezes canonical identifiers so future implementation issues can target
stable references without inventing new names. Important identifiers include:

- `ex:PumpStation_12` for the station.
- `ex:Pump_12` for the affected asset.
- `ex:Observation_Pump12_2026-05-18T14:03:00Z` for the UTC anomalous-sound observation.
- `ex:Procedure_InspectInletCavitation_Pump12` for the inlet/cavitation inspection procedure.
- `ex:EvidenceEdge_001` for KG evidence.
- `ex:SOP_Chunk_7` for document evidence.
- `ex:CandidateAction_Pump12_Incomplete_001` and
  `ex:CandidateAction_Pump12_Repaired_001` for the intentionally incomplete and repaired actions.
- `ex:EvidencePackage_Pump12_001`, `ex:ValidationReport_Pump12_001`, and
  `ex:ProvenanceTrace_Pump12_001` for release artifacts.

IDs are deterministic fixture values, not generated runtime identifiers.

## Frozen Architecture V1 scenario

The canonical scenario follows the frozen Architecture V1/paper example: an anomalous sound is
observed at Pump_12 at 14:03 UTC inside an explicit 2026-05-18 UTC anomaly window. The deterministic
candidate action is `Inspect the pump inlet of Pump_12 for cavitation`. SOP chunk `ex:SOP_Chunk_7`
supports inlet/cavitation inspection, and KG evidence `ex:EvidenceEdge_001` links Pump_12 to the same
procedure.

## Relationships

`ex:Pump_12` is located at `ex:PumpStation_12`. The anomaly observation references `ex:Pump_12`
and falls inside the explicit UTC anomaly window. KG evidence `ex:EvidenceEdge_001` links the pump
to `ex:Procedure_InspectInletCavitation_Pump12`; document evidence `ex:SOP_Chunk_7` links the SOP
chunk to the same procedure. The repaired candidate references the known target and both evidence
kinds. The expected evidence package links the repaired candidate, the validation report, and the
provenance trace.

The document evidence also freezes the generated index citation contract: repository-relative source
path `tests/fixtures/sop/pump12-sop.txt`, inclusive line range `1`–`1`, canonical source SHA-256
`3e538364b4d6a61f92e3bfd0976134865130063bdbcadd607cb203862957eecf`, and index contract version
`mfg-agentgraph-procedural-index-v1`. These values exactly match the canonical generated
`tests/fixtures/qdrant/pump12.json` artifact.

## valid/repair flow

The incomplete candidate deliberately lacks `target` and evidence references. The repaired candidate
is the deterministic valid form: it targets `ex:Pump_12` and carries both KG evidence
`ex:EvidenceEdge_001` and document evidence `ex:SOP_Chunk_7`. The validation report marks this
repaired candidate valid, and the provenance trace records the evidence package link with a successful
write result.

## failure variants

`failure_scenarios.json` contains exactly these deterministic variants. Each variant has exactly one
`prerequisite` string naming the single logical Architecture V1 condition broken by the variant, plus
exactly one machine-usable structured `mutation` object with `path`, `operation`, `expected_before`,
and `value` only when the mutation needs a replacement value. Mutation paths are
JSON-Pointer-like fixture operations tested against the canonical scenario, so each path resolves,
each `expected_before` matches the current fixture value, and each operation applies deterministically
to a copied scenario. The fallback intents below are
fixture-level Architecture V1 intent strings, not the issue #11 enum/API:

- `missing_target -> ask_operator_to_disambiguate`: breaks `resolved_target_asset` because the
  candidate action target is removed, so the operator must disambiguate the affected asset.
- `missing_observation -> insufficient_evidence`: breaks `observation_support` because the anomaly
  observation is removed, so the evidence base is insufficient for a recommendation.
- `missing_procedure -> unsupported_lower_ranked`: breaks `procedural_citation` because only SOP
  citation `ex:SOP_Chunk_7` is removed from the repaired candidate's authoritative `evidence_refs`
  list; procedure resources and SOP chunk remain intact, so the action is unsupported/lower-ranked
  rather than a missing-resource scenario.
- `invalid_evidence_package -> fail_closed`: breaks `complete_evidence_package` because the evidence
  package loses its validation-report link, so release must fail closed.
- `provenance_write_failure -> block_no_recommendation`: breaks `persisted_provenance_trace` because
  provenance write result changes from `success` to `failure`, so recommendation release is blocked
  and no recommendation is emitted.

These entries do not assert a final terminal-state enum.

## Boundary

This fixture JSON is test data, not final public CandidateAction/RDF/terminal-state API. It avoids
owning the public CandidateAction schema, RDF vocabulary, or terminal-state model reserved for later
implementation issues such as issue #11. Future work may map these deterministic fixture fields into
public contracts without silently changing the fixture contract tested here.
