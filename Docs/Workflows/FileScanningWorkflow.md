# File Scanning Workflow

This diagram shows the complete file scanning process from root folder discovery to transcode queue population.

```mermaid
flowchart TD
    A[Start File Scan<br/>FileScanningBusinessService.ScanAllRootFolders] --> B[Get Root Folders<br/>DatabaseManager.GetAllRootFolders]
    B --> C[For Each Root Folder<br/>Loop through folders]
    C --> D[Scan Directory Recursively<br/>FileManagerService.ScanDirectoryRecursively]
    D --> E[For Each File Found<br/>Loop through files]
    E --> F{Is Media File?<br/>FileManagerService.IsMediaFile}
    F -->|No| G[Skip File]
    F -->|Yes| H[Analyze File Properties<br/>FileManagerService.AnalyzeFileProperties]
    H --> I[Check if File Exists<br/>DatabaseManager.GetMediaFileByPath]
    I -->|Exists| J{File Modified?<br/>Compare modification times}
    I -->|New File| K[INSERT MediaFiles<br/>DatabaseManager.SaveMediaFile]
    J -->|No| L[Skip - No Changes]
    J -->|Yes| M[UPDATE MediaFiles<br/>DatabaseManager.SaveMediaFile]
    K --> N[Assign Profile Based on Rules<br/>ProfileService.AssignProfileToFile]
    M --> N
    N --> O[INSERT TranscodeQueue<br/>DatabaseManager.SaveTranscodeQueueItem]
    O --> P[Continue to Next File]
    G --> P
    L --> P
    P --> Q{More Files?}
    Q -->|Yes| E
    Q -->|No| R{More Root Folders?}
    R -->|Yes| C
    R -->|No| S[UPDATE RootFolder LastScannedDate<br/>DatabaseManager.SaveRootFolder]
    S --> T[INSERT ScanJobs Record<br/>DatabaseManager.SaveScanJob]
    T --> U[Scan Complete]
    
    %% Error Handling
    H -->|Error| V[INSERT ProblemFiles<br/>DatabaseManager.SaveProblemFile]
    V --> P
    
    %% Styling with dark text
    classDef startEnd fill:#2e7d32,stroke:#1b5e20,stroke-width:2px,color:#ffffff
    classDef process fill:#1976d2,stroke:#0d47a1,stroke-width:2px,color:#ffffff
    classDef decision fill:#f57c00,stroke:#e65100,stroke-width:2px,color:#ffffff
    classDef error fill:#d32f2f,stroke:#b71c1c,stroke-width:2px,color:#ffffff
    classDef skip fill:#757575,stroke:#424242,stroke-width:2px,color:#ffffff
    
    class A,U startEnd
    class B,C,D,E,H,I,K,M,N,O,P,S,T process
    class F,J,Q,R decision
    class V error
    class G,L skip
```

## Key Components

### Database Tables Updated:
- **RootFolders**: LastScannedDate updated
- **MediaFiles**: New files added, existing files updated if modified
- **TranscodeQueue**: Files added for transcoding
- **ProblemFiles**: Files with analysis errors
- **ScanJobs**: Scan job tracking and progress

### Key Decision Points:
1. **Media File Check**: Only process video/audio files
2. **File Existence**: Handle new vs existing files differently
3. **File Modification**: Only update if file has changed
4. **Profile Assignment**: Apply transcoding rules based on file properties

### Error Handling:
- Files that can't be analyzed go to ProblemFiles table
- Scan continues even if individual files fail
- ScanJobs table tracks overall progress and errors

