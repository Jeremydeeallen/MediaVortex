# MediaVortex Architecture

## Traditional MVVM as follows
We will only use PascalCase for everything!

## Database 
The database is located at \Data\MediaVortex.db
### Data Layer 

The DatabaseManager handles the business logic for data access (e.g., "get all users," "save this transaction"), and the DatabaseService provides the low-level infrastructure for connecting to the database.

- **DatabaseService**: Services/DatabaseService.py (The only file allowed to interact with /Data/MediaVortex.db)
- **DatabaseManager**: Repositories/DatabaseManager.py

### Critical Data Flow Principle

**ABSOLUTE RULE: MediaFiles table is ONLY for display and profile assignment**

- **MediaFiles table**: Contains file metadata (size, resolution, codec, etc.) for display purposes only
- **ProfileThresholds table**: The ONLY source for ALL transcoding configuration settings
- **Data Flow**: File → Profile Assignment → ProfileThresholds → Transcoding Settings

**NEVER use MediaFiles data for transcoding decisions. ALL transcoding settings (bitrates, quality, codec, target resolution) come exclusively from ProfileThresholds based on the assigned profile.** 

## Business Logic & Data (Models & Services)
This is where the most significant changes are needed. The Models should be simple data structures that represent your domain entities (e.g., a TranscodeProfile, a QueueItem). The Services should contain the complex operational logic.

### Models: These are simple data classes.

- **TranscodeQueueModel**: Represents a single transcoding job using TranscodeQueue table.
- **TranscodeAttemptModel**: Represents individual transcoding attempts using TranscodeAttempts table.
- **TranscodeFileModel**: Represents overall transcoding status using TranscodeFiles table.
- **TranscodeProfileModel**: Represents a set of transcoding settings using Profiles table.
- **ProfileThresholdModel**: Represents transcoding threshold settings using ProfileThresholds table.
- **RootFolderModel**: Represents a base directory with size information.
- **MediaFileModel**: Represents individual media files with metadata.
- **SeasonModel**: Represents season/folder organization.
- **FileScanResultModel**: Represents scan operation results.
- **FFmpegAnalysisModel**: Represents FFmpeg media analysis results.
- **FFmpegComparisonModel**: Represents FFmpeg video comparison results.
- **FFmpegVMAFComparisonModel**: Represents FFmpeg VMAF quality comparison results.
- **FFmpegScreenshotModel**: Represents FFmpeg screenshot generation results.

### Business Services (New Category): These services handle the core business processes by coordinating between models and other services.

- **TranscodingBusinessService**: The orchestrator for the entire transcoding process. It would use the FFmpegService or HandBrakeService.
- **QueueManagementBusinessService**: Handles transcoding queue operations including:
  - Queue population logic (evaluates MediaFiles against ProfileThresholds to determine what to transcode)
  - Adding, removing, and prioritizing items in the transcode queue
  - Queue statistics and management operations
  - Called by TranscodingBusinessService when queue is empty
- **FileScanningBusinessService**: Handles discovering media files in specified directories. It would use a FileManager.
- **ReportingBusinessService**: Collects data from various models to generate reports for the dashboard.

## Utility Services (Correct)
This layer is well-defined. Services like FFmpegService and HandBrakeService are perfect examples of utility services that encapsulate interactions with external tools.

- **FFmpegService**: Services/FFmpegService.py - Core FFmpeg command execution and FFprobe operations
- **FFmpegAnalysisService**: Services/FFmpegAnalysisService.py - Media file analysis using FFmpegService
- **FFmpegScreenshotService**: Services/FFmpegScreenshotService.py - Screenshot generation using FFmpegService
- **FFmpegComparisonService**: Services/FFmpegComparisonService.py - Video comparison operations using FFmpegService (includes VMAF quality comparison)
- **HandBrakeService**: Services/HandBrakeService.py
- **LoggingService**: Services/LoggingService.py - Centralized logging system with database storage
- **CleanupService**: Services/CleanupService.py
- **FileManagerService**: Services/FileManagerService.py - File system operations and metadata extraction

## Transcoding Workflow Architecture

The transcoding system follows a clear workflow with proper separation of concerns:

### Workflow Flow:
1. **FileScanningBusinessService** → Discovers and analyzes media files, stores in MediaFiles table
2. **QueueManagementBusinessService** → Evaluates MediaFiles against ProfileThresholds, populates TranscodeQueue
3. **TranscodingBusinessService** → Processes jobs from TranscodeQueue, updates TranscodeAttempts and TranscodeFiles

### Service Interactions:
- **TranscodingBusinessService** calls **QueueManagementBusinessService** when queue is empty
- **QueueManagementBusinessService** evaluates MediaFiles against ProfileThresholds to determine transcoding candidates
- **TranscodingBusinessService** uses **HandBrakeService** for actual transcoding operations
- All services use **DatabaseManager** for data persistence and **LoggingService** for operation tracking

### Database Tables Used:
- **MediaFiles**: Source files discovered by scanning
- **Profiles/ProfileThresholds**: Transcoding configuration and decision rules
- **TranscodeQueue**: Jobs ready for processing
- **TranscodeAttempts**: Individual transcoding attempt results
- **TranscodeFiles**: Overall transcoding status per file
- **Logs**: Operation tracking and error logging

## Presentation, API, and View Layers (Correct)
These layers are organized correctly. The ViewModels prepare data for the UI, the Controllers handle API requests and map them to ViewModels, and the Views are the final web interface.

### ViewModels (Presentation Logic)
- **FileScanningViewModel**: Manages scanning UI state and operations
- **FFmpegAnalysisViewModel**: Manages FFmpeg analysis UI state and operations
- **FFmpegComparisonViewModel**: Manages FFmpeg comparison UI state and operations (includes VMAF)
- **FFmpegScreenshotViewModel**: Manages FFmpeg screenshot UI state and operations
- **ProfileManagementViewModel**: Manages profile management UI state and operations
- **TranscodeQueueViewModel**: Manages transcoding queue UI state and operations
- **ActivityViewModel**: Manages real-time transcoding progress UI state
- **TranscodeHistoryViewModel**: Manages transcoding history and results UI state

### Controllers (API Layer)
- **FileScanningController**: Provides REST API endpoints for scanning operations
- **FFmpegController**: Provides REST API endpoints for FFmpeg operations (analysis, screenshots, comparisons, VMAF)
- **ProfileController**: Provides REST API endpoints for profile management
- **TranscodeQueueController**: Provides REST API endpoints for transcoding queue management
- **TranscodeJobController**: Provides REST API endpoints for transcoding job operations

### Views (UI Layer)
- **FileScanning.html**: Web interface for scanning operations
- **Settings.html**: Web interface for settings and profile management
- **Home.html**: Main dashboard interface
- **TranscodeQueue.html**: Web interface for transcoding queue management
- **TranscodeProgress.html**: Web interface for real-time transcoding progress
- **TranscodeHistory.html**: Web interface for transcoding history and results

## FFmpeg Integration Architecture

### Core FFmpeg Services
The FFmpeg integration follows a layered approach with clear separation of concerns:

1. **FFmpegService**: Core utility service that handles:
   - FFmpeg and FFprobe executable detection
   - Command execution with proper error handling
   - Unicode filename support
   - MediaVortex title metadata addition

2. **Specialized FFmpeg Services**: Each service focuses on specific functionality:
   - **FFmpegAnalysisService**: Media file analysis and metadata extraction
   - **FFmpegScreenshotService**: Screenshot generation at timestamps
   - **FFmpegComparisonService**: Video comparisons including VMAF quality analysis

### VMAF Quality Comparison
The VMAF (Video Multi-Method Assessment Fusion) comparison is a specialized feature that provides objective video quality assessment:

- **Purpose**: Compare original and transcoded videos using Netflix's VMAF algorithm
- **Implementation**: Uses FFmpeg's libvmaf filter with configurable VMAF models
- **Output**: XML results file with frame-by-frame and pooled metrics
- **Models**: Supports vmaf-8bit.json, vmaf-10bit.json, and vmaf-q25bit.json
- **API Endpoint**: `/api/FFmpeg/Comparison/VMAF`

### Data Flow for VMAF Comparison
1. **Controller**: Receives VMAF comparison request with file paths and parameters
2. **ViewModel**: Validates input and calls service layer
3. **Service**: Executes FFmpeg command with libvmaf filter
4. **Model**: Parses XML results and provides structured data
5. **Response**: Returns comprehensive VMAF metrics to client

## Logging Architecture

### Centralized Logging System
MediaVortex uses a centralized logging system that stores all log entries in the database for persistence, searchability, and analysis.

### LoggingService Design
The `LoggingService` is implemented as a singleton service that provides:

- **Database Storage**: All logs are stored in the `Logs` table in `MediaVortex.db`
- **Multiple Log Levels**: INFO, ERROR, WARNING, DEBUG, EXCEPTION
- **Function Tracking**: Each log entry includes the function name that generated it
- **Component Identification**: Logs are tagged with the component/service that generated them
- **Exception Handling**: Full stack traces for exceptions with automatic fallback to console

### Logging Database Schema
The `Logs` table structure:
```sql
CREATE TABLE Logs (
    Id INTEGER PRIMARY KEY AUTOINCREMENT,
    Timestamp DATETIME,
    LogLevel TEXT,           -- INFO, ERROR, WARNING, DEBUG
    FunctionName TEXT,       -- Name of the function that generated the log
    Message TEXT,            -- The actual log message
    SourceFile TEXT,         -- Source file (future use)
    SourceLine INTEGER,      -- Source line number (future use)
    SourceFunction TEXT,     -- Source function (future use)
    ExceptionType TEXT,      -- Exception type for error logs
    ExceptionMessage TEXT,   -- Exception message for error logs
    StackTrace TEXT,         -- Full stack trace for exceptions
    Component TEXT,          -- Component/service that generated the log
    Operation TEXT,          -- Operation being performed
    CreatedAt DATETIME
);
```

### Logging Method Signatures
All logging methods follow a consistent parameter pattern:

```python
# Standard logging methods
LoggingService.LogInfo(message, function_name, component, operation='')
LoggingService.LogError(message, function_name, component, operation='')
LoggingService.LogWarning(message, function_name, component, operation='')
LoggingService.LogDebug(message, function_name, component, operation='')

# Exception logging
LoggingService.LogException(message, exception, function_name, component, operation='')

# Function entry/exit logging (for debugging)
LoggingService.LogFunctionEntry(function_name, component, *args, **kwargs)
LoggingService.LogFunctionExit(function_name, result, component)

# Data logging
LoggingService.LogData(message, data, function_name, component, operation='')
```

### Logging Best Practices

1. **Function Name Parameter**: Always pass the current function name as the second parameter
   ```python
   def ProcessMediaFiles(self, MediaFiles):
       LoggingService.LogInfo(f"Processing {len(MediaFiles)} files", 'ProcessMediaFiles', 'FileScanningBusinessService')
   ```

2. **Component Identification**: Use the service/class name as the component
   ```python
   # In FileScanningBusinessService.py
   LoggingService.LogInfo("Starting scan", 'StartScanning', 'FileScanningBusinessService')
   
   # In FileScanningController.py  
   LoggingService.LogInfo("Received scan request", 'StartScan', 'FileScanningController')
   ```

3. **Operation Context**: Use the operation parameter for additional context
   ```python
   LoggingService.LogInfo("File processed successfully", 'ProcessFile', 'FileScanningBusinessService', 'FileProcessing')
   ```

4. **Exception Handling**: Always log exceptions with full context
   ```python
   try:
       # Some operation
   except Exception as e:
       LoggingService.LogException("Error processing file", e, 'ProcessFile', 'FileScanningBusinessService', 'FileProcessing')
   ```

### Logging Flow
1. **Application Code**: Calls appropriate LoggingService method with function name and component
2. **LoggingService**: Formats message and stores in database via DatabaseService
3. **Database**: Persists log entry with timestamp and metadata
4. **Fallback**: If database logging fails, falls back to console output

### Debug Mode
- **Environment Variable**: `MEDIAVORTEX_DEBUG=true` enables debug logging
- **Debug Methods**: `LogDebug`, `LogFunctionEntry`, `LogFunctionExit`, `LogData` only execute when debug mode is enabled
- **Performance**: Debug logging can be disabled in production for better performance

### Logging Benefits
- **Traceability**: Every log entry includes the exact function that generated it
- **Component Isolation**: Easy to filter logs by component/service
- **Operation Tracking**: Can trace operations across multiple components
- **Error Analysis**: Full exception context with stack traces
- **Performance Monitoring**: Function entry/exit logging for performance analysis
- **Audit Trail**: Complete record of all system operations

## Summary
This revised structure follows a more traditional and effective Service-Oriented Architecture within an MVVM framework. The Models remain focused on data, while the Services handle the complex logic and interactions with external resources. The centralized logging system provides comprehensive traceability and debugging capabilities throughout the application. This makes the system more modular, testable, and maintainable in the long run.