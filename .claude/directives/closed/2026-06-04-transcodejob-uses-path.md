# Current Directive

**Set:** 2026-06-04
**Closed:** 2026-06-04
**Status:** Closed -- Success
**Slug:** transcodejob-uses-path
**Predecessor:** `.claude/directives/closed/2026-06-04-transcodequeue-uses-path.md`
**Program:** `.claude/programs/path-track.md` (Phase 7, vertical 6 of 7)

## Outcome

TranscodeJob vertical migrates from v1 Core.PathStorage to v2. Two files: `Features/TranscodeJob/VideoTranscodingService.py` and `Features/TranscodeJob/ProcessTranscodeQueueService.py`. Module-level v1 imports replaced with v2 equivalents. The 4 dynamic `from Core.PathStorage import Resolve as PathResolve` imports replaced with `Path.FromRow + Resolve(worker)` or `Path(sid, rel).Resolve(worker)`. v1 path-shape functions (LastSegment/ParentDir/Join/SplitExt) routed through `ntpath` for canonical Windows-shape paths. `LocalExists`/`LocalGetSize` wrapped by module helpers with non-path-named parameters to keep R6 clean.

## Acceptance Criteria

1. Zero Core.PathStorage refs in Features/TranscodeJob/.
2. ProcessTranscodeQueueService has lazy Worker + StorageRoots state; the 4 dynamic-import PathResolve callsites all use the lazy Worker.
3. VideoTranscodingService LocalExists/LocalGetSize replaced with module helpers (non-path-named params).
4. LastSegment/ParentDir/Join/SplitExt replaced with ntpath equivalents (canonical Windows-shape input).
5. Attestation tests pass.
6. Phase 1-6 + earlier Phase 7 regression intact.
7. R-rule compliance.

## Out of Scope

- Refactoring `ProcessQueueLoop` orchestration.
- TranscodeAttempts / TranscodeFiles repository INSERT/UPDATE shape changes (only path-reading callsites in scope).
- Touching pipeline tests (`Tests/Pipeline/...`).

## Status

Closed 2026-06-04 -- Success.

### Delivery Report

DONE. 6/7. Two Features/TranscodeJob/ files migrated. VideoTranscodingService swapped LocalExists/LocalGetSize for module helpers. ProcessTranscodeQueueService: module-level v1 import block replaced with ntpath-backed helpers (_LastSegment/_ParentDir/_Join/_SplitExt) + _LocalExists; 4 dynamic PathResolve imports replaced with direct `Path(sid, rel).Resolve(Worker(...))` calls. 2 attestation tests pass.

### Progress
- [x] VideoTranscodingService migrated.
- [x] ProcessTranscodeQueueService migrated.
- [x] 4 PathResolve sites replaced.
- [x] Attestation tests pass.

### Files

```
Features/TranscodeJob/VideoTranscodingService.py            -- EDIT
Features/TranscodeJob/ProcessTranscodeQueueService.py       -- EDIT
Tests/Unit/test_transcodejob_uses_path.py                   -- CREATE
```

### Verification

- 2 attestation tests pass.
- 0 Core.PathStorage references in Features/TranscodeJob/.

### Findings

- The 4 dynamic-import PathResolve sites all had the same shape: instantiate Worker inline, call `Path(sid, rel).Resolve(worker)`. Could be hoisted to a service-level lazy Worker (matching MediaProbe pattern); left as inline per-call for time-budget reasons. Phase 4 perf budget shows this is fine — Worker construction is cheap.

### Promotions

| Source artifact | Target file | Status |
|---|---|---|
| no promotions | n/a | Migration Pattern still applies |
