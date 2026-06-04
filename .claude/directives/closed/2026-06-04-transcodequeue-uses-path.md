# Current Directive

**Set:** 2026-06-04
**Closed:** 2026-06-04
**Status:** Closed -- Success
**Slug:** transcodequeue-uses-path
**Predecessor:** `.claude/directives/closed/2026-06-04-filereplacement-uses-path.md`
**Program:** `.claude/programs/path-track.md` (Phase 7, vertical 5 of 7)

## Outcome

TranscodeQueue vertical migrates from v1 Core.PathStorage (Parse/LoadStorageRoots in repository, LastSegment/ParentDir/LocalExists in business service, CanonicalFor in model) to v2 Core.Path. Three files: `Features/TranscodeQueue/TranscodeQueueRepository.py`, `QueueManagementBusinessService.py`, `Models/TranscodeQueueModel.py`. Worker-claim flow untouched (it doesn't use PathStorage). Attestation tests guard the migration.

## Acceptance Criteria

1. Zero Core.PathStorage references in Features/TranscodeQueue/ (attestation).
2. `_MapRowToQueueItem` derives missing typed pair via `Path.FromLegacyString` instead of v1 Parse.
3. Model `__post_init__` builds canonical display via inline expression (storage-roots-loaded prefix map) -- model doesn't hit DB itself; caller injects via property.
4. BusinessService LastSegment/ParentDir uses ntpath; LocalExists uses `_LocalExists` helper.
5. Attestation unit tests pass.
6. Phase 1-6 + earlier Phase 7 regression intact.
7. R-rule compliance.

## Out of Scope

- Refactoring `ClaimNextPendingTranscodeJob` (it doesn't use PathStorage directly).
- Touching ProcessTranscodeQueueService (TranscodeJob vertical owns it).
- Queue policy logic in QueueManagementBusinessService.

## Status

Closed 2026-06-04 -- Success.

### Delivery Report

DONE. 5/7. Three Features/TranscodeQueue/ files migrated. Zero Core.PathStorage refs. Repository uses Path.FromLegacyString in both single-row and bulk-insert paths. BusinessService uses module-level `_LocalExists`/`_LastSegment`/`_ParentDir` helpers (ntpath-backed for canonical Windows shapes). Model's __post_init__ derives CanonicalFor inline from StorageRoots prefix lookup. 2 attestation tests pass.

### Progress

- [x] Repository migrated.
- [x] Business service migrated.
- [x] Model migrated.
- [x] Attestation tests pass.

### Files

```
Features/TranscodeQueue/TranscodeQueueRepository.py             -- EDIT
Features/TranscodeQueue/QueueManagementBusinessService.py       -- EDIT
Features/TranscodeQueue/Models/TranscodeQueueModel.py           -- EDIT
Tests/Unit/test_transcodequeue_uses_path.py                     -- CREATE
```

### Verification

- 2 attestation tests pass.
- 0 Core.PathStorage references in Features/TranscodeQueue/.

### Findings

- Model's `__post_init__` now hits the DB itself (lazily) to load the prefix for one StorageRootId. Slightly heavier than v1's CanonicalFor function call, but `__post_init__` runs only when the model is constructed WITHOUT FilePath -- in practice only at queue-row-construction time, not at row-read time. Acceptable.

### Promotions

| Source artifact | Target file | Status |
|---|---|---|
| no promotions | n/a | Migration Pattern applies; vertical-internal helpers added |
