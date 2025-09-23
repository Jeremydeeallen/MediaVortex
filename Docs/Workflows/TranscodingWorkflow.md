# Transcoding Workflow

This diagram shows the complete transcoding process from queue pickup to VMAF queue population.

```mermaid
flowchart TD
    A[Start Transcoding<br/>TranscodingBusinessService.StartTranscoding] --> A1[Set IsRunning = True<br/>TranscodingBusinessService.IsRunning]
    A1 --> B[Get Next Pending Job<br/>DatabaseManager.GetNextPendingTranscodeJob]
    B --> C{Job Available?}
    C -->|No| D[Queue Empty - Break Loop]
    D --> AA[Transcoding Complete]
    C -->|Yes| E[Mark Job as Running<br/>TranscodeQueueItem.MarkAsRunning]
    E --> F[UPDATE TranscodeQueue Status<br/>DatabaseManager.SaveTranscodeQueueItem]
    F -->     G[INSERT TranscodeAttempts Record<br/>DatabaseManager.SaveTranscodeAttempt]
    G --> G1[Load Profile Threshold Settings<br/>DatabaseManager.GetThresholdsByProfileId]
    G1 --> H[Initialize TranscodeProgress<br/>TranscodeProgressModel.MarkAsRunning]
    H --> I[Generate FFmpeg Command with Profile Settings<br/>FFmpegTranscodingService.GenerateTranscodeCommand]
    I --> I1[Apply Resolution Scaling if TranscodeDownTo is set<br/>FFmpegTranscodingService.ApplyResolutionScaling]
    I1 --> I2[Start FFmpeg/HandBrake Process<br/>FFmpegTranscodingService.StartTranscoding]
    I2 --> J[Monitor Progress<br/>FFmpegTranscodingService.MonitorProgress]
    J --> K[UPDATE TranscodeProgress Table<br/>DatabaseManager.SaveTranscodeProgress]
    K --> L{Process Complete?<br/>Check process exit code}
    L -->|No| M{Process Failed?<br/>Check for errors}
    M -->|No| J
    M -->|Yes| N[UPDATE TranscodeAttempts as Failed<br/>TranscodeAttemptModel.MarkAsFailed]
    N --> O[UPDATE TranscodeQueue Status to Failed<br/>DatabaseManager.SaveTranscodeQueueItem]
    O --> P[Log Error Message<br/>LoggingService.LogError]
    P --> Q[Continue to Next Job]
    L -->|Yes| R[Check Output File Size<br/>FileManagerService.GetFileSize]
    R --> S{Size Reduced?<br/>Compare file sizes}
    S -->|No| T[Mark as Failed - No Compression<br/>TranscodeAttemptModel.MarkAsFailed]
    T --> O
    S -->|Yes| U[UPDATE TranscodeAttempts as Success<br/>TranscodeAttemptModel.MarkAsSuccess]
    U --> V[UPDATE TranscodeQueue Status to Completed<br/>DatabaseManager.SaveTranscodeQueueItem]
    V --> W[Add to VMAFQueue<br/>VMAFQueueBusinessService.AddToVMAFQueue]
    W --> X[DELETE from TranscodeQueue<br/>DatabaseManager.DeleteTranscodeQueueItem]
    X --> Y[Continue to Next Job]
    Q --> Z{More Jobs?}
    Y --> Z
    Z -->|Yes| B
    Z -->|No| AA[Transcoding Complete]
    AA --> AA1[Set IsRunning = False<br/>TranscodingBusinessService.IsRunning]
    AA1 --> AA2[Log Process Complete<br/>LoggingService.LogInfo]
    
    %% VMAF Queue Addition Detail
    W --> W1[INSERT VMAFQueue Record<br/>DatabaseManager.SaveVMAFQueueItem]
    W1 --> W2[Set Status to Pending<br/>VMAFQueueModel.MarkAsPending]
    W2 --> W3[Set OriginalFilePath and TranscodedFilePath<br/>VMAFQueueModel.SetFilePaths]
    W3 --> W4[Set TranscodeAttemptId Foreign Key<br/>VMAFQueueModel.SetTranscodeAttemptId]
    
    %% Styling with dark text
    classDef startEnd fill:#2e7d32,stroke:#1b5e20,stroke-width:2px,color:#ffffff
    classDef process fill:#1976d2,stroke:#0d47a1,stroke-width:2px,color:#ffffff
    classDef decision fill:#f57c00,stroke:#e65100,stroke-width:2px,color:#ffffff
    classDef success fill:#388e3c,stroke:#2e7d32,stroke-width:2px,color:#ffffff
    classDef error fill:#d32f2f,stroke:#b71c1c,stroke-width:2px,color:#ffffff
    classDef vmaf fill:#7b1fa2,stroke:#4a148c,stroke-width:2px,color:#ffffff
    
    class A,AA startEnd
    class B,E,F,G,G1,H,I,I1,I2,J,K,R,U,V,X,W1,W2,W3,W4 process
    class C,L,M,S,Z decision
    class U,V success
    class N,O,P,T error
    class W,W1,W2,W3,W4 vmaf
```

## Key Components

### Database Tables Updated:
- **TranscodeQueue**: Status changes (Pending → Running → Completed/Failed)
- **TranscodeAttempts**: Success/failure tracking with compression details
- **TranscodeProgress**: Real-time progress updates during transcoding
- **VMAFQueue**: New records created for successful transcodes
- **ProfileThresholds**: Loaded to determine transcoding parameters

### Key Functions Used:
- **DatabaseManager.GetThresholdsByProfileId()**: Loads profile threshold settings for the assigned profile
- **FFmpegTranscodingService.GenerateTranscodeCommand()**: Creates base FFmpeg command with profile settings (bitrate, codec, quality)
- **FFmpegTranscodingService.ApplyResolutionScaling()**: Adds resolution scaling filters when TranscodeDownTo is set
- **FFmpegTranscodingService.StartTranscoding()**: Executes the complete FFmpeg command with all settings applied

### Key Decision Points:
1. **Job Availability**: Check for pending jobs in queue
2. **Process Completion**: Monitor FFmpeg/HandBrake process
3. **Size Reduction**: Verify file was actually compressed
4. **VMAF Queue Addition**: Only add successful compressions

### Success Criteria:
- Transcoding process completes without errors
- Output file is smaller than input file
- VMAFQueue record created with proper file paths

### Error Handling:
- Failed transcodes marked in TranscodeAttempts
- TranscodeQueue status updated to Failed
- Error messages logged for debugging
- Process continues to next job

### IsRunning Flag Management:
- **Start**: `IsRunning = True` when transcoding begins
- **During Processing**: Flag prevents multiple concurrent transcoding processes
- **Completion**: `IsRunning = False` in `finally` block ensures flag is always reset
- **Failure Recovery**: Flag reset on both success and failure paths
- **Prevents**: "Already transcoding" errors from stuck flags

### VMAF Integration:
- Successful transcodes automatically added to VMAFQueue
- Foreign key relationship maintained via TranscodeAttemptId
- Original and transcoded file paths preserved for quality testing

### Profile Threshold Processing:
- **Step G1**: Load profile thresholds for the file's assigned profile
  - Retrieves VideoBitrateKbps, AudioBitrateKbps, Codec, Quality, Grain settings
  - Determines if TranscodeDownTo field is set (e.g., 2160p → 720p)
- **Step I**: Generate base FFmpeg command using profile settings
  - Applies bitrate limits: `-maxrate {VideoBitrateKbps}k -bufsize {VideoBitrateKbps*2}k`
  - Sets codec: `-c:v {Codec}` (e.g., libx265)
  - Sets quality: `-crf {Quality}` (e.g., 25)
  - Sets audio bitrate: `-b:a {AudioBitrateKbps}k`
- **Step I1**: Apply resolution scaling if needed
  - Checks TranscodeDownTo field in profile thresholds
  - Adds scaling filter: `-vf scale=1280:720` for 2160p → 720p
  - Ensures proper aspect ratio maintenance
- **Step I2**: Execute complete command with all settings applied

### Resolution Scaling Logic:
- **2160p → 720p**: `-vf scale=1280:720`
- **1080p → 720p**: `-vf scale=1280:720` 
- **720p → 480p**: `-vf scale=854:480`
- **No scaling**: When TranscodeDownTo is null/empty

