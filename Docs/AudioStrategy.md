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

**Applies to:** Transcode, Remux, and SubtitleFix paths. All three re-encode audio to AAC, so the same `loudnorm` + optional `acompressor` chain is applied uniformly. The library-wide loudness consistency promise is upheld regardless of which pipeline produced the file.

### 3. Codec: Jellyfin-Compatible Output
Output audio uses codecs that Jellyfin can direct-play on all clients.

**Transcode, Remux, and SubtitleFix paths:** All three re-encode audio to AAC at 128 kbps so the normalization chain can be applied. Audio re-encoding is cheap relative to video (typically 5-20 seconds for a 60-minute file), so the cost of normalizing during remux is negligible compared to the consistency benefit.

MP4 container audio compatibility note (informational, not a decision branch any longer):
- `aac`, `ac3`, `eac3`, `mp3` are MP4-compatible codecs
- `dts`, `dts-hd`, `truehd`, `flac`, `pcm_*` are not

Prior versions of the remux path copied audio when the codec was already MP4-compatible. That branch was removed so loudness normalization is applied uniformly.

## Decision Matrix

| Path | English Selection | Normalization | Output Codec |
|------|------------------|---------------|--------------|
| **Transcode** | Yes (via `-map`) | Yes (`loudnorm` + optional `acompressor`) | AAC (always re-encoded) |
| **Remux** | Yes (via `-map`) | Yes (`loudnorm` + optional `acompressor`) | AAC 128k (always re-encoded; video stream still copied) |
| **SubtitleFix** | Yes (via `-map`) | Yes (`loudnorm` + optional `acompressor`) | AAC 128k (always re-encoded; video and subtitle streams handled separately) |

## Key Files
- `Services/FFmpegAnalysisService.py` — `SelectPreferredAudioStream()` picks the English track
- `Models/CommandBuilder.py` — `BuildCommand()` and `BuildRemuxCommand()` apply stream mapping and codec selection
- `Models/CommandBuilder.py` — `BuildAudioFilters()` constructs the normalization/compression filter chain
- `Services/CommandBuilderService.py` — orchestrates analysis + command building for both paths
