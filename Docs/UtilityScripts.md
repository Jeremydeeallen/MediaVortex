# MediaVortex Utility Scripts Documentation

This document provides an overview of all utility scripts in the `Scripts/` folder, their purpose, and current relevance.

## Active/Current Scripts

### Database Management

#### `AddLastTranscodeAttemptToQualityQueue.py` ✅ **CURRENT**
- **Purpose**: Automatically adds the most recent transcode attempt to the quality testing queue
- **Features**: 
  - Parses FFmpeg commands to extract correct input/output file paths
  - Prevents duplicate entries
  - Uses smart path resolution
- **Usage**: `py Scripts\AddLastTranscodeAttemptToQualityQueue.py`
- **Status**: **ACTIVE** - Recently updated with FFmpeg command parsing

#### `LogReader.py` ✅ **CURRENT**
- **Purpose**: Database log analysis tool for reading and analyzing logs
- **Features**:
  - Filter by log level, function, service, date range
  - Error summaries and recent error analysis
  - Message content filtering (recently added)
- **Usage**: `py Scripts\LogReader.py --message "Acute" --hours 48`
- **Status**: **ACTIVE** - Recently enhanced with message filtering

#### `UpdateDatabaseSchema.py` ✅ **CURRENT**
- **Purpose**: Generates DatabaseSchema.md by querying the database
- **Features**: Extracts table/column information, indexes, and index columns
- **Usage**: `py Scripts\UpdateDatabaseSchema.py`
- **Status**: **ACTIVE** - Used for documentation generation

### Service Management

#### `StopAllPythonServices.py` ✅ **CURRENT**
- **Purpose**: Stops all MediaVortex Python services and logs results
- **Features**: Process detection, graceful shutdown, logging
- **Usage**: `py Scripts\StopAllPythonServices.py`
- **Status**: **ACTIVE** - Essential for service management

### Data Analysis

#### `FindDuplicates.py` ✅ **CURRENT**
- **Purpose**: Find and optionally clean up duplicate media files
- **Features**: Uses DuplicateDetectionService for analysis
- **Usage**: `py Scripts\FindDuplicates.py`
- **Status**: **ACTIVE** - Useful for media library maintenance

#### `FindSampleFilesByCodec.py` ✅ **CURRENT**
- **Purpose**: Find sample files by codec type for analysis
- **Usage**: `py Scripts\FindSampleFilesByCodec.py`
- **Status**: **ACTIVE** - Useful for codec analysis

#### `AnalyzeCodecDifferences.py` ✅ **CURRENT**
- **Purpose**: Analyze differences between codecs
- **Usage**: `py Scripts\AnalyzeCodecDifferences.py`
- **Status**: **ACTIVE** - Used for codec comparison studies

### Troubleshooting

#### `CleanupStuckScans.py` ✅ **CURRENT**
- **Purpose**: Clean up stuck scan jobs in the database
- **Features**: Marks 'Pending' or 'Running' scans as 'Failed'
- **Usage**: `py Scripts\CleanupStuckScans.py`
- **Status**: **ACTIVE** - Useful for resolving stuck operations

#### `FixStuckQualityTestJob.py` ✅ **CURRENT**
- **Purpose**: Fix stuck quality test jobs
- **Usage**: `py Scripts\FixStuckQualityTestJob.py`
- **Status**: **ACTIVE** - Troubleshooting tool

#### `FixLogger.py` ✅ **CURRENT**
- **Purpose**: Fix logging issues
- **Usage**: `py Scripts\FixLogger.py`
- **Status**: **ACTIVE** - Maintenance tool

## Database Migration Scripts (One-time Use)

### ⚠️ **DEPRECATED - One-time Migration Scripts**

These scripts were used for specific database migrations and are no longer needed for regular operation:

#### `AddMaxConcurrentJobsColumn.py` ❌ **DEPRECATED**
- **Purpose**: Added MaxConcurrentJobs column to ServiceStatus table
- **Status**: **DEPRECATED** - One-time migration completed

#### `AddQualityTestColumns.py` ❌ **DEPRECATED**
- **Purpose**: Added missing columns to QualityTestingQueue table
- **Status**: **DEPRECATED** - One-time migration completed

#### `AddQualityTestColumnsToTranscodeAttempts.py` ❌ **DEPRECATED**
- **Purpose**: Added quality test columns to TranscodeAttempts table
- **Status**: **DEPRECATED** - One-time migration completed

#### `AddQualityTestingSchema.py` ❌ **DEPRECATED**
- **Purpose**: Added quality testing schema to database
- **Status**: **DEPRECATED** - One-time migration completed

#### `CreateActiveJobsTable.py` ❌ **DEPRECATED**
- **Purpose**: Created ActiveJobs table
- **Status**: **DEPRECATED** - One-time migration completed

## Specific Use Case Scripts

### `InsertDexterQualityQueue.py` ⚠️ **SPECIFIC USE CASE**
- **Purpose**: Manually insert Dexter S06E07 quality testing record
- **Status**: **SPECIFIC** - One-time use for specific file

### `CleanupTestData.py` ⚠️ **MAINTENANCE**
- **Purpose**: Clean up test data from database
- **Usage**: `py Scripts\CleanupTestData.py`
- **Status**: **MAINTENANCE** - Use with caution

### `CleanupTranscodingCommands.py` ⚠️ **MAINTENANCE**
- **Purpose**: Clean up transcoding commands
- **Usage**: `py Scripts\CleanupTranscodingCommands.py`
- **Status**: **MAINTENANCE** - Use with caution

## Analysis Data

### `CodecAnalysis/` 📊 **REFERENCE DATA**
- **Purpose**: Contains JSON analysis files for various codecs
- **Contents**: Analysis data for AV1, H.264, HEVC, MJPEG, MPEG2, MPEG4, etc.
- **Status**: **REFERENCE** - Historical analysis data

## Development Tools

### `Cursor/TroubleshootingTool.py` 🔧 **DEVELOPMENT**
- **Purpose**: Development troubleshooting tool
- **Status**: **DEVELOPMENT** - For development use only

### `DatabaseHelper.py` 🔧 **UTILITY**
- **Purpose**: Database helper utilities
- **Status**: **UTILITY** - Supporting library

### `LogAnalyzer.py` 🔧 **ANALYSIS**
- **Purpose**: Log analysis for identifying issues and patterns
- **Status**: **ANALYSIS** - Advanced log analysis tool

## Usage Guidelines

### ✅ **Safe to Use Regularly**
- `AddLastTranscodeAttemptToQualityQueue.py`
- `LogReader.py`
- `StopAllPythonServices.py`
- `FindDuplicates.py`
- `CleanupStuckScans.py`

### ⚠️ **Use with Caution**
- `CleanupTestData.py`
- `CleanupTranscodingCommands.py`
- `FixStuckQualityTestJob.py`

### ❌ **Do Not Use (Deprecated)**
- `AddMaxConcurrentJobsColumn.py`
- `AddQualityTestColumns.py`
- `AddQualityTestColumnsToTranscodeAttempts.py`
- `AddQualityTestingSchema.py`
- `CreateActiveJobsTable.py`

### 🔧 **Development Only**
- `Cursor/TroubleshootingTool.py`
- `DatabaseHelper.py`
- `LogAnalyzer.py`

## Recommendations

1. **Keep Active**: The current active scripts are well-maintained and useful
2. **Archive Deprecated**: Consider moving deprecated migration scripts to an archive folder
3. **Document Specific Use Cases**: Scripts like `InsertDexterQualityQueue.py` should be documented with their specific use case
4. **Regular Maintenance**: Review and update this documentation as scripts evolve

## Last Updated
- **Date**: 2025-01-08
- **Version**: 1.0
- **Status**: Current as of MediaVortex development
