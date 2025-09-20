# Data Model: Video Queue Transcoding

## Entities

### TranscodeQueueItem
**Purpose**: Represents individual videos in the transcoding queue with assigned profile and status
**Database Table**: TranscodeQueue (existing)

**Fields**:
- Id: INTEGER PRIMARY KEY
- FilePath: TEXT (source file path)
- FileName: TEXT (original filename)
- Directory: TEXT (source directory)
- SizeBytes: INTEGER (file size in bytes)
- SizeMB: REAL (file size in MB)
- Priority: INTEGER (queue priority - higher = more important)
- Status: TEXT (pending, processing, completed, failed)
- DateAdded: TIMESTAMP (when added to queue)
- DateStarted: TIMESTAMP (when processing began)
- AssignedProfile: TEXT (profile name assigned to this item)

**Validation Rules**:
- FilePath must exist and be accessible
- SizeMB must be positive
- Status must be one of: pending, processing, completed, failed
- AssignedProfile must reference existing profile

**State Transitions**:
- pending → processing (when transcoding starts)
- processing → completed (on successful transcoding)
- processing → failed (on transcoding failure)

### TranscodingJob
**Purpose**: Represents active transcoding operations with progress tracking and status updates
**Database Table**: TranscodeAttempts (existing, extended)

**Fields**:
- Id: INTEGER PRIMARY KEY
- FilePath: TEXT (source file path)
- AttemptDate: TIMESTAMP (when attempt started)
- Quality: INTEGER (transcoding quality setting)
- OldSizeBytes: INTEGER (original file size)
- NewSizeBytes: INTEGER (transcoded file size)
- Success: BOOLEAN (whether transcoding succeeded)
- SizeReductionBytes: INTEGER (bytes saved)
- SizeReductionPercent: REAL (percentage reduction)
- ErrorMessage: TEXT (error details if failed)
- TranscodeDurationSeconds: REAL (time taken)
- HandbrakeSettings: TEXT (settings used)
- AudioBitrateKbps: INTEGER (audio bitrate)
- VideoBitrateKbps: INTEGER (video bitrate)
- ProfileName: TEXT (profile used)
- JobId: TEXT (unique job identifier)
- ProgressPercent: REAL (completion percentage)
- Status: TEXT (running, completed, failed, cancelled)

**Validation Rules**:
- JobId must be unique
- ProgressPercent must be 0-100
- Status must be one of: running, completed, failed, cancelled
- OldSizeBytes must be positive
- NewSizeBytes must be positive (if successful)

**State Transitions**:
- running → completed (on successful completion)
- running → failed (on error)
- running → cancelled (on user/system cancellation)

### TranscodingResult
**Purpose**: Represents the outcome of transcoding operations including success/failure status and output file information
**Database Table**: TranscodeFiles (existing, extended)

**Fields**:
- Id: INTEGER PRIMARY KEY
- FilePath: TEXT (original file path)
- AllQualitiesFailed: BOOLEAN (whether all attempts failed)
- SuccessfullyTranscoded: BOOLEAN (whether any attempt succeeded)
- FirstAttemptDate: TIMESTAMP (first attempt time)
- LastAttemptDate: TIMESTAMP (most recent attempt time)
- SuccessDate: TIMESTAMP (when successful transcoding completed)
- FinalQuality: INTEGER (final quality used)
- FinalSizeBytes: INTEGER (final file size)
- TotalAttempts: INTEGER (number of attempts made)
- OriginalFilePath: TEXT (original file location)
- FinalFilePath: TEXT (final transcoded file location)
- OutputFileName: TEXT (name of transcoded file)
- ResolutionChange: TEXT (resolution change description, e.g., "1080p to 720p")

**Validation Rules**:
- FilePath must be valid
- TotalAttempts must be non-negative
- FinalSizeBytes must be positive (if successful)
- ResolutionChange must be descriptive if resolution changed

### TranscodingProfile
**Purpose**: Represents transcoding configuration templates with specific settings
**Database Table**: Profiles (existing)

**Fields**:
- Id: INTEGER PRIMARY KEY
- ProfileName: TEXT (unique profile name)
- Description: TEXT (profile description)
- CreatedDate: TIMESTAMP (when profile was created)
- LastModified: TIMESTAMP (when profile was last updated)
- HandbrakePreset: TEXT (HandBrake preset to use)
- VideoSettings: TEXT (JSON with video settings)
- AudioSettings: TEXT (JSON with audio settings)
- OutputFormat: TEXT (output container format)
- QualityTarget: INTEGER (target quality level)

**Validation Rules**:
- ProfileName must be unique
- HandbrakePreset must be valid HandBrake preset
- VideoSettings must be valid JSON
- AudioSettings must be valid JSON
- QualityTarget must be positive integer

## Relationships

### TranscodeQueueItem → TranscodingProfile
- Many-to-One relationship
- Each queue item has one assigned profile
- Profile can be used by multiple queue items

### TranscodingJob → TranscodeQueueItem
- One-to-One relationship
- Each job processes one queue item
- Job references the queue item's FilePath

### TranscodingResult → TranscodeQueueItem
- One-to-One relationship
- Each result corresponds to one queue item
- Result references the queue item's FilePath

### TranscodingJob → TranscodingResult
- One-to-One relationship
- Each job produces one result
- Result aggregates information from job

## Database Schema Extensions

### New Fields for Existing Tables

**TranscodeQueue**:
- AssignedProfile: TEXT (profile name assigned to this item)

**TranscodeAttempts**:
- JobId: TEXT (unique job identifier)
- ProgressPercent: REAL (completion percentage)
- Status: TEXT (running, completed, failed, cancelled)

**TranscodeFiles**:
- OutputFileName: TEXT (name of transcoded file)
- ResolutionChange: TEXT (resolution change description)

**Profiles**:
- HandbrakePreset: TEXT (HandBrake preset to use)
- VideoSettings: TEXT (JSON with video settings)
- AudioSettings: TEXT (JSON with audio settings)
- OutputFormat: TEXT (output container format)
- QualityTarget: INTEGER (target quality level)

## Data Validation Rules

### File Path Validation
- FilePath must exist and be accessible
- FilePath must be absolute path
- FilePath must be within allowed directories

### Size Validation
- SizeBytes must be positive
- SizeMB must match SizeBytes / (1024 * 1024)
- NewSizeBytes must be less than OldSizeBytes (for compression)

### Status Validation
- Status values must be from predefined lists
- Status transitions must follow defined state machine
- Invalid status combinations must be prevented

### Profile Validation
- ProfileName must be unique
- Profile settings must be valid for HandBrake
- Profile must exist before assignment to queue item
