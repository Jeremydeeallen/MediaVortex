# File Scanning Implementation Checklist

## Overview
Implement file scanning functionality to scan base directories, calculate directory sizes, and manage MediaFiles table entries following MVVM architecture.

## Database Tables Involved
- **RootFolders**: Store base directory information and sizes
- **MediaFiles**: Store individual file information with metadata
- **Seasons**: Organize files by season/folder structure

## MVVM Architecture Components

### Models (Data Layer)
- **RootFolderModel**: Represents a base directory with size information
- **MediaFileModel**: Represents individual media files with metadata
- **SeasonModel**: Represents season/folder organization
- **FileScanResultModel**: Represents scan operation results

### Business Services (Business Logic)
- **FileScanningBusinessService**: Orchestrates the entire scanning process
- **FileManagerService**: Handles file system operations and metadata extraction

### Repository Layer (Data Access)
- **DatabaseManager**: Extend existing with RootFolder and MediaFile operations

### ViewModels (Presentation Logic)
- **FileScanningViewModel**: Manages scanning UI state and operations

### Controllers (API Layer)
- **FileScanningController**: Provides REST API endpoints for scanning operations

### Views (UI Layer)
- **FileScanning.html**: Web interface for scanning operations

## Implementation Approach: Basic File Discovery Slice First

Start with a minimal working slice to prove core functionality and Unicode character handling, then build the complete feature.

### Slice Goals:
- Scan directories and discover media files
- Handle Unicode characters robustly (Cyrillic, emojis, special symbols)
- Store basic file information in database
- Provide simple web interface for scanning
- Track progress and handle errors

## Implementation Checklist

### Phase 1: Basic Slice - Models and Data Structures
- [x] Create `Models/RootFolderModel.py` - Basic directory information (RootFolder, LastScannedDate, TotalSizeGB) MVVM pattern using MVVM architecture
- [x] Create `Models/MediaFileModel.py` - Basic file information (FilePath, FileName, SizeMB, LastScannedDate) MVVM pattern using MVVM architecture
- [x] Ensure only PascalCase was used

### Phase 2: Basic Slice - Repository Layer Extensions
- [x] Extend `Repositories/DatabaseManager.py` with basic RootFolder operations (GetAllRootFolders, SaveRootFolder) MVVM pattern using MVVM architecture
- [x] Extend `Repositories/DatabaseManager.py` with basic MediaFile operations (GetAllMediaFiles, SaveMediaFile, DeleteMediaFile) MVVM pattern using MVVM architecture
- [x] Ensure only PascalCase was used

### Phase 3: Basic Slice - Utility Services
- [x] Create `Services/FileManagerService.py` - Basic file system operations, directory traversal, file discovery with Unicode character support MVVM pattern using MVVM architecture
- [x] Implement Unicode character validation and sanitization in FileManagerService MVVM pattern using MVVM architecture
- [x] Add error handling for problematic characters (Cyrillic, emojis, special symbols) MVVM pattern using MVVM architecture
- [x] Ensure only PascalCase was used

### Phase 4: Basic Slice - Business Services
- [x] Create `Services/FileScanningBusinessService.py` - Orchestrate basic scanning process, coordinate between FileManagerService and DatabaseManager MVVM pattern using MVVM architecture
- [x] Implement directory scanning logic with size calculation and Unicode path handling MVVM pattern using MVVM architecture
- [x] Implement basic file discovery (no metadata extraction) with robust character encoding support MVVM pattern using MVVM architecture
- [x] Implement database synchronization (Insert, Delete) with proper UTF-8 encoding MVVM pattern using MVVM architecture
- [x] Add fallback mechanisms for files with problematic Unicode characters MVVM pattern using MVVM architecture
- [x] Ensure only PascalCase was used

### Phase 5: Basic Slice - ViewModels
- [x] Create `ViewModels/FileScanningViewModel.py` - Manage basic scanning UI state, progress tracking, error handling with Unicode character support MVVM pattern using MVVM architecture
- [x] Implement scanning progress tracking with Unicode filename display MVVM pattern using MVVM architecture
- [x] Implement basic scan result management with proper character encoding for web display MVVM pattern using MVVM architecture
- [x] Add error reporting for files with problematic Unicode characters MVVM pattern using MVVM architecture
- [x] Ensure only PascalCase was used

### Phase 6: Basic Slice - Controllers
- [x] Create `Controllers/FileScanningController.py` - Basic REST API endpoints for scanning operations with Unicode character support MVVM pattern using MVVM architecture
- [x] Implement `/api/Scan/Start` endpoint to initiate scanning with proper UTF-8 encoding MVVM pattern using MVVM architecture
- [x] Implement `/api/Scan/Status` endpoint to check scan progress with Unicode filename reporting MVVM pattern using MVVM architecture
- [x] Implement `/api/Scan/Stop` endpoint to stop scanning MVVM pattern using MVVM architecture
- [x] Implement `/api/RootFolders` endpoints for basic root folder management with Unicode path support MVVM pattern using MVVM architecture
- [x] Implement `/api/MediaFiles` endpoints for basic media file management with proper character encoding MVVM pattern using MVVM architecture
- [x] Add error handling for API requests with problematic Unicode characters MVVM pattern using MVVM architecture
- [x] Ensure only PascalCase was used

### Phase 7: Basic Slice - Views
- [x] Create `Templates/FileScanning.html` - Basic web interface for scanning operations with proper UTF-8 encoding MVVM pattern using MVVM architecture
- [x] Implement root folder selection interface with Unicode path support MVVM pattern using MVVM architecture
- [x] Implement scanning progress display with Unicode filename rendering MVVM pattern using MVVM architecture
- [x] Implement basic scan results display with proper character encoding for international filenames MVVM pattern using MVVM architecture
- [x] Add error display for files with problematic Unicode characters MVVM pattern using MVVM architecture
- [x] Ensure only PascalCase was used

### Phase 8: Basic Slice - Integration
- [x] Update `MediaVortex.py` to register FileScanningController with UTF-8 encoding support MVVM pattern using MVVM architecture
- [x] Add navigation route for file scanning page MVVM pattern using MVVM architecture
- [x] Test end-to-end basic scanning functionality with Unicode character support MVVM pattern using MVVM architecture
- [x] Test with problematic filenames (Cyrillic, emojis, special symbols) MVVM pattern using MVVM architecture
- [x] Ensure only PascalCase was used

### Phase 8.5: Subprocess Implementation - Process Management
- [x] Create database table for scan job state tracking MVVM pattern using MVVM architecture
- [x] Create separate scan script for subprocess execution MVVM pattern using MVVM architecture
- [x] Implement subprocess management in FileScanningBusinessService MVVM pattern using MVVM architecture
- [x] Add PID tracking and process monitoring MVVM pattern using MVVM architecture
- [x] Update status endpoints to read from database instead of memory MVVM pattern using MVVM architecture
- [x] Implement proper process cleanup and error handling MVVM pattern using MVVM architecture
- [x] Ensure only PascalCase was used

### Phase 9: Complete Feature - Additional Models
- [ ] Create `Models/SeasonModel.py` - Simple data class for season organization MVVM pattern using MVVM architecture
- [ ] Create `Models/FileScanResultModel.py` - Simple data class for scan operation results MVVM pattern using MVVM architecture
- [ ] Extend `Models/MediaFileModel.py` - Add metadata fields (VideoBitrateKbps, AudioBitrateKbps, Resolution, Codec, DurationMinutes, FrameRate, CompressionPotential, AssignedProfile) MVVM pattern using MVVM architecture
- [ ] Ensure only PascalCase was used

### Phase 10: Complete Feature - Extended Repository Layer
- [ ] Extend `Repositories/DatabaseManager.py` with Season operations (GetAllSeasons, SaveSeason, DeleteSeason, GetSeasonsByRootFolder) MVVM pattern using MVVM architecture
- [ ] Extend `Repositories/DatabaseManager.py` with advanced MediaFile operations (UpdateMediaFile, GetMediaFilesByRootFolder) MVVM pattern using MVVM architecture
- [ ] Ensure only PascalCase was used

### Phase 11: Complete Feature - Additional Utility Services
- [ ] Create `Services/MediaAnalysisService.py` - Analyze media files for codec, bitrate, resolution, duration with robust Unicode filename handling MVVM pattern using MVVM architecture
- [ ] Extend `Services/FileManagerService.py` - Add metadata extraction capabilities MVVM pattern using MVVM architecture
- [ ] Ensure only PascalCase was used

### Phase 12: Complete Feature - Enhanced Business Services
- [ ] Extend `Services/FileScanningBusinessService.py` - Add metadata extraction coordination MVVM pattern using MVVM architecture
- [ ] Implement advanced database synchronization (Update existing files) MVVM pattern using MVVM architecture
- [ ] Add season organization logic MVVM pattern using MVVM architecture
- [ ] Ensure only PascalCase was used

### Phase 13: Complete Feature - Enhanced ViewModels
- [ ] Extend `ViewModels/FileScanningViewModel.py` - Add metadata display and management MVVM pattern using MVVM architecture
- [ ] Add season organization features MVVM pattern using MVVM architecture
- [ ] Add advanced filtering and search capabilities MVVM pattern using MVVM architecture
- [ ] Ensure only PascalCase was used

### Phase 14: Complete Feature - Enhanced Controllers
- [ ] Extend `Controllers/FileScanningController.py` - Add advanced API endpoints for metadata and seasons MVVM pattern using MVVM architecture
- [ ] Add bulk operations endpoints MVVM pattern using MVVM architecture
- [ ] Add export functionality endpoints MVVM pattern using MVVM architecture
- [ ] Ensure only PascalCase was used

### Phase 15: Complete Feature - Enhanced Views
- [ ] Extend `Templates/FileScanning.html` - Add metadata display and management interface MVVM pattern using MVVM architecture
- [ ] Add season organization interface MVVM pattern using MVVM architecture
- [ ] Add advanced filtering and search interface MVVM pattern using MVVM architecture
- [ ] Add export functionality interface MVVM pattern using MVVM architecture
- [ ] Ensure only PascalCase was used

### Phase 16: Complete Feature - Final Integration
- [ ] Test complete end-to-end functionality with all features MVVM pattern using MVVM architecture
- [ ] Performance testing with large file collections MVVM pattern using MVVM architecture
- [ ] Final Unicode character testing with all features MVVM pattern using MVVM architecture
- [ ] Ensure only PascalCase was used

## File Structure (Complete Feature)
```
MediaVortex/
├── Models/
│   ├── RootFolderModel.py
│   ├── MediaFileModel.py
│   ├── SeasonModel.py
│   └── FileScanResultModel.py
├── Services/
│   ├── FileManagerService.py
│   ├── MediaAnalysisService.py
│   └── FileScanningBusinessService.py
├── ViewModels/
│   └── FileScanningViewModel.py
├── Controllers/
│   └── FileScanningController.py
└── Templates/
    └── FileScanning.html
```

## Key Features (Complete Feature)
1. **Directory Size Calculation**: Calculate and store total size of root directories
2. **File Discovery**: Recursively scan directories for media files
3. **Metadata Extraction**: Extract video/audio codec, bitrate, resolution, duration
4. **Database Synchronization**: Insert new files, Update existing, Delete missing files
5. **Progress Tracking**: Real-time scanning progress updates
6. **Error Handling**: Handle file access errors and invalid media files
7. **Unicode Character Support**: Robust handling of international characters, emojis, Cyrillic, and special symbols
8. **Season Organization**: Organize files by season/folder structure
9. **Advanced Filtering**: Filter files by metadata, size, codec, etc.
10. **Export Functionality**: Export scan results and statistics

## Testing Requirements (Complete Feature)
- Test directory scanning with various folder structures
- Test file metadata extraction for different media formats
- Test database synchronization accuracy
- Test progress tracking and error handling
- Test API endpoints functionality
- Test web interface usability
- **Test Unicode character support with problematic filenames:**
  - Cyrillic characters: "HOMЯ", "Русский фильм"
  - Emojis: "🎬 Action Film", " Comedy Show"
  - International characters: "Français", "Español", "中文"
  - Special symbols: "Mathematical ∑ symbols", "Currency € symbols"
  - Mixed character sets: "The Simpsons - S12E09 - HOMЯ SDTV"
- Test fallback mechanisms for files with encoding issues
- Test cross-platform compatibility with Unicode paths
- Test database storage and retrieval of Unicode filenames
- Test web interface display of international characters
- Test season organization functionality
- Test metadata extraction accuracy
- Test advanced filtering and search capabilities
- Test export functionality
