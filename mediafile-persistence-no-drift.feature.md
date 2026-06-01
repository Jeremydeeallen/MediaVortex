# MediaFile Persistence: No Drift

**Slug:** mediafile-persistence-no-drift

## SUPERSEDED 2026-05-27

This feature's scope is subsumed by `.claude/directive.md` (clean happy-path
transcode cycle, active under CEO mode). Criterion 2 of the directive requires
every probe-populated column to round-trip through `SaveMediaFile`, which is
the load-bearing invariant this feature was created to enforce.

The criteria below are preserved as design input for the directive's
implementation. Use them as test cases / acceptance shape for criterion 2,
not as a separate feature to ship.

## Interrupts: compliance-gated-rename

## What It Does

Eliminates the recurring bug class where `Repositories/DatabaseManager.SaveMediaFile` silently drops columns assigned by callers because the UPDATE column list is hand-maintained and drifts out of sync with the `MediaFileModel` attribute surface (and with the actual `MediaFiles` table schema). Three confirmed instances of this class to date:

- **BUG-0017** (resolved 2026-05-25): 6 columns dropped (`FileSize`, `LastModifiedDate`, `ResolutionCategory`, `IsInterlaced`, `AudioLanguages`, `HasExplicitEnglishAudio`).
- **BUG-0019** (open): `AudioNormalizationMode` not persisted after loudnorm.
- **BUG-0021** (open, opened 2026-05-27): `AudioComplete` and (apparently) refreshed `Codec`/`AudioCodec` values not persisted after FileReplacement re-probe.

Each prior fix added the missing columns to the UPDATE list and moved on, leaving the architectural cause in place. This feature replaces the hand-maintained list with a mechanically enforced contract: **every column the model claims to manage must round-trip through `SaveMediaFile`**, and **drift between the model, the persistence layer, and the schema must be detectable at deploy time rather than via canary three days later**.

This is an internal infrastructure feature (no user-visible surface) gated by automated round-trip tests. The operator only sees the absence of stale-metadata bugs in future canaries.

## Scope

```
Repositories/DatabaseManager.py                     (SaveMediaFile UPDATE/INSERT paths)
Models/MediaFileModel.py                            (model definition + field surface)
Features/FileReplacement/FileReplacementBusinessService.py   (post-replacement assignment site -- read-only proof of round-trip)
Features/MediaProbe/MediaProbeBusinessService.py    (probe assignment site -- read-only proof of round-trip)
Features/FileScanning/FileScanningRepository.py     (scan assignment site -- read-only proof of round-trip)
Tests/Contract/TestMediaFilePersistence.py          (new -- round-trip + drift test)
KNOWN-ISSUES.md                                     (mark BUG-0017/0019/0021 closed on ship)
```

Explicitly OUT OF SCOPE: changes to `MediaFiles` schema columns themselves (column adds/removes are the operator's data-model decision; this feature only ensures the existing surface persists correctly). Changes to other models' Save methods (this feature is `MediaFile`-scoped; the same class likely exists for `TranscodeAttempt`, `Workers`, etc. -- separate features if/when those bugs surface).

## Success Criteria

1. **Round-trip invariant.** Every persistent attribute on `MediaFileModel` (i.e. every field that maps to a column on the `MediaFiles` table -- excluding computed/transient fields explicitly marked as non-persistent) round-trips through `SaveMediaFile`. Verifiable: a contract test loads any `MediaFiles` row by Id, mutates every persistent attribute to a non-default test value, calls `SaveMediaFile`, re-loads the row, asserts every mutated value persisted unchanged. The test enumerates persistent attributes via a single source of truth (model introspection, declared constant, or schema-derived list -- see criterion 3) so adding a new column without wiring it correctly will fail the test, not pass silently.

2. **Drift detection at startup or test-time.** Discrepancy between (a) the set of persistent attributes declared on `MediaFileModel`, (b) the columns referenced by `SaveMediaFile`'s UPDATE statements (both the duplicate-path UPDATE and the by-Id UPDATE), and (c) the actual columns present on the `MediaFiles` table is reported as an ERROR (logged at WorkerService/WebService startup AND failing a dedicated contract test). The drift report names the offending column(s) and which side is missing. Verifiable: rename a persistent attribute on the model OR add a new column to the schema without updating the model or SaveMediaFile -- the startup ERROR log line names the missing column and the contract test fails with the same message. (Acceptable implementations: model-introspection at startup with assertion; pre-deploy CI hook; schema-derived single source of truth that makes drift impossible at write time.)

3. **Single source of truth.** Adding a persistent column requires editing exactly one declaration to make `SaveMediaFile` write it; no parallel edits to a separate UPDATE column list. Verifiable: add a new column to `MediaFiles` schema, declare it as persistent in the chosen single source (model field, `MEDIAFILE_PERSISTENT_COLUMNS` constant, or schema introspection result), without touching `SaveMediaFile`'s body, then run the round-trip test from criterion 1 -- it passes. (Excludes the migration that adds the column to the actual DB table; that remains a separate migration script as today.)

4. **COALESCE protection preserved for partial-load callers.** Some callers (legacy SELECT paths that don't load every column into the model) call `SaveMediaFile` with a partially-populated model. BUG-0017's fix used `COALESCE(%s, ColumnName)` to prevent these callers from blanking columns they didn't load. The new persistence layer must preserve this protection on the same column set (or a superset). Verifiable: a contract test loads a MediaFile via a legacy SELECT path that omits specific columns, mutates one other field, calls `SaveMediaFile`, re-loads -- the omitted columns retain their original values (not blanked to NULL). The COALESCE set is itself a single-source-of-truth declaration (no hand-maintained list).

5. **BUG-0021 closure.** `Codec`, `AudioCodec`, `AudioComplete`, `AudioCompletedAt`, `AudioCorruptSuspect`, `AudioCorruptReason`, `AudioNormalizationMode`, `SourceIntegratedLufs`, `SourceLoudnessRangeLU`, `SourceTruePeakDbtp`, `SourceIntegratedThresholdLufs`, `LoudnessMeasuredAt`, `LoudnessMeasurementFailureReason`, `NeedsReprobe`, `LastProbedFileSize`, `LastProbedFileMtime`, `AdmissionDeferReason`, `PriorityScore`, `IsCompliant`, `RecommendedMode`, `NeedsQuick`, `NeedsTranscode` all round-trip through `SaveMediaFile` after the feature ships. (Subset of these columns is the BUG-0017/0019/0021 surface; the rest is the audit that confirms no other lurking drops remain.) Verifiable by the same contract test as criterion 1, with these column names explicitly enumerated in the test's expected set.

6. **BUG-0019 closure as side-effect.** `MediaFiles.AudioNormalizationMode` is populated for every encode that ran loudnorm. Verifiable: queue any dynamic-mode-eligible source through Transcode; after FileReplacement, `SELECT AudioNormalizationMode FROM MediaFiles WHERE Id=<id>` returns `'linear'` or `'dynamic'` matching the mode `BuildAudioFilters` selected, NOT NULL. (BUG-0019 is rooted in the same class as BUG-0021; closing the persistence drift closes both.)

7. **No live regression during cutover.** Existing callers (`_UpdateMediaFilesAfterReplacement`, scan path's MediaFile save, probe path's MediaFile save) continue to work without code change OR are migrated as part of the feature. Verifiable: contract tests for FileReplacement, MediaProbe, and FileScanning all pass after the cutover; canary 2 (Brooklyn Nine-Nine 38571 from compliance-gated-rename) re-run lands with all metadata fresh in the DB.

8. **BUG-0017, BUG-0019, BUG-0021 marked Resolved in `KNOWN-ISSUES.md`** on ship, with the cutover date and link to this feature. BUG-0017's "Resolution" stays as the historical 6-column patch (it shipped); the new entries explain the architectural fix that closes the class.

## Status

DRAFT -- criteria not yet approved.

### Progress

- [x] Bug trigger recorded: BUG-0021 (2026-05-27)
- [x] Architectural analysis: hand-maintained UPDATE column list + multi-step model rebuild = recurring silent column drops. Three options proposed (generate-from-fields, single-source-list, runtime-drift-check); criteria 1-4 are implementation-agnostic.
- [x] Feature doc drafted (this document)
- [ ] Criteria reviewed and approved
- [ ] Implementation choice: pick one of (A) dataclasses/pydantic generate UPDATE from fields, (B) `MEDIAFILE_PERSISTENT_COLUMNS` constant referenced by model + repository + migration, (C) runtime introspection + drift assertion at startup. Default recommendation: A (smallest surface, hardest to misuse).
- [ ] Inventory: enumerate every persistent attribute on `MediaFileModel`; cross-check against `MediaFiles` schema (64 columns per the audit) and current SaveMediaFile UPDATE/INSERT lists. Produce the gap list.
- [ ] Implement the chosen mechanism. Replace SaveMediaFile's UPDATE/INSERT bodies. Preserve COALESCE protection per criterion 4 via a declared subset.
- [ ] Contract tests: round-trip (criterion 1), drift detection (criterion 2), single-source add (criterion 3), COALESCE preservation (criterion 4), enumerated column closure (criterion 5).
- [ ] Re-run canary 2 (Brooklyn Nine-Nine 38571) to verify criterion 7 cutover health on a live transcode.
- [ ] Mark BUG-0017/0019/0021 Resolved in KNOWN-ISSUES.md with the architectural fix described.
- [ ] Update FileReplacement.feature.md criterion 14 (BUG-0021 tag) and any sibling tags (BUG-0019 in linear-loudnorm.feature.md) to IMPLEMENTED.

## Files

| File | Role |
|------|------|
| Repositories/DatabaseManager.py | `SaveMediaFile` UPDATE/INSERT paths -- the persistence layer being replaced. |
| Models/MediaFileModel.py | The source of truth for persistent attributes (criterion 3) under recommended option A. |
| Features/FileReplacement/FileReplacementBusinessService.py | `_UpdateMediaFilesAfterReplacement` -- read-only proof of round-trip via canary 2 re-run. Not modified unless the chosen implementation requires caller-side changes. |
| Features/MediaProbe/MediaProbeBusinessService.py | `_ExecuteProbe` -- read-only proof of round-trip via probe contract test. |
| Features/FileScanning/FileScanningRepository.py | `SaveMediaFile` callers in scan path -- read-only proof of round-trip via scan contract test. |
| Tests/Contract/TestMediaFilePersistence.py | New contract test suite -- round-trip, drift, single-source-add, COALESCE preservation. |
| KNOWN-ISSUES.md | BUG-0017/0019/0021 moved to Resolved with the architectural cutover date. |
| Features/FileReplacement/FileReplacement.feature.md | Criterion 14 (BUG-0021) marked IMPLEMENTED on ship. |
| Features/LoudnessAnalysis/linear-loudnorm.feature.md | Criterion 14 (BUG-0019, AudioNormalizationMode) marked IMPLEMENTED on ship. |
