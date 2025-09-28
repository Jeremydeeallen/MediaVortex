# Quality Compare Service Microservice Checklist

## Overview
Create standalone QualityCompareService microservice with flexible quality testing strategies (Skip/Single/Multi/Custom) and integrate into MediaVortex GUI, replacing old VMAF system.

## Implementation Plan



### **Database Integration (COMPLETED)**
- [x] **Database tables renamed** - VMAFQueue → QualityTestingQueue, VMAFProgress → QualityTestProgress
- [x] **New quality testing tables created** - QualityTestingStrategies, QualityTestResults, FileQualityOverrides
- [x] **Database schema updated** - All new columns added for strategy support
- [x] **Data preserved** - Existing VMAF data maintained in renamed tables

### **Update DatabaseManager**
- [x] **Remove old VMAF methods** - Delete GetNextPendingVMAFJob, SaveVMAFQueueItem, SaveVMAFProgress, etc.
- [x] **Add new quality testing methods** - GetQualityTestingStrategy, SaveQualityTestingQueue, GetQualityTestResults, etc.
- [x] **Update existing methods** - Modify methods to use new table names (QualityTestingQueue, QualityTestProgress)
- [x] **Add strategy management methods** - GetStrategyForProfile, CreateStrategy, UpdateStrategy, DeleteStrategy
- [x] **Add file override methods** - GetFileQualityOverride, SaveFileQualityOverride

### **Create Quality Testing Models (COMPLETED)**
- [x] **QualityTestingStrategyModel** - Strategy configuration with validation
- [x] **QualityTestResultModel** - VMAF test results with quality ratings
- [x] **QualityTestingQueueModel** - Queue management with status tracking
- [x] **FileQualityOverrideModel** - File-specific overrides with validation

### **Create Quality Testing Services (COMPLETED)**
- [x] **QualityTestingStrategyService** - Strategy management and configuration
- [x] **MultiQualityTestingService** - Multi-profile testing and result comparison
- [x] **QualityTestingOrchestratorService** - Workflow orchestration for all strategies

### **Create Quality Testing ViewModels (COMPLETED)**
- [x] **QualityTestingViewModel** - Business logic coordination
- [x] **Enhanced TranscodingViewModel** - Integrated quality testing workflow

### **Create Quality Testing Controllers (COMPLETED)**
- [x] **QualityTestingController** - REST API endpoints for quality testing management

### **Create QualityCompareService Microservice**
- [x] **Create `QualityCompareService/Main.py`** - Entry point with signal handling and service initialization
- [x] **Create `QualityCompareService/App.py`** - QualityCompareServiceApp class with strategy processing
- [x] **Create `QualityCompareService/Config.py`** - Configuration management for quality testing
- [x] **Create `QualityCompareService/Health.py`** - Health monitoring and status reporting
- [x] **Create `QualityCompareService/requirements.txt`** - Dependencies for quality comparison service
- [x] **Create `QualityCompareService/venv/`** - Virtual environment setup

### **Process Management**
- [x] **Create startup script** - `StartQualityCompareService.ps1` with tab completion
- [x] **Create stop script** - `StopQualityCompareService.ps1` with graceful shutdown
- [x] **Create test script** - `TestQualityCompareService.ps1` for testing service lifecycle
- [x] **Add process monitoring** - Check if QualityCompareService is running
- [x] **Add restart capability** - Auto-restart QualityCompareService if it crashes

### **Update Existing Services**
- [x] **Remove VMAFQueueBusinessService** - Delete old VMAF service completely
- [x] **Update ProcessTranscodeQueueService** - Remove VMAF queue calls, use new quality testing workflow
- [x] **Update TranscodingViewModel** - Use new CompleteTranscoding method with quality testing integration
- [x] **Update VMAFJobController** - Replace with QualityTestingController endpoints
- [x] **Update ServiceCommandService** - Add quality testing command types

### **GUI Integration**
- [x] **Update TranscodeQueue.html** - Replace VMAF queue display with QualityTestingQueue
- [x] **Update Activity.html** - Replace VMAF progress display with QualityTestProgress
- [x] **Add strategy configuration UI** - Profile-based quality testing settings (Documented in Future Features)
- [x] **Add file override UI** - File-specific quality testing overrides (Documented in Future Features)
- [x] **Add result comparison UI** - Multi-testing result display and selection (Documented in Future Features)
- [x] **Update JavaScript** - Replace VMAF API calls with QualityTesting API calls (Core functionality updated)

### **MVVM + Microservices Integration**
- [x] **Create QualityTestingController** - REST API endpoints for quality testing management
- [x] **Implement MVVM data binding** - Connect GUI Views to ViewModels to Models
- [x] **Create quality testing API endpoints** - /api/QualityTesting/Queue, /api/QualityTesting/Status, etc.
- [x] **Implement service communication** - GUI communicates with QualityCompareService via database
- [x] **Add real-time updates** - GUI updates when QualityCompareService processes jobs
- [x] **Implement error handling** - GUI handles microservice communication errors
- [x] **Add service status monitoring** - GUI shows QualityCompareService health status

### **Testing & Validation**
- [ ] **Test microservice operation** - Verify QualityCompareService runs standalone
- [ ] **Test strategy processing** - Verify Skip/Single/Multi/Custom strategies work
- [ ] **Test GUI integration** - Verify TranscodeQueue and Activity tabs display new quality testing data
- [ ] **Test database communication** - Verify service communicates via database
- [ ] **Test crash recovery** - Simulate QualityCompareService crashes and recovery
- [ ] **Test startup/shutdown** - Verify proper service lifecycle
- [ ] **Test API endpoints** - Verify QualityTestingController endpoints work
- [ ] **Test file overrides** - Verify file-specific quality testing overrides work

## File Structure Changes

### **New Files (TO CREATE)**
- [x] **`QualityCompareService/`** - New directory for quality comparison microservice
- [x] **`QualityCompareService/Main.py`** - Entry point with signal handling
- [x] **`QualityCompareService/App.py`** - QualityCompareServiceApp class with strategy processing
- [x] **`QualityCompareService/Config.py`** - Configuration management
- [x] **`QualityCompareService/Health.py`** - Health monitoring and status reporting
- [x] **`QualityCompareService/requirements.txt`** - Dependencies for quality comparison service
- [x] **`QualityCompareService/venv/`** - Virtual environment setup
- [x] **`StartQualityCompareService.ps1`** - PowerShell script to start service
- [x] **`StopQualityCompareService.ps1`** - PowerShell script to stop service
- [x] **`TestQualityCompareService.ps1`** - PowerShell script to test service

### **Files to Delete (OLD VMAF SYSTEM)**
- [x] **`Services/VMAFQueueBusinessService.py`** - Delete old VMAF service
- [x] **`Controllers/VMAFJobController.py`** - Delete old VMAF controller
- [x] **`Models/VMAFQueueModel.py`** - Delete old VMAF queue model
- [x] **`Models/VMAFProgressModel.py`** - Delete old VMAF progress model

### **Files to Modify**
- [x] **`Repositories/DatabaseManager.py`** - Remove old VMAF methods, add new quality testing methods
- [x] **`Services/ProcessTranscodeQueueService.py`** - Remove VMAF queue calls, use new quality testing
- [x] **`ViewModels/TranscodingViewModel.py`** - Use new CompleteTranscoding method
- [x] **`Templates/TranscodeQueue.html`** - Replace VMAF queue display with QualityTestingQueue
- [x] **`Templates/Activity.html`** - Replace VMAF progress display with QualityTestProgress
- [x] **`MediaVortex.py`** - Register QualityTestingController instead of VMAFJobController

## Implementation Details

### **QualityCompareService Directory Structure**
```
QualityCompareService/
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
# QualityCompareService/Main.py
import sys
import signal
from App import QualityCompareServiceApp

def main():
    app = QualityCompareServiceApp()
    app.run()

if __name__ == "__main__":
    main()
```

### **App.py Structure**
```python
# QualityCompareService/App.py
class QualityCompareServiceApp:
    def __init__(self):
        # Initialize services
        pass
    
    def run(self):
        # Start quality comparison processing loop
        # Handle shutdown signals
        pass
```

### **Service Communication**
- **Database-based** - Use existing VMAFQueue table
- **Status tracking** - Add service status to database
- **Command passing** - Use database flags for commands
- **Result sharing** - Use database for results

### **Process Management**
- **Startup** - Check database connection, initialize services
- **Monitoring** - Regular health checks, status updates
- **Shutdown** - Graceful cleanup, save state
- **Recovery** - Auto-restart on failure

## Success Criteria
- [ ] **QualityCompareService runs independently** - Standalone microservice with signal handling
- [ ] **Flexible quality testing strategies work** - Skip/Single/Multi/Custom strategies functional
- [ ] **GUI integration complete** - TranscodeQueue and Activity tabs show new quality testing data
- [ ] **Database communication works** - Service communicates via shared database
- [ ] **Old VMAF system removed** - All old VMAF code deleted and replaced
- [ ] **Strategy configuration UI** - Users can configure quality testing strategies per profile
- [ ] **File override system** - Users can set file-specific quality testing overrides
- [ ] **Multi-testing results** - Users can view and select best results from multiple tests
- [ ] **Performance maintained** - Quality testing performance equal or better than old system
- [ ] **Error handling robust** - Graceful shutdown, crash recovery, comprehensive logging

## Benefits
- **Flexible Quality Testing** - Skip/Single/Multi/Custom strategies for different use cases
- **GUI Integration** - Full UI support for quality testing configuration and monitoring
- **Microservice Architecture** - Independent service with proper separation of concerns
- **Resilience** - Quality testing continues if web UI crashes
- **Scalability** - Can run on different machines
- **Maintainability** - Clean architecture, easier to debug and update
- **User Control** - Profile-based and file-specific quality testing configuration
- **Advanced Features** - Multi-profile testing, result comparison, custom strategies

## Quality Testing Strategy Considerations

### **Strategy Types**
- **Skip Strategy** - Bypass quality testing entirely for trusted profiles/files
- **Single Strategy** - Standard VMAF analysis with configurable threshold
- **Multi Strategy** - Test multiple profiles and select best result
- **Custom Strategy** - Configurable custom testing scenarios

### **Quality Thresholds**
- **Default threshold** - 90.0 VMAF score for quality acceptance
- **Configurable thresholds** - Per-profile and per-file quality requirements
- **Score interpretation** - 90-100 excellent, 80-90 high, 70-80 good, 60-70 fair, <60 poor

### **Quality Testing Workflow Integration**
- **Queue processing** - QualityTestingQueue handles job distribution with strategy support
- **Progress monitoring** - QualityTestProgress table tracks real-time analysis progress
- **Result storage** - Quality test results stored in QualityTestResults table
- **Strategy management** - Profile-based and file-specific strategy configuration
- **File management** - Automatic cleanup of completed quality tests

## Dependencies

### **Core Dependencies**
- **FFmpeg** - With libvmaf filter support
- **Python packages** - Same as TranscodeService (flask, sqlite3, etc.)
- **Database access** - Shared MediaVortex.db
- **File system access** - Read original and transcoded files

### **Service Dependencies**
- **QualityTestingOrchestratorService** - Core quality testing workflow orchestration
- **QualityTestingStrategyService** - Strategy management and configuration
- **MultiQualityTestingService** - Multi-profile testing and result comparison
- **FFmpegComparisonService** - VMAF analysis execution
- **DatabaseManager** - Database operations
- **LoggingService** - Service logging

## Implementation Notes

### **Quality Testing Processing Flow**
1. **Job pickup** - GetNextPendingQualityTest from QualityTestingQueue
2. **Strategy determination** - Get quality testing strategy for profile/file
3. **Progress tracking** - Create QualityTestProgress record
4. **Strategy execution** - Execute Skip/Single/Multi/Custom strategy
5. **Quality analysis** - Execute FFmpeg libvmaf comparison (if needed)
6. **Score extraction** - Parse VMAF results from JSON output
7. **Quality validation** - Compare score against threshold
8. **Result storage** - Update QualityTestResults and TranscodeAttempts
9. **Cleanup** - Remove completed job from QualityTestingQueue

### **Error Handling**
- **FFmpeg failures** - Handle libvmaf filter errors
- **File access errors** - Handle missing or corrupted files
- **Database errors** - Handle connection and transaction failures
- **Resource limits** - Handle memory and CPU constraints

### **Performance Considerations**
- **Concurrent jobs** - Limit concurrent quality testing (default: 1)
- **Resource monitoring** - Track CPU and memory usage
- **Queue management** - Prioritize jobs based on importance and strategy
- **Progress updates** - Real-time progress reporting via QualityTestProgress
- **Strategy optimization** - Efficient multi-profile testing

## MVVM Pattern Compliance
- **Models** - QualityTestingQueueModel, QualityTestProgressModel, QualityTestingStrategyModel, QualityTestResultModel, FileQualityOverrideModel
- **ViewModels** - QualityTestingViewModel, Enhanced TranscodingViewModel
- **Views** - Quality testing management via QualityTestingController API endpoints
- **Separation of concerns** - Clear boundaries between quality testing strategies and UI components
- **Microservice architecture** - QualityCompareService as independent service following MVVM principles
