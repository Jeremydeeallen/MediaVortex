# Current Directive

**Set:** 2026-10-06
**Status:** Active -- phase: NEEDS_STANDARDS_REVIEW
**Slug:** tv-video-rule-tier1
**Replaces:** `directives/closed/2026-10-06-bug-0095-failure-classification.md` (closed Success)

## Outcome

A TV file's bucket is decided by one readable rule: source video bitrate against the TV library's default tier (Tier 1) target for its resolution times the per-resolution multiplier. Assigned profile and source codec no longer move a TV file between buckets. "This library is TV at Tier 1" is one operator-editable value on the library, not a path pattern. `transcode.flow.md` D4 states the rule for each bucket once; every other doc points at it. Movies and XXX behave exactly as before. First of three directives (then `tv-encode-tier-default`, `bucket-rules-display`); approved plan: `~/.claude/plans/we-have-to-simplify-refactored-hearth.md`.

## Acceptance Criteria

1. Each library carries an operator-set default quality tier. TV = 1; Movies and XXX unset. Verify: `SELECT Name, DefaultQualityTier FROM StorageRoots`.
2. In a library with a default tier, a file's video is compliant iff its source video kbps <= (the kbps that tier encodes a file of that resolution at) x (that resolution's multiplier). Verify: SQL recomputing the verdict from `ProfileThresholds` + `VideoComplianceThresholds` disagrees with stored `VideoCompliant` on 0 TV rows.
3. In such a library the verdict ignores assigned profile and source codec. Verify: 0 TV rows with `VideoCompliantReason LIKE 'source_codec_matches_target%'` or `= 'missing_input:AssignedProfile'`; setting a TV series to another profile leaves `VideoCompliant` + `WorkBucket` unchanged for its files.
4. The stored reason for a tier-ruled file names source kbps, ceiling, tier, target and multiplier. Verify: `SELECT VideoCompliantReason FROM MediaFiles WHERE StorageRootId=1 LIMIT 5`.
5. Libraries with no default tier are untouched. Verify: snapshot of `(Id, VideoCompliant, VideoCompliantReason, WorkBucket)` for Movies + XXX before vs after differs on 0 rows.
6. Operator views and changes a library's default tier on `/settings` with no SQL; the change re-evaluates that library's files and is seen by the next evaluation without restart.
7. The pre-replace compliance check gives a TV candidate the same video verdict the stored column gets. Verify: contract test feeding one TV row through both paths.
8. `transcode.flow.md` D4 holds one rule table covering Transcode / Remux / Audio / Compliant / Unclassified; `video-encoding.feature.md`, `container-format.feature.md`, `work-bucket.feature.md`, `DOMAIN.md` no longer state a conflicting rule. Verify: `grep -n "source_codec_matches_target\|acceptablevideocodecscsv" *.md Features/**/*.md` returns no rule text outside closed directives.

## Call-Graph Audit

- **Flow docs:** `transcode.flow.md` (D4/D7, ST4), `ingest.flow.md` (probe -> classifier -> compliance order), `Features/WorkBucket/work-bucket.flow.md` (UI request lifecycle, different operation). No pair describes one operation. `transcode.flow.md` ST4 points at `Features/Compliance/compliance.flow.md`, which does not exist -- pointer removed in this directive.
- **Orchestration mode branch:** none. `RecomputeForFiles` calls Audio/Video/Container verticals identically for every file.
- **Signal 5 (config-driven graph shape) -- VIOLATION INTRODUCED, named:** inside `VideoVertical.Evaluate`, library tier set -> tier-target lookup; unset -> profile-target + profile-codec lookups. Different functions per data value. Accepted only because operator deferred Movies/XXX; collapses when those libraries get their rule.
- **Second bucket derivation:** `QueueManagementBusinessService.EvaluateCandidateCompliance` re-derives the bucket in Python for `ComplianceGate`; lacks the generated column's terminal branch. Not fixed here; criterion 7 keeps the video verdict consistent across both.
- **Shared output columns:** `MediaFiles.VideoCompliant/VideoCompliantReason` written for every library by one writer (`VideoVertical._WriteResult`). Live 2026-10-06: TV has 580 non-terminal rows with `VideoCompliant IS NULL`; projected 20 after.
- **OOS categories:** below.

## Out of Scope

- (b) Movies / XXX video rule -- operator decision pending; old path preserved verbatim.
- (b) TV encode tier, bulk-queue Tier 2 default, probe-before-classifier ordering, `AlreadyAv1Skip` vs TV pin, `T:\%` rule + hardcoded TV root id -> `tv-encode-tier-default`.
- (b) Rule display on `/Work/<bucket>` -> `bucket-rules-display`.
- (b) `EvaluateCandidateCompliance` duplicate derivation + `ComplianceGate` silent excepts -> BUG-0106.
- (b) Generated `IsCompliant` lacking the terminal branch; `AudioVertical.Evaluate` side-effect writes; stale non-video contract tests.

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
Features/VideoEncoding/LibraryDefaultTierRepository.py            -- CREATE: fresh read/write of library tier
Features/Profiles/TierLadderRepository.py                         -- EDIT: tier target by (tier, content class, resolution)
Features/TranscodeQueue/QueueManagementBusinessService.py         -- EDIT: _RowToMediaFileForCompliance carries StorageRootId
Features/FileReplacement/ComplianceGate.py                        -- EDIT: only if CandidateRow lacks StorageRootId
Features/SystemSettings/SystemSettingsController.py               -- EDIT: GET/PUT library default tiers + cascade
Templates/Settings.html                                           -- EDIT: library default tier section
Scripts/RecomputeWorkBuckets.py                                   -- EDIT: restrict to one library
Tests/Contract/TestTvVideoRuleTier1.py                            -- CREATE
Tests/Contract/TestVideoVerticalCodecMatch.py                     -- EDIT
Tests/Contract/TestVideoComplianceMultiplier.py                   -- EDIT
Tests/Contract/TestVideoVerticalMvOutputExempt.py                 -- EDIT/DELETE: asserts removed branch
Tests/Contract/TestVerticalsAreProfileIndependent.py              -- EDIT: video case
transcode.flow.md, DOMAIN.md, Features/VideoEncoding/video-encoding.feature.md,
Features/ContainerFormat/container-format.feature.md, Features/WorkBucket/work-bucket.feature.md,
memory/KNOWN-ISSUES.md                                            -- EDIT at DELIVERING (Promotions)
```

### Promotions

### Verification

### Decisions Made
