# AV1 CommandBuilder Database Setup Plan

This document tracks the focused plan to get AV1 (libsvtav1) working with database-driven configuration instead of hardcoded values.

## Goal
Get AV1 transcoding working with all settings stored in the database, eliminating hardcoded values and enabling easy configuration changes.

## Current Working Command
```bash
C:\Code\Automation\MediaVortex\FFmpegMaster\bin\ffmpeg.exe -i "c:\MediaVortex\Source\The Garfield Show - S01E01 - Pasta Wars WEBDL-1080p.mkv" -c:v libsvtav1 -crf 42 -preset 6 -c:a copy -vf "yadif=1:1:1,scale=1280:720" -movflags +faststart "c:\MediaVortex\The Garfield Show - S01E01 - Pasta Wars WEBDL-720pcrf42NoGrain.mp4"
```

## Setup Checklist

### Phase 1: Testing Infrastructure
- [ ] **Create test script** - `test_command_builder.py` that uses real CGI profile and Garfield Show file from database
- [ ] **Use real production data** - Get CGI profile settings, Garfield Show media file record, and libsvtav1 codec parameters from database
- [ ] **Test with real file** - Use `c:\MediaVortex\Source\The Garfield Show - S01E01 - Pasta Wars WEBDL-1080p.mkv` as input
- [ ] **Generate real output** - Output to `c:\MediaVortex\` (actual production location)
- [ ] **Compare commands** - Verify generated command matches working manual command
- [ ] **Fast validation** - 1:45s runtime for quick testing

### Phase 2: Database Population
- [ ] **Populate CodecParameters table** - Add all libsvtav1 parameters from LibSvtAv1Options.md
- [ ] **Add ContainerType column** - Add to ProfileThresholds table (default MP4)
- [ ] **Set proper validation ranges** - Min/max values for all parameters
- [ ] **Configure FFmpeg flags** - Map parameters to correct FFmpeg syntax

### Phase 3: CommandBuilder Updates
- [ ] **Remove hardcoded video codec** - Use database value instead of 'libsvtav1' fallback
- [ ] **Remove hardcoded preset** - Use CodecParameters for preset values
- [ ] **Remove hardcoded CRF** - Use database quality settings
- [ ] **Remove hardcoded film grain** - Use CodecParameters for grain settings
- [ ] **Remove hardcoded audio codec** - Use database audio settings
- [ ] **Add container type support** - Use ContainerType from ProfileThresholds

### Phase 4: Testing & Verification
- [ ] **Test with database values** - Run test script with real database configuration
- [ ] **Compare generated commands** - Ensure output matches working manual command
- [ ] **Verify MP4 output** - Confirm faststart and container settings work
- [ ] **Test parameter validation** - Ensure invalid values are handled properly

## Key Parameters to Configure

### libsvtav1 Parameters (from LibSvtAv1Options.md)
- **preset**: -2 to 13 (default: -2)
- **crf**: 0 to 63 (default: 28)
- **film-grain**: 0 to 50 (default: 10)
- **tune**: 0-2 (visual, psnr, vmaf)
- **la-depth**: 0-120 (default: 0)

### Container Settings
- **ContainerType**: "mp4" (default) or "mkv"
- **Faststart**: Enabled for MP4 containers

### Audio Settings
- **AudioCodec**: "aac" or "copy"
- **AudioBitrate**: When transcoding audio

## Success Criteria
- [ ] CommandBuilder generates identical commands to working manual command
- [ ] All hardcoded values removed from CommandBuilder.py
- [ ] Database contains all necessary libsvtav1 parameters
- [ ] Test script can validate CommandBuilder without full app startup
- [ ] MP4 output with faststart works correctly
- [ ] Easy to change settings through database without code changes

## Files to Modify
- `Models/CommandBuilder.py` - Remove hardcoded values
- `Services/CommandBuilderService.py` - Update to use database values
- `Repositories/DatabaseManager.py` - Add methods for CodecParameters
- `test_command_builder.py` - New test script
- Database schema - Add ContainerType column

## Notes
- Focus only on AV1 (libsvtav1) - ignore H.265 complexity for now
- Use existing CodecFlags + CodecParameters table structure
- Maintain MVVM architecture pattern
- Ensure all changes are backward compatible
