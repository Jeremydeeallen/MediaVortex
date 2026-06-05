# Agent results scratchpad -- path-schema-migration

Working notes; deleted at directive close.

## Agent A: TranscodeQueueRepository -- DONE

Migrated methods in `Features/TranscodeQueue/TranscodeQueueRepository.py`:
`_MapRowToQueueItem`, `ConvertStringToDateTime`, `GetAllTranscodeQueueItems`, `GetTranscodeQueueItemById`, `SaveTranscodeQueueItem`, `BulkInsertQueueItems`, `GetExistingQueueFilePaths`, `DeleteTranscodeQueueItem`, `UpdateTranscodeQueueStatus`, `GetTranscodeQueueItemsByStatus`, `GetNextPendingTranscodeJob`, `ClaimNextPendingTranscodeJob`, `ClaimNextPendingRemuxJob`, `GetTranscodeQueueItemsPaginated`, `ClearAllTranscodeQueueItems`, `GetQueueStatistics`, `ResetQueueJobsToPending`.

Deletion list for DatabaseManager (parent deletes):
- GetAllTranscodeQueueItems
- GetTranscodeQueueItemsPaginated
- GetTranscodeQueueItemById
- SaveTranscodeQueueItem
- DeleteTranscodeQueueItem
- UpdateTranscodeQueueStatus
- GetTranscodeQueueItemsByStatus
- GetNextPendingTranscodeJob
- ClaimNextPendingTranscodeJob
- ClaimNextPendingRemuxJob
- ClearAllTranscodeQueueItems
- GetQueueStatistics
- ResetQueueJobsToPending

Keep in DatabaseManager (only there, not migrated): `GetJobCounts`.

## Agent B: TranscodeJobRepository -- PENDING

## Agent C: QualityTestRepository -- PENDING

## Agent D: MediaFilesRepository (new) -- PENDING

## Agent E: FileScanningRepository -- PENDING

## Agent F: ShowSettingsRepository + QualityTestingBusinessService -- PENDING

## In-parent migrations DONE

- `Core/Database/BaseRepository.py`: `LookupMediaFileId` migrated to typed pair.
- `Repositories/DatabaseManager.py`: now inherits BaseRepository; local `LookupMediaFileId` deleted.
- `Features/ClipBuilder/ClipBuilderController.py`: 4 SELECT FilePath sites + helper import swap.
- `Features/ClipBuilder/ClipBuilderBusinessService.py`: helper import swap.
- `Features/Profiles/ProfileRepository.py`: `UpdateMediaFilesProfileByRootFolder` typed-pair WHERE.
- `Features/QualityTesting/QualityTestController.py` line 598: typed-pair WHERE.
- `WorkerService/Main.py` line 1244: legacy fallback now reads `StorageRoots.CanonicalPrefix` instead of `MediaFiles.FilePath`.

Earlier parallel-agent work (already on disk):
- `Features/Optimization/OptimizationViewModel.py`
- `Features/ContentSignals/ContentSignalsService.py`
- `Services/QualityTestQueueService.py`
- `Features/ServiceControl/StuckJobDetectionService.py`
- `Features/ServiceControl/CrashRecoveryService.py`
- `Features/ShowSettings/Models/ShowSettingModel.py`
- `Features/SystemSettings/SystemSettingsController.py`

## Migration artifacts created

- `Scripts/SQLScripts/PathSchemaMigration_2026_06_04.py` (idempotent ALTER TABLE DROP COLUMN IF EXISTS).
- `Scripts/PathSchemaPreflight.py` (PASSED on current DB state; zero blockers).
- `path-schema-migration.rollback.md`.
- `Core/Path/V1Compat.py` (shim module providing LookupTypedPair / SynthesizeFilePath / SynthesizeFilePathInRows / v1 helpers).

## Pending operator actions

- pg_dump backup of 6 affected tables.
- Apply migration (`py Scripts/SQLScripts/PathSchemaMigration_2026_06_04.py`).
- Run unit regression.
