# MicroService Quality Testing Architecture - Database-Driven MVVM + KISS

## Database-Driven MicroService Flow:

### 1. Services/QualityTestingService.py (MicroService Entry Point)
- `Run()` → **calls** `self.DatabaseManager.GetServiceStatus('QualityTestingService')`
- If `Status = 'Running'` → **calls** `self.ViewModel.ProcessQueue()`
- If `Status = 'Stopped'` → **waits** and checks again
- **Loops every 10 seconds** checking ServiceStatus table
- `Initialize()` → **calls** `self.ViewModel.Initialize()`
- `Shutdown()` → **calls** `self.ViewModel.Shutdown()`

### 2. ViewModels/QualityTestingViewModel.py (Presentation Logic)
- `ProcessQueue()` → **calls** `self.QualityTestingBusinessService.ProcessQualityTestQueue()`
- `GetActiveJobs()` → **calls** `self.QualityTestingBusinessService.GetActiveJobs()`
- `CheckServiceStatus()` → **calls** `self.DatabaseManager.GetServiceStatus()`

### 3. Services/QualityTestingBusinessService.py (Business Logic)
- `ProcessQualityTestQueue()` → **calls** `self.DatabaseManager.GetQualityTestQueue()`
- `StartQualityTest()` → **calls** `self.DatabaseManager.CreateActiveJob()`
- `RunFFmpegVMAF()` → **calls** `subprocess.Popen()` (FFmpeg + PID capture)
- `MonitorProgress()` → **calls** `self.DatabaseManager.SaveQualityTestProgress()`
- `CheckConcurrencyLimit()` → **calls** `self.DatabaseManager.GetMaxConcurrentJobs()`

### 4. Repositories/DatabaseManager.py (Data Access)
- `GetServiceStatus(service_name)` → Check if service should run/stop
- `GetQualityTestQueue()` → Get pending jobs from QualityTestingQueue
- `CreateActiveJob()` → Track job execution in ActiveJobs table
- `SaveQualityTestProgress()` → Update progress in QualityTestProgress table
- `GetMaxConcurrentJobs()` → Get concurrency limit from ServiceStatus
- `UpdateQualityTestStatus()` → Update job status and VMAF score
- `CompleteActiveJob()` → Mark job as completed

## Key Features:

### Database-Driven Control:
- **ServiceStatus table** controls if microservice runs or stops
- **GUI integration ready** - can easily tie into existing GUI controls
- **Manual control** - database setting can be changed directly for testing

### FFmpeg Integration:
- **subprocess.Popen()** captures FFmpeg PID
- **Real-time progress tracking** with frame counts
- **XML VMAF output** parsing for quality scores
- **Async execution** with progress monitoring thread

### Concurrency Management:
- **MaxConcurrentJobs** from ServiceStatus table
- **ActiveJobs tracking** prevents over-processing
- **Single record updates** in QualityTestProgress (not multiple records)

### Architecture Benefits:
- **MVVM compliance** - proper layer separation
- **KISS principle** - 4 files, ~15 methods total
- **Database-driven** - easy GUI integration
- **MicroService pattern** - follows existing codebase patterns