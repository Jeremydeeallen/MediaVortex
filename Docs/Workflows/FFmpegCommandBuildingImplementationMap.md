# FFmpeg Command Building Implementation Map

This document maps each component of the FFmpeg command building workflow to its implementation location (Database vs Code).

## Data Sources (Database - DB)

### 1. ProfileThresholds Table (DB)
**Purpose**: Basic transcoding settings from profile assignment
**Location**: `Data/MediaVortex.db` → `ProfileThresholds` table
**Fields Used**:
- `VideoBitrateKbps` - Maximum video bitrate
- `AudioBitrateKbps` - Audio bitrate
- `Quality` - CRF/QP quality setting
- `Grain` - Film grain level (0-50)
- `TranscodeDownTo` - Target resolution for downscaling
- `Resolution` - Source resolution threshold

### 2. Profiles Table (DB)
**Purpose**: Codec selection for transcoding
**Location**: `Data/MediaVortex.db` → `Profiles` table
**Fields Used**:
- `Codec` - Video codec (libx265, libsvtav1, libx264, libvpx-vp9)
- `ProfileName` - Profile identifier

### 3. CodecFlags Table (DB)
**Purpose**: Codec-specific configuration and capabilities
**Location**: `Data/MediaVortex.db` → `CodecFlags` table
**Fields Used**:
- `CodecName` - Codec identifier
- `PresetType` - "numeric" or "string"
- `PresetMin/Max/Default` - Preset range and default
- `FilmGrainType` - "boolean" or "numeric"
- `FilmGrainMin/Max/Default` - Grain range and default

### 4. CodecParameters Table (DB)
**Purpose**: Individual FFmpeg flags and parameters for each codec
**Location**: `Data/MediaVortex.db` → `CodecParameters` table
**Fields Used**:
- `ParameterName` - crf, qp, preset, film-grain, tune
- `ParameterType` - integer, float, string, boolean
- `MinValue/MaxValue` - Validation ranges
- `DefaultValue` - Default parameter value
- `FFmpegFlag` - Actual FFmpeg flag (-crf, -svtav1-params film-grain)

## Code Implementation (Files)

### 1. Database Access Layer
**File**: `Repositories/DatabaseManager.py`
**Methods**:
- `GetProfileSettingsForTargetResolution()` - Get ProfileThresholds settings
- `GetCodecFlagsByCodecName()` - Get CodecFlags configuration
- `GetCodecParametersByCodecFlagsId()` - Get CodecParameters for codec
- `GetProfileByCodec()` - Get codec from Profiles table

### 2. FFmpeg Command Building
**File**: `Services/FFmpegTranscodingService.py`
**Methods**:
- `BuildFFmpegCommand()` - Main command building method (CURRENT: basic implementation)
- `BuildFFmpegMultiPassCommand()` - Multi-pass command building
- `GetScaleFilter()` - Resolution scaling filter generation
- `_ApplyCodecSpecificOptimizations()` - Codec-specific parameter application

### 3. Codec Configuration Models
**File**: `Models/CodecFlagsModel.py`
**Classes**:
- `CodecFlagsModel` - CodecFlags table representation
- Methods for parameter validation and FFmpeg flag generation

**File**: `Models/CodecParametersModel.py` (TO BE CREATED)
**Classes**:
- `CodecParametersModel` - CodecParameters table representation
- Methods for parameter validation and FFmpeg flag generation

### 4. Business Logic Layer
**File**: `Services/TranscodingBusinessService.py`
**Methods**:
- `GetQualitySettingsForFile()` - Get complete quality settings
- `GetProfileThresholdForFile()` - Get profile threshold for file
- `ValidateTranscodingSettings()` - Validate all settings before transcoding

### 5. Resolution Standardization
**File**: `Services/ResolutionService.py`
**Methods**:
- `StandardizeResolution()` - Convert resolution formats
- `FindMatchingThreshold()` - Find matching profile threshold
- `GetScaleFilter()` - Generate resolution scaling filters

## Implementation Mapping by Workflow Step

### Step 1: Input Processing
**DB**: ProfileThresholds, Profiles
**Code**: `TranscodingBusinessService.GetQualitySettingsForFile()`
**File**: `Services/TranscodingBusinessService.py`

### Step 2: CodecFlags Lookup
**DB**: CodecFlags table
**Code**: `DatabaseManager.GetCodecFlagsByCodecName()`
**File**: `Repositories/DatabaseManager.py`

### Step 3: CodecParameters Lookup
**DB**: CodecParameters table
**Code**: `DatabaseManager.GetCodecParametersByCodecFlagsId()`
**File**: `Repositories/DatabaseManager.py`

### Step 4: Parameter Mapping
**DB**: CodecParameters (for validation ranges)
**Code**: `CodecFlagsModel.ValidateParameter()`, `CodecParametersModel.ApplyProfileSetting()`
**Files**: `Models/CodecFlagsModel.py`, `Models/CodecParametersModel.py`

### Step 5: FFmpeg Argument Generation
**DB**: None (uses mapped parameters)
**Code**: `FFmpegTranscodingService.BuildFFmpegCommand()`
**File**: `Services/FFmpegTranscodingService.py`

### Step 6: Advanced Features
**DB**: None (uses generated arguments)
**Code**: `FFmpegTranscodingService.GetScaleFilter()`, `FFmpegTranscodingService._ApplyCodecSpecificOptimizations()`
**File**: `Services/FFmpegTranscodingService.py`

## Current vs Required Implementation

### Current Implementation (Basic)
**File**: `Services/FFmpegTranscodingService.py`
**Method**: `BuildFFmpegCommand()`
**Issues**:
- Hardcoded parameters (`-preset faster`, `-crf 22`)
- No CodecFlags/CodecParameters integration
- Missing grain support
- Limited codec-specific optimizations

### Required Implementation (Complete)
**Files to Modify**:
1. `Repositories/DatabaseManager.py` - Add CodecFlags/CodecParameters lookup methods
2. `Services/FFmpegTranscodingService.py` - Integrate CodecFlags/CodecParameters system
3. `Models/CodecParametersModel.py` - Create new model for CodecParameters
4. `Services/TranscodingBusinessService.py` - Update quality settings retrieval

**New Methods Required**:
- `DatabaseManager.GetCodecFlagsByCodecName()`
- `DatabaseManager.GetCodecParametersByCodecFlagsId()`
- `CodecParametersModel.__init__()`
- `CodecParametersModel.ValidateParameter()`
- `CodecParametersModel.GetFFmpegFlag()`
- `FFmpegTranscodingService._BuildCodecSpecificArguments()`
- `FFmpegTranscodingService._ApplyGrainParameters()`
- `FFmpegTranscodingService._ApplyPresetParameters()`

## Database Schema Dependencies

### Existing Tables (Ready)
- ✅ `ProfileThresholds` - Has all required fields
- ✅ `Profiles` - Has Codec field
- ✅ `CodecFlags` - Has all required fields
- ✅ `CodecParameters` - Has all required fields

### No Schema Changes Required
All required database tables and fields already exist. The implementation only needs to:
1. Add new database access methods
2. Integrate existing tables into command building
3. Create missing model classes

## File Dependencies

### Core Files (Must Modify)
1. `Services/FFmpegTranscodingService.py` - Main command building logic
2. `Repositories/DatabaseManager.py` - Database access methods

### Supporting Files (May Need Updates)
1. `Services/TranscodingBusinessService.py` - Quality settings integration
2. `Models/CodecFlagsModel.py` - May need additional methods
3. `Services/ResolutionService.py` - Resolution scaling integration

### New Files (To Create)
1. `Models/CodecParametersModel.py` - CodecParameters model
2. `Services/CodecConfigurationService.py` - Codec configuration business logic (optional)

## Implementation Priority

### Phase 1: Database Access (DB)
1. Add `GetCodecFlagsByCodecName()` to `DatabaseManager.py`
2. Add `GetCodecParametersByCodecFlagsId()` to `DatabaseManager.py`
3. Test database access methods

### Phase 2: Model Integration (Code)
1. Create `CodecParametersModel.py`
2. Add validation methods to `CodecFlagsModel.py`
3. Test model functionality

### Phase 3: Command Building Integration (Code)
1. Modify `BuildFFmpegCommand()` in `FFmpegTranscodingService.py`
2. Add codec-specific parameter application
3. Add grain and preset support
4. Test complete command generation

### Phase 4: Business Logic Integration (Code)
1. Update `GetQualitySettingsForFile()` in `TranscodingBusinessService.py`
2. Integrate with existing transcoding workflow
3. Test end-to-end transcoding

This mapping shows exactly where each piece of the workflow is implemented and what needs to be modified to achieve the complete FFmpeg command building system.
