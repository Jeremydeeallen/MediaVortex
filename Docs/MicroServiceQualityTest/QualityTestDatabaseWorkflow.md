# MicroServiceQualityTest Database Workflow

## Overview
This document describes the complete database workflow for the MicroServiceQualityTest service, from service startup through job processing to completion.

## Database Tables Involved

### Primary Tables
- **QualityTestingQueue**: Main job queue with status tracking
- **ActiveJobs**: Process monitoring and tracking
- **QualityTestResults**: Historical results storage
- **QualityTestProgress**: Real-time progress tracking during FFmpeg execution
- **SystemSettings**: Configuration management

## Complete Database Workflow

### 1. Service Startup
```sql
-- Read MaxConcurrentJobs setting to determine worker count
SELECT SettingValue 
FROM SystemSettings 
WHERE SettingKey = 'MaxConcurrentJobs'
```
**Result**: Service creates N worker threads based on this value

### 2. Worker Claims Job (Atomic Operation)
```sql
-- Step 1: Get the job to claim
SELECT Id, TranscodeAttemptId, OriginalFilePath, LocalSourcePath, TranscodedFilePath, Status, VMAFScore, CreatedDate
FROM QualityTestingQueue 
WHERE Status = 'Pending' 
ORDER BY Priority DESC, DateAdded ASC, CreatedDate ASC 
LIMIT 1

-- Step 2: Atomically claim the job
UPDATE QualityTestingQueue 
SET Status = 'Running', DateStarted = CURRENT_TIMESTAMP
WHERE Id = ? AND Status = 'Pending'
```
**Result**: Only one worker can claim each job, preventing conflicts
**Note**: Uses two-step process for SQLite compatibility

### 3. Create Active Job Tracking
```sql
-- Create active job record for process monitoring
INSERT INTO ActiveJobs (ServiceName, JobType, QueueId, ProcessId, ThreadId, Status, StartedAt)
VALUES ('QualityTest', 'QualityTest', 160, 1234, 0, 'Running', CURRENT_TIMESTAMP)
```
**Result**: Job is tracked in ActiveJobs table for monitoring

### 4. Job Processing - Real-time Progress Tracking
```sql
-- Create initial progress record when FFmpeg starts
INSERT INTO QualityTestProgress 
(QualityTestQueueId, TranscodeAttemptId, Status, ProgressPercentage, CurrentStep, 
 StartTime, SubprocessPID, SubprocessStartTime, CreatedAt, UpdatedAt)
VALUES (160, 288, 'Running', 0, 'Processing', CURRENT_TIMESTAMP, 1234, CURRENT_TIMESTAMP, 
        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)

-- Update progress during FFmpeg execution (multiple times)
UPDATE QualityTestProgress SET
    ProgressPercentage = 45.2, CurrentTime = '00:01:23.45', CurrentFrame = 1250, 
    TotalFrames = 2765, ProcessingSpeed = '1.2x', UpdatedAt = CURRENT_TIMESTAMP
WHERE QualityTestQueueId = 160
```
**Result**: Real-time progress tracking during FFmpeg VMAF comparison

### 5. Success Path - Update Job Status
```sql
-- Mark job as completed with VMAF score
UPDATE QualityTestingQueue 
SET Status = 'Completed', VMAFScore = 85.2, CompletedDate = CURRENT_TIMESTAMP
WHERE Id = 160
```
**Result**: Job status updated to Completed with VMAF score

### 5a. Success Path - Complete Progress Tracking
```sql
-- Mark progress as completed
UPDATE QualityTestProgress SET
    Status = 'Completed', ProgressPercentage = 100.0, EndTime = CURRENT_TIMESTAMP, 
    UpdatedAt = CURRENT_TIMESTAMP
WHERE QualityTestQueueId = 160
```
**Result**: Progress tracking completed

### 6. Success Path - Store Results
```sql
-- Store detailed results in results table for historical tracking
INSERT INTO QualityTestResults (VMAFQueueId, TranscodeAttemptId, VMAFScore, ProfileId, ProfileName, FileSize, TestDuration, PassesThreshold, Rank, ErrorMessage, DateTested)
VALUES (160, 288, 85.2, 1, 'High Quality', 1048576, 45.2, 1, 1, NULL, CURRENT_TIMESTAMP)
```
**Result**: Results permanently stored for analysis and reporting
**Note**: ProfileId is looked up from Profiles table using ProfileName from TranscodeAttempts

### 7. Success Path - Remove from Queue
```sql
-- Remove completed job from QualityTestingQueue (revolving door)
DELETE FROM QualityTestingQueue WHERE Id = 160
```
**Result**: Job removed from queue after successful completion

### 8. Success Path - Complete Active Job
```sql
-- Mark active job as completed
UPDATE ActiveJobs 
SET Status = 'Completed', CompletedAt = CURRENT_TIMESTAMP
WHERE Id = 25545
```
**Result**: Active job tracking completed

### 9. Failure Path - Update Job Status
```sql
-- Mark job as failed
UPDATE QualityTestingQueue 
SET Status = 'Failed', CompletedDate = CURRENT_TIMESTAMP
WHERE Id = 160
```
**Result**: Job marked as failed for retry or analysis

### 9a. Failure Path - Update Progress Tracking
```sql
-- Mark progress as failed with error message
UPDATE QualityTestProgress SET
    Status = 'Failed', EndTime = CURRENT_TIMESTAMP, ErrorMessage = 'FFmpeg failed with return code 4294967274',
    UpdatedAt = CURRENT_TIMESTAMP
WHERE QualityTestQueueId = 160
```
**Result**: Progress tracking marked as failed

### 10. Failure Path - Store Error Results
```sql
-- Store failed result with error message
INSERT INTO QualityTestResults (VMAFQueueId, TranscodeAttemptId, VMAFScore, ProfileId, ProfileName, FileSize, TestDuration, PassesThreshold, Rank, ErrorMessage, DateTested)
VALUES (160, 288, 0.0, 1, 'High Quality', 1048576, 0.0, 0, 0, 'FFmpeg failed with return code 4294967274', CURRENT_TIMESTAMP)
```
**Result**: Error details stored for debugging

### 11. Failure Path - Complete Active Job
```sql
-- Mark active job as failed
UPDATE ActiveJobs 
SET Status = 'Failed', CompletedAt = CURRENT_TIMESTAMP, ErrorMessage = 'FFmpeg failed with return code 4294967274'
WHERE Id = 25545
```
**Result**: Active job marked as failed

### 12. Worker Continues - Next Job
```sql
-- Worker immediately tries to claim next job (back to step 2)
-- Uses the same two-step process as step 2
```
**Result**: Worker continues processing queue

## Job State Lifecycle

### QualityTestingQueue Status Flow
```
Pending → Running → Completed (Success)
Pending → Running → Failed (Error)
Pending → Running → Pending (Interrupted - for retry)
```

### ActiveJobs Status Flow
```
Created → Running → Completed (Success)
Created → Running → Failed (Error)
```

## Database State Examples

### Successful Job Processing
```
QualityTestingQueue:
Id=160, Status='Pending' → Status='Running' → DELETED (job completed)

ActiveJobs:
Id=25545, Status='Running' → Status='Completed'

QualityTestProgress:
New record: QualityTestQueueId=160, Status='Running' → Progress updates (0% → 100%) → Status='Completed'

QualityTestResults:
New record: VMAFQueueId=160, VMAFScore=85.2, ProfileId=1, ProfileName='High Quality', FileSize=1048576, TestDuration=45.2, PassesThreshold=1, Rank=1, ErrorMessage=NULL
```

### Failed Job Processing
```
QualityTestingQueue:
Id=160, Status='Pending' → Status='Running' → Status='Failed'

ActiveJobs:
Id=25545, Status='Running' → Status='Failed'

QualityTestProgress:
New record: QualityTestQueueId=160, Status='Running' → Progress updates (0% → 45%) → Status='Failed' with ErrorMessage

QualityTestResults:
New record: VMAFQueueId=160, VMAFScore=0.0, ProfileId=1, ProfileName='High Quality', FileSize=1048576, TestDuration=0.0, PassesThreshold=0, Rank=0, ErrorMessage='FFmpeg failed'
```

## Key Database Features

### 1. Atomic Job Claiming
- **Purpose**: Prevents race conditions between multiple workers
- **Method**: Single UPDATE statement with subquery
- **Result**: Only one worker can claim each job

### 2. Status Tracking
- **Purpose**: Monitor job progress and state
- **States**: Pending → Running → Completed/Failed
- **Benefit**: Clear visibility into job lifecycle

### 3. Dual Storage
- **QualityTestingQueue**: Current job state and results
- **QualityTestResults**: Historical results for analysis
- **Benefit**: Both current status and permanent history

### 4. Active Monitoring
- **Purpose**: Track running processes and detect stuck jobs
- **ActiveJobs Table**: Real-time process monitoring
- **Benefit**: System health and debugging

### 5. Real-time Progress Tracking
- **Purpose**: Monitor FFmpeg execution progress in real-time
- **QualityTestProgress Table**: Live progress updates during VMAF comparison
- **Fields**: ProgressPercentage, CurrentFrame, TotalFrames, ProcessingSpeed, CurrentTime
- **Benefit**: User visibility into long-running quality tests

### 6. Revolving Door Pattern
- **Successful jobs**: Removed from queue after completion
- **Failed jobs**: Remain in queue with Failed status for analysis
- **Interrupted jobs**: Reset to Pending for retry
- **Results stored**: All outcomes recorded in QualityTestResults
- **Benefit**: Clean queue with complete audit trail

## Worker Behavior

### When Jobs Available
1. Claim job atomically
2. Process job (FFmpeg VMAF)
3. Update database with results
4. Immediately try to claim next job

### When No Jobs Available
1. Try to claim job (returns None)
2. Sleep for 5 seconds
3. Wake up and try again
4. Repeat until jobs available or service stopped

## Error Handling

### Process Interruption
- **Action**: Reset job status to 'Pending'
- **Reason**: Allow retry by another worker
- **Database**: Status = 'Pending' (not 'Failed')

### FFmpeg Failure
- **Action**: Mark job as 'Failed'
- **Reason**: Actual processing error
- **Database**: Status = 'Failed' with error message

### Database Errors
- **Action**: Log error and continue
- **Reason**: System resilience
- **Database**: Error logged, worker continues

## Performance Considerations

### Database Efficiency
- **Atomic operations**: Single queries for job claiming
- **Indexed queries**: Fast job selection by status
- **Minimal polling**: 5-second intervals when idle

### Concurrency
- **Multiple workers**: Process jobs in parallel
- **No locks needed**: Database handles concurrency
- **Scalable**: Worker count configurable

### Monitoring
- **ActiveJobs table**: Real-time process tracking
- **Status fields**: Clear job state visibility
- **Error logging**: Comprehensive error tracking

## Summary

The MicroServiceQualityTest uses a database-driven architecture where:

1. **Database is the single source of truth** for job state
2. **Atomic operations prevent race conditions** between workers
3. **Dual storage provides both current status and historical data**
4. **Workers continuously poll and process jobs** until service stops
5. **Complete audit trail** is maintained for all job processing

This design ensures reliable, scalable, and monitorable quality testing operations.
