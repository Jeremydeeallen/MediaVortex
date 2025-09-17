# File Scanning Flow Documentation

## Overview
This document traces the complete file scanning process from the UI button click to database cleanup, focusing on the delete file from database functionality.

## Architecture
The system follows MVVM (Model-View-ViewModel) architecture with proper separation of concerns:
- **View**: HTML templates and JavaScript (UI only)
- **ViewModel**: Handles UI state and business logic coordination
- **Model**: Data models and business services (business logic)
- **Controller**: REST API endpoints
- **Subprocess**: Process orchestration and job management (no business logic)

## Key Architectural Principles
- **Single Responsibility**: Each component has one clear responsibility
- **MVVM Compliance**: Business logic stays in business service layer
- **No Duplication**: Single source of truth for all file processing logic
- **Proper Cleanup Integration**: Cleanup happens at optimal time in workflow

## Complete Flow: From UI Click to Database Cleanup

### 1. User Interface (UI Layer)
**File**: `Templates/FileScanning.html`

**Trigger**: User clicks "Start Scan" button
```javascript
// Line 312: Event handler setup
$('#StartScanBtn').click(StartScan);

// Lines 342-375: StartScan function
function StartScan() {
    const RootFolderPath = $('#RootFolderPath').val().trim();
    const Recursive = $('#RecursiveScan').is(':checked');
    
    // AJAX POST to /api/Scan/Start
    $.ajax({
        url: '/api/Scan/Start',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            RootFolderPath: RootFolderPath,
            Recursive: Recursive
        }),
        success: function(response) {
            // Handle response and start progress polling
        }
    });
}
```

### 2. Controller Layer
**File**: `Controllers/FileScanningController.py`

**Endpoint**: `/api/Scan/Start` (POST)
```python
# Lines 18-41: StartScan endpoint
@self.Blueprint.route('/Scan/Start', methods=['POST'])
def StartScan():
    data = request.get_json()
    RootFolderPath = data.get('RootFolderPath', '')
    Recursive = data.get('Recursive', True)
    
    # Call ViewModel
    result = self.ViewModel.StartScanning(RootFolderPath, Recursive)
    return jsonify(result)
```

### 3. ViewModel Layer
**File**: `ViewModels/FileScanningViewModel.py`

**Method**: `StartScanning()`
```python
# Lines 31-62: StartScanning method
def StartScanning(self, RootFolderPath: str, Recursive: bool = True) -> Dict[str, Any]:
    # Call Business Service
    result = self.BusinessService.StartScanning(RootFolderPath, Recursive)
    
    # Update UI state
    if result['Success']:
        self.CurrentScanDirectory = RootFolderPath
        self.ScanStatusMessage = "Scan started successfully"
    else:
        self.IsError = True
        self.ErrorMessage = result.get('Message', 'Unknown error occurred')
    
    return result
```

### 4. Business Service Layer
**File**: `Services/FileScanningBusinessService.py`

**Method**: `StartScanning()`
```python
# Lines 49-137: StartScanning method
def StartScanning(self, RootFolderPath: str, Recursive: bool = True) -> Dict[str, Any]:
    # Validate path
    if not RootFolderPath or not os.path.exists(RootFolderPath):
        return {'Success': False, 'Message': f'Root folder does not exist: {RootFolderPath}'}
    
    # Generate unique job ID
    JobId = str(uuid.uuid4())
    self.CurrentJobId = JobId
    
    # Create scan job record in database
    self.CreateScanJob(JobId, RootFolderPath, Recursive)
    
    # Start subprocess
    ProcessArgs = ['py', str(self.ScriptPath), JobId, str(Recursive)]
    env = os.environ.copy()
    env['MEDIAVORTEX_ROOT_FOLDER_PATH'] = RootFolderPath
    env['PYTHONIOENCODING'] = 'utf-8'
    
    self.ScanProcess = subprocess.Popen(ProcessArgs, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=Path(__file__).parent.parent, env=env)
    
    return {'Success': True, 'Message': 'Scan started successfully', 'JobId': JobId, 'ProcessId': self.ScanProcess.pid}
```

### 5. Subprocess Script
**File**: `Scripts/ScanDirectoryProcess.py`

**Entry Point**: `main()` function
```python
# Lines 279-318: main function
def main():
    JobId = sys.argv[1]
    Recursive = len(sys.argv) > 2 and sys.argv[2].lower() == 'true'
    RootFolderPath = os.environ.get('MEDIAVORTEX_ROOT_FOLDER_PATH')
    
    Scanner = ScanDirectoryProcess(JobId, RootFolderPath, Recursive)
    Scanner.Run()  # Calls ScanDirectory()
```

**Main Logic**: `ScanDirectory()` method (REFACTORED)
```python
# Lines 136-270: ScanDirectory method
def ScanDirectory(self):
    # Get or create root folder
    RootFolderId = self.GetOrCreateRootFolder(self.RootFolderPath)
    
    # Scan directory for files
    Files = self.FileManagerService.ScanDirectory(self.RootFolderPath, self.Recursive)
    
    # *** USE BUSINESS SERVICE FOR ALL FILE PROCESSING ***
    # Set up business service with scan results
    self.FileScanningBusinessService.ScanResults = ScanResults
    self.FileScanningBusinessService.ScanProgress = 0.0
    
    # Process files with metadata extraction and cleanup
    self.FileScanningBusinessService.ProcessMediaFilesWithMetadata(Files, RootFolderId, self.RootFolderPath, ExtractMetadata=True)
    
    # Update scan results from business service
    ScanResults = self.FileScanningBusinessService.ScanResults
    
    # Update root folder size
    TotalSizeGB = self.FileManagerService.CalculateDirectorySize(self.RootFolderPath)
    
    # Mark as completed
    ScanResults.ScanStatus = 'Completed'
```

### 6. Business Service File Processing (REFACTORED)
**File**: `Services/FileScanningBusinessService.py`

**Method**: `ProcessMediaFilesWithMetadata()` - Main orchestration method
```python
# Lines 1113-1146: ProcessMediaFilesWithMetadata method
def ProcessMediaFilesWithMetadata(self, MediaFiles: List[str], RootFolderId: Optional[int], RootFolderPath: str = "", ExtractMetadata: bool = True):
    """Process media files with optional metadata extraction."""
    try:
        LoggingService.LogFunctionEntry("ProcessMediaFilesWithMetadata", 'FileScanningBusinessService', f"Processing {len(MediaFiles)} files, ExtractMetadata: {ExtractMetadata}")
        
        # *** CLEANUP MISSING FILES FIRST ***
        if RootFolderId:
            LoggingService.LogInfo("=== CALLING CLEANUP MISSING FILES ===")
            LoggingService.LogInfo("RootFolderId: {}, MediaFiles count: {}", RootFolderId, len(MediaFiles))
            self.CleanupMissingFiles(MediaFiles, RootFolderId)
            LoggingService.LogInfo("=== CLEANUP MISSING FILES CALL COMPLETED ===")
            # Clean up orphaned files (files on disk without database records)
            self.CleanupOrphanedFiles(RootFolderId)
        else:
            LoggingService.LogWarning("No RootFolderId provided - skipping cleanup")
        
        # Process each file with advanced logic
        for i, FilePath in enumerate(MediaFiles):
            # Update progress
            Progress = 30.0 + (60.0 * (i + 1) / TotalFiles)
            self.ScanProgress = Progress
            
            # Process the file with metadata extraction
            self.ProcessSingleMediaFile(FilePath, RootFolderId, RootFolderPath, ExtractMetadata)
        
        # Find and report duplicate files after processing
        if RootFolderId:
            DuplicateGroups = self.FindDuplicateMediaFiles(RootFolderId)
            if DuplicateGroups:
                LoggingService.LogInfo("Found {} duplicate file groups during scan", len(DuplicateGroups))
                
    except Exception as e:
        LoggingService.LogException("Error processing media files with metadata", e, 'FileScanningBusinessService', 'ProcessMediaFilesWithMetadata')
        raise
```

**Method**: `CleanupMissingFiles()` - Database cleanup
```python
# Lines 687-744: CleanupMissingFiles method
def CleanupMissingFiles(self, FoundFiles: List[str], RootFolderId: int):
    """Remove database records for files that no longer exist on disk."""
    try:
        LoggingService.LogInfo("=== CLEANUP MISSING FILES STARTED ===")
        
        # Get root folder path
        RootFolder = self.DatabaseManager.GetRootFolderById(RootFolderId)
        if not RootFolder:
            LoggingService.LogError("Root folder not found for ID: {}", RootFolderId)
            return
        
        # Get all files in database for this root folder path
        DatabaseFiles = self.DatabaseManager.GetMediaFilesByRootFolder(RootFolder.Path)
        
        # Check each database file to see if it actually exists on disk
        DeletedCount = 0
        for DbFile in DatabaseFiles:
            if not os.path.exists(DbFile.FilePath):
                LoggingService.LogInfo("FILE NOT FOUND ON DISK - DELETING FROM DATABASE: {}", DbFile.FilePath)
                
                # Delete directly using the database service
                DeleteQuery = "DELETE FROM MediaFiles WHERE Id = ?"
                AffectedRows = self.DatabaseManager.DatabaseService.ExecuteNonQuery(DeleteQuery, (DbFile.Id,))
                
                if AffectedRows > 0:
                    LoggingService.LogInfo("SUCCESS: Deleted missing file from database: {} (ID: {})", DbFile.FilePath, DbFile.Id)
                    DeletedCount += 1
        
        LoggingService.LogInfo("=== CLEANUP MISSING FILES COMPLETED ===")
        if DeletedCount > 0:
            LoggingService.LogInfo("SUCCESS: Cleaned up {} missing files from database", DeletedCount)
        else:
            LoggingService.LogInfo("No missing files found to clean up")
            
    except Exception as e:
        LoggingService.LogException("CRITICAL ERROR in CleanupMissingFiles: {}", e)
```

**Method**: `ProcessSingleMediaFile()` - Advanced file processing
```python
# Lines 616-700+: ProcessSingleMediaFile method
def ProcessSingleMediaFile(self, FilePath: str, RootFolderId: Optional[int], RootFolderPath: str = "", ExtractMetadata: bool = True):
    """Process a single media file with fuzzy matching and optional metadata extraction."""
    try:
        # Get file information
        FileSizeMB = self.FileManager.GetFileSizeMB(FilePath)
        FileName = self.FileManager.GetFileNameFromPath(FilePath)
        
        # Extract season information and get/create season
        SeasonName = self.ExtractSeasonFromPath(FilePath, RootFolderPath)
        Season = self.GetOrCreateSeason(SeasonName, RootFolderId)
        
        # Check if this file already exists in database (exact match)
        ExistingFile = self.DatabaseManager.GetMediaFileByPath(FilePath)
        if ExistingFile:
            # Update existing file with new information
            # Extract metadata if requested and not already present
            if ExtractMetadata and self.ShouldExtractMetadata(ExistingFile):
                self.ExtractAndUpdateMetadata(ExistingFile, FilePath)
        else:
            # Check for fuzzy match (renamed file)
            FuzzyMatch = self.FindFuzzyFileMatch(FilePath, FileName, FileSizeMB, RootFolderId)
            if FuzzyMatch:
                # Found a fuzzy match - this is likely a renamed file
                # Update the fuzzy match with new path and information
            else:
                # Create new file record with full metadata extraction
                
    except Exception as e:
        LoggingService.LogException("Error processing single media file", e, 'FileScanningBusinessService', 'ProcessSingleMediaFile')
```

### 7. Database Layer
**File**: `Repositories/DatabaseManager.py`

**Method**: `GetMediaFilesByRootFolder()`
```python
# Method that retrieves all media files for a given root folder path
def GetMediaFilesByRootFolder(self, RootFolderPath: str) -> List[MediaFileModel]:
    Query = "SELECT * FROM MediaFiles WHERE FilePath LIKE ?"
    Results = self.DatabaseService.ExecuteQuery(Query, (f"{RootFolderPath}%",))
    return [MediaFileModel(**row) for row in Results]
```

**Database Service**: `Services/DatabaseService.py`
```python
# ExecuteNonQuery method for DELETE operations
def ExecuteNonQuery(self, Query: str, Parameters: tuple = None) -> int:
    # Executes DELETE FROM MediaFiles WHERE Id = ? with the file ID
    # Returns number of affected rows
```

## Key Files and Methods Involved (REFACTORED)

### UI Layer
- `Templates/FileScanning.html` - Lines 312, 342-375
  - `StartScan()` function
  - AJAX call to `/api/Scan/Start`

### Controller Layer
- `Controllers/FileScanningController.py` - Lines 18-41
  - `StartScan()` endpoint
  - Calls ViewModel

### ViewModel Layer
- `ViewModels/FileScanningViewModel.py` - Lines 31-62
  - `StartScanning()` method
  - Calls Business Service

### Business Service Layer (PRIMARY BUSINESS LOGIC)
- `Services/FileScanningBusinessService.py`
  - `StartScanning()` - Lines 49-137 (starts subprocess)
  - `ProcessMediaFilesWithMetadata()` - Lines 1113-1146 (main orchestration)
  - `CleanupMissingFiles()` - Lines 687-744 (deletes missing files)
  - `ProcessSingleMediaFile()` - Lines 616-700+ (advanced file processing)
  - `CleanupOrphanedFiles()` - Removes files on disk without DB records
  - `FindDuplicateMediaFiles()` - Detects duplicate files

### Subprocess Script (ORCHESTRATION ONLY)
- `Scripts/ScanDirectoryProcess.py`
  - `main()` - Lines 279-318 (entry point)
  - `ScanDirectory()` - Lines 136-270 (orchestration logic)
  - `GetOrCreateRootFolder()` - Lines 107-132 (root folder management)
  - **REMOVED**: `ProcessFile()` - No longer needed (business logic moved to business service)

### Database Layer
- `Repositories/DatabaseManager.py`
  - `GetMediaFilesByRootFolder()` - Retrieves files by path
  - `GetRootFolderById()` - Gets root folder info
- `Services/DatabaseService.py`
  - `ExecuteNonQuery()` - Executes DELETE statements

## Critical Points for File Deletion (REFACTORED)

### 1. When Cleanup is Called (OPTIMIZED)
- **Primary Location**: `FileScanningBusinessService.ProcessMediaFilesWithMetadata()` - Line 1122
- **Timing**: **BEFORE** file processing to prevent FFprobe errors on missing files
- **Integration**: Fully integrated into business service workflow

### 2. Database Query Used
```sql
-- Gets all files in the root folder path (including orphaned records)
SELECT * FROM MediaFiles WHERE FilePath LIKE ?

-- Deletes specific file by ID
DELETE FROM MediaFiles WHERE Id = ?
```

### 3. File Existence Check
```python
# Uses os.path.exists() to check if file actually exists on disk
if not os.path.exists(DbFile.FilePath):
    # Delete from database
```

### 4. Logging for Debugging
The cleanup process includes extensive logging:
- `"=== CLEANUP MISSING FILES STARTED ==="`
- `"=== CALLING CLEANUP MISSING FILES ==="`
- `"FILE NOT FOUND ON DISK - DELETING FROM DATABASE: {}"`
- `"SUCCESS: Deleted missing file from database: {} (ID: {})"`
- `"=== CLEANUP MISSING FILES COMPLETED ==="`

## Architectural Improvements (REFACTORED)

### ✅ Single Responsibility Principle
- **Subprocess**: Only handles orchestration and job management
- **Business Service**: Handles all file processing and cleanup logic
- **Database Service**: Handles data persistence
- **File Manager**: Handles file system operations

### ✅ MVVM Compliance
- **View**: HTML/JavaScript (UI only)
- **ViewModel**: State management and coordination
- **Model**: Business logic in `FileScanningBusinessService`
- **Controller**: REST API endpoints

### ✅ No Code Duplication
- **Removed**: Duplicate `ProcessFile()` method from subprocess
- **Single Source**: All file processing uses `ProcessSingleMediaFile()`
- **Consistent**: Same advanced logic everywhere (fuzzy matching, metadata, cleanup)

### ✅ Optimal Cleanup Timing
- **Before Processing**: Cleanup happens before FFprobe analysis
- **Prevents Errors**: No more FFprobe errors on missing files
- **Integrated**: Part of the main business service workflow

## New Flow Summary

1. **UI Click** → Controller → ViewModel → Business Service
2. **Business Service** → Starts subprocess with job ID
3. **Subprocess** → Scans files → **Calls business service workflow**
4. **Business Service** → **Cleanup FIRST** → Process files with metadata → Report duplicates
5. **Subprocess** → Updates progress → Completes

## Testing the Refactored Flow

To verify the cleanup is working:

1. **Check Logs**: Look for the detailed logging messages from business service
2. **Database Verification**: Check that orphaned records are removed
3. **File System Check**: Ensure only existing files remain in database
4. **No FFprobe Errors**: Missing files should be cleaned up before FFprobe runs

The refactored flow ensures proper MVVM architecture, single responsibility, and optimal cleanup timing while maintaining all advanced features like fuzzy matching, metadata extraction, and comprehensive error handling.
