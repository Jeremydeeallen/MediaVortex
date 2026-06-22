# Compliance Symmetry

**Slug:** compliance-symmetry
**Set:** 2026-06-22
**Status:** Active -- phase: NEEDS_PLAN
**Reference:** `docs/superpowers/specs/2026-06-22-compliance-symmetry-design.md` (canonical design)

## Outcome

Implement the design specified in `docs/superpowers/specs/2026-06-22-compliance-symmetry-design.md`. The "target keeps moving for compliance" cycle stops: once a file becomes Compliant, no profile tweak silently re-enters it into a queue. Per-profile compliance bars are immutable after Finalize; tweaks happen via Copy-as-new-draft. Three orthogonal compliance verticals (Video / Container / Audio) each evaluate against the cascade-resolved bar; `WorkBucket` derives from the three booleans with explicit NULL handling. CommandBuilder emits the minimum-scope op set per bucket so no worker can push a file into a higher-cost bucket post-replacement.

The slow E2E suite (`Tests/Contract/TestE2EPerBucket.py -m slow`) is the live verification gate -- all 4 tests pass green against the live worker fleet.

## Carry-forward from `harness-drift-fixes` (closed 2026-06-22 via supersession)

| Inherited criterion | Source |
|---|---|
| All 4 slow E2E pass green | `harness-drift-fixes` C5 (full) |
| BypassReplace -> FileReplaced=True within 60s | `harness-drift-fixes` C6.1 |
| VMAF queue drains, no >15min stuck rows | `harness-drift-fixes` C6.2 |
| Remux fixture passes compliance gate (no `ComplianceGateFailed`) | `harness-drift-fixes` C6.3 |
| `pytest.mark.slow` registered in `pyproject.toml` | `harness-drift-fixes` C7 |

## Acceptance Criteria (placeholder -- finalized at NEEDS_PLAN exit)

Criteria are drafted at NEEDS_PLAN. The spec's "Verification Plan" table names the contract tests; each acceptance criterion will cite one row of that table. Draft outline:

- **Schema**: `ALTER TABLE Profiles` + `ALTER TABLE AudioNormalizationConfig` + redefined `MediaFiles.WorkBucket` generated column all land idempotently; the seeded `_PreMigrationDefault` profile is queryable.
- **Vertical refactor**: `VideoVertical`, `AudioVertical`, `ContainerVertical` read per-profile columns; no library-wide rules tables consulted; legacy savings/BPP/mvtrust paths deleted.
- **Lifecycle**: API + GUI honor Draft -> Finalized -> Retired. Locked compliance fields refuse PATCH; "Copy as new draft" produces an editable clone.
- **GUI**: `/Setup -> Profiles` editor renders Draft vs Finalized states; new `/MediaFile/<id>/ComplianceSummary` view exists; `MaxAudioChannels` moves to `/AudioNormalization`.
- **Idempotency**: three surface queries return 0 in steady state.
- **Slow E2E**: all 4 tests in `Tests/Contract/TestE2EPerBucket.py -m slow` pass green against live worker fleet.
- **Dialog Boost behavior**: existing shipped contract (Original = LRA preserved, Dialog Boost = LRA compressed to <=11.0 LU, both loudnorm'd to `TargetIntegratedLufs`, Dialog Boost `disposition.default=1`). Operator-locked 2026-06-22.

## Files (placeholder -- finalized at NEEDS_PLAN exit)

Per the spec's "Schema Changes" + "Verification Plan" + "Migration / Rollout" sections, the file roster includes:

- `Scripts/SQLScripts/AlterProfilesAddComplianceColumns.py` -- NEW
- `Scripts/SQLScripts/AlterAudioNormalizationConfigAddMaxChannels.py` -- NEW
- `Scripts/SQLScripts/RedefineWorkBucketGeneratedColumn.py` -- NEW
- `Scripts/SQLScripts/SeedPreMigrationDefaultProfile.py` -- NEW
- `Scripts/SQLScripts/RenameLegacyComplianceRulesTables.py` -- NEW (renames `VideoComplianceRules` + `ContainerComplianceRules`)
- `Features/VideoEncoding/VideoVertical.py` -- refactor: drop savings/BPP/mvtrust; read per-profile bar with NULL-aware bitrate check
- `Features/AudioNormalization/AudioVertical.py` -- refactor: per-profile codec/bitrate check; defer channel count to `AudioPolicyAdmissionGate`
- `Features/AudioNormalization/AudioPolicyAdmissionGate.py` -- add `MaxAudioChannels` read from `AudioNormalizationConfig`
- `Features/ContainerFormat/ContainerVertical.py` -- drop `AcceptableAudioCodecsCsv`; per-profile container compare only
- `Features/Profiles/ProfileController.py` -- new endpoints: `/finalize`, `/copy-draft`; PATCH immutability enforcement
- `Features/Profiles/ProfileRepository.py` -- new columns reads/writes; lifecycle state
- `Features/Profiles/Models/TranscodeProfileModel.py` -- new fields
- `Features/MediaFile/ComplianceSummaryController.py` -- NEW endpoint `/api/MediaFile/<id>/ComplianceSummary`
- `Features/MediaFile/templates/ComplianceSummary.html` -- NEW view
- `Templates/Settings.html` -- profile editor Draft/Finalized split; pre-migration finalize pass UX
- `Templates/AudioNormalization.html` -- add `MaxAudioChannels` knob
- `pyproject.toml` -- register `pytest.mark.slow`
- 8 new contract tests under `Tests/Contract/` per the spec's Verification Plan table
- `transcode.flow.md` -- Stage 4 + Stage 7 prose pruned (consolidation continued from the 2026-06-22 doc consolidation commit)

## R18 overrides

(none yet -- add lines `<path>` here if full reads of `*.feature.md` files are needed during NEEDS_DOC_PREREAD)

## Status

NEEDS_PLAN. The plan is fleshed out by reading the spec, picking the exact criterion wording for each test in the Verification Plan, and naming the final `## Files` list. No open operator-input items remain -- all decisions are locked in spec section "Decisions Made During Tightening (2026-06-22)".
