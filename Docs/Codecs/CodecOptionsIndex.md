# Codec Options Documentation Index

## Overview
This directory contains detailed documentation for all supported video codecs in MediaVortex, including their available options, parameters, and usage examples.

## Supported Codecs

### Primary Codecs (Most Used)

#### [LibX265 (H.265/HEVC)](LibX265Options.md)
- **Encoder**: libx265 H.265 / HEVC
- **Best For**: High compatibility, good compression, hardware acceleration
- **Key Features**: 
  - String presets (ultrafast to placebo)
  - Tune options (grain, fastdecode, zerolatency, animation)
  - Film grain via `-tune grain` (boolean)
  - CRF/QP rate control

#### [LibSvtAv1 (AV1)](LibSvtAv1Options.md)
- **Encoder**: SVT-AV1 (Scalable Video Technology for AV1)
- **Best For**: Best compression efficiency, future-proof
- **Key Features**:
  - Numeric presets (-2 to 13)
  - Film grain via `-svtav1-params "film-grain=N"` (numeric 0-50)
  - CRF/QP rate control
  - Advanced tuning options

### Secondary Codecs

#### LibX264 (H.264)
- **Encoder**: libx264 H.264 / AVC
- **Best For**: Maximum compatibility, older devices
- **Key Features**: String presets, tune options, film grain via `-tune film`

#### LibVpxVp9 (VP9)
- **Encoder**: libvpx-vp9 VP9
- **Best For**: Web streaming, good compression
- **Key Features**: Numeric presets (0-5), limited film grain support

## Codec Selection Guidelines

### Choose H.265 (libx265) When:
- Maximum hardware compatibility is required
- Hardware acceleration is available
- Encoding speed is important
- Film grain preservation is needed (via tune grain)

### Choose AV1 (libsvtav1) When:
- Best compression efficiency is desired
- File size is critical
- Encoding time is not a concern
- Future-proofing is important
- Film grain synthesis is needed (numeric control)

### Choose H.264 (libx264) When:
- Maximum compatibility with older devices
- Hardware acceleration is not available
- Simple encoding requirements

### Choose VP9 (libvpx-vp9) When:
- Web streaming optimization
- Good compression with reasonable speed
- Limited hardware acceleration

## Configuration Management

All codec configurations are managed through the `CodecFlags` and `CodecParameters` database tables, which store:

- **CodecFlags**: Basic codec information (preset types, film grain types, defaults)
- **CodecParameters**: Individual parameters with their FFmpeg flags, ranges, and descriptions

This allows for dynamic UI generation and proper parameter validation based on the selected codec.

## Related Documentation

- [Database Schema](../DatabaseSchema.md) - CodecFlags and CodecParameters table structures
- [Architecture](../Architecture.md) - Overall system architecture
- [Transcoding Workflow](../Workflows/TranscodingWorkflow.md) - How codecs are used in transcoding
