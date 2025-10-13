# Automated Crash Recovery System

## Overview

The MediaVortex Automated Crash Recovery System provides comprehensive recovery from crashes and system failures for both transcoding and quality testing services. This system automatically detects and recovers from three main crash scenarios without requiring manual intervention.

## System Startup

MediaVortex consists of three independent processes that must be started separately:

### Starting the Complete System

Launch these three processes in separate terminal windows:

```bash
# Terminal 1: Web Interface / Dashboard
cd WebService && py Main.py

# Terminal 2: Transcoding Service
cd TranscodeService && py Main.py

# Terminal 3: Quality Testing Service
cd QualityTestService && py Main.py
```


### Verifying Single Instance Operation

To verify only one instance of each service is running:

**Windows:**
```powershell
tasklist | findstr "python.exe"
```

**Linux/macOS:**
```bash
ps aux | grep python
```

You should see exactly three Python processes:
1. WebService (port 5000)
2. TranscodeService
3. QualityTestService

### Duplicate Instance Prevention

Each service includes duplicate instance detection in its startup code:
- Checks if another instance is already running
- Exits immediately if duplicate detected
- Prevents database conflicts and resource issues

## Crash Scenarios Handled

### 1. Computer Crash (Complete System Failure)
- **Scenario**: System reboot, power loss, or complete system crash
- **Impact**: All processes terminated, database shows "Running" jobs
- **Recovery**: Reset all "Running" jobs to "Pending" status for restart

### 2. Service Crash (Orphaned FFmpeg Processes)
- **Scenario**: TranscodeService or QualityTestService crashes but FFmpeg continues running
- **Impact**: FFmpeg processes consume resources but are not monitored
- **Recovery**: Kill orphaned FFmpeg processes, reset jobs to "Pending"

### 3. Service + FFmpeg Crash
- **Scenario**: Both service and FFmpeg processes crash
- **Impact**: Same as computer crash scenario
- **Recovery**: Reset jobs to "Pending" status

## Architecture

### Core Components

#### 1. ProcessManagementService
**File**: `Services/ProcessManagementService.py`

Cross-platform process management utilities using the `psutil` library:

- `IsProcessRunning(ProcessId)` - Check if a process exists
- `KillProcess(ProcessId, Graceful)` - Kill processes gracefully or forcefully
- `GetProcessInfo(ProcessId)` - Get detailed process information
- `FindFFmpegProcesses()` - Find all running FFmpeg processes
- `KillAllFFmpegProcesses()` - Emergency cleanup of all FFmpeg processes

#### 2. CrashRecoveryService
**File**: `Services/CrashRecoveryService.py`

Main recovery logic that orchestrates the crash recovery process:

- `RecoverServiceJobs(ServiceName)` - Primary recovery method
- `ResetTranscodeQueue(QueueIds)` - Reset transcode jobs to Pending
- `ResetQualityTestQueue(QueueIds)` - Reset quality test jobs to Pending
- `CleanupProgressRecords(QueueId, JobType)` - Clean up progress tracking
- `CleanupActiveJobs(ServiceName)` - Remove old ActiveJobs records

#### 3. DatabaseManager Extensions
**File**: `Repositories/DatabaseManager.py`

New methods added for crash recovery support:

- `GetActiveJobDetails(JobId)` - Get specific job information
- `DeleteActiveJob(JobId)` - Delete individual active job
- `DeleteActiveJobsByService(ServiceName)` - Bulk delete by service
- `ResetQueueJobsToPending(QueueIds, QueueTable)` - Reset multiple jobs

## Recovery Process Flow

### 1. Service Startup Detection
When a service starts up, it automatically calls the crash recovery system:

```python
# TranscodeService/App.py
def RecoverFromCrash(self):
    from Services.CrashRecoveryService import CrashRecoveryService
    recovery_service = CrashRecoveryService(self.DatabaseManager)
    result = recovery_service.RecoverServiceJobs("TranscodeService")
```

### 2. ActiveJobs Analysis
The system queries the `ActiveJobs` table to find jobs from previous sessions:

```sql
SELECT Id, ServiceName, JobType, QueueId, ProcessId, ThreadId, StartedAt
FROM ActiveJobs 
WHERE ServiceName = ? AND Status = 'Running'
```

### 3. Process Validation
For each active job, the system checks if the associated FFmpeg process still exists:

- **Process Exists**: Indicates orphaned FFmpeg process → Kill it
- **Process Not Found**: Process already terminated → Log and continue

### 4. Database State Reset
The system resets the database to a clean state:

- **Queue Tables**: Set `Status='Pending'`, clear `DateStarted`
- **Progress Tables**: Delete or mark as 'Cancelled'
- **ActiveJobs Table**: Remove old records

### 5. Comprehensive Logging
All recovery actions are logged to the `Logs` table with detailed information:

```json
{
  "ServiceName": "TranscodeService",
  "JobsRecovered": 3,
  "OrphanedProcessesKilled": 1,
  "RecoveryDetails": [
    {
      "JobId": 123,
      "ProcessId": 4567,
      "QueueId": 89,
      "JobType": "Transcode",
      "RecoveryAction": "OrphanedProcessKilled",
      "ProcessWasOrphaned": true
    }
  ]
}
```

## Integration Points

### TranscodeService Integration
**File**: `TranscodeService/Main.py` (entry point) → `TranscodeService/App.py` (recovery logic)

- Replaced `ResetStuckJobs()` method with `RecoverFromCrash()`
- Called during service startup in the `Run()` method
- Provides comprehensive recovery for transcoding operations
- Launch with: `py TranscodeService/Main.py`

### QualityTestService Integration
**File**: `QualityTestService/Main.py` (entry point and recovery logic)

- Enhanced existing cleanup in `Initialize()` method
- Maintains compatibility with existing `DatabaseCleanupService`
- Provides recovery for quality testing operations
- Launch with: `py QualityTestService/Main.py`

## Logging and Monitoring

### Log Levels
- **INFO**: Normal recovery operations, process cleanup
- **WARNING**: Orphaned processes detected and killed
- **ERROR**: Recovery failures, database errors

### Log Components
- **Component**: "CrashRecoveryService"
- **Operation**: "RecoverJobs", "KillProcess", "ResetQueue"
- **AdditionalData**: JSON with detailed recovery information

### Monitoring Recommendations
1. Monitor logs for recovery frequency to identify stability issues
2. Track orphaned process counts to detect service reliability
3. Alert on recovery failures that require manual intervention

## Testing

### Test Script
**File**: `Scripts/TestCrashRecovery.py`

Comprehensive test suite that validates:
- ProcessManagementService functionality
- CrashRecoveryService operations
- DatabaseManager methods
- Active job management
- End-to-end recovery scenarios

### Manual Testing Scenarios

**Important**: Before testing, ensure you have the complete system running:
- `cd WebService && py Main.py`
- `cd TranscodeService && py Main.py`
- `cd QualityTestService && py Main.py`

#### Scenario 1: Computer Crash Simulation
1. Start a transcoding job via the web interface
2. Force kill all Python processes (`taskkill /f /im python.exe` on Windows)
3. Restart all three services (see System Startup section)
4. Verify: Job reset to Pending, recovery logged

#### Scenario 2: Service Crash with Orphaned FFmpeg
1. Start a transcoding job via the web interface
2. Kill only the TranscodeService process (leave FFmpeg running)
   - Find the PID: `tasklist | findstr "TranscodeService"`
   - Kill it: `taskkill /f /pid <PID>`
3. Restart TranscodeService: `py TranscodeService/Main.py`
4. Verify: FFmpeg killed, job reset to Pending, logged as orphaned

#### Scenario 3: Multiple Stuck Jobs
1. Start multiple transcoding and quality testing jobs via the web interface
2. Force system crash or kill all Python processes
3. Restart all three services (see System Startup section)
4. Verify: All jobs recovered, comprehensive logging in database

## Dependencies

### Required Libraries
- `psutil>=5.9.0` - Cross-platform process management
- Built-in Python modules: `os`, `signal`, `platform`, `datetime`

### Database Tables Used
- `ActiveJobs` - Primary tracking table
- `TranscodeQueue` - Transcoding job queue
- `QualityTestingQueue` - Quality testing job queue
- `TranscodeProgress` - Transcoding progress tracking
- `QualityTestProgress` - Quality testing progress tracking
- `Logs` - Recovery action logging

## Configuration

### Service Names
The system uses these service identifiers:
- `"TranscodeService"` - For transcoding operations
- `"QualityTestService"` - For quality testing operations

### Process Management
- **Graceful Termination**: 10-second timeout before force kill
- **Process Detection**: Uses `psutil.Process.is_running()`
- **Cross-Platform**: Works on Windows, Linux, and macOS

## Future Enhancements

### Phase 2: Smart Resume (Documented in FutureImprovements.md)
Future enhancement to preserve work already completed by:
- Starting FFmpeg with log file redirection
- Reading log files to recover progress
- Continuing orphaned processes instead of killing them
- Real-time progress monitoring from log files

## Troubleshooting

### Common Issues

#### Multiple Service Instances Running
**Symptom**: Database locks, competing jobs, unpredictable behavior
**Solution**: 
1. Kill all Python processes: `taskkill /f /im python.exe`
2. Verify no Python processes remain: `tasklist | findstr "python.exe"`
3. Restart services one at a time, waiting for each to fully start
4. Check logs for "already running" messages

#### Recovery Not Working
1. Check if `psutil` is installed: `pip install psutil>=5.9.0`
2. Verify service startup logs for recovery messages
3. Check `Logs` table for recovery operation details
4. Ensure services are launched with correct commands (see System Startup)

#### Orphaned Processes Not Detected
1. Verify `ActiveJobs` table has records with `ProcessId`
2. Check if processes are running: `tasklist | findstr ffmpeg`
3. Review process management service logs

#### Database State Issues
1. Check `ActiveJobs` table for old records
2. Verify queue tables have correct status values
3. Review database transaction logs

### Recovery Verification
To verify recovery is working:
1. Check service startup logs for "Crash recovery completed" messages
2. Query `Logs` table for recent recovery operations:
   ```sql
   SELECT * FROM Logs 
   WHERE Component = 'CrashRecoveryService' 
   ORDER BY Timestamp DESC 
   LIMIT 10
   ```
3. Verify no "Running" jobs exist in queue tables after startup:
   ```sql
   SELECT * FROM TranscodeQueue WHERE Status = 'Running';
   SELECT * FROM QualityTestingQueue WHERE Status = 'Running';
   ```
4. Check that only one instance of each service is running (see System Startup section)

## Security Considerations

- Process killing requires appropriate system permissions
- Database operations use parameterized queries to prevent SQL injection
- Log files may contain sensitive file path information
- Process information is logged for debugging purposes

## Performance Impact

- **Startup Time**: Minimal impact (~1-2 seconds for recovery check)
- **Memory Usage**: Negligible additional memory overhead
- **Database Load**: Light queries during startup only
- **Process Overhead**: No ongoing monitoring overhead

## Maintenance

### Regular Tasks
- Monitor recovery frequency in logs
- Clean up old log entries periodically
- Verify recovery functionality after system updates
- Review orphaned process patterns for service stability

### Updates and Changes
- Recovery logic is self-contained and doesn't require configuration changes
- New services can be added by implementing the same recovery pattern
- Database schema changes may require recovery logic updates
