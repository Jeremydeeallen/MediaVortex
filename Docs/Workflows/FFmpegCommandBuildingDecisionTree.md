# FFmpeg Command Building Decision Tree

This document provides a visual decision tree for the FFmpeg command building process.

## Decision Tree Flow

```
Start: BuildFFmpegCommand
│
├─ Get QualitySettings from ProfileThresholds
│  ├─ VideoBitrateKbps ✓
│  ├─ AudioBitrateKbps ✓
│  ├─ Quality ✓
│  ├─ Codec ✓
│  ├─ Grain ✓
│  └─ TargetResolution ✓
│
├─ Lookup CodecFlags by Codec Name
│  │
│  ├─ CodecFlags Found? ──┐
│  │                      │
│  │ YES                  │ NO
│  │ │                    │ │
│  │ ▼                    │ ▼
│  │ Get CodecFlags       │ Use Fallback
│  │ Configuration        │ Hardcoded
│  │ │                    │ Parameters
│  │ │                    │ │
│  │ │                    │ ▼
│  │ │                    │ Return Basic
│  │ │                    │ FFmpeg Command
│  │ │                    │
│  │ ▼                    │
│  │ Lookup CodecParameters
│  │ │
│  │ ├─ CodecParameters Found? ──┐
│  │ │                          │
│  │ │ YES                      │ NO
│  │ │ │                        │ │
│  │ │ ▼                        │ ▼
│  │ │ Build Parameter Map      │ Use CodecFlags
│  │ │ from CodecParameters     │ Defaults Only
│  │ │ │                        │ │
│  │ │ │                        │ ▼
│  │ │ │                        │ Generate Basic
│  │ │ │                        │ FFmpeg Arguments
│  │ │ │                        │
│  │ │ ▼                        │
│  │ │ Apply Profile Settings   │
│  │ │ to Parameters            │
│  │ │ │                        │
│  │ │ ▼                        │
│  │ │ Generate FFmpeg          │
│  │ │ Arguments                │
│  │ │ │                        │
│  │ │ ▼                        │
│  │ │ Add Codec-Specific       │
│  │ │ Optimizations            │
│  │ │ │                        │
│  │ │ ▼                        │
│  │ │ Add Resolution Scaling   │
│  │ │ if Needed                │
│  │ │ │                        │
│  │ │ ▼                        │
│  │ └─ Return Complete         │
│  │    FFmpeg Command          │
│  │                            │
│  └────────────────────────────┘
│
└─ End: Complete FFmpeg Command
```

## Key Decision Points

### 1. CodecFlags Availability
```
CodecFlags Found?
├─ YES → Continue with full system
└─ NO → Use hardcoded fallback
```

### 2. CodecParameters Availability
```
CodecParameters Found?
├─ YES → Use dynamic parameter generation
└─ NO → Use CodecFlags defaults only
```

### 3. Parameter Validation
```
Profile Setting Valid?
├─ YES → Use profile setting value
└─ NO → Use CodecParameters default
```

### 4. Grain Setting
```
Grain > 0?
├─ YES → Apply grain parameters
└─ NO → Skip grain parameters
```

### 5. Resolution Scaling
```
TranscodeDownTo Set?
├─ YES → Add scale filter
└─ NO → Skip scale filter
```

## Data Sources Integration

### ProfileThresholds → CodecParameters Mapping
```
ProfileThresholds          CodecParameters
├─ Quality (22)        →   ├─ crf parameter
├─ Grain (10)          →   ├─ film-grain parameter
├─ VideoBitrate (3000) →   ├─ maxrate/bufsize
├─ AudioBitrate (192)  →   ├─ audio bitrate
└─ TranscodeDownTo     →   └─ scale filter
```

### Codec-Specific Parameter Examples
```
libx265:
├─ crf: -crf 22
├─ preset: -preset 6
├─ grain: -tune grain
└─ threads: -x265-params "threads=0"

libsvtav1:
├─ crf: -crf 30
├─ preset: -preset 6
├─ grain: -svtav1-params "film-grain=10"
└─ tune: -svtav1-params "tune=0"
```

## Error Handling Paths

### Database Lookup Failures
```
Database Error?
├─ CodecFlags lookup fails → Use hardcoded fallback
├─ CodecParameters lookup fails → Use CodecFlags defaults
└─ Parameter validation fails → Use CodecParameters defaults
```

### Missing Configuration
```
Configuration Missing?
├─ CodecFlags missing → Log warning, use fallback
├─ CodecParameters missing → Log warning, use defaults
└─ Profile settings missing → Log error, fail gracefully
```

## Implementation Phases

### Phase 1: Basic Integration
```
Current State → Phase 1
├─ Add CodecFlags lookup
├─ Add CodecParameters lookup
├─ Implement basic parameter mapping
└─ Add fallback handling
```

### Phase 2: Advanced Features
```
Phase 1 → Phase 2
├─ Implement grain parameter support
├─ Add preset parameter support
├─ Implement parameter validation
└─ Add codec-specific optimizations
```

### Phase 3: UI Integration
```
Phase 2 → Phase 3
├─ Add CodecFlags/CodecParameters management UI
├─ Add parameter validation in UI
├─ Add parameter descriptions and help
└─ Add codec-specific parameter groups
```

## Benefits Visualization

### Current Implementation
```
Hardcoded Parameters
├─ -preset faster (fixed)
├─ -crf 22 (fixed)
├─ Basic codec optimizations (limited)
└─ No grain support
```

### Ideal Implementation
```
Dynamic Parameters
├─ -preset 6 (from CodecParameters)
├─ -crf 22 (from ProfileThresholds)
├─ -tune grain (from Grain setting)
├─ -svtav1-params "film-grain=10" (codec-specific)
└─ Full codec optimization support
```

This decision tree shows the complete flow from input to output, with all the decision points and fallback paths clearly defined.
