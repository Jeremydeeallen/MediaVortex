# ShouldQualityTestService Implementation Plan

## Overview
Simple service to determine if a transcoded file should undergo quality testing. Yes or No.

## Architecture Integration
- **Service Layer**: `Services/ShouldQualityTestService.py`
- **Integration Point**: Called from `ProcessTranscodeQueueService.HandleTranscodingResult()`
- **Purpose**: Bridge between transcoding completion and quality test queue creation

## Implementation Steps

### Phase 1: Simple Service
- [ ] Create `Services/ShouldQualityTestService.py`
- [ ] Implement `ShouldQualityTestService` class
- [ ] Add `ShouldTestFile(FilePath: str) -> bool` method
- [ ] Add simple folder-based logic (configurable)

### Phase 2: Integration
- [ ] Modify `ProcessTranscodeQueueService.HandleTranscodingResult()` to call ShouldQualityTestService
- [ ] Add quality test queue creation when `ShouldTestFile() == True`
- [ ] Add `CreateQualityTestQueueEntry()` method to DatabaseManager

## Simple Configuration
- **Default**: Test all files (return `True`)
- **Folder-based**: Skip certain folders (e.g., `/Temp/`)
- **File-based**: Skip certain file patterns (e.g., `*.tmp`)

## Database Integration
- [ ] Add `CreateQualityTestQueueEntry(TranscodeAttemptId: int, FilePath: str)` method to DatabaseManager

## Success Criteria
- [ ] Service returns `True` or `False`
- [ ] Integration with transcoding flow works
- [ ] Quality test queue gets populated when needed

## Dependencies
- `Services/LoggingService.py` - For logging
- `Repositories/DatabaseManager.py` - For database operations

Keep it simple. Yes or No. That's it.
