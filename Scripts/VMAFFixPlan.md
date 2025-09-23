# VMAF Process Fix Plan

## **Issue Analysis**
- **VMAF Score Calculation**: ✅ Working (91.37 score calculated successfully)
- **VMAF Score Saving**: ❌ Failing due to missing database method
- **File Management**: ❌ Not triggered due to failed score saving
- **Frontend Display**: ❌ API errors preventing UI updates

## **Root Cause**
The `GetTranscodeAttemptById` method in `DatabaseManager` uses non-existent `ExecuteQuerySingle` method.

## **Fix Implementation Plan**

### **1. DatabaseManager Fix**
**File**: `Repositories/DatabaseManager.py`
**Method**: `GetTranscodeAttemptById`
**Issue**: Uses `ExecuteQuerySingle` which doesn't exist
**Fix**: Use `ExecuteQuery` and handle single result

```python
# BEFORE (Broken)
row = self.DatabaseService.ExecuteQuerySingle(query, (AttemptId,))

# AFTER (Fixed)
rows = self.DatabaseService.ExecuteQuery(query, (AttemptId,))
row = rows[0] if rows else None
```

### **2. VMAFQueueBusinessService Enhancement**
**File**: `Services/VMAFQueueBusinessService.py`
**Method**: `ProcessVMAFJob`
**Enhancement**: Add better error handling and logging

```python
# Add try-catch around TranscodeAttempt update
try:
    transcodeAttempt = self.DatabaseManager.GetTranscodeAttemptById(VMAFQueueItem.TranscodeAttemptId)
    if transcodeAttempt:
        transcodeAttempt.VMAF = VMAFResult.OverallVMAFScore
        self.DatabaseManager.SaveTranscodeAttempt(transcodeAttempt)
        LoggingService.LogInfo(f"Updated TranscodeAttempt {transcodeAttempt.Id} with VMAF score {VMAFResult.OverallVMAFScore:.2f}")
    else:
        LoggingService.LogError(f"TranscodeAttempt {VMAFQueueItem.TranscodeAttemptId} not found")
except Exception as e:
    LoggingService.LogException(f"Failed to update TranscodeAttempt with VMAF score", e)
```

### **3. VMAFJobController Fix**
**File**: `Controllers/VMAFJobController.py`
**Method**: `GetVMAFStatus`
**Issue**: Returns HTML instead of JSON on errors
**Fix**: Ensure consistent JSON responses

```python
# Add proper error handling
try:
    # Existing logic
    return jsonify({
        "Success": True,
        "IsProcessing": SharedVMAFService.IsRunning,
        "CurrentVMAFJob": currentJob,
        "QueueStatistics": queueStats
    })
except Exception as e:
    LoggingService.LogException("Error in GetVMAFStatus", e)
    return jsonify({
        "Success": False,
        "ErrorMessage": str(e),
        "IsProcessing": False,
        "CurrentVMAFJob": None,
        "QueueStatistics": {"TotalJobs": 0, "PendingJobs": 0, "RunningJobs": 0, "CompletedJobs": 0, "FailedJobs": 0}
    })
```

### **4. Database Service Enhancement**
**File**: `Services/DatabaseService.py`
**Enhancement**: Add `ExecuteQuerySingle` method for consistency

```python
def ExecuteQuerySingle(self, query: str, parameters: tuple = ()) -> Optional[Dict[str, Any]]:
    """Execute query and return single result or None."""
    rows = self.ExecuteQuery(query, parameters)
    return rows[0] if rows else None
```

## **Testing Plan**

### **Phase 1: Database Fix**
1. Fix `GetTranscodeAttemptById` method
2. Test with existing VMAF queue item
3. Verify VMAF score gets saved to TranscodeAttempts

### **Phase 2: VMAF Process Test**
1. Clear VMAF queues
2. Start new transcode job
3. Monitor VMAF process from start to finish
4. Verify complete workflow: Transcode → VMAF → File Management

### **Phase 3: Frontend Fix**
1. Fix VMAF Status API errors
2. Test UI updates during VMAF processing
3. Verify progress tracking works

## **Expected Results**
- ✅ VMAF scores properly saved to TranscodeAttempts table
- ✅ File management triggered for high-quality files (VMAF > 90)
- ✅ **High Quality**: Delete original from T:\, move transcoded from C:\MediaVortex\ to T:\
- ✅ **Low Quality**: Delete transcoded from C:\MediaVortex\, keep original on T:\
- ✅ Frontend displays VMAF progress correctly
- ✅ Complete workflow: Transcode → VMAF → File Operations

## **Files to Modify**
1. `Repositories/DatabaseManager.py` - Fix GetTranscodeAttemptById
2. `Services/VMAFQueueBusinessService.py` - Enhance error handling
3. `Controllers/VMAFJobController.py` - Fix API responses
4. `Services/DatabaseService.py` - Add ExecuteQuerySingle method

## **Priority Order**
1. **High**: DatabaseManager.GetTranscodeAttemptById fix
2. **High**: VMAFQueueBusinessService error handling
3. **Medium**: VMAFJobController API fixes
4. **Low**: DatabaseService.ExecuteQuerySingle addition
