# MediaVortex Service Architecture (MVVM + KISS), Database Driven decisions, MicroServices can read from each others tables but can only insert, update and delete from their own tables.
## Simple Quality Testing Flow: User Click → Direct FFmpeg VMAF Test

### 1. User Clicks "Start Quality Test" Button
- **View**: `Templates/Queue.html` → `StartQualityTest(jobId)`
- **Action**: API call to `/api/QualityTest/Start` with JobId

### 2. QualityTest Controller Processes Request
- **Controller**: `QualityTestController.py` → `StartQualityTest()`
- **Action**: 
  - Gets job details from `QualityTestingQueue` table
  - Creates active job record in `ActiveJobs` table
  - Runs FFmpeg VMAF comparison directly

### 3. Direct FFmpeg VMAF Test
- **Execution**: `RunFFmpegVMAF()` method runs FFmpeg subprocess
- **Command**: `ffmpeg -i transcoded_file -i original_file -lavfi libvmaf=model_path=model/vmaf_v0.6.1.pkl -f null -`
- **Result**: Parses VMAF score from FFmpeg output

### 4. Database Update
- **Action**: Updates `QualityTestingQueue` table with results
- **Fields**: Status, VMAFScore, CompletedDate
- **Cleanup**: Completes active job record

### 5. Frontend Update
- **View**: `Templates/Queue.html` displays updated status
- **Refresh**: Auto-refresh shows completed quality test results

## MVVM Architecture

### Models (Data)
- **QualityTestingQueue**: Files to test (simplified structure)
- **ActiveJobs**: Concurrent job tracking
- **ServiceStatus**: Service states

### Controllers (Business Logic)
- **QualityTestController**: Simple quality testing logic
  - `StartQualityTest()`: Direct FFmpeg execution
  - `GetQualityTestStatus()`: Get job status
  - `GetQualityTestQueue()`: Get all jobs

### Views (UI)
- **Queue.html**: Quality testing interface with simple controls

## KISS Principle

**One responsibility per component:**
- **QualityTestController**: Direct quality testing with FFmpeg
- **TranscodeService**: Transcoding only
- **WebService**: Web interface only

**Simple Quality Testing Architecture:**
- **Maximum 4 method calls**: Frontend → Controller → DatabaseManager → Database → FFmpeg
- **No complex threading**: Simple subprocess calls
- **No service architecture**: Direct controller execution
- **Direct database operations**: No complex data models

## Simple Data Flow

1. User clicks "Start Quality Test" → QualityTestController
2. Controller gets job details → DatabaseManager
3. Controller runs FFmpeg VMAF → Direct subprocess call
4. Controller updates results → DatabaseManager
5. Frontend refreshes → Shows updated status

## Benefits of Simple Architecture

- **No complex service orchestration**: Direct execution
- **No threading complexity**: Simple subprocess calls
- **No memory leaks**: No long-running threads
- **Easy debugging**: Clear execution path
- **Fast execution**: No service startup overhead
