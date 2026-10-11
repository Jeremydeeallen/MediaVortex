# Current Directive

**Set:** 2026-10-11
**Status:** Active -- phase: IMPLEMENTING
**Slug:** demucs-liveness
**Replaces:** `directives/closed/2026-10-11-remove-savings-gate.md` (closed Success)

## Outcome

A vocal-separation run is failed as hung only when it has stopped working, not because it has run for 30 minutes. Long episodes separated on CPU (wakko: 85-119 minute episodes, about 30 minutes of separation) finish instead of being killed at the 1800-second mark. Long episodes also stop running the worker out of memory: separation memory no longer grows with episode length. Operator 2026-10-11: "We shouldn't be doing a 30 minute timeout we should be watching to see if the process is still working. That's the correct detection."

## Acceptance Criteria

1. A separation that keeps working is never failed for elapsed time, however long it runs. Verify: contract test drives a fake separator that stays active past any fixed cap; live run of a long episode on wakko-worker-1 whose separation exceeds 30 minutes or previously timed out.
2. A separation that goes silent -- no progress output and no CPU time consumed -- for the stall window is failed with an error that says it stalled and for how long, and the separator process is killed so the next job starts a fresh one. Verify: contract test with a fake separator that stops all activity.
3. A separator process that exits mid-run is still reported immediately as today. Verify: existing behaviour, contract test.
4. No production code holds a total-duration cap on a separation request. Verify: `grep -rn "IsolateReadTimeoutSec\|response timeout after" --include=*.py Features WorkerService` returns 0.
5. Separating a long episode uses about the same memory as separating a 20-minute one. Verify: live Audio job on a ~2-hour episode completes on dot-worker-1 (killed at its 24 GB cap before) and on a long episode on wakko-worker-1 (killed at its 14 GB cap before), with no kernel memory kill.
6. The joined result has no gap, repeat or click where pieces meet. Verify: contract test splits and rejoins a known signal and gets the same signal back; prototype measurement (below) shows piece boundaries match whole-file output better than the rest of the file does.
7. Episodes short enough for one piece are separated exactly as before. Verify: contract test of the piece plan.
8. Separation runs on the device the worker's hardware calls for -- NVIDIA GPU where the worker has one, Intel GPU where it has one, CPU only on a worker with neither -- or the job fails with an error naming the required device and the host. It never runs on a slower device than the hardware calls for. Verify: contract tests; live: wakko-worker-1 (Intel GPU not visible to torch since the 2026-09-22 kernel change) fails an Audio job with that error instead of running 4x slower on CPU; dot-worker-1 and a CPU-only worker still complete.
9. A loudness or level measurement in the separation path that yields no usable number fails the job with the measurement's output in the error. It is never replaced by silence, by "unknown", or by a different loudness method. Verify: contract tests.

## Call-Graph Audit

- **Flow docs:** `Features/AudioNormalization/audio-normalization.flow.md` (pre-encode separation stage), sub-flow of `transcode.flow.md`. One flow per operation.
- **Orchestration mode branches:** none added or touched; the change is inside the daemon client's wait loop.
- **Signal 5:** no flag, no config toggle.
- **Shared output columns:** none written. `TranscodeAttempts.ErrorMessage` gets a new stall message in place of the timeout message.
- **OOS categories:** below.

## Out of Scope

- (b) Restoring wakko's Intel GPU for torch (kernel 6.14 -> 7.0 on 2026-09-22; compute runtime enumerates no GPU since) is a host change: reboot into the still-installed 6.14 kernel. Operator executes. Until then criterion 8 makes wakko's Audio jobs fail loud.
- (b) Found, not Demucs: `AudioPreEncodeFacade.PersistSourceLoudness` logs and swallows a failed DB write; `PreEncodeAudioPipeline._SelectPreferredAudioIndex` logs a warning and picks the first stream when the preference lookup throws. Named here, not changed.
- (b) The 180-second start-up handshake timeout stays: start-up length does not depend on the input.
- (b) Other fixed timeouts in the audio vertical (ffmpeg downmix 1800 s, OpenVINO path 3600 s) are untouched; only the separation request the operator named.
- (b) The stall window is a constructor default (300 s), as the old cap was; not a settings-page knob. Piece length (20 min) and overlap (10 s) are constants for the same reason: they bound memory, they are not operator tuning.

## Constraints

- Deploy through `py deploy/deploy-fleet.py`.

## Escalation Defaults

- Risk tolerance: medium.

## Engineering Calls Already Made

- Operator 2026-10-11: detection is "is the process still working", not elapsed time.
- Operator 2026-10-11, after the prototype: "do chunking". Absorbed here because criterion 1 cannot be shown live without it: the wakko live run got past 30 minutes and was then killed for memory at 14 GB.
- Operator 2026-10-11: "we cannot close demucs if there are bugs. The demucs needs to be a complete solution. If it isn't working somewhere it needs to FAIL loud. Fallbacks are not acceptable." Criteria 8-9.

## Status

### Files

```
Features/AudioNormalization/Services/DemucsDaemonClient.py
Features/AudioNormalization/Services/demucs-daemon.feature.md
Tests/Contract/TestDemucsDaemonLiveness.py (new)
Features/AudioNormalization/Services/DemucsDaemonEntry.py
Features/AudioNormalization/Services/DemucsChunking.py (new)
Tests/Contract/TestDemucsChunking.py (new)
Features/AudioNormalization/Services/DemucsVocalIsolationService.py
Tests/Contract/TestDemucsNoFallback.py (new)
Features/AudioNormalization/Services/DemucsDaemonProtocol.py
```

### Plan

One commit. In `DemucsDaemonClient`: record the time of the last sign of work. A sign of work is any line on the separator's error stream (progress ticks included) or an increase in the separator process's consumed CPU time, sampled while waiting. The wait loop fails the request only when the gap since the last sign exceeds the stall window. The total cap and its parameter are deleted.

Second commit (chunking). The daemon cuts the input into 20-minute pieces that overlap by 10 seconds, separates all pieces in one separator call, crossfades each overlap and writes one vocals file and one background file in the place the caller already reads. An input that fits in one piece takes the old path untouched. The daemon announces the piece count so the client can report progress across the whole episode instead of restarting at each piece.

Prototype (I9, Dancing with the Stars S29E11, 84 min): whole-file peak 16-19 GB, chunked 6-7.4 GB, same wall time (~105 s). Chunked vs whole-file difference -27 dB (vocals) against -31 dB between two ordinary whole-file runs; at the four piece boundaries -38 dB.

Third commit (no fallbacks). The required device comes from the worker's hardware flags in `Workers` (`NvencCapable` -> cuda, else `QsvCapable` -> xpu, else cpu), read when the daemon is started, and is passed to the daemon on its command line. The daemon checks torch can use that device before announcing ready and exits with a named error otherwise; the client puts that error in the exception. Auto-detection and the optional Intel pre-warm import are deleted. The three measurement helpers (vocals level, source loudness, premix loudness) raise when ffmpeg gives no parsable number.

Deleted code, by bucket: `_DetectDevice` cpu return and the `None`/silence returns are defensive defaults on decision inputs -- producers audited (torch device, ffmpeg astats/loudnorm output), replaced by raises. `_PreWarmXpu` is an orphan: the package it imports is in no requirements file and torch 2.6 has native xpu.

Seam changed:

| Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|
| demucs-daemon.S1 | `DemucsDaemonClient.IsolateVocals` | same call; raises `DemucsDaemonUnavailableError('Demucs daemon stalled: ...')` instead of `'... response timeout after 1800s'` | `DemucsVocalIsolationService` / `PreEncodeAudioPipeline` propagate any `DemucsDaemonUnavailableError` unchanged | contract test + live |
| demucs-daemon.S3 | `DemucsDaemonEntry._IsolateOnce` | long input: separator called with N piece files, outputs joined to `OutputDir/<Model>/vocals.wav` + `no_vocals.wav` (16-bit PCM, separator's sample rate) | caller reads the same two paths as before | contract test + live |
| daemon stderr -> client progress | daemon | line `MV_DEMUCS_CHUNKS <n> <total_seconds>` before a multi-piece run | client scales per-piece progress to whole-episode percent | contract test |

Deleted code, by bucket: the 1800 s cap is a defensive default against a hung daemon -- its purpose (do not block the worker forever) moves to the stall check; delete.

### Promotions

| Source artifact | Target file |
|---|---|
| Hang detection is lack of work (stderr output + CPU time), no total cap | `Features/AudioNormalization/Services/demucs-daemon.feature.md` C8 (same commit as the code) |
| Long input is separated in overlapping pieces and joined; progress marker line | `Features/AudioNormalization/Services/demucs-daemon.feature.md` C12, S3, S4, Files (same commit as the code) |
| Device is required from worker hardware flags, never detected; measurements raise instead of defaulting | `Features/AudioNormalization/Services/demucs-daemon.feature.md` C5, C13 (same commit as the code) |

### Verification

- **Commits:** `82549971` (liveness), `f2e5da1a` (chunking). Pushed. Fleet on `f2e5da1a`, 9 workers OK.
- **Tests:** chunking, liveness, protocol, progress-parser suites 24/24. Claim tests not run (they take live queue rows). `TestFailLoud` baseline tests fail the same with and without these changes.
- **1, live:** wakko-worker-1, attempt 99827, Dancing with the Stars S33E10 (127 min): 55.3 minutes wall on CPU, well past the old 1800 s mark, completed, placed. Earlier the same day (liveness only, before chunking) attempt 99826 ran 30 min 36 s without a timeout and was then killed for memory at 14 GB.
- **2, 3:** contract tests (silent process failed as stalled within the window; exited process reported at once).
- **4:** production grep returns 0.
- **5, live 2026-10-11:**
  - dot-worker-1, attempt 99828, S31E03 (120 min): 12.3 minutes wall, completed, Dialog Boost emitted, placed, Compliant. Worker cgroup peak 14.6 GiB of a 24 GiB cap, no kernel memory kill, no restart. The 119-minute S31E01 was killed at 24.2 GB on 2026-10-08.
  - wakko-worker-1, attempt 99827 (above): completed, Dialog Boost emitted, placed, Compliant. No kernel memory kill, no restart. Cgroup peak reads equal to the 14 GiB cap; that counter includes file cache, so it shows the cap was reached and reclaimed from, not how much headroom the separator had.
- **6:** split-then-join of a random signal returns it within 1 LSB. Through the real daemon on I9 (84-minute input): one vocals + one background file, piece directory removed, progress 0 -> 100 without going backwards, -27.3 dB vs whole-file on vocals (prototype: -27 dB; two whole-file runs differ by -31 dB).
- **7:** piece-plan contract tests; inputs up to 21 minutes are not split.

### Decisions Made

- Chunking was absorbed into this directive rather than opened as its own: the liveness criterion could not be shown live without it.
- Liveness uses two signals, stderr output and CPU time, because the separator prints nothing while it writes its output files.
- Pieces go to the separator in one call, so the model loads once per episode as before.
- Split and join use the standard library and numpy; no new dependency.
- Chunked output is not sample-identical to whole-file output; the operator approved building it after seeing the measurements.
