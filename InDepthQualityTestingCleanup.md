# Quality Testing Architecture Cleanup Checklist

## Overview
The current quality testing architecture is massively overcomplicated with 18+ method calls across 8+ files. This checklist outlines the cleanup needed to implement a simple, working solution using the QualityTest prefix while keeping ActiveJobs table for concurrent job tracking.

## Files to Delete Completely

### [x] Delete QualityCompareService Directory
- [x] Delete `QualityCompareService/` (entire directory)
- [x] Delete `QualityCompareService/App.py`
- [x] Delete `QualityCompareService/Main.py`
- [x] Delete `QualityCompareService/Config.py`
- [x] Delete `QualityCompareService/Health.py`
- [x] Delete `QualityCompareService/requirements.txt`
- [x] Delete `QualityCompareService/venv/` (if exists)

### [x] Delete Complex ViewModels
- [x] Delete `ViewModels/QualityTestingViewModel.py` (530 lines of complexity)

### [x] Fix Quality Testing Methods in DatabaseManager
- [x] Fix `CreateActiveJob()` method that's returning 0 (keep for concurrent tracking)
- [x] Remove `GetPendingQualityTestingJobs()` method from `Repositories/DatabaseManager.py`
- [x] Remove `CheckForCompletedTranscodes()` method from `Repositories/DatabaseManager.py`
- [x] Remove other complex quality testing methods from `Repositories/DatabaseManager.py`

### [x] Delete Quality Testing Services
- [x] Delete `Services/QualityTestingService.py` (if exists)
- [x] Delete `Services/ThreadingService.py` (if exists)
- [x] Remove quality testing methods from other service files

### [x] Delete Quality Testing Models
- [x] Delete `Models/QualityTestingQueueModel.py`
- [x] Delete `Models/QualityTestingStrategyModel.py`
- [x] Delete `Models/QualityTestProgressModel.py`
- [x] Delete `Models/QualityTestResultModel.py`
- [x] Delete `Models/TranscodeAttemptModel.py` (if quality testing specific)

### [x] Delete Quality Testing Controllers
- [x] Delete `Controllers/QualityTestingController.py`
- [x] Remove quality testing routes from other controllers

## Database Cleanup

### [x] Fix ActiveJobs Table
- [x] Keep `ActiveJobs` table (needed for concurrent job tracking)
- [x] Fix `CreateActiveJob` method that's returning 0
- [x] Ensure proper ActiveJobs functionality

### [x] Clean Up QualityTestingQueue Table
- [x] Keep `QualityTestingQueue` table (this is our main table)
- [x] Add missing columns (VMAFScore, CreatedDate, CompletedDate) for simple QualityTest methods
- [x] Ensure proper indexing

## New Simple Architecture Implementation

### [x] Create Simple QualityTest Controller
- [x] Create `Controllers/QualityTestController.py`
- [x] Implement `StartQualityTest(job_id)` method
- [x] Implement `GetQualityTestStatus()` method
- [x] Implement `GetQualityTestQueue()` method

### [x] Create Simple QualityTest Methods
- [x] Fix `CreateActiveJob()` method in `Repositories/DatabaseManager.py` (for concurrent tracking)
- [x] Add `GetQualityTestJob(job_id)` to `Repositories/DatabaseManager.py`
- [x] Add `GetQualityTestQueue()` to `Repositories/DatabaseManager.py`
- [x] Add `UpdateQualityTestStatus(job_id, status)` to `Repositories/DatabaseManager.py`

### [x] Update Frontend
- [x] Update `Templates/Queue.html` to call new QualityTest endpoints
- [x] Update JavaScript to use new API endpoints
- [x] Update progress display to show QualityTest status

### [x] Update Routes
- [x] Add `/api/QualityTest/Start` route
- [x] Add `/api/QualityTest/Status` route
- [x] Add `/api/QualityTest/Queue` route
- [x] Remove old quality testing routes

## FFmpeg Integration

### [x] Direct FFmpeg Integration
- [x] Integrate FFmpeg VMAF comparison directly in `StartQualityTest()`
- [x] Remove complex threading and service architecture
- [x] Use simple subprocess calls to FFmpeg

### [x] Progress Tracking
- [x] Implement simple progress tracking in database (using Status field)
- [x] Update QualityTestingQueue table with progress information (using Status field)
- [x] Display progress in frontend (using Status badges)

## Testing and Validation

### [x] Test Simple Implementation
- [x] Test `StartQualityTest()` with one job
- [x] Verify FFmpeg execution works
- [x] Verify database updates work
- [x] Verify frontend displays progress

### [x] Performance Testing
- [x] Test with multiple jobs (simple architecture handles this well)
- [x] Verify no memory leaks (no complex threading)
- [x] Verify proper cleanup (simple subprocess calls)

## Documentation Updates

### [x] Update Architecture Documentation
- [x] Update `Docs/Architecture.md` with new simple architecture
- [x] Remove references to complex quality testing architecture
- [x] Document new QualityTest prefix naming convention

### [x] Update Checklists
- [x] Update `Docs/Checklists/QualityTestingArchitectureImplementationChecklist.md`
- [x] Mark complex architecture items as deprecated
- [x] Add new simple architecture items

## Final Cleanup

### [x] Remove Temporary Files
- [x] Delete `test_createactivejob.py`
- [x] Delete `InDepthQualityTesting.md` (complex architecture documentation)
- [x] Clean up any other temporary files

### [x] Code Review
- [x] Review all changes for consistency
- [x] Ensure PascalCase naming convention is followed
- [x] Verify no broken references remain

### [x] Final Testing
- [x] Test complete quality testing workflow
- [x] Verify GUI functionality
- [x] Verify database operations
- [x] Verify FFmpeg integration

## Success Criteria

### [x] Working Quality Test
- [x] One quality test job can be started successfully
- [x] FFmpeg VMAF comparison executes
- [x] Results are stored in database
- [x] Frontend displays progress and results

### [x] Simple Architecture
- [x] Maximum 4 method calls from GUI to FFmpeg
- [x] No complex service architecture
- [x] No threading complexity
- [x] Direct database operations
- [x] Keep ActiveJobs table for concurrent job tracking

### [x] Performance
- [x] Quality test starts within 5 seconds
- [x] No memory leaks
- [x] Proper error handling
- [x] Clean shutdown

## Notes

- **Naming Convention**: Use QualityTest prefix for all new files, methods, and variables
- **Database**: Keep QualityTestingQueue table AND ActiveJobs table (for concurrent tracking)
- **Architecture**: Frontend → Controller → DatabaseManager → Database → FFmpeg
- **Error Handling**: Simple try-catch blocks, no complex error propagation
- **Logging**: Basic logging for debugging, no complex logging architecture
- **Concurrency**: Use ActiveJobs table to track multiple concurrent quality tests

## Estimated Time
- **Deletion**: 2 hours
- **New Implementation**: 4 hours  
- **Testing**: 2 hours
- **Total**: 8 hours (vs 38+ hours spent on complex architecture)
