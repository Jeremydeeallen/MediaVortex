# MediaVortex Architecture

## Traditional MVVM as follows
We will only use PascalCase for everything!

## Database 
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

### Business Services (New Category): These services handle the core business processes by coordinating between models and other services.

- **TranscodingBusinessService**: The orchestrator for the entire transcoding process. It would use the FFmpegService or HandBrakeService.
- **QueueManagementBusinessService**: Handles adding, removing, and prioritizing items in the transcode queue.
- **FileScanningBusinessService**: Handles discovering media files in specified directories. It would use a FileManager.
- **ReportingBusinessService**: Collects data from various models to generate reports for the dashboard.

## Utility Services (Correct)
This layer is well-defined. Services like FFmpegService and HandBrakeService are perfect examples of utility services that encapsulate interactions with external tools.

- **FFmpegService**: Services/FFmpegService.py
- **HandBrakeService**: Services/HandBrakeService.py
- **LoggingService**: Services/LoggingService.py
- **CleanupService**: Services/CleanupService.py
- **FileManagerService**: A dedicated service for file operations.

## Presentation, API, and View Layers (Correct)
These layers are organized correctly. The ViewModels prepare data for the UI, the Controllers handle API requests and map them to ViewModels, and the Views are the final web interface.

- **ViewModels**: ViewModels/
- **Controllers**: Controllers/
- **Views**: Views/

## Summary
This revised structure follows a more traditional and effective Service-Oriented Architecture within an MVVM framework. The Models remain focused on data, while the Services handle the complex logic and interactions with external resources. This makes the system more modular, testable, and maintainable in the long run.