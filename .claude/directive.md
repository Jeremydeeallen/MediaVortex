# Current Directive

**Set:** 2026-10-11
**Status:** Active -- phase: IMPLEMENTING
**Slug:** demucs-liveness
**Replaces:** `directives/closed/2026-10-11-remove-savings-gate.md` (closed Success)

## Outcome

A vocal-separation run is failed as hung only when it has stopped working, not because it has run for 30 minutes. Long episodes separated on CPU (wakko: 85-119 minute episodes, about 30 minutes of separation) finish instead of being killed at the 1800-second mark. Operator 2026-10-11: "We shouldn't be doing a 30 minute timeout we should be watching to see if the process is still working. That's the correct detection."

## Acceptance Criteria

1. A separation that keeps working is never failed for elapsed time, however long it runs. Verify: contract test drives a fake separator that stays active past any fixed cap; live run of a long episode on wakko-worker-1 whose separation exceeds 30 minutes or previously timed out.
2. A separation that goes silent -- no progress output and no CPU time consumed -- for the stall window is failed with an error that says it stalled and for how long, and the separator process is killed so the next job starts a fresh one. Verify: contract test with a fake separator that stops all activity.
3. A separator process that exits mid-run is still reported immediately as today. Verify: existing behaviour, contract test.
4. No production code holds a total-duration cap on a separation request. Verify: `grep -rn "IsolateReadTimeoutSec\|response timeout after" --include=*.py Features WorkerService` returns 0.

## Call-Graph Audit

- **Flow docs:** `Features/AudioNormalization/audio-normalization.flow.md` (pre-encode separation stage), sub-flow of `transcode.flow.md`. One flow per operation.
- **Orchestration mode branches:** none added or touched; the change is inside the daemon client's wait loop.
- **Signal 5:** no flag, no config toggle.
- **Shared output columns:** none written. `TranscodeAttempts.ErrorMessage` gets a new stall message in place of the timeout message.
- **OOS categories:** below.

## Out of Scope

- (b) dot's failures on 2-hour episodes: the separator is killed for memory at the worker's 24 GB cap (kernel cgroup kill, 2026-10-08 22:19 MDT). Not a timeout; needs chunked separation. Separate directive.
- (b) wakko's separator runs on CPU because torch sees no Intel GPU device. Host/BIOS matter for the operator.
- (b) The 180-second start-up handshake timeout stays: start-up length does not depend on the input.
- (b) Other fixed timeouts in the audio vertical (ffmpeg downmix 1800 s, OpenVINO path 3600 s) are untouched; only the separation request the operator named.
- (b) The stall window is a constructor default (300 s), as the old cap was; not a settings-page knob.

## Constraints

- Deploy through `py deploy/deploy-fleet.py`.

## Escalation Defaults

- Risk tolerance: medium.

## Engineering Calls Already Made

- Operator 2026-10-11: detection is "is the process still working", not elapsed time.

## Status

### Files

```
Features/AudioNormalization/Services/DemucsDaemonClient.py
Features/AudioNormalization/Services/demucs-daemon.feature.md
Tests/Contract/TestDemucsDaemonLiveness.py (new)
```

### Plan

One commit. In `DemucsDaemonClient`: record the time of the last sign of work. A sign of work is any line on the separator's error stream (progress ticks included) or an increase in the separator process's consumed CPU time, sampled while waiting. The wait loop fails the request only when the gap since the last sign exceeds the stall window. The total cap and its parameter are deleted.

Seam changed:

| Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|
| demucs-daemon.S1 | `DemucsDaemonClient.IsolateVocals` | same call; raises `DemucsDaemonUnavailableError('Demucs daemon stalled: ...')` instead of `'... response timeout after 1800s'` | `DemucsVocalIsolationService` / `PreEncodeAudioPipeline` propagate any `DemucsDaemonUnavailableError` unchanged | contract test + live |

Deleted code, by bucket: the 1800 s cap is a defensive default against a hung daemon -- its purpose (do not block the worker forever) moves to the stall check; delete.

### Promotions

| Source artifact | Target file |
|---|---|
| Hang detection is lack of work (stderr output + CPU time), no total cap | `Features/AudioNormalization/Services/demucs-daemon.feature.md` C8 (same commit as the code) |

### Verification

### Decisions Made
