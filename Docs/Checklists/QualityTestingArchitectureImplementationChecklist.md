# Quality Testing Architecture Implementation Checklist

## Overview
This checklist implements the simplified Quality Testing architecture following MVVM and KISS principles. Focus on getting the core system running with quality tests.

## 📊 **CURRENT IMPLEMENTATION STATUS**

### ✅ **COMPLETED (40%)**
- **GUI Layer**: HTML templates, controllers, JavaScript integration ✅
- **Service Layer**: QualityTestingService, FFmpegComparisonService, ThreadingService ✅
- **ViewModel Layer**: Basic structure exists ✅
- **Database Layer**: QualityTestingQueue, QualityTestProgress, ServiceStatus tables ✅
- **Cleanup**: Complex orchestration removed ✅

### ❌ **MISSING (60%)**
- **Database Schema**: ActiveJobs table, TranscodeAttempts columns ❌
- **DatabaseManager**: Core job tracking methods ❌
- **ViewModel**: Complete implementation ❌
- **Service Integration**: SystemOrchestratorService integration ❌
- **Service Control**: GUI service control ❌

## 🎯 **IMPLEMENTATION ORDER (CRITICAL PATH)**

### **STEP 1: Database Schema (BLOCKING)**
1. Create `ActiveJobs` table
2. Add quality test columns to `TranscodeAttempts`
3. Add core DatabaseManager methods

### **STEP 2: Complete ViewModel (BLOCKING)**
4. Complete QualityTestingViewModel implementation
5. Add job processing methods
6. Add progress tracking

### **STEP 3: Service Integration (BLOCKING)**
7. Integrate with SystemOrchestratorService
8. Add service control to GUI
9. Test end-to-end workflow

### **STEP 4: Testing & Validation**
10. Unit testing
11. Integration testing
12. Service management testing

## ✅ **COMPLETED PHASES**

### **Phase 0: Remove Complex Orchestration (COMPLETED)**
- [x] **Delete**: `Services/QualityTestingOrchestratorService.py` - Replace with database-driven approach ✅
- [x] **Delete**: `Services/QualityTestingStrategyService.py` - Strategy pattern removed for KISS ✅
- [x] **Delete**: Complex orchestration logic in existing services ✅
- [x] **Update**: `MediaVortex.py` - Remove references to deleted services ✅
- [x] **Update**: `SystemOrchestratorService/App.py` - Remove QualityTestingOrchestratorService references ✅
- [x] **Update**: `ProcessTranscodeQueueService.py` - Remove direct QualityTesting service calls ✅

### **Phase 0.5: Verify Existing Tables (COMPLETED)**
- [x] **Verify**: `QualityTestingQueue` table exists with proper columns ✅
- [x] **Verify**: `QualityTestProgress` table exists for real-time progress ✅
- [x] **Verify**: `ServiceStatus` table has `MaxConcurrentJobs` and `ActiveJobsCount` columns ✅

## 🚨 **REMAINING WORK - IMPLEMENTATION ORDER**

### **3.1 Create QualityTestingViewModel**
- [x] **Create**: `ViewModels/QualityTestingViewModel.py` ✅
  - [x] `__init__(self)` - Initialize DatabaseManager, QualityTestingService, ThreadingService ✅
  - [ ] `ProcessQueue(self)` - Check database for completed transcodes needing quality tests
  - [ ] `CheckForCompletedTranscodes(self)` - Query TranscodeAttempts for QualityTestRequired=True
  - [ ] `StartQualityTestForTranscode(self, transcode_attempt)` - Start quality test directly from TranscodeAttempts
  - [ ] `StartQualityTestJob(self, job)` - Start quality test with progress tracking
  - [ ] `QualityTestProgressCallback(self, job_id, progress_data)` - Handle progress updates
  - [ ] `HandleQualityTestResult(self, job, result)` - Update TranscodeAttempts.VMAF, set QualityTestCompleted=True
  - [ ] `CancelJob(self, job_id)` - Cancel individual job by PID
  - [ ] `GetActiveJobs(self)` - Get list of active jobs with PIDs
  - [ ] `Shutdown(self)` - Graceful shutdown for SystemOrchestrator
  - [ ] `Cleanup(self)` - Cleanup active jobs on shutdown

### **3.2 Create QualityTestingService**
- [x] **Create**: `Services/QualityTestingService.py` (rename from VMAFService) ✅
  - [x] `StartQualityTest(self, job, progress_callback, result_callback)` - Async execution ✅
  - [x] `ExecuteQualityTest(self, job)` - Core quality test logic ✅
  - [x] `MonitorQualityTestProgress(self, process, progress_callback)` - Progress monitoring ✅
  - [x] `HandleQualityTestErrors(self, error)` - Error processing ✅
  - [x] `ParseQualityTestResults(self, output)` - Parse results ✅

### **3.3 Create ThreadingService**
- [x] **Create**: `Services/ThreadingService.py` ✅
  - [x] `StartQualityTestThread(self, job, progress_callback, result_callback)` - Thread management ✅
  - [x] `MonitorThreads(self, active_jobs)` - Thread monitoring ✅
  - [x] `CleanupThreads(self, active_jobs)` - Thread cleanup ✅

## 🚨 **CRITICAL MISSING COMPONENTS - MUST IMPLEMENT FIRST**

### **Phase 1: Database Schema (BLOCKING)**
- [ ] **Create**: `ActiveJobs` table for unified job tracking
  - [ ] `Id` (Primary Key)
  - [ ] `ServiceName` (TranscodeService, QualityTestingService, etc.)
  - [ ] `JobType` (Transcode, QualityTest, FileScan, etc.)
  - [ ] `QueueId` (Foreign Key to QualityTestingQueue.Id)
  - [ ] `ProcessId` (PID)
  - [ ] `ThreadId` (Thread identifier)
  - [ ] `StartedAt` (Timestamp)
  - [ ] `Status` (Running/Completed/Failed)
- [ ] **Add**: `QualityTestRequired` column to `TranscodeAttempts` table
- [ ] **Add**: `QualityTestSkipped` column to `TranscodeAttempts` table  
- [ ] **Add**: `QualityTestCompleted` column to `TranscodeAttempts` table

### **Phase 2: Core DatabaseManager Methods (BLOCKING)**
- [ ] **Add**: `CreateActiveJob(service_name, job_type, queue_id, process_id, thread_id)` - Track job execution
- [ ] **Add**: `CompleteActiveJob(job_id, success=True, error_message=None)` - Remove from ActiveJobs, log result
- [ ] **Add**: `GetActiveJobByQueueId(service_name, queue_id)` - Get job by service and queue ID
- [ ] **Add**: `GetActiveJobsByService(service_name)` - Get all active jobs for a service
- [ ] **Add**: `GetAllActiveJobs()` - Get all running jobs for cleanup
- [ ] **Add**: `CancelActiveJob(job_id)` - Cancel specific job by PID
- [ ] **Add**: `GetCompletedTranscodesNeedingQualityTest()` - Get TranscodeAttempts where QualityTestRequired=True
- [ ] **Add**: `CreateQualityTestingJob(transcode_attempt)` - Create QualityTestingQueue entry from TranscodeAttempts
- [ ] **Add**: `UpdateTranscodeAttemptVMAF(transcode_attempt_id, vmaf_score)` - Update TranscodeAttempts.VMAF
- [ ] **Add**: `MarkQualityTestCompleted(transcode_attempt_id)` - Set QualityTestCompleted=True

### **Phase 3: Complete QualityTestingViewModel (BLOCKING)**
- [ ] `ProcessQueue(self)` - Check database for completed transcodes needing quality tests
- [ ] `CheckForCompletedTranscodes(self)` - Query TranscodeAttempts for QualityTestRequired=True
- [ ] `StartQualityTestForTranscode(self, transcode_attempt)` - Start quality test directly from TranscodeAttempts
- [ ] `StartQualityTestJob(self, job)` - Start quality test with progress tracking
- [ ] `QualityTestProgressCallback(self, job_id, progress_data)` - Handle progress updates
- [ ] `HandleQualityTestResult(self, job, result)` - Update TranscodeAttempts.VMAF, set QualityTestCompleted=True
- [ ] `CancelJob(self, job_id)` - Cancel individual job by PID
- [ ] `GetActiveJobs(self)` - Get list of active jobs with PIDs
- [ ] `Shutdown(self)` - Graceful shutdown for SystemOrchestrator
- [ ] `Cleanup(self)` - Cleanup active jobs on shutdown

### **Phase 4: Service Integration (BLOCKING)**
- [ ] **Add**: `QualityTestingViewModel` to managed services list
- [ ] **Add**: `QualityTestingService` to service management
- [ ] **Update**: Service startup/shutdown logic
- [ ] **Add**: QualityTesting service to GUI service control
- [ ] **Ensure**: Proper service status tracking
- [ ] **Add**: QualityTesting service start/stop methods
- [ ] **Add**: Service status monitoring for QualityTesting
- [ ] **Add**: Job cancellation by PID functionality

### **Phase 5: Update ProcessTranscodeQueueService**
- [ ] **Update**: `Services/ProcessTranscodeQueueService.py`
  - [ ] Set `QualityTestRequired = True` on transcoding completion
  - [ ] Remove direct QualityTesting service calls
  - [ ] Use database-driven workflow

### **Phase 6: Testing and Validation**
- [ ] **Test**: `QualityTestingViewModel` methods
- [ ] **Test**: `QualityTestingService` methods
- [ ] **Test**: `DatabaseManager` quality testing methods
- [ ] **Test**: `ThreadingService` methods
- [ ] **Test**: End-to-end quality testing workflow
- [ ] **Test**: Concurrent job processing
- [ ] **Test**: Progress tracking
- [ ] **Test**: Error handling scenarios
- [ ] **Test**: Service start/stop from GUI
- [ ] **Test**: Graceful shutdown
- [ ] **Test**: Immediate stop
- [ ] **Test**: Service status updates

### **Phase 7: Cleanup and Documentation**
- [x] **Delete**: Old complex orchestration files ✅
- [x] **Delete**: Unused strategy pattern files ✅
- [x] **Clean**: Remove unused imports and dependencies ✅
- [x] **Update**: Remove references to deleted services ✅
- [ ] **Update**: `Docs/Architecture.md` - Reflect new simplified architecture
- [ ] **Update**: `Docs/DatabaseSchema.md` - Update quality testing tables
- [ ] **Create**: API documentation for new methods
- [ ] **Update**: Service integration documentation

## Success Criteria

### **Functional Requirements:**
- [ ] Quality tests can be started and monitored
- [ ] Progress tracking works in real-time
- [ ] Concurrent job limits are respected
- [ ] Results are properly stored and accessible
- [ ] Error handling works correctly
- [ ] Service status is properly updated
- [ ] **QualityTesting service can be started/stopped from GUI** (CRITICAL)
- [ ] **Service shutdown is graceful with proper cleanup** (CRITICAL)
- [ ] **Service status is visible in GUI** (CRITICAL)
- [ ] **Individual jobs can be cancelled by PID** (CRITICAL)
- [ ] **Job PIDs are tracked in unified ActiveJobs table** (CRITICAL)

### **Architectural Requirements:**
- [ ] MVVM pattern is properly implemented
- [ ] KISS principles are followed
- [ ] No complex orchestration remains
- [ ] Clear separation of concerns
- [ ] Minimal dependencies between layers

### **Performance Requirements:**
- [ ] Concurrent jobs process efficiently
- [ ] Database operations are optimized
- [ ] Memory usage is reasonable
- [ ] No memory leaks in threading

## Implementation Order

### **Critical Path:**
1. **Database Schema** - Ensure all tables and columns exist
2. **DatabaseManager Updates** - Core data access methods
3. **QualityTestingViewModel** - Main business logic with shutdown/cleanup
4. **QualityTestingService** - Core execution logic
5. **ThreadingService** - Thread management
6. **SystemOrchestratorService Updates** - Service management (CRITICAL)
7. **ServiceControlController Updates** - GUI service control (CRITICAL)
8. **Controller Updates** - Integration points
9. **Service Integration** - Downstream services
10. **Testing and Validation**

## Notes

### **Areas Requiring Special Attention:**
- **Thread Management**: Ensure proper cleanup of completed threads
- **Database Transactions**: Ensure data consistency during updates
- **Service Integration**: Maintain compatibility with existing services
- **Error Recovery**: Handle service restarts and job recovery
- **Progress Tracking**: Ensure real-time updates work correctly
- **ActiveJobs Cleanup**: Failed jobs must be removed from ActiveJobs table
- **Error Logging**: All job failures must be logged to Logs table with "Error" level
- **Orphaned Process Detection**: Clean up processes that are no longer tracked

### **Potential Risks:**
- **Service Dependencies**: Other services may depend on current architecture
- **Database Changes**: Schema changes may affect existing data
- **Threading Issues**: Improper thread management could cause resource leaks
- **Integration Points**: Changes may break existing workflows

This checklist ensures a complete transition to the simplified Quality Testing architecture while maintaining system stability and functionality.
