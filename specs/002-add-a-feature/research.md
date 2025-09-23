# Research: Video Queue Transcoding

## Video Transcoding Library Selection

### Decision: Use FFmpeg for transcoding and VMAF analysis
**Rationale**: 
- FFmpeg provides excellent transcoding capabilities with both CRF and multi-pass options
- FFmpeg used for VMAF quality analysis (libvmaf filter)
- Single tool for both transcoding and analysis reduces complexity
- Better Python integration and error handling
- More mature and widely used in production environments

**CRITICAL HANDLING RULE - CRF vs Multi-Pass Incompatibility**:
- **CRF (Constant Rate Factor) and multi-pass are INCOMPATIBLE in FFmpeg**
- CRF is single-pass quality-based encoding
- Multi-pass is for bitrate-based encoding
- **NEVER use both -crf and -b:v in the same command**
- **Single-pass: Use -crf for quality-based encoding**
- **Multi-pass: Use -b:v for bitrate-based encoding**

**Alternatives considered**:
- HandBrake CLI with subprocess: External dependency, limited Python integration
- MoviePy: Good for simple operations but limited transcoding capabilities
- OpenCV: Excellent for analysis but limited transcoding features
- GStreamer: Powerful but complex setup and steep learning curve

### Quality Setting Implementation
**Decision**: Use FFmpeg CRF (Constant Rate Factor) for single-pass quality control
**Rationale**:
- CRF provides precise quality control for single-pass encoding
- Scale: CRF 18 (visually lossless) to CRF 30 (poor quality)
- CRF 22-25: Good quality range (default)
- More precise control over encoding parameters
- Industry standard for H.264/H.265 encoding

**CRITICAL**: CRF is single-pass encoding - do NOT use with multi-pass parameters

**Quality Scale**:
- CRF 18-20: Visually lossless to high quality
- CRF 22-25: Good quality (default range)
- CRF 26-30: Lower quality to poor quality

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

## VMAF Quality Analysis Implementation

### Decision: Use FFmpeg libvmaf filter for perceptual quality scoring
**Rationale**:
- VMAF (Video Multi-Method Assessment Fusion) provides industry-standard perceptual quality metrics
- FFmpeg libvmaf filter integrates seamlessly with existing FFmpeg pipeline
- Provides objective quality scores (0-100) for transcoded video comparison
- Enables automated quality validation and optimization

**Working Command Structure**:
```bash
ffmpeg -i "transcoded.mkv" -i "source.avi" -lavfi "[0:v]scale=1280x720,format=yuv420p[dist];[1:v]scale=1280x720,format=yuv420p[ref];[dist][ref]libvmaf=log_path=vmaf_results.json:log_fmt=json" -f null -
```

**Key Implementation Details**:
- **Input order**: Transcoded file first, source file second
- **Scaling**: Both inputs scaled to identical resolution (1280x720) for fair comparison
- **Format conversion**: Both inputs converted to yuv420p for consistent processing
- **Output**: JSON log file with detailed VMAF metrics
- **Performance**: ~1.5x real-time processing speed

**VMAF Score Interpretation**:
- **90-100**: Excellent quality, imperceptible differences
- **80-90**: High quality, minimal perceptible differences  
- **70-80**: Good quality, some differences noticeable
- **60-70**: Fair quality, differences clearly visible
- **<60**: Poor quality, significant degradation

**Test Results**:
- **Sample VMAF Score**: 90.793227 (excellent quality)
- **Processing Speed**: 1.52x real-time
- **Frame Processing**: 45 fps vs 30 fps video
- **Total Frames**: 41,923 frames processed successfully

**Implementation Requirements**:
- Parse JSON output for VMAF score extraction
- Handle VMAF processing failures gracefully
- Store VMAF scores in TranscodeAttempt table
- Separate VMAF analysis from transcoding success/failure
- Consider separate QualityVMAF queue for parallel processing

**Alternatives considered**:
- PSNR/SSIM: Less accurate perceptual quality metrics
- Manual quality assessment: Not scalable or objective
- No quality analysis: No validation of transcoding results
