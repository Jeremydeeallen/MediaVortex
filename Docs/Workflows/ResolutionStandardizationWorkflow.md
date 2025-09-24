# Resolution Standardization Workflow

## Overview
This workflow defines how MediaVortex handles the standardization of video resolutions for transcoding. The system processes over 1,350 different resolution formats and maps them to standard resolutions while maintaining aspect ratios and quality.

## Problem Statement
- **Database contains**: 1,353 distinct resolutions
- **Standard resolutions**: Only 1 (`1080p`)
- **Pixel format resolutions**: 1,352 (e.g., `1920x1080`, `1280x720`, `854x480`)
- **Challenge**: Map diverse resolutions to standard profiles while maintaining quality

## Core Principles
1. **Exact matches**: No changes needed for standard resolutions
2. **Round down**: Always round down to nearest standard height
3. **Maintain aspect ratio**: Adjust width proportionally
4. **Quality preservation**: Use closest standard resolution without upscaling

## Standard Resolution Targets
The system targets these standard resolutions:
- **480p**: 854x480 (SD)
- **720p**: 1280x720 (HD)
- **1080p**: 1920x1080 (Full HD)
- **2160p**: 3840x2160 (4K UHD)

## Resolution Standardization Logic

### Step 1: Exact Match Detection
```python
def IsExactMatch(Resolution: str) -> bool:
    """Check if resolution is already in standard format."""
    standard_resolutions = ['480p', '720p', '1080p', '2160p']
    return Resolution in standard_resolutions
```

**Examples:**
- ✅ `1080p` → No change needed
- ✅ `720p` → No change needed
- ❌ `1920x1080` → Needs standardization
- ❌ `1280x720` → Needs standardization

### Step 2: Height-Based Rounding Down
```python
def GetStandardHeight(SourceHeight: int) -> int:
    """Round down to nearest standard height."""
    if SourceHeight >= 2160:
        return 2160  # 4K
    elif SourceHeight >= 1080:
        return 1080  # Full HD
    elif SourceHeight >= 720:
        return 720   # HD
    elif SourceHeight >= 480:
        return 480   # SD
    else:
        return 480   # Default to SD for very low resolutions
```

### Step 2.5: Ultra-Wide/VR Detection (Skip)
```python
def IsUltraWideOrVR(Width: int, Height: int) -> bool:
    """Detect ultra-wide or VR formats that should be skipped."""
    aspect_ratio = Width / Height
    
    # Ultra-wide formats (21:9, 32:9, etc.)
    if aspect_ratio > 2.0:
        return True
    
    # VR formats (square or near-square)
    if 0.8 <= aspect_ratio <= 1.2 and (Width > 2000 or Height > 2000):
        return True
    
    return False
```

**Examples:**
- `1920x1080` → Height: 1080 → Standard: 1080
- `1920x1030` → Height: 1030 → Standard: 1080 (round down)
- `1280x800` → Height: 800 → Standard: 720 (round down)
- `854x480` → Height: 480 → Standard: 480

### Step 3: Aspect Ratio Preservation
```python
def CalculateStandardWidth(SourceWidth: int, SourceHeight: int, TargetHeight: int) -> int:
    """Calculate width to maintain aspect ratio."""
    aspect_ratio = SourceWidth / SourceHeight
    target_width = int(TargetHeight * aspect_ratio)
    
    # Ensure width is even (required for most codecs)
    if target_width % 2 != 0:
        target_width += 1
    
    return target_width
```

**Examples:**
- `1920x1080` (16:9) → `1920x1080` (no change)
- `1920x1030` (1.86:1) → `1920x1080` (maintains 1.86:1)
- `1280x800` (16:10) → `1152x720` (maintains 16:10)
- `854x480` (16:9) → `854x480` (no change)

### Step 4: Standard Resolution Mapping
```python
def MapToStandardResolution(Width: int, Height: int) -> str:
    """Map pixel dimensions to standard resolution name."""
    if Height == 2160:
        return "2160p"
    elif Height == 1080:
        return "1080p"
    elif Height == 720:
        return "720p"
    elif Height == 480:
        return "480p"
    else:
        return "480p"  # Default fallback
```

## Complete Standardization Process

### Input Processing
1. **Parse resolution string**: Extract width and height from formats like:
   - `1920x1080`
   - `1280x720`
   - `854x480`
   - `1080p` (already standard)

2. **Handle edge cases**:
   - Portrait videos: `1080x1920` → `720x1280` → `720p`
   - Mobile formats: `720x1280` → `480x854` → `480p`
   - Ultra-wide/VR: `2560x1080` → **SKIP** (excluded from transcoding)

### Standardization Examples

| Source Resolution | Source Aspect | Standard Height | Calculated Width | Standard Resolution | Profile Match |
|-------------------|---------------|-----------------|------------------|-------------------|---------------|
| `1920x1080` | 16:9 | 1080 | 1920 | `1080p` | ✅ Exact match |
| `1920x1030` | 1.86:1 | 1080 | 1920 | `1080p` | ✅ Uses 1080p profile |
| `1280x800` | 16:10 | 720 | 1152 | `720p` | ✅ Uses 720p profile |
| `854x480` | 16:9 | 480 | 854 | `480p` | ✅ Uses 480p profile |
| `1080x1920` | 9:16 | 720 | 384 | `720p` | ✅ Uses 720p profile |
| `720x1280` | 9:16 | 480 | 270 | `480p` | ✅ Uses 480p profile |
| `2560x1080` | 21:9 | **SKIP** | **SKIP** | **No transcoding** | ❌ VR/Ultra-wide - excluded |

## Implementation in ResolutionService

### Core Methods
```python
class ResolutionService:
    def StandardizeResolution(self, Resolution: str) -> str:
        """Main entry point for resolution standardization."""
        
    def ParseResolution(self, Resolution: str) -> Tuple[int, int]:
        """Extract width and height from resolution string."""
        
    def IsUltraWideOrVR(self, Width: int, Height: int) -> bool:
        """Detect ultra-wide or VR formats that should be skipped."""
        
    def GetStandardHeight(self, SourceHeight: int) -> int:
        """Round down to nearest standard height."""
        
    def CalculateStandardWidth(self, SourceWidth: int, SourceHeight: int, TargetHeight: int) -> int:
        """Calculate width maintaining aspect ratio."""
        
    def MapToStandardResolution(self, Width: int, Height: int) -> str:
        """Map dimensions to standard resolution name."""
```

### Integration Points
1. **TranscodingBusinessService**: Use standardized resolution for profile matching
2. **VMAFQueueBusinessService**: Use standardized resolution for KeepSource logic
3. **QueueManagementBusinessService**: Use standardized resolution for queue processing
4. **FileScanningBusinessService**: Use standardized resolution for profile assignment

## Quality Considerations

### Rounding Down Benefits
- **No upscaling**: Prevents quality degradation from upscaling
- **Consistent profiles**: All similar resolutions use same transcoding settings
- **Predictable output**: Standard resolutions ensure consistent results

### Aspect Ratio Preservation
- **Maintains visual integrity**: Videos don't appear stretched or distorted
- **Codec compatibility**: Even widths required for most video codecs
- **User experience**: Preserves original video proportions

## Error Handling

### Invalid Resolutions
- **Malformed strings**: `"invalid"` → Default to `480p`
- **Zero dimensions**: `"0x0"` → Default to `480p`
- **Missing data**: `None` or `""` → Default to `480p`

### Edge Cases
- **Very low resolutions**: `< 480p` → Round up to `480p`
- **Very high resolutions**: `> 2160p` → Round down to `2160p`
- **Unusual aspect ratios**: Handle gracefully with proportional scaling

## Testing Strategy

### Unit Tests
- Test all standard resolution mappings
- Test aspect ratio preservation
- Test edge cases and error conditions
- Test performance with large resolution lists

### Integration Tests
- Test with real MediaFiles database
- Test transcoding pipeline integration
- Test profile matching accuracy
- Test VMAF queue processing

## Performance Considerations

### Caching
- **Cache standardized resolutions**: Avoid repeated calculations
- **Database optimization**: Index resolution lookups
- **Memory management**: Handle large resolution datasets efficiently

### Batch Processing
- **Bulk standardization**: Process multiple resolutions at once
- **Background processing**: Standardize resolutions during file scanning
- **Incremental updates**: Only process new/changed resolutions

## Future Enhancements

### Advanced Features
- **Custom resolution profiles**: Support for non-standard target resolutions
- **Quality-based mapping**: Consider source quality when standardizing
- **User preferences**: Allow custom resolution mapping rules
- **Analytics**: Track resolution distribution and standardization patterns

### VR Support
- **360° video handling**: Special logic for VR resolutions
- **Stereoscopic formats**: Support for 3D video resolutions
- **VR profile matching**: Dedicated VR transcoding profiles

## Conclusion

This workflow provides a robust, scalable solution for handling the diverse resolution landscape in MediaVortex. By standardizing resolutions while preserving aspect ratios and quality, the system ensures consistent transcoding results across all media types.

The approach balances simplicity (round down to standard heights) with quality preservation (maintain aspect ratios), making it suitable for the wide variety of source materials while ensuring predictable, high-quality output.
