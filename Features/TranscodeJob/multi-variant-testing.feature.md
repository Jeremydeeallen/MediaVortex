# Feature: Multi-Variant Transcode Testing

**Slug:** multi-variant-testing

## What It Does

Lets the operator queue a single source file for N transcode variants in one
admission, run them through the production worker pipeline (FFmpeg encode +
VMAF + auto-capture stills) without touching the source, and surface all N
results grouped together in the comparison slider for visual + metric
evaluation.

This is the path from "smoke tests give me 3 sources of data" to "fleet of
workers gives me 30 sources x 4 variants of data overnight." It is the
empirical data generator for tier-threshold calibration, CRF/FG sweeps, and
content-type-specific encoder tuning.

The smoke harness in `Scripts/Smoke/EncodeAndVmaf.py` remains as the ad-hoc
out-of-DB path; this feature is the in-pipeline production-grade path.

## Surface

- **Admission**: "Queue for testing" form on the `/VmafCompare` page — variant
  set dropdown + textarea for file paths (one per line) + Submit. Inserts one
  TranscodeQueue row per file with the chosen `TestVariantSetId`. Shows submit
  count and any per-file admission errors inline. SQL admission remains
  available via `/SQLQueries` for power users or automation.
- **Variant sets**: defined as rows in new `TestVariantSets` table; admin-edited
  via SQL for v1. Each set has a Name, Description, and a JSONB `Variants`
  column listing the N recipes.
- **Worker behavior**: same WorkerService process and capability flags
  (TranscodeEnabled, QualityTestEnabled). Picks up test-mode queue rows
  alongside production rows; each test row produces N TranscodeAttempts in
  sequence.
- **Comparison UI**: `/VmafCompare` Recent attempts table groups by
  `(MediaFileId, TestVariantSetId)` so a single source's N variants appear
  as one row with N variant pills.
- **Errors visible to operator**: variant set referenced but not found, source
  file unreadable, individual variant encode/VMAF failure (other variants
  in the same set still proceed).

## Flow (operator's path)

| Step | What the operator does | What the system does | Failure mode |
|---|---|---|---|
| 1 | Picks variant set + source files; runs SQL INSERT against TranscodeQueue with `TestVariantSetId` set | Rows admitted as Pending; same FilePath validation as production queue | Bad variant set id -> insert fails with FK violation |
| 2 | (no action) | Worker picks up a test row. For each variant in the set, runs encode -> VMAF -> auto-capture stills | Single-variant failure -> recorded on that attempt; remaining variants still process |
| 3 | (no action) | Each variant lands a row in `TranscodeAttempts` with `TestVariantSetId` and `TestVariantName` populated. Disposition is forced to `NoReplace`; source file is never touched | Disposition wiring bug would risk source -- guarded by an explicit short-circuit |
| 4 | Opens `/VmafCompare` | Recent attempts shows test-mode rows grouped: one row per `(MediaFileId, TestVariantSetId)`, with a variant-count badge | -- |
| 5 | Clicks Open on a test row | Variant pills render for each TranscodeAttempt in the group, with VMAF score + film grain + CRF in the label | -- |
| 6 | Clicks a variant pill | Slider loads; thumbnail strip shows 4 timestamps per `VmafStillCaptureTimestamps`. Source side is constant across variants | -- |

## Success Criteria

1. **Variant set storage.** New table `TestVariantSets(Id, Name, Description, VariantsJson JSONB, CreatedAt)`. `VariantsJson` is an array of variant recipes, each with at minimum `{Name, Label, Crf, FilmGrain, Scale}`. Verifiable: query the table after migration; at least one seed row exists ("FG Sweep 1080p CRF32" with 4 variants FG=0/4/8/12).

2. **Queue admission.** `TranscodeQueue` gains a nullable `TestVariantSetId` column referencing `TestVariantSets(Id)`. NULL means normal production transcode (existing behavior unchanged); populated means run the referenced variant set. Verifiable: INSERT a test row pointing at an existing variant set, observe the row admitted; INSERT pointing at a non-existent set, observe FK violation.

3. **Attempt grouping.** `TranscodeAttempts` gains nullable `TestVariantSetId INT` and `TestVariantName TEXT`. Production transcodes leave both NULL. Test transcodes write both. Verifiable: after a test set completes, query attempts WHERE TestVariantSetId IS NOT NULL; you see N rows for one source, each with the matching variant name.

4. **Worker multi-variant execution.** When the worker picks up a queue row with `TestVariantSetId` set, it iterates the variant set's recipes and produces one TranscodeAttempt per variant. Encoding uses the variant's specific Crf, FilmGrain, and Scale, overriding the assigned profile. Verifiable: queue one test row with a 4-variant set; observe 4 TranscodeAttempts created, each with FFmpegCommand reflecting the variant's params.

5. **VMAF per variant.** Each variant goes through the same QualityTestEnabled path as production -- one VMAF score per variant lands in `TranscodeAttempts.VMAF`. Verifiable: query test attempts for the same MediaFileId; each has a non-NULL VMAF score reflecting that variant's quality.

6. **Auto-capture per variant.** With `VmafStillCapturePolicy=All`, each variant gets comparison stills extracted at the configured `VmafStillCaptureTimestamps` set after VMAF completes. Verifiable: cache directory has N variants * timestamp count * 2 (source + transcoded) PNGs.

7. **Source preservation (disposition shortcut).** When `TestVariantSetId` is populated, `DecidePostTranscodeDisposition` short-circuits to `NoReplace` regardless of VMAF score, gate config, or any other factor. `FileReplaced` stays `false`. The original source file is never moved, archived, or deleted. Verifiable: file system inspection before and after a test set completes; source path is byte-identical (size + mtime unchanged).

8. **Per-variant failure isolation.** If one variant's encode or VMAF fails, the remaining variants in the same set still process. The failed variant has a TranscodeAttempt row with `Success=false` and an error message; the queue row is marked complete only after all variants attempt. Verifiable: force-fail one variant (e.g. bad CRF in the variant set); observe other variants complete with their VMAF scores intact.

9. **Test bench grouping in UI.** `/VmafCompare` Recent attempts surface groups test rows: one row per `(MediaFileId, TestVariantSetId)` instead of N separate rows. Group row shows source filename, variant set name, variant count badge. Clicking Open renders the variant pills as in the smoke-test test bench. Verifiable: with two complete test sets in the DB, Recent attempts shows two grouped rows, not 2N individual rows.

10. **Variant pills show distinguishing params.** The pill label includes the variant's distinguishing parameters (e.g. "FG=8 CRF=32 @ 1080p") plus VMAF score so the operator can attribute outcomes to inputs at a glance. Verifiable: open a test set with FG sweep; each pill label clearly shows the variant's FG value.

11. **Retention policy.** Test-mode encoded outputs live in `TemporaryFilePaths.LocalOutputPath` (same place production unfinished attempts live). A new maintenance script removes test-mode staged outputs older than 30 days (configurable via `SystemSettings.TestModeRetentionDays`). Verifiable: configure retention to 1 day, age a test row's encoded files via touch, run the cleanup script, observe deletion of the encoded files but not the TranscodeAttempts rows.

12. **No effect on production transcodes.** Production queue rows (TestVariantSetId IS NULL) flow through exactly as before this feature: one attempt per row, disposition logic unchanged, auto-replace happens when configured. Verifiable: run a non-test queue row through after this feature lands; behavior matches the prior `transcode.flow.md` step table identically.

13. **Queue admission UI.** `/VmafCompare` has a "Queue for testing" card with: (a) variant set dropdown populated from `TestVariantSets`, (b) textarea for file paths (one per line), (c) Submit button. Submit POSTs to a new endpoint that inserts one TranscodeQueue row per file with `TestVariantSetId` set; reports the count of accepted rows plus per-file errors (e.g. file not found, duplicate already pending) inline. Verifiable: pick the FG Sweep variant set, paste two valid 4K test source paths, click Submit; UI shows "2 rows queued"; querying TranscodeQueue shows two new rows with `TestVariantSetId=<set id>`.

## Status

**NOT STARTED** -- doc-first, awaiting operator approval of criteria.

### Progress

- [x] Draft this feature doc with criteria
- [ ] Operator approval
- [ ] **Migration** `Scripts/SQLScripts/AddMultiVariantTesting.py`: idempotent. Creates `TestVariantSets` table, adds `TestVariantSetId` to `TranscodeQueue`, adds `TestVariantSetId` + `TestVariantName` to `TranscodeAttempts`. Seeds one variant set "FG Sweep 1080p CRF32" with FG=0/4/8/12 variants
- [ ] **Worker change**: `Features/TranscodeJob/ProcessTranscodeQueueService.py` -- detect TestVariantSetId on the picked queue row, iterate variant set, create one TranscodeAttempt per variant with TestVariantSetId+TestVariantName populated, override Crf/FilmGrain/Scale from variant. Sequential within one queue row
- [ ] **Disposition short-circuit**: `Features/QualityTesting/PostTranscodeDispositionService.py:DecidePostTranscodeDisposition` -- if `TranscodeAttempts.TestVariantSetId IS NOT NULL`, return NoReplace with reason="test mode" before any other logic
- [ ] **Recent attempts grouping**: `Features/QualityTesting/QualityTestController.py:RecentAttempts` -- GROUP BY (MediaFileId, COALESCE(TestVariantSetId, 0)) so test rows surface as one row with VariantCount; production rows still surface individually
- [ ] **Frontend grouping**: `Templates/VmafCompare.html` Recent attempts table -- render grouped rows differently (variant-count badge, click Open shows pills)
- [ ] **Retention script** `Scripts/Maintenance/CleanTestModeStaging.py`: removes TestMode TranscodeAttempts.LocalOutputPath files older than retention days; does NOT delete DB rows
- [ ] **Queue admission UI**: `Templates/VmafCompare.html` adds a "Queue for testing" card; new endpoint `POST /api/QualityTest/QueueTestRun` validates and inserts queue rows
- [ ] **Smoke test**: queue 2 sources with the FG sweep set via the UI; observe 8 TranscodeAttempts created; each gets VMAF + auto-captured stills; source files untouched on disk; Recent attempts shows 2 grouped rows
- [ ] **Documentation**: update `transcode.flow.md` to show the test-mode branch of disposition

## Scope

```
Scripts/SQLScripts/AddMultiVariantTesting.py
Scripts/Maintenance/CleanTestModeStaging.py
Features/TranscodeJob/                          -- ProcessTranscodeQueueService variant loop
Features/QualityTesting/PostTranscodeDispositionService.py  -- short-circuit
Features/QualityTesting/QualityTestController.py            -- grouped Recent attempts
Templates/VmafCompare.html                                  -- grouped row rendering
Features/TranscodeJob/multi-variant-testing.feature.md      -- this doc
```

## Files

| File | Role |
|---|---|
| `Scripts/SQLScripts/AddMultiVariantTesting.py` | Schema migration + variant set seed |
| `Features/TranscodeJob/ProcessTranscodeQueueService.py` | Multi-variant execution loop |
| `Features/QualityTesting/PostTranscodeDispositionService.py` | Disposition short-circuit |
| `Features/QualityTesting/QualityTestController.py` | Grouped recent attempts endpoint |
| `Templates/VmafCompare.html` | Grouped row UI |
| `Scripts/Maintenance/CleanTestModeStaging.py` | Retention cleanup |
| `transcode.flow.md` | Pipeline doc update for test-mode branch |

## Out of Scope (deferred to v2)

- **Pre-encode remux of MKV sources**: the bimodal VMAF bug (KNOWN-ISSUES.md) makes MKV-source test data unreliable. v1 deliberately stays on clean MP4 sources (the 4K test corpus). Pre-encode remux is a candidate mitigation in the bug entry and will be addressed as part of the bug fix, not this feature.
- **Variant set editor UI**: operator manages variant sets via SQL for v1. Editor UI is v2.
- **Cross-variant statistical analysis**: comparison trends across many test rows (per-FG median VMAF, etc.) is a v2 reporting surface, not this feature.
- **Parallel variant execution across workers**: v1 runs variants sequentially within one queue row on one worker. Multi-worker parallelism per test set is v2.

## Deviation from conventions

None. Each criterion is observable from outside the codebase (SQL query + UI inspection + file system inspection) and traceable to a specific operator-visible behavior. The grouping criterion (#9) references aggregate behavior, not an internal symbol.
