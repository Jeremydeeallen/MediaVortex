# MediaVortex - Large-Scale File Scanning Optimization Guide

## 📊 Problem Statement

**Current System**: Scanning 50,000-150,000 media files
**Current Approach**: Full scan of all files every scan cycle
**Problem**: Extremely inefficient - takes hours to scan files that haven't changed

## 🎯 Optimization Strategies

### 1. ⚡ Incremental Scanning (CRITICAL - Highest Impact)

**Problem**: Currently scans ALL files every time, even if 99% haven't changed

**Solution**: Only process files that changed since last scan

```python
# Add to MediaFiles table
LastModifiedDate DATETIME  # From filesystem mtime
LastScannedDate DATETIME   # When we last checked this file

# Scanning logic
def ShouldProcessFile(file_path, db_record):
    filesystem_mtime = os.path.getmtime(file_path)
    db_mtime = db_record.LastModifiedDate

    # Only process if file is newer than what we have in DB
    return filesystem_mtime > db_mtime
```

**Expected Impact**:
- **Before**: Scan 150,000 files = 2-4 hours
- **After**: Scan ~100 changed files = 2-5 minutes
- **Speedup**: 50-100x faster!

**Implementation**:
1. Add `LastModifiedDate` and `LastScannedDate` columns to MediaFiles table
2. In `ProcessSingleMediaFile()`, check modification time before processing
3. Skip ffprobe metadata extraction for unchanged files
4. Only update database records that actually changed

---

### 2. 📁 Directory-Level Change Detection (HIGH Impact)

**Problem**: Walking entire directory tree is slow (os.walk on 150k files)

**Solution**: Track directory modification times

```python
# New table: DirectoryCache
CREATE TABLE DirectoryCache (
    DirectoryPath TEXT PRIMARY KEY,
    LastModifiedDate DATETIME,
    FileCount INTEGER,
    LastScannedDate DATETIME
)

# Before scanning a directory
def ShouldScanDirectory(dir_path):
    dir_mtime = os.path.getmtime(dir_path)
    cached = GetDirectoryCache(dir_path)

    if not cached:
        return True  # Never scanned before

    # Skip if directory hasn't changed
    return dir_mtime > cached.LastModifiedDate
```

**Expected Impact**:
- Skip entire directory branches that haven't changed
- Reduces I/O operations significantly
- 20-30x reduction in directories scanned

---

### 3. 🚀 Smart Metadata Extraction (MEDIUM-HIGH Impact)

**Problem**: `ffprobe` is expensive - takes 0.5-2 seconds per file

**Current Behavior**: Extract metadata for every file, every scan

**Solution**: Only extract when needed

```python
def ProcessSingleMediaFile(file_path, db_record):
    # Quick checks first (milliseconds)
    filesystem_mtime = os.path.getmtime(file_path)

    if db_record and db_record.LastModifiedDate >= filesystem_mtime:
        # File unchanged, skip everything
        return {'Skipped': True}

    # File changed or new - update basic info
    UpdateBasicFileInfo(file_path, db_record)

    # Only extract metadata if:
    # 1. File is new (no db_record)
    # 2. File size changed
    # 3. Metadata is missing/incomplete
    if ShouldExtractMetadata(file_path, db_record):
        ExtractAndSaveMetadata(file_path)

    return {'Processed': True}
```

**Expected Impact**:
- Before: 150,000 files × 1 sec = 41 hours
- After: 100 changed files × 1 sec = 100 seconds
- **Speedup**: 1,000x+ for metadata extraction

---

### 4. 💾 Batch Database Operations (MEDIUM Impact)

**Problem**: Committing to database after every file is slow

**Solution**: Batch operations

```python
# Instead of:
for file in files:
    ProcessFile(file)
    db.commit()  # 150,000 commits!

# Do this:
batch = []
for file in files:
    result = ProcessFile(file)
    batch.append(result)

    if len(batch) >= 100:
        db.execute_many(batch)
        db.commit()
        batch = []

# Commit remaining
if batch:
    db.execute_many(batch)
    db.commit()
```

**Expected Impact**:
- 100x fewer database commits
- Reduces scan time by 20-30%

---

### 5. 🔍 Database Indexing (MEDIUM Impact)

**Problem**: Slow lookups when checking if file exists

**Solution**: Add strategic indexes

```sql
-- Critical indexes for file scanning
CREATE INDEX IF NOT EXISTS idx_mediafiles_filepath
    ON MediaFiles(FilePath);

CREATE INDEX IF NOT EXISTS idx_mediafiles_lastmodified
    ON MediaFiles(LastModifiedDate);

CREATE INDEX IF NOT EXISTS idx_mediafiles_filename
    ON MediaFiles(FileName);

CREATE INDEX IF NOT EXISTS idx_mediafiles_rootfolder
    ON MediaFiles(RootFolderId);

-- For transcoded file matching
CREATE INDEX IF NOT EXISTS idx_mediafiles_basefilename
    ON MediaFiles(FileName COLLATE NOCASE);
```

**Expected Impact**:
- File lookups: 1000ms → 1-5ms
- 200x faster database queries

---

### 6. ⏱️ Smart Scheduling (LOW-MEDIUM Impact)

**Problem**: Scanning during peak usage affects system performance

**Solution**: Adaptive scheduling

```python
class SmartScheduler:
    def ShouldRunScan(self):
        # Check system load
        cpu_usage = psutil.cpu_percent(interval=1)
        if cpu_usage > 80:
            self.delay_scan(minutes=15)
            return False

        # Check disk I/O
        disk_io = psutil.disk_io_counters()
        if disk_io.busy_time_percent > 70:
            self.delay_scan(minutes=10)
            return False

        return True

    def GetOptimalScanInterval(self):
        # More frequent scans during low-activity hours
        hour = datetime.now().hour
        if 2 <= hour < 6:  # Night time
            return 30  # Scan every 30 minutes
        else:
            return 60  # Scan every hour
```

---

### 7. 📊 Scan Statistics & Monitoring (Important for UX)

**What to Track**:

```python
class ScanStatistics:
    TotalFilesScanned: int      # Files checked (quick stat check)
    FilesProcessed: int         # Files fully processed
    FilesChanged: int           # Files that changed
    FilesAdded: int            # New files discovered
    FilesRemoved: int          # Files no longer exist
    FilesSkipped: int          # Unchanged files skipped
    MetadataExtracted: int     # Files with new metadata
    Duration: timedelta        # How long scan took

    # Efficiency metrics
    SkipRate: float            # % of files skipped (higher = better)
    ProcessingRate: float      # Files/second
```

**Display in UI**:
- Show real-time progress with meaningful numbers
- "Scanned 50,000 files, 127 changed (99.7% skipped)"
- "Scan completed in 3m 42s (average: 222 files/sec)"

---

## 📈 Expected Performance Improvements

### Scenario 1: Typical Day (Few Changes)
**Files**: 150,000 total, 50 changed (0.03%)

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Files Scanned | 150,000 | 150,000 | Same |
| Files Processed | 150,000 | 50 | 3,000x |
| Metadata Extracted | 150,000 | 50 | 3,000x |
| Database Operations | 150,000 | 50 | 3,000x |
| **Total Time** | **2-4 hours** | **3-5 minutes** | **50x faster** |

### Scenario 2: After Bulk Changes
**Files**: 150,000 total, 5,000 changed (3.3%)

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Files Processed | 150,000 | 5,000 | 30x |
| **Total Time** | **2-4 hours** | **15-20 minutes** | **8x faster** |

### Scenario 3: Initial Full Scan
**Files**: 150,000 total, ALL new

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Files Processed | 150,000 | 150,000 | Same |
| **Total Time** | **2-4 hours** | **1.5-2 hours** | **2x faster** |
*Improvement from batching and indexing only*

---

## 🛠️ Implementation Priority

### Phase 1: Quick Wins (Implement First)
1. ✅ **Database Indexes** (10 minutes)
   - Immediate 10-20x query speedup

2. ✅ **Batch Database Operations** (30 minutes)
   - 20-30% overall speedup

3. ✅ **Skip Unchanged Files** (2 hours)
   - Add LastModifiedDate column
   - Check mtime before processing
   - **50-100x speedup for typical scans**

### Phase 2: Major Optimizations (Implement Next)
4. 📁 **Directory-Level Change Detection** (4 hours)
   - Create DirectoryCache table
   - Skip unchanged directories
   - **Additional 10-20x speedup**

5. 🚀 **Smart Metadata Extraction** (2 hours)
   - Only run ffprobe when needed
   - **1,000x speedup for metadata**

### Phase 3: Advanced Features (Later)
6. ⏱️ **Smart Scheduling** (3 hours)
   - Adaptive intervals
   - System load monitoring

7. 👀 **File System Watchers** (1-2 days, advanced)
   - Real-time change detection
   - Ultimate optimization but complex

---

## 💡 Code Examples

### Incremental Scanning Implementation

```python
# FileScanningBusinessService.py

def ProcessSingleMediaFile(self, FilePath: str, ...) -> Dict[str, Any]:
    """Process a single media file with incremental scanning."""

    # Get filesystem metadata (FAST - no ffprobe yet)
    try:
        file_stats = os.stat(FilePath)
        filesystem_mtime = datetime.fromtimestamp(file_stats.st_mtime)
        file_size = file_stats.st_size
    except Exception as e:
        return {'Success': False, 'Error': str(e)}

    # Check if file exists in database
    db_record = self.DatabaseManager.GetMediaFileByPath(FilePath)

    if db_record:
        # File exists in database - check if it changed
        if (db_record.LastModifiedDate and
            db_record.LastModifiedDate >= filesystem_mtime and
            db_record.FileSize == file_size):

            # File unchanged - SKIP PROCESSING
            return {
                'Success': True,
                'Skipped': True,
                'Reason': 'File unchanged since last scan'
            }

    # File is new or changed - process it
    LoggingService.LogInfo(f"Processing {'new' if not db_record else 'changed'} file: {FilePath}")

    # Extract metadata (expensive operation)
    metadata = self.ExtractMetadata(FilePath)

    # Update or create database record
    if db_record:
        self.DatabaseManager.UpdateMediaFile(db_record.Id, {
            'LastModifiedDate': filesystem_mtime,
            'FileSize': file_size,
            'LastScannedDate': datetime.now(),
            **metadata
        })
    else:
        self.DatabaseManager.CreateMediaFile({
            'FilePath': FilePath,
            'LastModifiedDate': filesystem_mtime,
            'FileSize': file_size,
            'LastScannedDate': datetime.now(),
            **metadata
        })

    return {
        'Success': True,
        'Processed': True,
        'IsNew': db_record is None
    }
```

---

## 📋 Database Schema Changes

```sql
-- Add to MediaFiles table
ALTER TABLE MediaFiles ADD COLUMN LastModifiedDate DATETIME;
ALTER TABLE MediaFiles ADD COLUMN LastScannedDate DATETIME;
ALTER TABLE MediaFiles ADD COLUMN FileSize INTEGER;

-- Update existing records with current timestamp
UPDATE MediaFiles
SET LastScannedDate = datetime('now'),
    LastModifiedDate = datetime('now')
WHERE LastScannedDate IS NULL;

-- New table for directory caching
CREATE TABLE IF NOT EXISTS DirectoryCache (
    Id INTEGER PRIMARY KEY AUTOINCREMENT,
    DirectoryPath TEXT UNIQUE NOT NULL,
    LastModifiedDate DATETIME,
    FileCount INTEGER DEFAULT 0,
    LastScannedDate DATETIME,
    Created DATETIME DEFAULT (datetime('now', 'localtime'))
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_dircache_path ON DirectoryCache(DirectoryPath);
CREATE INDEX IF NOT EXISTS idx_dircache_modified ON DirectoryCache(LastModifiedDate);
```

---

## 🎯 Success Metrics

After implementing optimizations, you should see:

✅ **Scan Time**: 2-4 hours → 3-10 minutes (typical day)
✅ **CPU Usage**: 80-100% → 10-30% during scans
✅ **Disk I/O**: Heavy → Light (90% reduction)
✅ **Database Size Growth**: Same (no bloat)
✅ **Skip Rate**: 0% → 99%+ on typical scans
✅ **User Experience**: "Scans take forever" → "Scans are instant"

---

## 🔧 Monitoring & Debugging

Add logging to track efficiency:

```python
LoggingService.LogInfo(f"""
Scan Statistics:
- Total files checked: {total_files}
- Files skipped (unchanged): {skipped_files} ({skip_rate:.1f}%)
- Files processed: {processed_files}
- Files changed: {changed_files}
- Files added: {new_files}
- Files removed: {removed_files}
- Metadata extracted: {metadata_extracted}
- Duration: {duration}
- Processing rate: {files_per_second:.1f} files/sec
""")
```

---

## ⚠️ Important Notes

1. **First Scan After Implementation**: Will be SLOW (all files need LastModifiedDate populated)
2. **Subsequent Scans**: Will be FAST (50-100x faster)
3. **Backup Database**: Before adding new columns/tables
4. **Test on Small Dataset First**: Verify logic before full deployment
5. **Monitor Initial Rollout**: Watch logs for any issues

---

## 🚀 Next Steps

1. Add database columns for incremental scanning
2. Implement modification time checking
3. Add batch database operations
4. Create database indexes
5. Update UI to show skip statistics
6. Monitor performance improvements
7. Iterate and optimize further

**Target Goal**: Reduce typical scan time from hours to minutes while maintaining accuracy.
