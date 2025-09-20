# Research: Video Queue Transcoding

## Video Transcoding Library Selection

### Decision: Switch from HandBrake CLI to FFmpeg with Python bindings
**Rationale**: 
- FFmpeg provides better Python integration through ffmpeg-python library
- More mature and widely used in production environments
- Better error handling and progress tracking capabilities
- No external HandBrake dependency required
- Quality control (CRF) works similarly to HandBrake quality settings
- More active development and community support

**Alternatives considered**:
- HandBrake CLI with subprocess: External dependency, limited Python integration
- MoviePy: Good for simple operations but limited transcoding capabilities
- OpenCV: Excellent for analysis but limited transcoding features
- GStreamer: Powerful but complex setup and steep learning curve

### Quality Setting Implementation
**Decision**: Use FFmpeg CRF (Constant Rate Factor) for quality control
**Rationale**:
- CRF provides same quality control as HandBrake quality setting
- Scale: CRF 18 (visually lossless) to CRF 30 (poor quality)
- HandBrake quality 22 ≈ FFmpeg CRF 23 (good quality default)
- More precise control over encoding parameters
- Industry standard for H.264/H.265 encoding

**Quality Scale Conversion**:
```python
def ConvertHandBrakeQualityToFFmpegCRF(HandBrakeQuality: int) -> int:
    if HandBrakeQuality <= 18: return 18      # Visually lossless
    elif HandBrakeQuality <= 20: return 20    # High quality
    elif HandBrakeQuality <= 22: return 23    # Good quality (default)
    elif HandBrakeQuality <= 24: return 26    # Lower quality
    else: return 30                           # Poor quality
```

## File Size-Based Queue Prioritization

### Decision: Sort TranscodeQueue by SizeMB DESC, then by DateAdded ASC
**Rationale**:
- Largest files processed first maximizes storage space recovery
- Secondary sort by date ensures FIFO within same size groups
- Database query can efficiently handle this ordering
- Aligns with user requirement for largest file priority

**Alternatives considered**:
- Simple FIFO: Doesn't optimize for storage space recovery
- Random processing: No predictable behavior
- User-defined priority: Adds complexity without clear benefit

## FFmpeg Integration Patterns

### Decision: Use ffmpeg-python library with proper error handling
**Rationale**:
- ffmpeg-python provides native Python bindings for FFmpeg
- Better integration than subprocess calls to external binaries
- Real-time progress monitoring and output capture
- Exception handling for encoding failures
- Supports timeout handling for long-running operations

**Implementation Pattern**:
```python
import ffmpeg

def TranscodeWithFFmpeg(InputPath: str, OutputPath: str, Quality: int, Resolution: str):
    CRF = ConvertHandBrakeQualityToFFmpegCRF(Quality)
    
    stream = ffmpeg.input(InputPath)
    stream = ffmpeg.output(
        stream, 
        OutputPath,
        vcodec='libx264',
        crf=CRF,
        preset='medium',
        s=Resolution
    )
    ffmpeg.run(stream, overwrite_output=True)
```

**Alternatives considered**:
- Subprocess calls to FFmpeg: Less Python integration, harder error handling
- Direct FFmpeg binary execution: No progress tracking or error handling
- External wrapper scripts: Adds complexity and maintenance overhead

## Database Transaction Management

### Decision: Use database transactions with proper rollback handling
**Rationale**:
- Transcoding operations involve multiple database updates
- Atomic operations ensure data consistency
- Rollback capability handles partial failures
- Existing database schema supports transaction patterns

**Alternatives considered**:
- No transactions: Risk of inconsistent state
- File-based locking: Doesn't integrate with existing database patterns
- External state management: Adds complexity

## Error Handling and Recovery Patterns

### Decision: Comprehensive error logging with graceful failure handling
**Rationale**:
- FFmpeg operations can fail for various reasons (codec issues, file corruption, etc.)
- Detailed error logging aids in troubleshooting
- Graceful failure prevents system crashes
- Database logging provides audit trail
- ffmpeg-python provides better exception handling than subprocess

**Alternatives considered**:
- Silent failures: No visibility into problems
- Automatic retry: Can cause infinite loops
- Crash on error: Poor user experience

## File Management Patterns

### Decision: Copy-then-replace pattern with temporary directory
**Rationale**:
- Preserves original files during transcoding
- Temporary directory isolates transcoding operations
- Atomic replacement ensures consistency
- Follows user specification for c:\handbraketemp structure

**Alternatives considered**:
- In-place transcoding: Risk of data loss
- Backup-then-replace: Unnecessary complexity
- Move-then-transcode: Risk of file loss

## Progress Tracking Implementation

### Decision: Database-based progress tracking with periodic updates
**Rationale**:
- FFmpeg provides detailed progress output through ffmpeg-python
- Database storage enables persistence across restarts
- Periodic updates balance performance and accuracy
- Integrates with existing logging infrastructure
- ffmpeg-python allows real-time progress monitoring

**Implementation**:
```python
def TranscodeWithProgress(InputPath: str, OutputPath: str, ProgressCallback):
    stream = ffmpeg.input(InputPath)
    stream = ffmpeg.output(stream, OutputPath, vcodec='libx264', crf=23)
    
    # FFmpeg progress can be captured and processed
    ffmpeg.run(stream, overwrite_output=True, 
               progress=ProgressCallback)
```

**Alternatives considered**:
- File-based progress: Not persistent across restarts
- Real-time updates: Performance overhead
- No progress tracking: Poor user experience

## Resolution Categorization System

### Decision: Implement smart resolution categorization for profile matching
**Rationale**:
- Exact resolutions (e.g., "1280x720", "1172x720") need to match standardized profile categories (e.g., "720p")
- Non-standard resolutions between categories need intelligent classification
- Maintain exact resolution for aspect ratio calculations during transcoding
- Enable proper profile matching for all video files

**Implementation**:
```python
def CategorizeResolution(Width: int, Height: int) -> str:
    """Categorize exact resolution into standard categories with smart edge case handling."""
    TotalPixels = Width * Height
    
    # 4K and above
    if TotalPixels >= 3840 * 2160:
        return "2160p"
    
    # 1080p range (including non-standard like 1920x800)
    elif TotalPixels >= 1920 * 1080 * 0.8:  # 80% of standard 1080p
        return "1080p"
    
    # 720p range (including non-standard like 1172x720)
    elif TotalPixels >= 1280 * 720 * 0.8:  # 80% of standard 720p
        return "720p"
    
    # 480p range
    elif TotalPixels >= 854 * 480 * 0.8:  # 80% of standard 480p
        return "480p"
    
    # Below 480p
    else:
        return "360p"
```

**Edge Case Examples**:
- "1024x576" → "720p" (closer to 720p than 480p)
- "1172x720" → "720p" (non-standard 720p)
- "1920x800" → "1080p" (1080p with different aspect ratio)
- "3840x1600" → "2160p" (4K with different aspect ratio)

**Alternatives considered**:
- Exact resolution matching: Fails for non-standard resolutions
- Fixed category boundaries: Doesn't handle edge cases
- Manual categorization: Not scalable

## Resolution-Based File Naming

### Decision: Dynamic filename generation based on transcoding resolution
**Rationale**:
- User specified resolution-based naming (e.g., 1080p → 720p)
- Maintains file organization and clarity
- Prevents filename conflicts
- Follows user requirements for resolution indication

**Alternatives considered**:
- Keep original filename: Doesn't indicate resolution change
- Timestamp-based naming: Unclear and confusing
- Hash-based naming: No human-readable information
