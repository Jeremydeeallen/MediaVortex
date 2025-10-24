# Case Sensitivity Problem and Solution

## The Problem

### Root Cause
`Services/FileScanningBusinessService.py` line 482 uses **case-sensitive string comparison**:
```python
if Folder.RootFolder == RootFolderPath:  # CASE-SENSITIVE!
```

### Impact
- Creates duplicate RootFolder entries (`Z:\videos\Couple` vs `z:\videos\couple`)
- Every MediaFile under duplicate RootFolders becomes a duplicate
- Potentially **thousands of duplicate MediaFiles** in database
- Transcode operations reference wrong records
- Queue shows duplicate files

### Current Database State
- **RootFolders**: Multiple duplicates on Z: drive (e.g., IDs 578, 580, 583 for same folder)
- **MediaFiles**: Unknown number of duplicates (not yet fully detected)
- **TranscodeAttempts**: 4 duplicates found
- **TemporaryFilePaths**: 4 duplicates found
- **Primary Issue**: Z: drive case sensitivity from manual typing during service setup

## The Solution: Filesystem Validation Approach

### 1. Get Canonical Paths from Filesystem
- Add `GetCanonicalPathFromFilesystem()` method to get actual case from disk
- Use `pathlib.Path.resolve()` to get the real filesystem path
- **Benefit**: Preserves original case, validates path exists, handles edge cases

### 2. Fix Case-Sensitive Comparison with Filesystem Validation
- Change line 482 in FileScanningBusinessService.py to use canonical path comparison
- Compare `GetCanonicalPathFromFilesystem(Folder.RootFolder) == GetCanonicalPathFromFilesystem(RootFolderPath)`
- **Benefit**: Prevents future duplicate RootFolders, validates against actual filesystem

### 3. Merge Existing Duplicates
- **Priority 1**: Keep transcoded files (TranscodedByMediaVortex = 1)
- **Priority 2**: Archive originals to MediaFilesArchive for learning
- **Priority 3**: Use fuzzy matching for files with different resolutions

### 4. Enhanced Detection and Merge Scripts
- Add RootFolders table to detection script
- Create merge logic that handles RootFolders first, then MediaFiles
- Preserve transcoded versions, archive originals

## Expected Results
- **RootFolders**: Z: drive duplicates merged → canonical folders with proper case
- **MediaFiles**: Thousands of duplicates merged → unique files only
- **Future scans**: No new duplicates created using filesystem validation
- **Learning data**: Originals preserved in MediaFilesArchive
- **User Experience**: Paths display with correct case as they exist on disk

## Implementation Phases

### Phase 0: Add Filesystem Validation Methods
- Create `GetCanonicalPathFromFilesystem()` method in FileScanningBusinessService
- Add error handling for filesystem access issues
- Ensures all new data uses canonical paths from filesystem

### Phase 1: Fix Root Cause with Filesystem Validation
- Update GetOrCreateRootFolder to use canonical path comparison
- Replace case-sensitive string comparison with filesystem validation
- Prevents creation of new duplicate RootFolders

### Phase 2: Add Database Lookup Method
- Create GetRootFolderByCanonicalPath with filesystem validation
- Replace in-memory loop with database query + filesystem validation
- Handle edge cases like network drives, symlinks

### Phase 3: Enhanced Detection
- Add RootFolders table to detection script
- Focus on Z: drive duplicates (primary issue)
- Reveal full scope of MediaFiles duplicates

### Phase 4: Smart Merge Logic
- Merge RootFolders first using canonical path matching
- Update MediaFiles to reference canonical RootFolders
- Prioritize transcoded files, archive originals
- Handle fuzzy matching for different resolutions

### Phase 5: Documentation and Validation
- Update DatabaseStandards.md with RootFolder guidelines
- Create validation test to prevent regressions
- Document filesystem validation approach

## Critical Execution Order
1. **Fix code first** - Implement filesystem validation to prevent new duplicates during cleanup
2. **Focus on Z: drive** - Primary issue is Z: drive case sensitivity from manual typing
3. **Merge RootFolders** - Foundation for everything else using canonical path matching
4. **Merge MediaFiles** - Apply smart merge logic
5. **Update references** - Fix TranscodeAttempts, etc.
6. **Validate results** - Ensure no data loss and paths display correctly

## Risk Mitigation
- Create database backups before any changes
- Use dry-run mode to preview all operations
- Generate rollback scripts for safety
- Test with small subset first
- Validate file existence and sizes during merge
- Test filesystem validation with network drives and edge cases
- Focus initial cleanup on Z: drive duplicates (known issue)
