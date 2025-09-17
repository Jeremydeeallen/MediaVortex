# MediaVortex Architecture

## Traditional MVVM as follows
We will only use PascalCase for everything!

## Database 
The database is located at \Data\MediaVortex.db
### Data Layer 

The DatabaseManager handles the business logic for data access (e.g., "get all users," "save this transaction"), and the DatabaseService provides the low-level infrastructure for connecting to the database.

- **DatabaseService**: Services/DatabaseService.py (The only file allowed to interact with /Data/MediaVortex.db)
- **DatabaseManager**: Repositories/DatabaseManager.py 

## Business Logic & Data (Models & Services)
This is where the most significant changes are needed. The Models should be simple data structures that represent your domain entities (e.g., a TranscodeProfile, a QueueItem). The Services should contain the complex operational logic.

### Models: These are simple data classes.

- **TranscodeJobModel**: Represents a single item in the queue.
- **TranscodeProfileModel**: Represents a set of transcoding settings.
- **FileStatusModel**: Represents the status of a specific file.
- **SystemConfigurationModel**: Represents the app's settings.
- **LogEntryModel**: Represents a single log entry.
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
- **QueueManagementBusinessService**: Handles adding, removing, and prioritizing items in the transcode queue.
- **FileScanningBusinessService**: Handles discovering media files in specified directories. It would use a FileManager.
- **ReportingBusinessService**: Collects data from various models to generate reports for the dashboard.

## Utility Services (Correct)
This layer is well-defined. Services like FFmpegService and HandBrakeService are perfect examples of utility services that encapsulate interactions with external tools.

- **FFmpegService**: Services/FFmpegService.py - Core FFmpeg command execution and FFprobe operations
- **FFmpegAnalysisService**: Services/FFmpegAnalysisService.py - Media file analysis using FFmpegService
- **FFmpegScreenshotService**: Services/FFmpegScreenshotService.py - Screenshot generation using FFmpegService
- **FFmpegComparisonService**: Services/FFmpegComparisonService.py - Video comparison operations using FFmpegService (includes VMAF quality comparison)
- **HandBrakeService**: Services/HandBrakeService.py
- **LoggingService**: Services/LoggingService.py
- **CleanupService**: Services/CleanupService.py
- **FileManagerService**: Services/FileManagerService.py - File system operations and metadata extraction

## Presentation, API, and View Layers (Correct)
These layers are organized correctly. The ViewModels prepare data for the UI, the Controllers handle API requests and map them to ViewModels, and the Views are the final web interface.

### ViewModels (Presentation Logic)
- **FileScanningViewModel**: Manages scanning UI state and operations
- **FFmpegAnalysisViewModel**: Manages FFmpeg analysis UI state and operations
- **FFmpegComparisonViewModel**: Manages FFmpeg comparison UI state and operations (includes VMAF)
- **FFmpegScreenshotViewModel**: Manages FFmpeg screenshot UI state and operations
- **ProfileManagementViewModel**: Manages profile management UI state and operations

### Controllers (API Layer)
- **FileScanningController**: Provides REST API endpoints for scanning operations
- **FFmpegController**: Provides REST API endpoints for FFmpeg operations (analysis, screenshots, comparisons, VMAF)
- **ProfileController**: Provides REST API endpoints for profile management

### Views (UI Layer)
- **FileScanning.html**: Web interface for scanning operations
- **Settings.html**: Web interface for settings and profile management
- **Home.html**: Main dashboard interface

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

## Summary
This revised structure follows a more traditional and effective Service-Oriented Architecture within an MVVM framework. The Models remain focused on data, while the Services handle the complex logic and interactions with external resources. This makes the system more modular, testable, and maintainable in the long run.