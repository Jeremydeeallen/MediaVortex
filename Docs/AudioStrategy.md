# Audio Strategy

MediaVortex enforces three audio rules to ensure every file plays natively on Jellyfin clients without on-the-fly transcoding.

## Rules

### 1. Language: English Preferred
When a file contains multiple audio streams, the English track is selected automatically.

- Streams tagged `eng` or `en` are preferred
- When multiple English tracks exist, the one with the most channels wins (e.g., 5.1 surround over stereo)
- When no English track exists, the first audio stream is used as a fallback

**Implementation:** `FFmpegAnalysisService.SelectPreferredAudioStream()` runs at analysis time and sets `FFmpegAnalysisModel.AudioStreamIndex`. Both `CommandBuilder.BuildCommand()` (transcode) and `CommandBuilder.BuildRemuxCommand()` (remux) use this index in their `-map 0:a:{index}` flag.

### 2. Normalization: Industry-Standard Loudness
Audio is normalized so volume is consistent across the library.

| Parameter | Default | FFmpeg Flag |
|-----------|---------|-------------|
| Target Loudness (LUFS) | -23 | `loudnorm=I=-23` |
| Loudness Range (LRA) | 7 | `LRA=7` |
| True Peak (dBTP) | -2 | `TP=-2` |

Dynamic range compression is also available (configurable via system settings):

| Parameter | Default | FFmpeg Flag |
|-----------|---------|-------------|
| Threshold | -15 dB | `acompressor=threshold=-15dB` |
| Ratio | 3:1 | `ratio=3` |
| Attack | 10 ms | `attack=10` |
| Release | 100 ms | `release=100` |
| Makeup Gain | 3 dB | `makeup=3dB` |

Both filters are toggled independently via `AudioNormalizationEnabled` and `AudioCompressionEnabled` system settings.

**Applies to:** Transcode path only. Remux path copies audio without re-encoding when the codec is already compatible (see rule 3), so normalization is not applied during remux.

### 3. Codec: Jellyfin-Compatible Output
Output audio uses codecs that Jellyfin can direct-play on all clients.

**Transcode path:** Always re-encodes to AAC at the profile's configured bitrate (default 128 kbps). This is required because normalization filters need decoded audio.

**Remux path:** Copies the audio stream if it is already MP4-compatible. Otherwise re-encodes to AAC 128k.

MP4-compatible codecs (copied as-is during remux):
- `aac`
- `ac3` (Dolby Digital)
- `eac3` (Dolby Digital Plus)
- `mp3`

Codecs that trigger re-encoding to AAC:
- `dts` / `dts-hd` (licensing issues, many clients can't decode)
- `truehd` (Dolby TrueHD — not supported in MP4 container)
- `flac` (lossless, not supported in MP4)
- `pcm_*` (uncompressed, massive file size)

## Decision Matrix

| Path | English Selection | Normalization | Output Codec |
|------|------------------|---------------|--------------|
| **Transcode** | Yes (via `-map`) | Yes (`loudnorm` + optional `acompressor`) | AAC (always re-encoded) |
| **Remux** | Yes (via `-map`) | No (stream copied) | Copy if compatible, else AAC |

## Key Files
- `Services/FFmpegAnalysisService.py` — `SelectPreferredAudioStream()` picks the English track
- `Models/CommandBuilder.py` — `BuildCommand()` and `BuildRemuxCommand()` apply stream mapping and codec selection
- `Models/CommandBuilder.py` — `BuildAudioFilters()` constructs the normalization/compression filter chain
- `Services/CommandBuilderService.py` — orchestrates analysis + command building for both paths
