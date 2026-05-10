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

### 3. Codec: Source-Preserving with MP4 Fallback (revised 2026-05-10)
Output audio matches the source codec, channel count, and bitrate whenever the source is MP4-compatible. The previous "always AAC stereo 128k" policy was retired because audio is a small fraction of total bitrate (~10% on a 720p AV1 file) and forcing stereo AAC threw away surround sound for very little space saved.

**Policy** (implemented in `CommandBuilder.BuildAudioCodecArgs`):

| Source Codec | Output Codec | Channels | Bitrate |
|---|---|---|---|
| `aac` | aac | match source (no `-ac` flag) | match source, fall back to channel-aware default |
| `ac3` | ac3 | match source | match source, fall back to channel-aware default |
| `eac3` | eac3 | match source | match source, fall back to channel-aware default |
| `mp3` | aac | match source | match source, fall back to channel-aware default |
| `dts`, `flac`, `truehd`, `pcm_*`, anything else | **eac3** | match source | channel-aware default (source bitrate is meaningless for lossless) |

**Channel-aware default bitrates** (used when source bitrate is NULL or for lossless-to-eac3 fallback):
- mono → 96 kbps
- stereo → 128 kbps
- 5.1 → 256 kbps
- 7.1 → 384 kbps

**Operator override:** `ProfileThresholds.AudioBitrateKbps` is the override knob. **Zero (0) means "use source policy"**; any non-zero value forces that bitrate regardless of source. As of 2026-05-10 every existing row was reset to 0 to make source-matching the default everywhere. To pin a profile to a specific bitrate, edit the `ProfileThresholds` row for that profile + resolution.

**Why re-encode at all?** The loudness-normalization filter chain requires decoded audio. Stream-copy is incompatible with `loudnorm` / `acompressor`, so audio passes through a decode → filter → re-encode cycle even when the codec is unchanged. Cost: ~5-20 seconds per hour of content.

## Decision Matrix

| Path | English Selection | Normalization | Output Codec | Channels | Bitrate |
|------|------------------|---------------|--------------|----------|---------|
| **Transcode** (`BuildCommand`) | Yes | Yes | source-matching (per table above) | preserved | source / channel-aware default / profile override |
| **Remux** (`BuildRemuxCommand`) | Yes | Yes | source-matching (per table above) | preserved | source / channel-aware default (no profile override) |
| **SubtitleFix** (`BuildSubtitleFixCommand`) | Yes | Yes | source-matching (per table above) | preserved | source / channel-aware default (no profile override) |

## Key Files
- `Services/FFmpegAnalysisService.py` — `SelectPreferredAudioStream()` picks the English track
- `Models/CommandBuilder.py` — `BuildCommand()` and `BuildRemuxCommand()` apply stream mapping and codec selection
- `Models/CommandBuilder.py` — `BuildAudioFilters()` constructs the normalization/compression filter chain
- `Services/CommandBuilderService.py` — orchestrates analysis + command building for both paths
