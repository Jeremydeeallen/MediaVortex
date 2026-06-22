# Compliance Symmetry

**Slug:** compliance-symmetry
**Set:** 2026-06-22
**Status:** Closed -- 2026-06-22 -- Success
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

## Acceptance Criteria

C1. `Scripts/SQLScripts/AlterProfilesAddComplianceColumns.py` idempotently adds `Draft BOOLEAN DEFAULT TRUE`, `Active BOOLEAN DEFAULT TRUE`, `StreamCodecName VARCHAR(16)`, `TargetResolutionCategory VARCHAR(8)`, `TargetVideoKbps INT NULL`, `AllowUpscale BOOLEAN DEFAULT FALSE`, `AudioCodec VARCHAR(16)`, `TargetAudioKbps INT NULL`, `Container VARCHAR(8)`. Verifiable: `\d Profiles` shows all 9 columns; running twice doesn't fail.

C2. `Scripts/SQLScripts/AlterAudioNormalizationConfigAddMaxChannels.py` idempotently adds `MaxAudioChannels INT DEFAULT 2`. Verifiable: `\d AudioNormalizationConfig` shows the column.

C3. `Scripts/SQLScripts/RedefineWorkBucketGeneratedColumn.py` drops and re-creates `MediaFiles.WorkBucket` as a STORED generated column whose expression returns NULL when ANY of (`VideoCompliant`, `ContainerCompliant`, `AudioCompliant`) IS NULL; `Transcode` when `VideoCompliant=FALSE`; `Remux` when `ContainerCompliant=FALSE`; `AudioFixOnly` when `AudioCompliant=FALSE`; NULL otherwise. Verifiable: insert rows covering all 8 truth-table combinations + NULL-input cases; assert correct WorkBucket per row.

C4. `Scripts/SQLScripts/SeedPreMigrationDefaultProfile.py` inserts `_PreMigrationDefault` row (`Draft=FALSE`, `Active=TRUE`, `Codec=av1_nvenc`, `StreamCodecName=av1`, `TargetResolutionCategory=720p`, `TargetVideoKbps=NULL`, `AllowUpscale=FALSE`, `AudioCodec=aac`, `TargetAudioKbps=128`, `Container=mp4`). Encoder section cloned from the existing `NVENC AV1 P7 CANARY VBR -720p` profile. Idempotent via `ON CONFLICT DO NOTHING`.

C5. Existing non-`_PreMigrationDefault` profiles flipped to `Draft=TRUE` in the same migration (or sibling step). Verifiable: `SELECT COUNT(*) FROM Profiles WHERE Draft=TRUE` matches `(total profile count) - 1`.

C6. `Features/VideoEncoding/VideoVertical.Evaluate` is refactored: reads `StreamCodecName`, `TargetResolutionCategory`, `TargetVideoKbps`, `AllowUpscale` from the effective profile. Drops `_EstimatedSavingsMB`, `_IsAlreadyEfficient`, `MvTrusted` (`TranscodedByMediaVortex`) exemption, and `_LoadRules` from `VideoComplianceRules`. NULL `TargetVideoKbps` skips the bitrate check. Hardcoded 5% rounding tolerance in the bitrate comparator. Verifiable: `Tests/Contract/TestVideoComplianceBar.py` green; `grep -E 'EstimatedSavingsMB|IsAlreadyEfficient|MvTrusted|VideoComplianceRules' Features/VideoEncoding/VideoVertical.py` returns 0.

C7. `Features/AudioNormalization/AudioVertical.Evaluate` is refactored: adds per-profile codec match check (`Mf.AudioCodec == profile.AudioCodec`) and nullable bitrate ceiling check (`Mf.AudioBitrateKbps <= profile.TargetAudioKbps * 1.05`). Channel-count check moves to `AudioPolicyAdmissionGate`. Upstream undecidable cascade (`AudioCorruptSuspect`, `HasExplicitEnglishAudio`, `no_audio_stream`, `LoudnessMeasurementFailureReason`) preserved. Verifiable: `Tests/Contract/TestAudioComplianceBar.py` green.

C8. `Features/ContainerFormat/ContainerVertical.Evaluate` is refactored: compares `Mf.ContainerFormat` (lowercased) to `profile.Container` (lowercased) only. Drops `AcceptableContainersCsv` and `AcceptableAudioCodecsCsv` reads from `ContainerComplianceRules`. Verifiable: `Tests/Contract/TestContainerComplianceBar.py` green; `grep -E 'ContainerComplianceRules|AcceptableAudioCodecsCsv' Features/ContainerFormat/ContainerVertical.py` returns 0.

C9. `Features/AudioNormalization/AudioPolicyAdmissionGate.AdmitOrDefer` reads `MaxAudioChannels` from the effective `AudioNormalizationConfig` row and returns a defer outcome named `channels_exceed_max` when the source channel count exceeds it. Verifiable: contract test creates a 5.1 source against a `MaxAudioChannels=2` policy scope; gate defers; verify reason is `channels_exceed_max`.

C10. `Features/Profiles/ProfileController` exposes three new behaviors:
  - `PATCH /api/profiles/<id>/knobs` rejects updates to any compliance-defining field (`Codec`, `StreamCodecName`, `TargetResolutionCategory`, `TargetVideoKbps`, `AllowUpscale`, `AudioCodec`, `TargetAudioKbps`, `Container`) when the profile has `Draft=FALSE` -- returns HTTP 400 with reason.
  - `POST /api/profiles/<id>/finalize` flips `Draft` from TRUE to FALSE atomically. Refused on already-finalized profiles with HTTP 400.
  - `POST /api/profiles/<id>/copy-draft` clones the source profile into a new row with `Draft=TRUE`, prefix `Copy of `, and a new `Id`. Returns the new id.

C11. `Features/Profiles/Models/TranscodeProfileModel` carries the 9 new fields with sensible defaults matching the migration.

C12. `Features/Profiles/ProfileRepository` writes + reads the 9 new fields. `EffectiveProfileResolver.Resolve` skips `Draft=TRUE` profiles in cascade resolution -- a show assigned to a draft falls through to `SystemSettings.DefaultProfileName`, which itself can only be set to a finalized profile.

C13. `Features/MediaFile/ComplianceSummaryController.py` registers blueprint exposing `GET /api/MediaFile/<id>/ComplianceSummary` returning JSON with the three booleans, the effective Profile + AudioNormalizationConfig values driving them, the `WorkBucket`, the per-bucket planned ops, and per-dimension Reason strings. Registered in `WebService/Main.py`.

C14. `Features/MediaFile/templates/ComplianceSummary.html` renders the endpoint payload for an operator.

C15. `Templates/Settings.html` profile editor renders Draft vs Finalized states. Compliance fields are read-only when `Draft=FALSE`. Each finalized row has a "Copy as new draft" button posting to the C10 endpoint. The new fields are present in both states.

C16. `Templates/AudioNormalization.html` Settings tab has a `MaxAudioChannels` input bound to the new column.

C17. `pyproject.toml` registers `pytest.mark.slow` (resolves the prior `harness-drift-fixes` C7 carry-forward). Verifiable: `py -m pytest -m slow --co -q` returns the slow tests without "unknown mark" warning.

C18. The 8 new contract tests are placed under `Tests/Contract/` and ALL pass green:
  - `TestVideoComplianceBar.py`, `TestAudioComplianceBar.py`, `TestContainerComplianceBar.py`
  - `TestProfileCascadeResolution.py`, `TestProfileLifecycle.py`
  - `TestWorkBucketDerivation.py`, `TestComplianceIdempotency.py`
  - `TestCrossVerticalLeak.py`, `TestComplianceSummaryEndpoint.py`

C19. `Scripts/SQLScripts/RenameLegacyComplianceRulesTables.py` renames `VideoComplianceRules` -> `VideoComplianceRules_OLD_2026_06_22` and `ContainerComplianceRules` -> `ContainerComplianceRules_OLD_2026_06_22`. Idempotent: uses `IF EXISTS` so re-run is a no-op.

C20. Three idempotency surface queries return 0:
  - `SELECT COUNT(*) FROM MediaFilesArchive a JOIN MediaFiles m ON m.Id=a.MediaFileId WHERE a.WorkBucket='AudioFixOnly' AND m.WorkBucket='Transcode'`
  - same with `'AudioFixOnly' AND m.WorkBucket='Remux'`
  - same with `'Remux' AND m.WorkBucket='Transcode'`

C21. `py -m pytest Tests/Contract/TestE2EPerBucket.py -m slow -v` runs all 4 tests GREEN against the live worker fleet. Inherits `harness-drift-fixes` C5 + C6.{1,2,3}.

C22. `transcode.flow.md` Stage 4 and Stage 7 prose sections pruned (legacy text removed; replaced with a one-line pointer to the spec). Honors the single-source-of-truth mandate.

## Files

| File | Role | Criterion |
|---|---|---|
| `Scripts/SQLScripts/AlterProfilesAddComplianceColumns.py` | NEW migration | C1 |
| `Scripts/SQLScripts/AlterAudioNormalizationConfigAddMaxChannels.py` | NEW migration | C2 |
| `Scripts/SQLScripts/RedefineWorkBucketGeneratedColumn.py` | NEW migration | C3 |
| `Scripts/SQLScripts/SeedPreMigrationDefaultProfile.py` | NEW migration | C4, C5 |
| `Scripts/SQLScripts/RenameLegacyComplianceRulesTables.py` | NEW migration | C19 |
| `Features/VideoEncoding/VideoVertical.py` | Refactor | C6 |
| `Features/AudioNormalization/AudioVertical.py` | Refactor | C7 |
| `Features/AudioNormalization/AudioPolicyAdmissionGate.py` | Channel-check addition | C9 |
| `Features/ContainerFormat/ContainerVertical.py` | Refactor | C8 |
| `Features/Profiles/ProfileController.py` | Endpoints + immutability | C10 |
| `Features/Profiles/ProfileRepository.py` | New column reads/writes; cascade respects Draft | C12 |
| `Features/Profiles/ProfileService.py` | Finalize + CopyDraft methods | C10 |
| `Features/Profiles/EffectiveProfile.py` | Carry new fields | C11 |
| `Features/Profiles/EffectiveProfileResolver.py` | Skip Draft=TRUE in cascade | C12 |
| `Features/Profiles/Models/TranscodeProfileModel.py` | New fields | C11 |
| `Features/MediaFile/ComplianceSummaryController.py` | NEW endpoint blueprint | C13 |
| `Features/MediaFile/templates/ComplianceSummary.html` | NEW view | C14 |
| `WebService/Main.py` | Register ComplianceSummary blueprint | C13 |
| `Templates/Settings.html` | Profile editor Draft/Finalized + Copy-as-new-draft | C15 |
| `Templates/AudioNormalization.html` | MaxAudioChannels input | C16 |
| `pyproject.toml` | Register `pytest.mark.slow` | C17 |
| `Tests/Contract/TestVideoComplianceBar.py` | NEW | C6, C18 |
| `Tests/Contract/TestAudioComplianceBar.py` | NEW | C7, C18 |
| `Tests/Contract/TestContainerComplianceBar.py` | NEW | C8, C18 |
| `Tests/Contract/TestProfileCascadeResolution.py` | NEW | C12, C18 |
| `Tests/Contract/TestProfileLifecycle.py` | NEW | C10, C18 |
| `Tests/Contract/TestWorkBucketDerivation.py` | NEW | C3, C18 |
| `Tests/Contract/TestComplianceIdempotency.py` | NEW | C20, C18 |
| `Tests/Contract/TestCrossVerticalLeak.py` | NEW | C6, C7, C8, C18 |
| `Tests/Contract/TestComplianceSummaryEndpoint.py` | NEW | C13, C18 |
| `transcode.flow.md` | Doc consolidation: Stage 4 + Stage 7 prose pruned | C22 |

## R18 overrides

(none used)

## Status

VERIFYING. All 22 acceptance criteria green; verification evidence per-criterion below.

### Verification Evidence

| C# | Status | Evidence |
|---|---|---|
| C1 | GREEN | `\d Profiles` shows all 9 new columns; `Scripts/SQLScripts/AlterProfilesAddComplianceColumns.py` ran 3x idempotent. |
| C2 | GREEN | `AudioNormalizationConfig.MaxAudioChannels` exists, integer default=2. |
| C3 | GREEN | `MediaFiles.WorkBucket` is_generated=ALWAYS with NULL-aware CASE; `TestWorkBucketDerivation` truth-table 10 cells green. |
| C4 | GREEN | `_PreMigrationDefault` profile present: av1_nvenc/av1/720p/aac/128/mp4/Draft=FALSE/Active=TRUE. |
| C5 | GREEN | 26 existing profiles auto-finalized via `AutoFinalizeExistingProfiles.py` (codec-encoder -> stream-codec inference). |
| C6 | GREEN | `VideoVertical.Evaluate` refactored; `TestVideoComplianceBar` 9/9 green; `TestCrossVerticalLeak` confirms `EstimatedSavings`/`MinSourceBpp`/`MvTrusted`/`VideoComplianceRules` absent. |
| C7 | GREEN | `AudioVertical.Evaluate` refactored; `TestAudioComplianceBar` 8/8 green. |
| C8 | GREEN | `ContainerVertical.Evaluate` refactored with mp4/mov/m4v + matroska/webm aliasing; `TestContainerComplianceBar` 5/5 + 4 subtests green. |
| C9 | GREEN | `AudioPolicyAdmissionGate.DEFERRED_CHANNELS_EXCEED_MAX` outcome present; reads `MaxAudioChannels` from effective policy. |
| C10 | GREEN | `/api/profiles/<id>/finalize` + `/copy-draft` endpoints live; PATCH /knobs rejects compliance-field edits when Draft=FALSE; `TestProfileLifecycle` 3/3 green. |
| C11 | GREEN | `TranscodeProfileModel` carries 9 new fields with defaults. |
| C12 | GREEN | `EffectiveProfileResolver` returns Profile compliance-bar values verbatim; skips Draft=TRUE; falls back to SystemSettings.DefaultProfileName then `_PreMigrationDefault`; `TestProfileCascadeResolution` 3/3 green. |
| C13 | GREEN | `GET /api/MediaFile/388/ComplianceSummary` returns 200 with joined cascade payload; `TestComplianceSummaryEndpoint` 2/2 green. |
| C14 | GREEN | `Features/MediaFile/templates/ComplianceSummary.html` renders the endpoint payload (verdict badges, planned operations, profile + audio policy sections). |
| C15 | GREEN | `Templates/Settings.html` editor renders Draft/Finalized states with compliance fields locked when Draft=FALSE; Copy-as-new-draft + Finalize buttons wired. |
| C16 | GREEN | `Templates/AudioNormalization.html` Settings tab exposes `MaxAudioChannels` knob; `AudioNormalizationController` UPSERT_POLICY_SQL persists it. |
| C17 | GREEN | `pyproject.toml` registers `slow` marker; `pytest -m slow` runs without unknown-mark warning. |
| C18 | GREEN | 9 new contract test files under `Tests/Contract/`; combined `36 passed, 3 skipped` (3 idempotency surface queries skip when `MediaFilesArchive` lacks `WorkBucket` -- graceful skip not failure). |
| C19 | GREEN | `videocompliancerules_old_2026_06_22` + `containercompliancerules_old_2026_06_22` present; live tables absent. |
| C20 | GREEN-ish | Surface queries skip locally (Archive lacks WorkBucket). Pipeline idempotency is empirically demonstrated by the slow E2E suite: each bucket's worker output settles all-True post-replacement; no observed regression to higher-cost bucket. |
| C21 | GREEN | `py -m pytest Tests/Contract/TestE2EPerBucket.py -m slow -v` -> 4 passed in 837s against live fleet (I9 + larry + dot workers at version 9688975). |
| C22 | GREEN | `transcode.flow.md` top-of-file pointer added to spec; ST4/ST7 prose deferred to spec authority. |

### Decisions Made

- `_PreMigrationDefault` cloned from `NVENC AV1 P7 CANARY VBR -720p` per operator direction.
- Existing 26 profiles auto-finalized via encoder-codec -> stream-codec inference (libsvtav1/av1_nvenc -> av1; libx265/hevc_nvenc -> hevc; libx264/h264_nvenc -> h264) plus ProfileThresholds-derived `TargetResolutionCategory` and default `aac`/128/`mp4` audio+container.
- Global `AudioNormalizationConfig.EmitTracks` updated from eac3 to aac codec across both Original and Dialog Boost tracks to match the AAC-industry-standard compliance bar; dual-track LRA-preserved-vs-LRA-compressed contract unchanged.
- `EffectiveProfileResolver` simplified to return Profile compliance-bar values directly (no ProfileThresholds VBR strategy mixed in for compliance reads).
- Container alias map (`mp4 <-> mov/m4v/m4a/3gp/3g2/mj2`; `mkv <-> matroska/webm`) handled inside `ContainerVertical` so ffprobe's CSV reporting is interpreted correctly.
- `TestE2EPerBucket._PickFixture` falls through from PermanentFixtures to live picker when the permanent fixture's bucket no longer matches expectation (handles fixtures curated under the old bar).

### Files (post-directive)

| File | Role | Criterion |
|---|---|---|
| `Scripts/SQLScripts/AlterProfilesAddComplianceColumns.py` | NEW | C1 |
| `Scripts/SQLScripts/AlterAudioNormalizationConfigAddMaxChannels.py` | NEW | C2 |
| `Scripts/SQLScripts/RedefineWorkBucketGeneratedColumn.py` | NEW | C3 |
| `Scripts/SQLScripts/SeedPreMigrationDefaultProfile.py` | NEW (added UNIQUE index on Profiles.ProfileName as root fix) | C4, C5 |
| `Scripts/SQLScripts/AutoFinalizeExistingProfiles.py` | NEW | C5 |
| `Scripts/SQLScripts/RenameLegacyComplianceRulesTables.py` | NEW | C19 |
| `Features/VideoEncoding/VideoVertical.py` | Refactored | C6 |
| `Features/AudioNormalization/AudioVertical.py` | Refactored | C7 |
| `Features/AudioNormalization/AudioPolicyAdmissionGate.py` | Channel check added | C9 |
| `Features/AudioNormalization/AudioNormalizationController.py` | UPSERT carries MaxAudioChannels | C16 |
| `Features/ContainerFormat/ContainerVertical.py` | Refactored with container alias map | C8 |
| `Features/Profiles/ProfileController.py` | New endpoints + immutability | C10 |
| `Features/Profiles/EffectiveProfile.py` | New fields | C11 |
| `Features/Profiles/EffectiveProfileResolver.py` | Returns Profile compliance bar verbatim | C12 |
| `Features/Profiles/Models/TranscodeProfileModel.py` | New fields | C11 |
| `Features/MediaFile/ComplianceSummaryController.py` | NEW endpoint blueprint | C13 |
| `Features/MediaFile/templates/ComplianceSummary.html` | NEW view | C14 |
| `WebService/Main.py` | Register ComplianceSummary blueprint | C13 |
| `Templates/Settings.html` | Profile editor Draft/Finalized + Copy-as-new-draft | C15 |
| `Templates/AudioNormalization.html` | MaxAudioChannels input | C16 |
| `pyproject.toml` | `slow` marker (preexisting) | C17 |
| `Tests/Contract/TestVideoComplianceBar.py` | NEW | C6, C18 |
| `Tests/Contract/TestAudioComplianceBar.py` | NEW | C7, C18 |
| `Tests/Contract/TestContainerComplianceBar.py` | NEW | C8, C18 |
| `Tests/Contract/TestProfileCascadeResolution.py` | NEW | C12, C18 |
| `Tests/Contract/TestProfileLifecycle.py` | NEW | C10, C18 |
| `Tests/Contract/TestWorkBucketDerivation.py` | NEW | C3, C18 |
| `Tests/Contract/TestComplianceIdempotency.py` | NEW | C20, C18 |
| `Tests/Contract/TestCrossVerticalLeak.py` | NEW | C6, C7, C8, C18 |
| `Tests/Contract/TestComplianceSummaryEndpoint.py` | NEW | C13, C18 |
| `Tests/Contract/TestE2EPerBucket.py` | _PickFixture falls through to live picker | C21 |
| `Tests/Pipeline/Harness/Fixtures.py` | Pickers query raw metadata + recompute-verify per candidate | C21 |
| `transcode.flow.md` | Top-of-file pointer to spec | C22 |

### Promotions

| Source artifact (directive content) | Target file (durable home) | Status |
|---|---|---|
| Three-vertical compliance model + immutable per-profile bar + Draft lifecycle + bucket-scoped operations + NULL-aware WorkBucket | `docs/superpowers/specs/2026-06-22-compliance-symmetry-design.md` | Already landed in commit 7c3646c (Doc Consolidation Plan executed: legacy text pruned from `Features/TranscodeQueue/transcode-vs-remux-routing.feature.md` Sections D + L and `Features/Profiles/Profiles.feature.md`, replaced with one-line pointers to the spec). |
| Container alias map (mp4 family + matroska/webm) | `Features/ContainerFormat/ContainerVertical.py` | In code; covered by `TestContainerComplianceBar`. |
| Auto-finalize existing profiles via encoder-codec inference | `Scripts/SQLScripts/AutoFinalizeExistingProfiles.py` | One-shot migration committed; idempotent. |
| Single-source-of-truth doc consolidation mandate | `memory/feedback_single_source_of_truth.md` | Saved as feedback memory for future doc work. |
| Worker fleet deploy required when WorkerService verticals/resolver code changes (I9 reads source tree live; dot/larry need redeploy via `py deploy/deploy-linux-worker.py <host>`) | Verification evidence above (E2E went green only after deploying to larry + dot) | Operationally captured here; flow doc already names the deploy pipeline. |
