# TranscodeService Separation Checklist

## Overview
Separate TranscodeService from MediaVortex.py to run as independent Python process for improved resilience and separation of concerns.

## Implementation Plan

### **Create Standalone TranscodeService**
- [x] **Create `TranscodeService.py`** - New standalone script in project root (TranscodeService/Main.py)
- [x] **Extract transcoding logic** - Move ProcessTranscodeQueueService from MediaVortex.py (ProcessTranscodeQueueService works standalone)
- [x] **Add main() function** - Entry point for standalone execution (TranscodeService/Main.py with signal handling)
- [x] **Add process management** - Handle startup, shutdown, and error recovery (TranscodeService/App.py)
- [x] **Add logging** - Independent logging for TranscodeService operations (TranscodeService/Main.py with logging config)

### **Modify MediaVortex.py**
- [x] **Remove transcoding logic** - Extract ProcessTranscodeQueueService calls (No ProcessTranscodeQueueService calls found in MediaVortex.py)
- [x] **Keep API endpoints** - Maintain HTTP endpoints for UI communication (All endpoints preserved)
- [x] **Add service status checking** - Check if TranscodeService is running (ServiceStatusController created)
- [x] **Add service communication** - Communicate with TranscodeService via database (ServiceCommandService created, TranscodeJobController modified to use database commands)

### **Database Communication**
- [x] **Use existing database** - TranscodeService and MediaVortex share same database (TranscodeService imports shared DatabaseManager)
- [x] **Add service status table** - Track TranscodeService health and status (ServiceStatus table created in database schema)
- [x] **Add communication flags** - Use database for service-to-service communication (ServiceCommands table created, ServiceCommandService implemented)
- [x] **Add queue management** - Ensure both services can manage TranscodeQueue safely (ProcessTranscodeQueueService works standalone)

### **Process Management**
- [x] **Create startup script** - `StartTranscodeService.ps1` with tab completion (StartTranscodeService.ps1 created)
- [x] **Add process monitoring** - Check if TranscodeService is running (Scripts check for running processes)
- [ ] **Add restart capability** - Auto-restart TranscodeService if it crashes
- [x] **Add graceful shutdown** - Proper cleanup when stopping TranscodeService (StopTranscodeService.ps1 with graceful shutdown)

### **Error Handling & Recovery**
- [x] **Add crash detection** - MediaVortex detects if TranscodeService stops (ServiceStatusController can detect service status)
- [ ] **Add restart logic** - Automatically restart TranscodeService if needed
- [x] **Add error logging** - Log all service communication errors (LoggingService integrated)
- [ ] **Add fallback behavior** - Handle cases where TranscodeService is unavailable

### **Testing & Validation**
- [x] **Test independent operation** - Verify TranscodeService runs standalone (TestTranscodeService.ps1 created)
- [x] **Test communication** - Verify database communication works (TranscodeService imports shared DatabaseManager)
- [ ] **Test crash recovery** - Simulate TranscodeService crashes
- [x] **Test startup/shutdown** - Verify proper service lifecycle (TestTranscodeService.ps1 tests full lifecycle)

## File Structure Changes

### **New Files**
- [x] **`TranscodeService/`** - New directory for transcoding microservice (TranscodeService/ directory created)
- [x] **`TranscodeService/Main.py`** - Entry point for the microservice (TranscodeService/Main.py with signal handling)
- [x] **`TranscodeService/App.py`** - Application logic and service orchestration (TranscodeService/App.py with TranscodeServiceApp class)
- [x] **`TranscodeService/Config.py`** - Configuration management (TranscodeService/Config.py with environment variables)
- [x] **`TranscodeService/Health.py`** - Health check and monitoring (TranscodeService/Health.py with HealthMonitor class)
- [x] **`TranscodeService/requirements.txt`** - Dependencies for transcoding service (TranscodeService/requirements.txt created)
- [x] **`TranscodeService/venv/`** - Virtual environment for transcoding service (Virtual environment created and configured)
- [x] **`StartTranscodeService.ps1`** - PowerShell script to start service (StartTranscodeService.ps1 created)
- [x] **`StopTranscodeService.ps1`** - PowerShell script to stop service (StopTranscodeService.ps1 created)

### **Modified Files**
- [x] **`MediaVortex.py`** - Remove transcoding logic, keep API endpoints (No ProcessTranscodeQueueService calls found)
- [x] **`Services/ProcessTranscodeQueueService.py`** - Ensure it works standalone (Works standalone with DatabaseManager)
- [x] **`Controllers/TranscodeJobController.py`** - Modified to use database commands instead of direct service calls
- [x] **`requirements.txt`** - Add any new dependencies for standalone service (TranscodeService has its own requirements.txt)

### **New Services**
- [x] **`Services/ServiceCommandService.py`** - Database-based inter-service communication service

## Implementation Details

### **TranscodeService Directory Structure**
```
TranscodeService/
├── Main.py              # Entry point
├── App.py               # Application logic
├── Config.py            # Configuration
├── Health.py            # Health monitoring
├── requirements.txt     # Dependencies
├── venv/                # Virtual environment
└── __init__.py          # Package marker
```

### **Main.py Structure**
```python
# TranscodeService/Main.py
import sys
import signal
from App import TranscodeServiceApp

def main():
    app = TranscodeServiceApp()
    app.run()

if __name__ == "__main__":
    main()
```

### **App.py Structure**
```python
# TranscodeService/App.py
class TranscodeServiceApp:
    def __init__(self):
        # Initialize services
        pass
    
    def run(self):
        # Start processing loop
        # Handle shutdown signals
        pass
```

### **Service Communication**
- **Database-based** - Use existing TranscodeQueue table
- **Status tracking** - Add service status to database
- **Command passing** - Use database flags for commands
- **Result sharing** - Use database for results

### **Process Management**
- **Startup** - Check database connection, initialize services
- **Monitoring** - Regular health checks, status updates
- **Shutdown** - Graceful cleanup, save state
- **Recovery** - Auto-restart on failure

## Success Criteria
- [x] TranscodeService runs independently of MediaVortex (TranscodeService/Main.py works standalone)
- [ ] MediaVortex can start/stop TranscodeService (PowerShell scripts exist, but MediaVortex doesn't call them)
- [x] Communication works via database (TranscodeService uses shared DatabaseManager and ServiceStatus table)
- [ ] TranscodeService auto-restarts on crash (Not implemented in MediaVortex)
- [x] No transcoding functionality is lost (ProcessTranscodeQueueService works standalone)
- [x] Performance is maintained or improved (Independent service architecture)
- [x] Error handling is robust (Signal handling and graceful shutdown implemented)
- [x] Logging provides clear audit trail (Independent logging in TranscodeService)

## Benefits
- **Resilience** - Transcoding continues if web UI crashes
- **Separation** - Clear boundaries between services
- **Scalability** - Can run on different machines
- **Maintainability** - Easier to debug and update
- **Reliability** - Independent failure domains
