# Current Directive

**Set:** 2026-06-16
**Status:** Active -- phase: IMPLEMENTING
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
