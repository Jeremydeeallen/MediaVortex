# Transcode Queue Management Workflow

## Overview
This workflow defines the behavior for managing the transcoding queue, including clearing pending jobs and stopping active transcoding processes.

## Clear Queue Operation

### Purpose
Remove pending and cancelled jobs from the queue while allowing running jobs to continue.

### Behavior
- **Clear Pending Jobs**: Remove all jobs with status "Pending" from the queue
- **Clear Cancelled Jobs**: Remove all jobs with status "Cancelled" from the queue  
- **Preserve Running Jobs**: Leave jobs with status "Running" untouched
- **No Process Interruption**: Do not stop any active transcoding processes

### Implementation Requirements
- Query TranscodeQueue table for jobs with status "Pending" or "Cancelled"
- Delete these records from the database
- Do not interact with ProcessTranscodeQueueService or VideoTranscodingService
- Do not modify TranscodeProgress or TranscodeAttempts tables

## Stop Transcoding Operation

### Purpose
Immediately stop all transcoding activity and clean up associated data.

### Behavior
1. **Stop Transcoding Processes Only**
   - Terminate only the active transcoding FFmpeg processes
   - Stop transcoding threads managed by ProcessTranscodeQueueService
   - Clear ProcessTranscodeQueueService.ActiveJobs list
   - Do not interfere with other FFmpeg processes (VMAF, analysis, etc.)

2. **Update Queue Status**
   - Change currently running job status from "Running" to "Cancelled"
   - Update TranscodeQueue record with cancelled status

3. **Update TranscodeAttempt Record**
   - Set TranscodeAttempt.Success = False
   - Set TranscodeAttempt.ErrorMessage = "Cancelled by user"
   - Update TranscodeAttempt record with cancellation details

4. **Clean Up Progress Data**
   - Delete record from TranscodeProgress table
   - Remove all progress tracking data

5. **Clean Up Temporary Files**
   - Delete files from C:\MediaVortex\ (output directory)
   - Delete files from C:\MediaVortex\Source\ (source directory)
   - Remove any temporary transcoding files

### Implementation Requirements
- Call ProcessTranscodeQueueService.Stop() (stops only transcoding processes)
- Update TranscodeQueue status to "Cancelled"
- Update TranscodeAttempt with cancellation details
- Delete from TranscodeProgress table
- Clean up temporary files in both directories
- Ensure no orphaned transcoding processes or data remain
- Do not affect VMAF processes, file analysis, or other FFmpeg operations

## User Interface Integration

### Clear Queue Button
- **Location**: TranscodeQueue page
- **Action**: Clear pending and cancelled jobs only
- **Confirmation**: "Clear all pending and cancelled jobs from queue?"
- **Result**: Queue shows only running jobs

### Stop Transcoding Button  
- **Location**: Activity/TranscodeProgress pages
- **Action**: Stop all transcoding and clean up
- **Confirmation**: "Stop transcoding and cancel current job? This cannot be undone."
- **Result**: All transcoding stops, queue shows no active jobs

## Database State Management

### Clear Queue State
```
Before: [Pending, Pending, Running, Cancelled, Pending]
After:  [Running]
```

### Stop Transcoding State
```
Before: [Running] + Active FFmpeg Process + Progress Data
After:  [Cancelled] + No Processes + Clean Database
```

## Error Handling

### Clear Queue Errors
- If no pending/cancelled jobs exist, show "No jobs to clear"
- If database error occurs, show "Failed to clear queue"
- Always preserve running jobs regardless of errors

### Stop Transcoding Errors
- If no active transcoding, show "No transcoding to stop"
- If process termination fails, show "Failed to stop transcoding"
- Always attempt cleanup even if some operations fail
- Log all cleanup operations for debugging

## File Cleanup Requirements

### Directories to Clean
- `C:\MediaVortex\` - Output transcoded files
- `C:\MediaVortex\Source\` - Temporary source files

### Cleanup Strategy
- List all files in both directories
- Delete files that match transcoding patterns
- Preserve any files not related to current transcoding
- Log all file deletions for audit trail

## Implementation Notes

### MVVM Architecture Compliance
- **Models**: TranscodeQueueModel, TranscodeAttemptModel, TranscodeProgressModel
- **ViewModels**: TranscodeQueueViewModel, ActivityViewModel  
- **Views**: TranscodeQueue.html, Activity.html
- **Services**: ProcessTranscodeQueueService, VideoTranscodingService
- **Controllers**: TranscodeQueueController, TranscodeJobController

### Database Operations
- Use existing DatabaseManager methods where possible
- Add new methods for file cleanup operations
- Ensure all operations are wrapped in try-catch blocks
- Log all database modifications

### Process Management
- Use existing VideoTranscodingService.StopTranscoding()
- Enhance ProcessTranscodeQueueService.Stop() method
- Ensure proper thread cleanup
- Handle timeout scenarios gracefully
