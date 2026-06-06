# Directive (backlog): Business Service Decompose

**Slug:** business-service-decompose
**Prerequisite:** `db-monolith-decompose` (services should depend on per-aggregate Repos before they get sub-divided; otherwise the decomposed pieces all still hold the god-DatabaseManager)

## Outcome

The 2000+ line "god services" (`FileScanningBusinessService`, `QualityTestingBusinessService`, `ProcessTranscodeQueueService`) get decomposed by Single Responsibility into focused sub-modules. Each new module owns one concern (scanning, dedup-detection, move-detection, reconcile, cleanup -- not all five in one class).

After this directive: a unit test for "duplicate detection" doesn't pull in scanning + reconcile + move-detection code. Each concern is independently testable, deployable as a separate microservice if/when warranted, and modifiable without ripple risk.

## Acceptance Criteria

1. `FileScanningBusinessService` decomposed into: `FileScanner` (the walk + insert), `DuplicateReconciler` (the dedup pass), `MovedFileDetector` (rename detection), `MissingFileSweeper` (cleanup), `RootFolderManager` (add/save/remove root folders). Each is its own class in its own file.
2. `QualityTestingBusinessService` decomposed into: `VmafCommandBuilder`, `VmafExecutor`, `VmafResultParser`, `ComparisonStillGenerator`, `DispositionHandler`. Same pattern.
3. `ProcessTranscodeQueueService` decomposed into: `TranscodeClaimant` (claim + dispatch), `TranscodeExecutor` (ffmpeg invoke + monitor), `PostTranscodeRouter` (disposition + handoff). Same pattern.
4. The original god-class files either (a) become thin orchestrators that compose the sub-modules, or (b) get deleted entirely with callers updated. Decide per service.
5. R-rule: any service file exceeding 800 LOC triggers a refactor recommendation (advisory, not blocking).
6. Test isolation: a `pytest -k duplicate_detection` run touches only the DuplicateReconciler + its mocked Reader dependencies. No FileScanner imports.
7. Existing end-to-end smoke (transcode + VMAF + scan) still green after the decomposition.

## Out of Scope

- Splitting WebService into microservices. The decomposition unlocks it; the actual process split is a separate operator decision.
- The smaller services (`MediaProbeBusinessService`, `OptimizationViewModel`, etc.) -- they're already close to SRP and don't need this treatment.
- Renaming any external/public method signatures. Internal restructure only.

## Why this is backlog

The decomposition is most valuable AFTER per-aggregate Repos exist (sub-modules can depend on focused Repos instead of god-DatabaseManager). It's also higher-risk than the repo split because business logic is being moved, not just renamed. Sequence: `db-monolith-decompose` first, then this.

## Estimated scope

Large. Each of the 3 god-services is its own sub-directive. Plan to do `business-service-decompose-filescanning`, `business-service-decompose-qualitytesting`, `business-service-decompose-transcodejob` as separate worktree-based directives in sequence.

## Notes for sequencing

If `query-vs-write-split` lands before this directive: the decomposed sub-modules can each take Reader/Writer pairs as constructor injection -- cleaner DI. If `query-vs-write-split` does NOT land first: sub-modules take Repos (same as the rest of the codebase), still better than god-DatabaseManager.
