# TemporaryFilePaths Implementation Plan

## Overview
Implementation plan for creating a TemporaryFilePaths table to track temporary file locations during transcoding, quality testing, and file replacement operations. This follows MVVM architecture with proper logging and error handling.

## Phase 1: Database Schema & Infrastructure

### [X] Create Database Migration Script


### [X] Add DatabaseManager Methods
- **File**: `Repositories/DatabaseManager.py`
- **Methods to add**:
  - `CreateTemporaryFilePath(TranscodeAttemptId, OriginalPath, LocalSourcePath)`
  - `UpdateTemporaryFilePath(TranscodeAttemptId, LocalOutputPath)`
  - `GetTemporaryFilePath(TranscodeAttemptId)`
  - `DeleteTemporaryFilePath(TranscodeAttemptId)`
- **Logging**: Log all CRUD operations to Logs table
- **Error Handling**: Handle invalid TranscodeAttemptId, database connection failures, constraint violations
- **Private Functions**: Use `PrivateValidateTranscodeAttemptId`, `PrivateLogTemporaryFilePathOperation`, `PrivateNormalizeFilePath`
- **Path Normalization**: All file paths normalized to use single backslashes (like MediaFiles table)

## Phase 2: Update Transcoding Service

### [X] Update SetupFilePreparation
- **File**: `Services/ProcessTranscodeQueueService.py`
- **Location**: Line ~350-365
- **Change**: After successful file copy, create TemporaryFilePaths record
- **Logic**: Store `OriginalPath` and `LocalSourcePath`
- **Logging**: Log TemporaryFilePaths record creation success/failure
- **Error Handling**: Handle file copy failures, database insertion failures, rollback scenarios
- **Private Functions**: Use `PrivateCreateTemporaryFilePathRecord`, `PrivateHandleFilePreparationFailure`

### [X] Update HandleTranscodingResult
- **File**: `Services/ProcessTranscodeQueueService.py`
- **Location**: Line ~570-580
- **Change**: Update TemporaryFilePaths record with `LocalOutputPath`
- **Logic**: Query table to get correct paths for quality test creation
- **Logging**: Log TemporaryFilePaths record update success/failure
- **Error Handling**: Handle missing TemporaryFilePaths records, update failures, quality test creation failures
- **Private Functions**: Use `PrivateUpdateTemporaryFilePathRecord`, `PrivateHandleTranscodingResultFailure`

## Phase 3: Update Quality Testing Service

### [ ] Update Quality Test Creation
- **File**: `Services/ProcessTranscodeQueueService.py`
- **Location**: Line ~578-580
- **Change**: Query TemporaryFilePaths table instead of using `Job.FilePath`
- **Logic**: Use `LocalSourcePath` and `LocalOutputPath` from table
- **Logging**: Log TemporaryFilePaths table query results, quality test creation attempts
- **Error Handling**: Handle missing TemporaryFilePaths records, fallback to original behavior
- **Private Functions**: Use `PrivateGetTemporaryFilePaths`, `PrivateCreateQualityTestWithCorrectPaths`

### [ ] Update Quality Test Execution
- **File**: `Services/QualityTestingBusinessService.py`
- **Location**: Line ~141-143
- **Change**: Ensure correct file paths are used (should already work with Phase 3.1)
- **Logging**: Log file path validation, FFmpeg command construction
- **Error Handling**: Handle file not found errors, path validation failures
- **Private Functions**: Use `PrivateValidateQualityTestFilePaths`, `PrivateLogFFmpegCommand`

## Phase 4: Clean Up Existing Hardcoded Paths

### [ ] Remove Hardcoded Paths from ProcessTranscodeQueueService
- **File**: `Services/ProcessTranscodeQueueService.py`
- **Locations to clean up**:
  - Line 359: `DestinationPath = f"C:\\MediaVortex\\Source\\{MediaFile.FileName}"`
  - Line 684: `return os.path.join("C:\\MediaVortex", InputFileName)`
  - Line 690: `return os.path.join("C:\\MediaVortex", InputFileName)`
  - Line 699: `OutputFilePath = os.path.join("C:\\MediaVortex", OutputFileName)`
- **Replace with**: TemporaryFilePaths table lookups
- **Logging**: Log hardcoded path removal, migration to table-based approach
- **Error Handling**: Handle missing TemporaryFilePaths records gracefully

### [ ] Remove Hardcoded Paths from CommandBuilder
- **File**: `Models/CommandBuilder.py`
- **Locations to clean up**:
  - Line 35: `InputPath = f"c:\\MediaVortex\\Source\\{MediaFile.FileName}"`
  - Line 39: `OutputPath = f"c:\\MediaVortex\\{OutputFileName}"`
- **Replace with**: TemporaryFilePaths table lookups
- **Logging**: Log command builder path migration
- **Error Handling**: Handle missing TemporaryFilePaths records

### [ ] Remove Hardcoded Paths from FileReplacementBusinessService
- **File**: `Services/FileReplacementBusinessService.py`
- **Locations to clean up**:
  - Line 257: `temp_source_path = f"C:\\MediaVortex\\Source\\{os.path.basename(OriginalFilePath)}"`
- **Replace with**: TemporaryFilePaths table lookups
- **Logging**: Log file replacement path migration
- **Error Handling**: Handle missing TemporaryFilePaths records

### [ ] Remove Hardcoded Paths from TranscodingFileManagerService
- **File**: `Services/TranscodingFileManagerService.py`
- **Locations to clean up**:
  - Line 20: `SourceDir = "C:\\MediaVortex\\Source"`
  - Line 26: `OutputDir = "C:\\MediaVortex"`
- **Replace with**: Configuration-based paths or TemporaryFilePaths table
- **Logging**: Log file manager path migration
- **Error Handling**: Handle configuration failures

### [ ] Remove Hardcoded Paths from FileManagerService
- **File**: `Services/FileManagerService.py`
- **Locations to clean up**:
  - Line 258: `mediaVortexSourceDir = r"c:\MediaVortex\Source"`
  - Line 259: `mediaVortexTempDir = r"c:\MediaVortex"`
- **Replace with**: Configuration-based paths
- **Logging**: Log file manager path migration
- **Error Handling**: Handle configuration failures

### [ ] Clean Up Test Files
- **Files to clean up**:
  - `Tests/CursorTests/CheckVMAFQueuePaths.py` (Line 43: hardcoded path)
  - `Tests/CursorTests/ManualFileReplacement.py` (Line 46: hardcoded path)
- **Replace with**: TemporaryFilePaths table lookups or configuration
- **Logging**: Log test file cleanup
- **Error Handling**: Handle test environment setup failures

## Phase 5: Add Cleanup & Error Handling

### [ ] Add Cleanup Methods
- **File**: `Services/ProcessTranscodeQueueService.py`
- **Purpose**: Clean up TemporaryFilePaths records when processing completes
- **Location**: In `CleanupOrContinue` method
- **Logging**: Log cleanup operations, record deletion success/failure
- **Error Handling**: Handle cleanup failures, orphaned records
- **Private Functions**: Use `PrivateCleanupTemporaryFilePathRecord`, `PrivateHandleCleanupFailure`

### [ ] Add Error Handling
- **Purpose**: Handle cases where TemporaryFilePaths records don't exist
- **Logic**: Fallback to current behavior if table lookup fails
- **Logging**: Log fallback scenarios, missing record warnings
- **Error Handling**: Graceful degradation, user notification
- **Private Functions**: Use `PrivateHandleMissingTemporaryFilePath`, `PrivateLogFallbackBehavior`

## Phase 5: Testing & Validation

### [ ] Test Complete Flow
- Run a transcode job from start to finish
- Verify TemporaryFilePaths table is populated correctly
- Verify quality test uses correct local file paths
- Verify cleanup removes temporary records
- **Logging**: Log test execution steps, validation results
- **Error Handling**: Handle test failures, data validation errors

### [ ] Test Error Scenarios
- Test with missing TemporaryFilePaths records
- Test with file copy failures
- Test with transcoding failures
- Test with database connection failures
- **Logging**: Log error scenario testing, failure recovery
- **Error Handling**: Verify graceful error handling, proper cleanup

## Implementation Order:
1. **Database migration script** (Phase 1.1)
2. **DatabaseManager methods** (Phase 1.2)
3. **Update SetupFilePreparation** (Phase 2.1)
4. **Update HandleTranscodingResult** (Phase 2.2)
5. **Update quality test creation** (Phase 3.1)
6. **Clean up hardcoded paths** (Phase 4.1-4.6)
7. **Add cleanup methods** (Phase 5.1)
8. **Test implementation** (Phase 6.1)

## Files with Hardcoded Paths to Clean Up:
- **ProcessTranscodeQueueService.py**: 4 hardcoded paths (lines 359, 684, 690, 699)
- **CommandBuilder.py**: 2 hardcoded paths (lines 35, 39)
- **FileReplacementBusinessService.py**: 1 hardcoded path (line 257)
- **TranscodingFileManagerService.py**: 2 hardcoded paths (lines 20, 26)
- **FileManagerService.py**: 2 hardcoded paths (lines 258, 259)
- **Test files**: 2 hardcoded paths in test scripts

## Benefits After Implementation:
- ✅ Quality tests use correct local file paths
- ✅ File Replacement feature can find transcoded files
- ✅ ShouldTranscode can check processing status
- ✅ No hardcoded paths in business logic
- ✅ Clean separation of temporary file management
- ✅ Easy cleanup when processing completes
- ✅ Comprehensive logging for troubleshooting
- ✅ Robust error handling and recovery

## Architecture Compliance:
- **MVVM Pattern**: Models (business logic), ViewModels (presentation logic), Views (UI)
- **PascalCase Naming**: All variables, functions, classes, files, tables, columns, routes, URLs
- **KISS Principle**: Keep It Simple, Stupid - straightforward implementation
- **Private Functions**: All private functions start with "Private" (no underscores)
- **Logging**: All operations logged to Logs table for debugging and monitoring
- **Error Handling**: Comprehensive error handling with graceful degradation
x