<!-- 39bf6d98-db8f-45ed-997c-5b45ee04c8f7 0ee3beaf-23c3-4942-80da-bfc8f37582fc -->
# Skip File Copy and Fix Progress Messages

## Changes Required

### 1. Skip File Copy if Already Exists

**File**: `Services/TranscodingFileManagerService.py`

- Modify `CopyFile()` method (lines 38-57)
- Add check if destination file already exists before copying
- If file exists, log info message and return True (skip copy)
- This prevents redundant copies during testing when source file is already in place

### 2. Fix Progress Message Timing

**File**: `Services/ProcessTranscodeQueueService.py`

- Move progress updates to BEFORE the operations they describe (lines 274-344)
- Current issue: "Building Command" shows AFTER command is built
- Fix: Show progress message BEFORE each operation starts
- Update sequence:
  - Show "Loading Media Data" BEFORE GetMediaFileData()
  - Show "Loading Settings" BEFORE GetTranscodingSettings()
  - Show "Building Command" BEFORE BuildTranscodeCommand()
  - Show "Preparing Files" BEFORE SetupFilePreparation()
  - Show "Starting Transcode" BEFORE ExecuteTranscoding()

## Implementation Details

**TranscodingFileManagerService.CopyFile()** changes:

```python
def CopyFile(self, SourcePath: str, DestinationPath: str) -> bool:
    # Check if file already exists
    if os.path.exists(DestinationPath):
        LoggingService.LogInfo(f"File already exists at destination, skipping copy: {DestinationPath}")
        return True
    
    # Existing copy logic...
```

**ProcessTranscodeQueueService.ProcessSingleJob()** changes:

- Move each `UpdateTranscodeProgress()` call to immediately BEFORE its corresponding operation
- Update messages to use present tense ("Loading..." instead of "Retrieved...")

### To-dos

- [ ] Add file existence check in TranscodingFileManagerService.CopyFile() to skip copy if file already exists
- [ ] Move all UpdateTranscodeProgress() calls in ProcessTranscodeQueueService.ProcessSingleJob() to before their operations
- [ ] Update progress messages to use present tense to reflect they show before operations start