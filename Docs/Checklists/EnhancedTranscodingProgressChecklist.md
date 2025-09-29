# Enhanced Transcoding Progress Tracking - Implementation Checklist

## Overview
Add step-by-step progress tracking to the transcoding workflow so users can see exactly what's happening during each phase of the process.

## Progress Phases
1. **"Initializing"** - Job started, getting ready
2. **"Loading Media Data"** - Retrieving MediaFile information  
3. **"Loading Settings"** - Retrieving transcoding profile and codec settings
4. **"Building Command"** - Generating FFmpeg command
5. **"Preparing Files"** - Setting up directories, copying source file
6. **"Starting Transcode"** - About to begin actual transcoding
7. **"Transcoding"** - The actual video processing with precise frame-based progress
8. **"Finalizing"** - Processing results, cleanup, moving files

## Implementation Checklist

### Phase 1: Create Progress Helper Method
**File:** `Services/ProcessTranscodeQueueService.py`

- [ ] Add `UpdateTranscodeProgress()` helper method
  - [ ] Parameters: TranscodeAttemptId, CurrentPhase, ProgressPercent (default 0.0), AdditionalInfo (optional)
  - [ ] Call DatabaseManager.SaveTranscodeProgress() with appropriate values
  - [ ] Log phase changes for debugging

### Phase 2: Update ProcessJob Workflow
**File:** `Services/ProcessTranscodeQueueService.py`

- [ ] Move `CreateTranscodeAttempt()` to start of ProcessJob method (before step a)
- [ ] Add progress tracking after each step:
  - [ ] "Initializing" - After job start, before any processing
  - [ ] "Loading Media Data" - After GetMediaFileData() success
  - [ ] "Loading Settings" - After GetTranscodingSettings() success  
  - [ ] "Building Command" - After BuildTranscodeCommand() success
  - [ ] "Preparing Files" - After SetupFilePreparation() success
  - [ ] "Starting Transcode" - Before ExecuteTranscoding() call
  - [ ] "Finalizing" - After HandleTranscodingResult() success

### Phase 3: Update ExecuteTranscoding Method
**File:** `Services/ProcessTranscodeQueueService.py`

- [ ] Modify `ExecuteTranscoding()` method signature to accept MediaFile parameter
- [ ] Pass MediaFile.TotalFrames to VideoTranscoding.TranscodeVideo()
- [ ] Use MediaFile.TotalFrames in initial progress record instead of 0
- [ ] Update call to ExecuteTranscoding() in ProcessJob to pass MediaFile

### Phase 4: Update VideoTranscodingService
**File:** `Services/VideoTranscodingService.py`

- [ ] Modify `TranscodeVideo()` method signature to accept TotalFramesFromMediaFile parameter
- [ ] Set `self._TotalFrameCount = TotalFramesFromMediaFile` if provided (> 0)
- [ ] Update `ParseProgressLine()` to prioritize MediaFile TotalFrames over FFmpeg extraction
- [ ] Add logging when using TotalFrames from MediaFile

### Phase 5: Update ProcessJob Call
**File:** `Services/ProcessTranscodeQueueService.py`

- [ ] Update the call to ExecuteTranscoding() in ProcessJob method
- [ ] Pass MediaFile parameter: `ExecuteTranscoding(Job, TranscodeCommand, TranscodeAttemptId, MediaFile)`

### Phase 6: Test Implementation
**Test Scenarios:**

- [ ] **Phase Display Test**
  - [ ] Verify all 8 phases display in correct order
  - [ ] Verify non-transcoding phases show ProgressPercent = 0
  - [ ] Verify phases flash briefly then move to next phase

- [ ] **Transcoding Progress Test**
  - [ ] Verify "Transcoding" phase shows precise frame-based progress
  - [ ] Verify ProgressPercent = (CurrentFrame / TotalFrames) * 100
  - [ ] Verify ETA calculation works correctly
  - [ ] Verify TotalFrames from MediaFile is used (not FFmpeg extraction)

- [ ] **Error Handling Test**
  - [ ] Verify progress tracking continues if individual steps fail
  - [ ] Verify appropriate error messages are shown
  - [ ] Verify progress cleanup on job failure

### Phase 7: UI Enhancement (Optional)
**File:** `Templates/TranscodeProgress.html`

- [ ] Update `updateActivityProgressDisplay()` method
- [ ] Add phase-specific styling for different progress types
- [ ] Improve phase display formatting
- [ ] Add phase transition animations (optional)

## Progress Percentage Rules

**Non-Transcoding Phases (1-6, 8):**
- ProgressPercent = 0
- Show phase name only
- Flash on screen briefly

**Transcoding Phase (7):**
- ProgressPercent = (CurrentFrame / TotalFrames) * 100
- Show detailed frame progress, FPS, ETA
- Use TotalFrames from MediaFile (preferred over FFmpeg extraction)

## Files Modified Summary

1. **Services/ProcessTranscodeQueueService.py**
   - Add UpdateTranscodeProgress() helper method
   - Modify ProcessJob() workflow
   - Modify ExecuteTranscoding() method
   - Update method calls

2. **Services/VideoTranscodingService.py**
   - Modify TranscodeVideo() method signature
   - Update ParseProgressLine() logic

3. **Templates/TranscodeProgress.html** (Optional)
   - Enhance UI display for better phase visualization

## Success Criteria

- [ ] Users can see exactly what step the transcoding process is on
- [ ] Transcoding phase shows precise, frame-based progress
- [ ] Non-transcoding phases show current activity without fake percentages
- [ ] TotalFrames from MediaFile is used for accurate progress calculation
- [ ] Progress tracking works reliably through all phases
- [ ] Error handling maintains progress visibility

## Notes

- Keep existing TranscodeProgress table structure
- Maintain backward compatibility with existing progress display
- Focus on user experience - clear, accurate progress information
- Ensure performance is not impacted by additional progress updates
