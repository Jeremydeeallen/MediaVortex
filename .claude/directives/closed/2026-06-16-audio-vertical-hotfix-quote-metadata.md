# Current Directive

**Set:** 2026-06-16
**Status:** Closed 2026-06-16 PM

## Delivery Report

DIRECTIVE: Hotfix the AudioFilterEmitter so multi-word metadata values
(`title=Dialog Boost`) survive the shape's `' '.join(CommandParts)` call to
ffmpeg, restart WebService, and apply the deferred library sweep.

STATUS: Done.

WHAT SHIPPED:
- `AudioFilterEmitter._BuildBlockForTrack`: wrap every metadata value in
  double quotes (`f'"language={Language}"'`, `f'"title={Label}"'`,
  `f'"dialnorm={DialNorm}"'`). 12/12 TestAudioFilterEmitter contract tests
  green.
- `Templates/AudioNormalization.html`: extends `Base.html` instead of the
  non-existent `_layout.html`. Page now renders HTTP 200 with the
  Audio Normalization heading visible.
- WebService restart on I9: blueprint live, all four API endpoints return
  200 with the expected `{Success, Message, Data}` envelope.
- WorkerService restart on I9: now running the new emitter + quote fix.
- Library sweep `--apply`: 22 `invalid_loudness_measurement` + 1918
  `ungainable_all_streams` defer reasons applied. Review API confirms
  Count=1918.

ROOT CAUSE OF THE PRIOR FAILURES: ffmpeg error
  [AVFormatContext] Unable to choose an output format for 'Boost'
caused by `-metadata:s:a:0 title=Dialog Boost` (no quotes). ffmpeg
interpreted `Boost` as a positional output filename. Fix is the quote
wrap above.

CRITERIA VERIFICATION:
- H1: `Block.MetadataArgs` items quote each value (line 191 / 196 of
  AudioFilterEmitter.py). Verified.
- H2: TestAudioFilterEmitter + TestRemuxShape + TestTranscodeShape +
  TestSubtitleFixShape -- 29 tests green after the change.
- H3: `curl -s http://localhost:5000/api/AudioNormalization/Settings` ->
  `{Success: True, Data: {Rows: 1 row}}`. Dashboard + Review + page
  render also 200.
- H4: 22 + 1918 defer reasons applied via Scripts/SweepAudioPolicyForExistingFiles.py
  --apply; confirmed via Review API + direct DB count.

WHAT YOU NEED TO EXECUTE:
- Unpause I9-2024 worker (currently `Status='Paused'`) when ready to
  verify a live emitter-generated transcode end-to-end.
- Deploy worker code to the Linux containers on larry + dot (the
  successful transcode 38638 was the OLD code path emitting
  `-af "loudnorm..."`; new code is I9-only until those containers
  update). Use the `mediavortex-deploy-worker` flow.

DECISIONS I MADE:
- Quoted the metadata values rather than restructuring to push -map args
  to the front of the argv. ffmpeg accepts the interleaved layout, and
  the shape's argv-building convention is "value-needing-quotes wraps
  the value at emit time" (mirrors how FilterArgs already work).
- Did not change the `-disposition:a:0 0` arg even though it looked
  suspicious. ffmpeg docs confirm `0` is the valid "clear all flags"
  value; the original failure was solely the unquoted title.

### Promotions

The hotfix narrative stays in this directive doc; the durable behavior is
in `Features/AudioNormalization/audio-normalization.feature.md` (C1, C2,
C20) which already specifies the metadata + DialNorm contracts. No new
feature/flow doc needed.
**Slug:** audio-vertical-hotfix-quote-metadata

## Outcome

Hotfix the AudioFilterEmitter's metadata args so multi-word values
(`title=Dialog Boost`) survive the shape's ` `.join(CommandParts)` call to
ffmpeg. The unquoted value caused ffmpeg to treat "Boost" as an output
filename and fail every emitter-generated transcode with EINVAL.

Also restart WebService on I9 so the new `/AudioNormalization` blueprint is
reachable for live API + UI smoke.

## Acceptance Criteria

H1. `Block.MetadataArgs` items wrap each metadata value in double quotes so
spaces survive the join. Verifiable: synthetic Build() command contains
`"title=Dialog Boost"` not bare `title=Dialog Boost`.

H2. Existing TestAudioFilterEmitter / TestRemuxShape / TestTranscodeShape /
TestSubtitleFixShape contract tests stay green after the change.

H3. WebService restart on I9 picks up the `/AudioNormalization` blueprint;
`curl -s http://localhost:5000/api/AudioNormalization/Settings` returns
`{Success:true, Data:{Rows:[...]}}`.

H4. Library sweep `--apply` runs and the 22 `invalid_loudness_measurement`
+ 1918 `ungainable_all_streams` rows are marked.

## Files

```
Features/AudioNormalization/AudioFilterEmitter.py  -- quote metadata values
```

## Status

### Promotions

[Populated at DELIVERING]
