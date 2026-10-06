# Current Directive

**Set:** 2026-10-06
**Status:** Active -- phase: VERIFYING
**Slug:** tv-video-rule-tier1
**Replaces:** `directives/closed/2026-10-06-bug-0095-failure-classification.md` (closed Success)

## Outcome

A TV file's bucket is decided by one readable rule: source video bitrate against the TV library's default tier (Tier 1) target for its resolution times the per-resolution multiplier. Assigned profile and source codec no longer move a TV file between buckets. "This library is TV at Tier 1" is one operator-editable value on the library, not a path pattern. `transcode.flow.md` D4 states the rule for each bucket once; every other doc points at it. The library tier is also the only thing that gives a TV file its default encode profile (the `T:\%` path rule is gone), and the bucket is derived in exactly one place. Movies and XXX behave exactly as before. Phase 1 of two; phase 2 list: `.claude/directives/backlog/_bucket-rules-phase-2.md`. Operator approved scope 2026-10-06 (three conceptual changes in one directive, accepted knowingly).

## Acceptance Criteria

1. Each library carries an operator-set default quality tier. TV = 1; Movies and XXX unset. Verify: `SELECT Name, DefaultQualityTier FROM StorageRoots`.
2. In a library with a default tier, a file's video is compliant iff its source video kbps <= (the kbps that tier encodes a file of that resolution at) x (that resolution's multiplier). Verify: SQL recomputing the verdict from `ProfileThresholds` + `VideoComplianceThresholds` disagrees with stored `VideoCompliant` on 0 TV rows.
3. In such a library the verdict ignores assigned profile and source codec. Verify: 0 TV rows with `VideoCompliantReason LIKE 'source_codec_matches_target%'` or `= 'missing_input:AssignedProfile'`; setting a TV series to another profile leaves `VideoCompliant` + `WorkBucket` unchanged for its files.
4. The stored reason for a tier-ruled file names source kbps, ceiling, tier, target and multiplier. Verify: `SELECT VideoCompliantReason FROM MediaFiles WHERE StorageRootId=1 LIMIT 5`.
5. Libraries with no default tier are untouched. Verify: snapshot of `(Id, VideoCompliant, VideoCompliantReason, WorkBucket)` for Movies + XXX before vs after differs on 0 rows.
6. Operator views and changes a library's default tier on `/settings` with no SQL; the change re-evaluates that library's files and is seen by the next evaluation without restart.
7. A finished encode is never thrown away for its video bitrate: the pre-replace check does not judge video on our own output (D7). Verify: contract test -- check passes a candidate at any bitrate when container + audio pass; 0 new `ComplianceGateFailed` attempts with a `source_above_ceiling` reason after ship.
8. `transcode.flow.md` D4 holds one rule table covering Transcode / Remux / Audio / Compliant / Unclassified; `video-encoding.feature.md`, `container-format.feature.md`, `work-bucket.feature.md`, `DOMAIN.md` no longer state a conflicting rule. Verify: `grep -n "source_codec_matches_target\|acceptablevideocodecscsv" *.md Features/**/*.md` returns no rule text outside closed directives.

9. A TV file with no profile gets the profile of its library's default tier, whatever its codec; no classification rule names the TV path. Verify: `SELECT COUNT(*) FROM ContentClassificationRules WHERE FolderPathPattern LIKE 'T:%'` = 0; 0 TV rows with `AssignedProfile IS NULL` and probe data present.
10. The bucket is derived in one place (the `WorkBucket` column). The pre-replace check answers only pass/fail and reports the failing dimension's own reason. Verify: contract test asserts the check's result carries no bucket name and its refusal reason equals the failing vertical's reason.

## Call-Graph Audit

- **Flow docs:** `transcode.flow.md` (D4/D7, ST4), `ingest.flow.md` (probe -> classifier -> compliance order), `Features/WorkBucket/work-bucket.flow.md` (UI request lifecycle, different operation). No pair describes one operation. `transcode.flow.md` ST4 points at `Features/Compliance/compliance.flow.md`, which does not exist -- pointer removed in this directive.
- **Orchestration mode branch:** none. `RecomputeForFiles` calls Audio/Video/Container verticals identically for every file.
- **Signal 5 (config-driven graph shape) -- VIOLATION INTRODUCED, named:** inside `VideoVertical.Evaluate`, library tier set -> tier-target lookup; unset -> profile-target + profile-codec lookups. Different functions per data value. Accepted only because operator deferred Movies/XXX; collapses when those libraries get their rule.
- **Second bucket derivation:** `QueueManagementBusinessService.EvaluateCandidateCompliance` re-derives the bucket in Python for `ComplianceGate`. Removed here (criterion 10): it returns pass/fail + reason only; `ComplianceGate` never needed the bucket name.
- **TV identity copies:** runtime copy is the `TvPinTier1Efficient` classifier row; removed here (criterion 9). `TV_STORAGE_ROOT_ID` lives in an already-run one-shot script (history). `WorkBucket.html` label map and `NoAudioResolver` root-name check map library name to label / Sonarr -- a different concept, left alone.
- **Shared output columns:** `MediaFiles.VideoCompliant/VideoCompliantReason` written for every library by one writer (`VideoVertical._WriteResult`). Live 2026-10-06: TV has 580 non-terminal rows with `VideoCompliant IS NULL`; projected 20 after.
- **OOS categories:** below.

## Out of Scope

- (b) Movies / XXX video rule -- operator decision pending; old path preserved verbatim.
- (b) Everything in `.claude/directives/backlog/_bucket-rules-phase-2.md`: bulk-queue tier rewrite, rule display, `ComplianceGate` silent excepts (BUG-0106 A), `IsCompliant` terminal parity, `AudioVertical.Evaluate` side-effect writes, stale non-video contract tests, dead ladder cells + ladder audit trail.

## Constraints

- No change to the `WorkBucket` generated column.
- No production config values changed for testing.
- Workers drained before the TV recompute and before any restart.

## Escalation Defaults

- Rule clarity vs preserving a current verdict -> rule clarity (TV only).
- Risk tolerance: medium (projected 13 TV files move to Transcode).

## Engineering Calls Already Made

- Operator 2026-10-06: ceiling = Tier 1 target x multiplier; codec-match dropped, AV1 included; TV tier is a default, per-series override changes encode tier only, never the bucket; TV only.
- Ceilings come from live data, not doc numbers. Target = the bitrate the tier actually encodes that source at, i.e. the cell of the resolution the tier outputs (`TranscodeDownTo`), not the source-resolution cell. Operator raised Tier 1 720p 900 -> 1000 between 2026-09-06 and 2026-09-08 (ffmpeg commands flip `900k` -> `1000k` then, downscaled 1080p included); the 1080p/2160p Tier 1 cells still say 900 and are not what encodes run at. Operator 2026-10-06: "we want the better bitrate". Live ceilings: 480p 400x4.0=1600, 720p 1000x2.0=2000, 1080p 1000x2.0=2000, 2160p 1000x3.0=3000 kbps.
- TV identity = nullable `StorageRoots.DefaultQualityTier`, read fresh per evaluation.
- Tier target read filters `ProfileThresholds.ContentClass` (existing `GetTier1Target` filters `Profiles.ContentClass` and can return either content-class row).

## Status

Phases advance by editing the `**Status:**` header line at the top of this file.

### Files

```
Scripts/SQLScripts/AddStorageRootDefaultQualityTier_2026_10_06.py  -- CREATE: nullable column, TV=1, idempotent
Features/VideoEncoding/VideoVertical.py                           -- EDIT: tier rule when library tier set
Features/Profiles/LibraryDefaultTierRepository.py                 -- CREATE: fresh read/write of library tier
Features/Profiles/TierLadderRepository.py                         -- EDIT: tier encode kbps + tier profile name
Features/TranscodeQueue/QueueManagementBusinessService.py         -- EDIT: EvaluateCandidateCompliance pass/fail, no video, no bucket
Features/FileReplacement/ComplianceGate.py                        -- EDIT: pass/fail only
Features/ContentClassifier/ContentClassifierService.py            -- EDIT: library default tier before rules walk
Scripts/SQLScripts/RetireTvPinRule_2026_10_06.py                  -- CREATE: delete TvPinTier1Efficient row; backfill NULL-profile TV
Tests/Contract/TestTvPinTier1Classification.py                    -- EDIT: asserts library-tier assignment
Tests/Contract/TestComplianceGatePassFailOnly.py                  -- CREATE
Features/SystemSettings/SystemSettingsController.py               -- EDIT: GET/PUT library default tiers + cascade
Templates/Settings.html                                           -- EDIT: library default tier section
Scripts/RecomputeWorkBuckets.py                                   -- EDIT: restrict to one library
Tests/Contract/TestTvVideoRuleTier1.py                            -- CREATE
Tests/Contract/TestVideoVerticalMvOutputExempt.py                 -- DELETE: asserted a branch removed 2026-08-07
Tests/Contract/TestVerticalsAreProfileIndependent.py              -- EDIT: video case
transcode.flow.md, DOMAIN.md, ingest.flow.md, e2e-bug-fixes.feature.md,
Features/VideoEncoding/video-encoding.feature.md, Features/ContentClassifier/classifier.feature.md,
Features/FileReplacement/compliance-gated-rename.feature.md,
Features/ContainerFormat/container-format.feature.md, Features/WorkBucket/work-bucket.feature.md,
memory/KNOWN-ISSUES.md                                            -- EDIT at DELIVERING (Promotions)
```

### Plan

1. Migration: `StorageRoots.DefaultQualityTier INT NULL CHECK (BETWEEN 1 AND 5)`, `IF NOT EXISTS`; set 1 on `media_tv` only when NULL.
2. `LibraryDefaultTierRepository`: `GetDefaultQualityTier(StorageRootId)`, `ListLibraries()`, `SetDefaultQualityTier(StorageRootId, Tier)`. Fresh read per call.
3. `TierLadderRepository.GetTierEncodeKbps(Tier, ContentClass, Resolution)`: `Family='ANY'` tier profile; source-resolution row -> its `TranscodeDownTo` row -> `TargetKbps`. None when any hop is missing.
4. `VideoVertical.Evaluate`: after the resolution + bitrate guards, read library tier; set -> ceiling from step 3 x multiplier, reason `source_{at_or_below,above}_ceiling:<src><op><ceiling>(tier=<n>:<kbps>*<mult>)`; unset -> existing lines unchanged.
5. `EvaluateCandidateCompliance` returns `{IsCompliant, RefusalReason}` from Container + Audio only; gate drops its bucket-named fallback reasons.
6. `ContentClassifierService`: before the rules walk, library tier set -> assign that tier's `Family='ANY'` profile (`IfUnsetOnly=True`, source `library_default_tier`). Single + batch paths.
7. `RetireTvPinRule_2026_10_06.py`: delete `TvPinTier1Efficient`; assign the library-tier profile to TV rows with NULL profile through `ProfileAssignmentService` (cascades).
8. `/settings`: GET/PUT library default tiers; PUT recomputes that library's files in a daemon thread (same pattern as `ContainerFormatController.UpdateRules`).
9. Tests per Files list. Run `TestClaimAuthority`, `TestWriterOwnsCascadeEnforcement`, `TestFailLoud`.
10. Order: column migration (additive, safe for old-code workers) -> commit + push -> fleet deploy (operator) -> `RetireTvPinRule` -> TV recompute -> verify. Rule retirement and recompute wait for the deploy: an old-code worker would send new TV files to the 1080p rule and overwrite TV verdicts with the old rule.

Seams added or changed (existing `transcode.S*` untouched):

| Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|
| Library tier -> video rule | operator via `/settings` PUT | `StorageRoots.DefaultQualityTier INT NULL (1-5)` | `VideoVertical.Evaluate` reads per call; NULL = old path | `TestTvVideoRuleTier1` |
| Library tier -> default profile | same column | same | `ContentClassifierService` maps tier -> `Profiles(Family='ANY', QualityTier)` name | `TestTvPinTier1Classification` |
| Candidate verdict -> gate | `EvaluateCandidateCompliance` | `{IsCompliant: bool/None, RefusalReason: str/None}` | gate: pass iff `IsCompliant is True` | `TestComplianceGatePassFailOnly` |

### Promotions

### Verification

- **1:** migration applied twice 2026-10-06; `media_tv=1, movies=NULL, xxx=NULL`.
- **2, 3, 9 (data half):** pending fleet deploy -> `RetireTvPinRule` -> TV recompute. Live tests `TestTvVideoRuleTier1Live` (2) + `TestTvPinTier1Classification` (2) fail until then, by design.
- **Logic:** 60 contract tests pass (`TestTvVideoRuleTier1`, `TestComplianceGatePassFailOnly`, `TestVerticalsAreProfileIndependent`, `TestVideoVerticalCodecMatch`, `TestVideoComplianceMultiplier`, `TestClaimAuthority`, `TestWriterOwnsCascadeEnforcement`, `TestClassifierCascade`, 2 of 4 `TestTvPinTier1Classification`).
- **6 (partial):** I9 WebService restarted on `32f24fb9`; `GET /api/SystemSettings/LibraryTiers` returns the three libraries; PUT rejects tier 9 (400) and unknown library (404); `/settings` renders the section. Successful PUT + cascade not yet exercised -- it is the TV recompute, held for after fleet deploy.
- **Read-only evaluation on live rows:** TV AV1 1080p 2086 kbps (Id 616542) -> `source_above_ceiling:2086>2000(tier=1:1000*2.0)` (stored: codec-match compliant). TV unprofiled (Id 700831) -> decided (stored: Unclassified). Movie + XXX samples -> old path, reasons carry `profile=`.

### Decisions Made

- Gate does not judge video. Before the 2026-08-14 codec-match the gate threw away 207 finished encodes for video bitrate (`source_above_multiplier` 203, `source_above_ceiling` 4); zero since. Dropping codec-match without this would bring them back, worst on ICQ encodes that have no bitrate cap. D7 already says our output is terminal.
- `LibraryDefaultTierRepository` lives in `Features/Profiles` (tiers are that vertical's concept); VideoEncoding and ContentClassifier both already depend on it.
- Library tier has its own PUT, not folded into the Transcoding save: every save cascades a full-library recompute and must not fire on unrelated ladder edits.
- Existing codec-match and multiplier tests left as-is: they still describe the untiered-library path.
- `TestFailLoud` and `TestCrossVerticalLeak` fail before and after this directive on files it does not touch (baseline drift; phase 2 row 7).
