# MicroServiceTranscode Separation Plan

## Overview
This document outlines the plan to properly separate the TranscodeService microservice from MediaVortex. **TranscodeService already exists and is functional** - this is about removing duplicate control paths and ensuring clean separation.

## Current State Analysis

### What Already Works
- **TranscodeService/** - Fully functional standalone microservice
  - `Main.py`: Entry point with signal handlers ✅
  - `App.py`: TranscodeServiceApp with queue processing ✅
  - `Config.py`: Configuration management ✅
  - `Health.py`: Health check endpoints ✅
  - Database-driven control via ServiceStatus table ✅
  - Health monitoring and status updates ✅
  - Graceful shutdown support ✅
  - Stuck job recovery on startup ✅

### The Problem
- **MediaVortex.py** hosts `TranscodeJobController` with direct API endpoints
- This creates a **duplicate control path** that bypasses the database
- Should be: Both services use database as single source of truth (like QualityTest)

### The Correct Architecture
**Service Separation (Database-Driven):**
1. **TranscodeService** - Launched from command line, runs independently
   - Always monitoring database for jobs and status changes
   - Processes jobs when Status = "Running" in ServiceStatus table
   - Pauses when Status = "Stopped" in ServiceStatus table

2. **MediaVortex GUI** - Web interface for control
   - Enables/disables transcoding by updating ServiceStatus table
   - Displays status by reading from ServiceStatus table
   - No direct communication with TranscodeService

3. **Database** - Single source of truth
   - ServiceStatus table: Service control (Running/Stopped)
   - TranscodeQueue table: Jobs to process
   - TranscodeProgress table: Real-time progress
   - Both services read/write to database, never talk directly

### What Needs to Change
1. **Remove TranscodeJobController** - eliminate API-based control
2. **Update frontend** to use database updates (like QualityTest does)
3. **Verify database schema** - ensure ServiceStatus has all needed columns
4. **Document the architecture** - make separation crystal clear
5. **Keep it simple** - Database-driven only, no APIs between services

## Target Architecture

### TranscodeService Structure (Already Exists)
```
TranscodeService/
├── Main.py                          # Entry point ✅
├── App.py                           # TranscodeServiceApp (database-driven) ✅
├── Config.py                        # Configuration management ✅
├── Health.py                        # Health monitoring ✅
├── requirements.txt                 # Dependencies ✅
├── TranscodeService.log             # Log file
└── venv/                            # Virtual environment ✅
```

### How It Works (Database-Driven Control)

#### 1. TranscodeService Runs Independently
- Started manually via `python TranscodeService/Main.py`
- Runs as separate process with title "TranscodeService"
- Continuously monitors TranscodeQueue for pending jobs
- Updates ServiceStatus table with health metrics every 30 seconds

#### 2. Control via ServiceStatus Table
MediaVortex frontend updates ServiceStatus table to control TranscodeService:

**Start Transcoding:**
```sql
UPDATE ServiceStatus 
SET Status = 'Running', IsProcessing = 1 
WHERE ServiceName = 'TranscodeService'
```

**Stop Transcoding:**
```sql
UPDATE ServiceStatus 
SET Status = 'Stopped', IsProcessing = 0 
WHERE ServiceName = 'TranscodeService'
```

**Graceful Stop:**
```sql
UPDATE ServiceStatus 
SET Status = 'GracefulStop' 
WHERE ServiceName = 'TranscodeService'
```

#### 3. TranscodeService Polls Database
- Checks ServiceStatus table every 5 seconds
- Responds to status changes automatically
- No HTTP API needed - pure database-driven architecture

## Database Workflow

### Tables Involved
- **TranscodeQueue**: Main job queue (Status: Pending → Running → Completed/Failed)
- **TranscodeAttempts**: Historical attempt tracking
- **TranscodeProgress**: Real-time progress during FFmpeg execution
- **ActiveJobs**: Process monitoring and tracking
- **ServiceStatus**: Service health and control
- **SystemSettings**: Configuration (MaxConcurrentJobs)

### Job Processing Flow
1. **Service Startup**
   - Read MaxConcurrentJobs from SystemSettings
   - Create N worker threads
   - Register service in ServiceStatus table

2. **Worker Claims Job** (Atomic)
   ```sql
   SELECT Id FROM TranscodeQueue WHERE Status = 'Pending' ORDER BY Priority DESC LIMIT 1
   UPDATE TranscodeQueue SET Status = 'Running', DateStarted = CURRENT_TIMESTAMP WHERE Id = ? AND Status = 'Pending'
   ```

3. **Create Active Job Tracking**
   ```sql
   INSERT INTO ActiveJobs (ServiceName, JobType, QueueId, ProcessId, ThreadId, Status, StartedAt)
   VALUES ('TranscodeService', 'Transcode', ?, ?, ?, 'Running', CURRENT_TIMESTAMP)
   ```

4. **Process Job**
   - Create TranscodeProgress record
   - Execute FFmpeg transcoding
   - Update progress in real-time
   - Handle success/failure

5. **Complete Job**
   - Update TranscodeQueue status
   - Update TranscodeAttempts record
   - Complete ActiveJobs record
   - Optionally add to QualityTestingQueue

### Service Control via ServiceStatus
The microservice polls ServiceStatus table for control commands:
- **Status = "Running"** → Workers process queue
- **Status = "Stopped"** → Workers stop claiming new jobs
- **Status = "GracefulStop"** → Complete current jobs then stop
- **Status = "Paused"** → Pause processing (same as Stopped)

## Separation Steps

### Phase 1: Remove Duplicate Control from MediaVortex
**Goal:** Eliminate TranscodeJobController from MediaVortex

1. **Remove TranscodeJobController import** from `MediaVortex.py`
   - Line 69: `from Controllers.TranscodeJobController import TranscodeJobBlueprint`
   
2. **Remove TranscodeJobController blueprint registration** from `MediaVortex.py`
   - Line 237: `self.App.register_blueprint(TranscodeJobBlueprint)`

3. **Keep TranscodeQueueController** in MediaVortex
   - This is for queue management (add/remove/view jobs)
   - NOT for starting/stopping transcoding

### Phase 2: Update Frontend to Use Database Control
**Goal:** Frontend updates ServiceStatus table instead of calling API endpoints (exactly like QualityTest)

1. **Update Activity.html** - Replace API calls with database updates
   - **Old:** `POST /api/Transcode/Start` → Direct API call
   - **New:** `POST /api/ServiceControl/UpdateServiceStatus` → Database update
   - Button calls: `UpdateServiceStatus('TranscodeService', 'Running')` to enable
   - Button calls: `UpdateServiceStatus('TranscodeService', 'Stopped')` to pause
   - Keep progress display (reads from TranscodeProgress table)

2. **Use existing ServiceControlController** (already exists for QualityTest)
   - Already has `UpdateServiceStatus()` method
   - Just needs to support TranscodeService name
   - Updates ServiceStatus table: `SET Status = ?, IsProcessing = ? WHERE ServiceName = 'TranscodeService'`

3. **Update Status.html** - Add TranscodeService monitoring
   - Display TranscodeService status from ServiceStatus table
   - Show health metrics, uptime, active jobs
   - Same pattern as QualityTest service display

### Phase 3: Verify Database Schema
**Goal:** Ensure ServiceStatus table has all required columns

1. **Check ServiceStatus table structure** (from DatabaseSchema.md):
   - ServiceName ✅
   - Status ✅
   - IsProcessing ✅
   - ActiveJobsCount ✅
   - ProcessId ✅
   - HealthStatus ✅
   - All columns already exist!

2. **No schema changes needed** - ServiceStatus table is complete

### Phase 4: Documentation
**Goal:** Document the separated architecture

1. **Create TranscodeService user requirements doc**
   - `Docs/MicroServiceTranscode/MicroServiceTranscode.md`
   - Similar to QualityTest documentation

2. **Create database workflow doc**
   - `Docs/MicroServiceTranscode/TranscodeDatabaseWorkflow.md`
   - Document job processing flow

3. **Update Architecture.md**
   - Add TranscodeService to microservices section
   - Document database-driven control pattern

### Phase 5: Testing
**Goal:** Verify clean separation works

1. **Test TranscodeService independently**
   - Start via `python TranscodeService/Main.py`
   - Verify it registers in ServiceStatus table
   - Verify health monitoring works

2. **Test database-driven control**
   - Update ServiceStatus table manually
   - Verify TranscodeService responds to status changes
   - Test Start/Stop/GracefulStop

3. **Test MediaVortex integration**
   - Verify frontend can control TranscodeService via database
   - Verify progress display works
   - Verify status monitoring works

4. **Test edge cases**
   - Service restart (stuck jobs reset)
   - Graceful shutdown (current job completes)
   - Force stop (process termination)

## Key Design Patterns (Already Implemented)

### 1. Database-Driven Control (No API Needed)
```python
def PrivateStatusPollingLoop(self):
    """Poll ServiceStatus table every 5 seconds for control commands"""
    while not self.ShutdownEvent.is_set():
        statusResult = self.StatusHelper.GetTranscodingStatus()
        if statusResult.get("Success", False):
            newStatus = statusResult.get("Status", "Stopped")
            if newStatus != self.CurrentStatus:
                self.PrivateHandleStatusChange(newStatus, isProcessing)
                self.CurrentStatus = newStatus
        self.ShutdownEvent.wait(5)
```

### 2. Single Job Processing (No Worker Pool)
```python
def TranscodingProcessingLoop(self):
    """Simple single-job processing - no concurrency needed"""
    while not self.ShutdownEvent.is_set():
        pending_jobs = self.DatabaseManager.GetTranscodeQueueItemsByStatus("Pending")
        if pending_jobs and len(pending_jobs) > 0:
            if not self.ProcessTranscodeQueue.IsProcessing:
                # Start processing with MaxConcurrentJobs=1 (hardcoded)
                result = self.ProcessTranscodeQueue.Run(MaxConcurrentJobs=1)
        self.ShutdownEvent.wait(10)
```

### 3. Health Monitoring
```python
def HealthMonitoringLoop(self):
    """Update ServiceStatus table every 30 seconds with health metrics"""
    while not self.ShutdownEvent.is_set():
        status = self.ProcessTranscodeQueue.GetStatus()
        is_transcoding = status.get("IsTranscoding", False)
        active_jobs = status.get("ActiveJobsCount", 0)
        
        self.UpdateServiceStatus(
            status="Running",
            health_status="Healthy",
            active_jobs=active_jobs,
            is_processing=is_transcoding
        )
        self.ShutdownEvent.wait(30)
```

### 4. Graceful Shutdown
```python
def PrivateMonitorGracefulStop(self):
    """Wait for current job to complete before stopping"""
    while self.ProcessTranscodeQueue.IsProcessing and not self.ShutdownEvent.is_set():
        LoggingService.LogInfo("Waiting for current transcoding job to complete...")
        time.sleep(5)
    
    # Job completed, now stop
    self.ProcessTranscodeQueue.Stop()
    self.UpdateServiceStatus("Stopped", "Stopped", 0, False)
    self.ShutdownEvent.set()
```

## Files to Modify

### Phase 1: MediaVortex Changes
1. **MediaVortex.py** - Remove TranscodeJobController
   - Remove import on line 69
   - Remove blueprint registration on line 237
   - Keep TranscodeQueueController (for queue management)

### Phase 2: Frontend Changes
2. **Templates/Activity.html** - Update control buttons
   - Replace `/api/Transcode/Start` with database update call
   - Replace `/api/Transcode/Stop` with database update call
   - Keep progress display (unchanged)

3. **Templates/Status.html** - Add TranscodeService monitoring
   - Add TranscodeService status card
   - Display health metrics from ServiceStatus table

### Phase 3: New Controller for Database Control
4. **Controllers/ServiceControlController.py** (may already exist)
   - Add `UpdateTranscodeServiceStatus()` method
   - Updates ServiceStatus table based on frontend requests

### Phase 4: Documentation
5. **Docs/MicroServiceTranscode/MicroServiceTranscode.md** (NEW)
   - User requirements document
   
6. **Docs/MicroServiceTranscode/TranscodeDatabaseWorkflow.md** (NEW)
   - Database workflow documentation

7. **Docs/Architecture.md** - Update
   - Add TranscodeService to microservices section

## Files to Keep (No Changes)
- `TranscodeService/Main.py` ✅ Already correct
- `TranscodeService/App.py` ✅ Already correct
- `TranscodeService/Config.py` ✅ Already correct
- `TranscodeService/Health.py` ✅ Already correct
- `Controllers/TranscodeQueueController.py` ✅ Keep in MediaVortex for queue management

## Benefits of Microservice Architecture

### 1. Separation of Concerns
- MediaVortex: Web UI and orchestration only
- TranscodeService: Transcoding processing only
- QualityTestService: Quality testing only

### 2. Independent Scaling
- Can run multiple TranscodeService instances
- Each instance manages its own worker pool
- Database handles job distribution

### 3. Fault Isolation
- TranscodeService crash doesn't affect MediaVortex
- Easy to restart individual services
- Better error tracking per service

### 4. Deployment Flexibility
- Update TranscodeService without restarting MediaVortex
- Deploy services on different machines
- Scale services independently

### 5. Resource Management
- Each service has its own process
- Better CPU/memory isolation
- Easier to monitor resource usage

## Configuration Example

### SystemSettings Table
```sql
INSERT INTO SystemSettings (SettingKey, SettingValue, Description)
VALUES ('MaxConcurrentJobs', '2', 'Maximum concurrent transcoding jobs');
```

### ServiceStatus Table
```sql
INSERT INTO ServiceStatus (
    ServiceName, Status, HealthStatus, ProcessId, 
    ServiceType, MaxConcurrentJobs, IsProcessing
) VALUES (
    'TranscodeService', 'Running', 'Healthy', 12345,
    'Microservice', 2, 1
);
```

## Database Integration Example (No APIs Between Services)

### MediaVortex Frontend → Database → TranscodeService

**Frontend Control (Activity.html):**
```javascript
// Start transcoding - Update database
async function StartTranscoding() {
    const response = await fetch('/api/ServiceControl/UpdateServiceStatus', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
            ServiceName: 'TranscodeService',
            Status: 'Running',
            IsProcessing: true
        })
    });
    const result = await response.json();
    console.log('TranscodeService enabled:', result);
}

// Stop transcoding - Update database
async function StopTranscoding() {
    const response = await fetch('/api/ServiceControl/UpdateServiceStatus', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
            ServiceName: 'TranscodeService',
            Status: 'Stopped',
            IsProcessing: false
        })
    });
    const result = await response.json();
    console.log('TranscodeService paused:', result);
}

// Get progress - Read from database
async function GetTranscodeProgress() {
    const response = await fetch('/api/Transcode/Progress');  // MediaVortex endpoint that reads DB
    const progress = await response.json();
    UpdateProgressUI(progress);
}
```

**TranscodeService Polling (App.py):**
```python
# TranscodeService polls database every 5 seconds
def PrivateStatusPollingLoop(self):
    while not self.ShutdownEvent.is_set():
        # Read ServiceStatus table
        service_status = self.DatabaseManager.GetServiceStatus("TranscodeService")
        
        if service_status:
            new_status = service_status.get('Status', 'Stopped')
            
            # React to status changes
            if new_status == 'Running' and not self.IsProcessing:
                self.StartProcessing()  # Enable transcoding
            elif new_status == 'Stopped' and self.IsProcessing:
                self.StopProcessing()   # Pause transcoding
        
        time.sleep(5)  # Poll every 5 seconds
```

**Key Point:** No direct communication - database is the message bus!

## Architecture Clarification

### How Services Interact (Database as Message Bus)

**Launch:**
```bash
# Terminal 1: Start TranscodeService (command line)
cd TranscodeService
python Main.py

# Terminal 2: Start MediaVortex (command line)
cd ..
python MediaVortex.py
```

**Control Flow:**
1. **User clicks "Start Transcoding" in GUI**
   - Frontend → MediaVortex API → Database (UPDATE ServiceStatus)
   - Database: `Status = 'Running'` for TranscodeService

2. **TranscodeService detects change**
   - Polls database every 5 seconds
   - Sees Status = 'Running'
   - Starts processing TranscodeQueue

3. **User clicks "Stop Transcoding" in GUI**
   - Frontend → MediaVortex API → Database (UPDATE ServiceStatus)
   - Database: `Status = 'Stopped'` for TranscodeService

4. **TranscodeService detects change**
   - Polls database every 5 seconds
   - Sees Status = 'Stopped'
   - Pauses processing (completes current job first)

**No Direct Communication:**
- MediaVortex never calls TranscodeService APIs (no APIs exist!)
- TranscodeService never calls MediaVortex APIs
- Both read/write to shared database
- Database is the single source of truth

**This is exactly how QualityTest works!**

## Success Criteria

### Functional Requirements
- ✅ TranscodeService runs as independent process (launched from command line)
- ✅ Worker-based job processing (configurable concurrency)
- ✅ Atomic job claiming (no race conditions)
- ✅ Real-time progress tracking
- ✅ Graceful shutdown support
- ✅ Service health monitoring
- ✅ MediaVortex integration via REST API

### Non-Functional Requirements
- ✅ No duplicate job processing
- ✅ Proper error handling and recovery
- ✅ Clean process termination
- ✅ Database consistency
- ✅ Logging and debugging support
- ✅ PascalCase naming throughout

## Rollback Plan

If migration fails:
1. Keep existing TranscodeJobController in MediaVortex
2. Disable MicroServiceTranscode
3. Revert MediaVortex.py changes
4. Revert Template changes
5. Continue using embedded transcoding

## Timeline Estimate

- **Phase 1**: 30 minutes (remove TranscodeJobController from MediaVortex)
- **Phase 2**: 2-3 hours (update frontend to use database control)
- **Phase 3**: 1 hour (verify database schema - likely no changes needed)
- **Phase 4**: 2 hours (create documentation)
- **Phase 5**: 2 hours (testing and validation)

**Total**: 6-8 hours (much simpler since TranscodeService already works!)

## References

- `MicroServiceQualityTest/QualityTestingService.py` - Worker pattern reference
- `Docs/MicroServiceQualityTest/MicroServiceQualityTest.md` - Architecture reference
- `Docs/MicroServiceQualityTest/QualityTestDatabaseWorkflow.md` - Database workflow reference
- `Docs/Architecture.md` - Overall system architecture
- `Services/ProcessTranscodeQueueService.py` - Core transcoding logic
