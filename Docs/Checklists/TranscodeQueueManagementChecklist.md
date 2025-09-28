# Transcode Queue Management Checklist

## Overview
Implementation checklist for the Transcode Queue Management Workflow, following MVVM architecture and single responsibility principles.

## Clear Queue Operation (Modify Existing)

### Database Layer
- [ ] **Rename `DatabaseManager.ClearAllTranscodeQueueItems()` to `ClearPendingAndCancelledJobs()`** - Change from clearing ALL items to only clearing "Pending" and "Cancelled" jobs
- [ ] **Add `DatabaseManager.GetTranscodeQueueItemsByStatus()`** - Helper method to get jobs by status (if not exists)

### ViewModel Layer  
- [ ] **Modify `TranscodeQueueViewModel.ClearQueue()`** - Update to use new selective clearing method
- [ ] **Add status validation** - Ensure running jobs are preserved during clear operation

### Controller Layer
- [ ] **Update `TranscodeQueueController.ClearQueue()`** - Keep simple name for HTTP endpoint, ensure proper error handling

### View Layer
- [ ] **Update `TranscodeQueue.html` clearQueue() function** - Add confirmation dialog for selective clearing
- [ ] **Add status indicators** - Show which jobs will be cleared vs preserved

## Stop Transcoding Operation (Enhance Existing)

### Service Layer
- [ ] **Enhance `ProcessTranscodeQueueService.Stop()`** - Already implemented, verify it handles all requirements
- [ ] **Add `ProcessTranscodeQueueService.CancelRunningJob()`** - New method to cancel specific running job
- [ ] **Enhance `VideoTranscodingService.StopTranscoding()`** - Already implemented, verify process termination
- [ ] **Add `TranscodingFileManagerService.CleanupTemporaryFiles()`** - New service method for file cleanup

### Database Layer
- [ ] **Add `DatabaseManager.UpdateTranscodeQueueStatus()`** - Method to update queue item status to "Cancelled"
- [ ] **Enhance `DatabaseManager.UpdateTranscodeAttempt()`** - Ensure it handles cancellation status
- [ ] **Verify `DatabaseManager.DeleteTranscodeProgress()`** - Already exists, ensure it's called properly

### ViewModel Layer
- [ ] **Enhance `ActivityViewModel.StopTranscoding()`** - Add queue status update and file cleanup
- [ ] **Add `ActivityViewModel.CancelCurrentJob()`** - New method for cancelling specific job

### Controller Layer
- [ ] **Enhance `TranscodeJobController.StopTranscoding()`** - Add queue status update and file cleanup calls
- [ ] **Add confirmation handling** - Ensure user confirms destructive operation

### View Layer
- [ ] **Update `Activity.html` stopTranscoding() function** - Add confirmation dialog
- [ ] **Update `TranscodeProgress.html`** - Ensure stop button works properly
- [ ] **Add progress cleanup** - Clear progress display when transcoding stops

## File Cleanup Service (New)

### Service Layer
- [ ] **Create `Services/TranscodingFileCleanupService.py`** - New service for temporary file management
- [ ] **Add `CleanupTemporaryFiles()`** - Method to clean C:\MediaVortex\ and C:\MediaVortex\Source\
- [ ] **Add `CleanupTranscodingFiles()`** - Method to clean transcoding-specific files
- [ ] **Add file pattern matching** - Identify transcoding files vs other files
- [ ] **Add safety checks** - Ensure only transcoding files are deleted

### Integration
- [ ] **Integrate with `ProcessTranscodeQueueService.Stop()`** - Call cleanup service during stop
- [ ] **Add error handling** - Handle file cleanup failures gracefully
- [ ] **Add logging** - Log all file cleanup operations

## Database Schema Updates (If Needed)

### Schema Verification
- [ ] **Verify TranscodeQueue.Status column** - Ensure "Cancelled" status is supported
- [ ] **Verify TranscodeAttempts.ErrorMessage column** - Ensure it can store cancellation messages
- [ ] **Verify TranscodeProgress cleanup** - Ensure progress records are properly deleted

## Error Handling & Logging

### Error Handling
- [ ] **Add comprehensive try-catch blocks** - All new methods need proper error handling
- [ ] **Add rollback mechanisms** - If file cleanup fails, ensure database consistency
- [ ] **Add timeout handling** - Process termination should have timeouts

### Logging
- [ ] **Add operation logging** - Log all clear queue and stop transcoding operations
- [ ] **Add file cleanup logging** - Log all file deletions for audit trail
- [ ] **Add error logging** - Log all failures with context

## Testing & Validation

### Unit Tests
- [ ] **Test selective queue clearing** - Verify only pending/cancelled jobs are removed
- [ ] **Test stop transcoding** - Verify all processes stop and cleanup occurs
- [ ] **Test file cleanup** - Verify only transcoding files are deleted
- [ ] **Test error scenarios** - Test failure cases and recovery

### Integration Tests
- [ ] **Test end-to-end clear queue** - Full workflow test
- [ ] **Test end-to-end stop transcoding** - Full workflow test
- [ ] **Test concurrent operations** - Ensure no race conditions

## Documentation Updates

### Documentation
- [ ] **Update API documentation** - Document new endpoints and parameters
- [ ] **Update user guide** - Document new clear queue behavior
- [ ] **Update troubleshooting guide** - Document common issues and solutions

## MVVM Architecture Compliance

### Single Responsibility
- [ ] **DatabaseManager** - Only database operations
- [ ] **TranscodingFileCleanupService** - Only file cleanup operations  
- [ ] **ProcessTranscodeQueueService** - Only transcoding process management
- [ ] **ViewModels** - Only UI state management and coordination

### Separation of Concerns
- [ ] **Models** - Data structures only
- [ ] **ViewModels** - UI logic only
- [ ] **Services** - Business logic only
- [ ] **Controllers** - HTTP handling only

## Implementation Notes

### File Locations
- **DatabaseManager**: `Repositories/DatabaseManager.py`
- **TranscodeQueueViewModel**: `ViewModels/TranscodeQueueViewModel.py`
- **TranscodeQueueController**: `Controllers/TranscodeQueueController.py`
- **ProcessTranscodeQueueService**: `Services/ProcessTranscodeQueueService.py`
- **VideoTranscodingService**: `Services/VideoTranscodingService.py`
- **ActivityViewModel**: `ViewModels/ActivityViewModel.py`
- **TranscodeJobController**: `Controllers/TranscodeJobController.py`
- **TranscodeQueue.html**: `Templates/TranscodeQueue.html`
- **Activity.html**: `Templates/Activity.html`
- **TranscodeProgress.html**: `Templates/TranscodeProgress.html`

### Key Requirements
- **Clear Queue**: Only remove "Pending" and "Cancelled" jobs, preserve "Running" jobs
- **Stop Transcoding**: Stop processes, update status to "Cancelled", clean up files
- **File Cleanup**: Remove files from C:\MediaVortex\ and C:\MediaVortex\Source\
- **Database Updates**: Update TranscodeAttempt with cancellation details
- **Progress Cleanup**: Delete TranscodeProgress records

### Success Criteria
- [ ] Clear queue preserves running jobs
- [ ] Stop transcoding terminates all processes
- [ ] File cleanup removes only transcoding files
- [ ] Database records are properly updated
- [ ] UI reflects correct state after operations
- [ ] Error handling prevents data corruption
- [ ] Logging provides audit trail
