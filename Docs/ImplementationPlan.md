# FFmpeg Progress Monitoring Implementation Plan

## Overview
Implement real-time FFmpeg progress monitoring and VMAF quality comparison in the MediaVortex transcoding application.

## Current Status
✅ **FFmpeg Execution**: Working with proper progress output
✅ **VMAF Comparison**: Working — full QualityTestService microservice implemented
✅ **Two-Pass Encoding**: Working with proper pass detection
✅ **Progress Data Format**: Working — frame, fps, bitrate, time captured in TranscodeProgress table

## Implementation Tasks

### Phase 0: Critical Fix - Two-Pass Transcoding ✅ COMPLETE
**Priority: Critical**

#### 0.1 Replace Single-Pass with Two-Pass
- [x] Two-pass transcoding implemented and confirmed working
- [x] Pass 1: Analysis pass, Pass 2: Encoding pass
- [x] Progress reading works across both passes

### Phase 1: FFmpeg Progress Capture ✅ COMPLETE
**Priority: High**

#### 1.1 Replace Progress Callback System
- [x] Replaced complex threading/callback with direct stdout reading
- [x] Progress lines parsed with simple `Line.startswith("frame=")`
- [x] Every FFmpeg progress update creates new `TranscodeProgress` record

#### 1.2 Enhance Progress Data Capture
- [x] TranscodeProgress table stores frame, FPS, bitrate, ETA
- [x] FFmpeg output parsed for all progress fields
- [x] Real-time progress tracking operational

#### 1.3 Two-Pass Transcoding
- [x] Merged with Phase 0 — two-pass working

### Phase 2: VMAF Quality Integration ✅ COMPLETE
**Priority: Medium**

#### 2.1 VMAF Service Creation
- [x] Full QualityTestService microservice implemented (`QualityTestService/Main.py`)
- [x] VMAF comparison runs via dedicated queue (`QualityTestQueue` table)
- [x] VMAF scores parsed and stored in `QualityTestResults` table
- [x] Results linked to `TranscodeAttempts` with preferred attempt marking

#### 2.2 VMAF UI Integration
- [x] Quality test history viewable with pagination
- [x] Quality test progress tracking in Activity page
- [x] Service control (start/stop/pause/resume) from UI

#### 2.3 VMAF Configuration
- [x] Quality thresholds configurable per profile
- [x] `ShouldQualityTestService` determines when testing is needed
- [x] Pause/resume/graceful stop controls implemented

### Phase 3: Enhanced Progress Monitoring
**Priority: Medium**

#### 3.1 Real-Time Progress Updates
- [ ] **WebSocket Integration**: Push progress updates to UI in real-time
- [ ] **Progress Bar**: Visual progress bar with percentage
- [ ] **ETA Calculation**: Estimate time remaining based on current speed
- [ ] **Files**: `Templates/TranscodeProgress.html`, `Static/js/`

#### 3.2 Progress Analytics
- [ ] **Speed Tracking**: Monitor encoding speed over time
- [ ] **Quality vs Speed**: Track relationship between preset and quality
- [ ] **Performance Metrics**: Average encoding times per resolution
- [ ] **Files**: `Services/AnalyticsService.py` (new)

#### 3.3 Error Handling
- [ ] **FFmpeg Error Detection**: Parse FFmpeg error messages
- [ ] **Progress Recovery**: Resume from last known good state
- [ ] **Error Reporting**: Detailed error messages in UI
- [ ] **Files**: `Services/FFmpegService.py`, `Services/TranscodingBusinessService.py`

### Phase 4: Advanced Features
**Priority: Low**

#### 4.1 Multi-Resolution VMAF
- [ ] **Multiple Comparisons**: Compare against multiple source resolutions
- [ ] **Quality Matrix**: Show quality scores for different target resolutions
- [ ] **Optimal Resolution**: Suggest best resolution based on VMAF scores
- [ ] **Files**: `Services/FFmpegVMAFService.py`

#### 4.2 Batch VMAF Processing
- [ ] **Queue Integration**: Add VMAF jobs to processing queue
- [ ] **Parallel Processing**: Run VMAF comparisons in background
- [ ] **Batch Results**: Aggregate VMAF scores for multiple files
- [ ] **Files**: `Services/QueueManagementBusinessService.py`

#### 4.3 Quality Optimization
- [ ] **Auto-Tuning**: Automatically adjust CRF based on VMAF scores
- [ ] **Preset Selection**: Choose optimal preset based on quality requirements
- [ ] **Bitrate Optimization**: Adjust bitrate to achieve target VMAF score
- [ ] **Files**: `Services/QualityOptimizationService.py` (new)

## Technical Requirements

### Database Schema Updates
```sql
-- Add VMAF score to TranscodeAttempts
ALTER TABLE TranscodeAttempts ADD COLUMN VMAFScore REAL;

-- Add progress fields to TranscodeProgress
ALTER TABLE TranscodeProgress ADD COLUMN CurrentFrame INTEGER;
ALTER TABLE TranscodeProgress ADD COLUMN CurrentFPS REAL;
ALTER TABLE TranscodeProgress ADD COLUMN CurrentBitrate INTEGER;
ALTER TABLE TranscodeProgress ADD COLUMN CurrentTime TEXT;
```

### New Services
- `Services/FFmpegVMAFService.py` - VMAF quality comparison
- `Services/AnalyticsService.py` - Performance analytics
- `Services/QualityOptimizationService.py` - Quality optimization

### New Models
- `Models/VMAFResultModel.py` - VMAF comparison results
- `Models/ProgressAnalyticsModel.py` - Progress analytics data

## Testing Strategy

### Unit Tests
- [ ] FFmpeg progress parsing
- [ ] VMAF score extraction
- [ ] Two-pass detection
- [ ] Progress callback chain

### Integration Tests
- [ ] End-to-end transcoding with progress
- [ ] VMAF comparison workflow
- [ ] Database progress storage
- [ ] UI progress updates

### Performance Tests
- [ ] Progress update frequency
- [ ] Database write performance
- [ ] VMAF processing time
- [ ] Memory usage during transcoding

## Success Criteria

### Phase 1 Success
- [ ] Every FFmpeg progress update creates database record
- [ ] Progress data includes frame, fps, bitrate, time
- [ ] Two-pass encoding properly detected and tracked
- [ ] UI shows real-time progress updates

### Phase 2 Success
- [ ] VMAF comparison runs automatically after transcoding
- [ ] VMAF scores displayed in UI
- [ ] Quality assessment shown (Excellent, Very Good, etc.)
- [ ] VMAF results stored in database

### Phase 3 Success
- [ ] Real-time progress updates via WebSocket
- [ ] Accurate ETA calculations
- [ ] Comprehensive error handling
- [ ] Performance analytics dashboard

### Phase 4 Success
- [ ] Multi-resolution quality comparison
- [ ] Automated quality optimization
- [ ] Batch VMAF processing
- [ ] Quality-based preset selection

## Risk Mitigation

### Technical Risks
- **FFmpeg Output Parsing**: Robust regex patterns for progress data
- **Database Performance**: Indexed queries for progress data
- **VMAF Processing Time**: Background processing with progress indicators
- **Memory Usage**: Streaming progress data, not buffering

### User Experience Risks
- **Progress Accuracy**: Handle FFmpeg output variations
- **UI Responsiveness**: Non-blocking progress updates
- **Error Recovery**: Clear error messages and recovery options
- **Performance Impact**: Minimal overhead on transcoding speed

## Timeline Estimate

- **Phase 1**: 1-2 weeks (Critical path - using proven TestFfmpeg.py approach)
- **Phase 2**: 1-2 weeks (using proven TestFfmpegVMAFComparison.py approach)
- **Phase 3**: 2-3 weeks
- **Phase 4**: 3-4 weeks

**Total Estimated Time**: 7-11 weeks (reduced due to proven working code)

## Dependencies

### External Dependencies
- FFmpeg with VMAF support
- WebSocket support in web framework
- JSON parsing for VMAF results

### Internal Dependencies
- Database schema updates
- UI framework updates
- Service architecture modifications
- Testing framework setup

## Notes

- VMAF processing is CPU-intensive and should run in background
- Progress updates should be throttled to avoid database overload
- Two-pass encoding requires careful progress tracking across passes
- Quality optimization may require multiple transcoding attempts
- Consider caching VMAF results for identical source/target combinations