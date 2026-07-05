# Command Composer

**Slug:** command-composer

## What It Does

One composer function that takes a `Plan` tuple (`{VideoOp, AudioOp, SubtitleOp, ContainerOp}`) and composes four SRP-clean Slot services in a fixed order to produce ffmpeg argv. Every path -- Reencode, StreamCopy Remux, StreamCopy AudioFix, StreamCopy Quick, SubtitleFix -- goes through the same 4 slots. `SubtitleSlot` always fires with container-appropriate codec, closing BUG-0083 subtitle-drop across all non-SubtitleFix paths (~27127 files).

## Workflows

| # | User action | Surface | Handler | Backing |
|---|---|---|---|---|
| W1 | Worker claims a queued job and builds ffmpeg argv | (internal) | `ITranscodeJobStrategy.BuildCommand` -> `CommandComposer.Build` | `Features/TranscodeJob/Emit/CommandComposer.Build` |

## Success Criteria

C1. `Features/TranscodeJob/Emit/CommandComposer.py` exists. Public method `Build(Job, MediaFile, Plan) -> CommandSpec` composes 4 slots in fixed order: input(s) + VideoSlot + AudioSlot + SubtitleSlot + ContainerSlot + output. Slot services are DIP-injected. Verifiable: import + call + argv shape.

C2. `Features/TranscodeJob/Emit/Slots/VideoSlot.py` exposes Reencode + StreamCopy implementations. Reencode dispatches by Family (Nvenc inline / QSV inline / SVT-AV1 via `SvtAv1EncoderArgsStrategy`) reading Family from Profile row. Absolute knobs from `ProfileThresholds.TargetKbps` / `IcqQ` (per `profile-tier-ladder.feature.md`). StreamCopy emits `-c:v copy [-tag:v hvc1]`. Verifiable: `TestCommandComposer` per Op.

C3. `Features/TranscodeJob/Emit/Slots/AudioSlot.py` emits the 2-track pipeline (Original preserved up to 7.1 + Dialog Boost forced stereo) for AudioOp='Reencode' via `AudioPolicyResolver.GetEffectivePolicy` + `AudioFilterEmitter.EmitTracks`. Empty Blocks / missing Policy raises `AudioPolicyUnresolvedError` (no silent fallback). For AudioOp='Copy' emits `-c:a copy` on all source audio streams. Verifiable: `TestCommandComposer` per Op + audio-emit ffprobe on smoke output.

C4. **`Features/TranscodeJob/Emit/Slots/SubtitleSlot.py` ALWAYS fires.** MP4 target -> `-map 0:s? -c:s mov_text`; MKV target -> `-map 0:s? -c:s copy`; source contains image-based subs (PGS `hdmv_pgs_subtitle`, DVB `dvbsub`) targeted to MP4 -> emit `[]` for those streams + `LoggingService.LogWarning` naming dropped codec + attempt id. Metadata preserved (`-metadata:s:s:N language=...`). Verifiable: `Tests/Contract/TestCommandComposer.py::test_subtitle_slot_always_fires` + smokes (e/f/g) from directive.

C5. `Features/TranscodeJob/Emit/Slots/ContainerSlot.py` emits container-format switches (`.mkv -> .mp4` etc.) or preserves. Reads `Plan.ContainerOp` + `Profile.Container`. Verifiable: `TestCommandComposer` per Op.

C6. `Tests/Contract/TestNoLegacyResidue.py` grep-fence `RETIRED_SYMBOLS` returns 0 hits across production tree for: `EncodeShapeRegistry`, `EncodeShape`, `TranscodeShape`, `RemuxShape`, `SubtitleFixShape`, `CodecParameterAssembler`, `AudioCodecArgsBuilder`, `NvencEncoderArgsStrategy`, `QsvEncoderArgsStrategy`. Deleted-files assertion confirms the corresponding `.py` files do not exist. Verifiable: `pytest Tests/Contract/TestNoLegacyResidue.py`.

C7. `ITranscodeJobStrategy.BuildCommand` delegates to `CommandComposer.Build`. No Shape-registry lookup by ProcessingMode remains at the Emit layer. Verifiable: `grep 'EncodeShapeRegistry' Features/**/*.py` returns 0.

C8. `Plan` frozen dataclass + `PlanFactory.FromProcessingMode`: Transcode -> `(Reencode, Reencode, Preserve, Mp4)`; Remux / Quick / AudioFix / SubtitleFix -> `(Copy, Reencode, Preserve, Mp4)`. Verifiable: `TestCommandComposer::TestPlanFactory`.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `Strategy -> CommandComposer.Build` | `ITranscodeJobStrategy.BuildCommand` | `(Job, MediaFile, Plan)` | `CommandSpec {Command, OutputPath}` | `TestCommandComposer` |
| S2 | `CommandComposer -> Slot ordering` | Composer internal | 4-slot fixed order Video + Audio + Subtitle + Container | argv list assembled deterministically | `TestCommandComposer::test_slot_ordering` |
| S3 | `SubtitleSlot -> ffmpeg argv` | Slot emitter | container-appropriate codec + optional map | 0 dropped text-sub streams; image subs dropped with WARN | `TestCommandComposer::test_subtitle_slot_always_fires` + smokes |

## Status

Shipped 2026-07-04 via `transcode-flow-canonical` directive Reset 10 (C17 collapse) + Reset 14 (promoted at DELIVERING). BUG-0083 CLOSED.

## Files

- `Features/TranscodeJob/Emit/CommandComposer.py`
- `Features/TranscodeJob/Emit/Plan.py`
- `Features/TranscodeJob/Emit/Slots/VideoSlot.py`
- `Features/TranscodeJob/Emit/Slots/AudioSlot.py`
- `Features/TranscodeJob/Emit/Slots/SubtitleSlot.py`
- `Features/TranscodeJob/Emit/Slots/ContainerSlot.py`
- `Tests/Contract/TestCommandComposer.py` -- 29 tests
- `Tests/Contract/TestNoLegacyResidue.py` -- grep-fence + deleted-files
- `Tests/Contract/TestSubtitleSlot.py` -- 13 tests
