# Current Directive

**Set:** 2026-10-11
**Status:** Active -- phase: DELIVERING
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
10. A deploy to a host fails, naming the device, when the device its workers require for separation is not usable there; the host's workers are not restarted onto the new code by that run. Verify: live fleet deploy passes the check on dot (cuda) and wakko (xpu); the check run against a device the host lacks fails.
11. After a deploy, the GPU driver packages on a GPU host are held, so neither the automatic updater nor a manual "install all updates" replaces them. Verify: `apt-mark showhold` on dot and wakko after a fleet deploy.

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
deploy/deploy-baremetal-worker.py
deploy/worker-deploy-baremetal.flow.md
Features/AudioNormalization/Services/DemucsDaemonProtocol.py
```

### Plan

One commit. In `DemucsDaemonClient`: record the time of the last sign of work. A sign of work is any line on the separator's error stream (progress ticks included) or an increase in the separator process's consumed CPU time, sampled while waiting. The wait loop fails the request only when the gap since the last sign exceeds the stall window. The total cap and its parameter are deleted.

Second commit (chunking). The daemon cuts the input into 20-minute pieces that overlap by 10 seconds, separates all pieces in one separator call, crossfades each overlap and writes one vocals file and one background file in the place the caller already reads. An input that fits in one piece takes the old path untouched. The daemon announces the piece count so the client can report progress across the whole episode instead of restarting at each piece.

Prototype (I9, Dancing with the Stars S29E11, 84 min): whole-file peak 16-19 GB, chunked 6-7.4 GB, same wall time (~105 s). Chunked vs whole-file difference -27 dB (vocals) against -31 dB between two ordinary whole-file runs; at the four piece boundaries -38 dB.

Third commit (no fallbacks). The required device comes from the worker's hardware flags in `Workers` (`NvencCapable` -> cuda, else `QsvCapable` -> xpu, else cpu), read when the daemon is started, and is passed to the daemon on its command line. The daemon checks torch can use that device before announcing ready and exits with a named error otherwise; the client puts that error in the exception. Auto-detection and the optional Intel pre-warm import are deleted. The three measurement helpers (vocals level, source loudness, premix loudness) raise when ffmpeg gives no parsable number.

Deleted code, by bucket: `_DetectDevice` cpu return and the `None`/silence returns are defensive defaults on decision inputs -- producers audited (torch device, ffmpeg astats/loudnorm output), replaced by raises. `_PreWarmXpu` is an orphan: the package it imports is in no requirements file and torch 2.6 has native xpu.

Fourth commit (deploy guard). `deploy-baremetal-worker.py` gains two steps after requirements install: read the host's workers' hardware flags from `Workers`, map them to the required device with the same function the runtime uses, and prove in the freshly built venv that torch can run a small operation on that device; then `apt-mark hold` the GPU driver packages (NVIDIA packages on a cuda host; Intel compute runtime, media driver and the kernel metapackages that carry the Intel GPU driver on an xpu host). A host with no `Workers` rows yet (first deploy) skips both, visibly. The deploy doc loses its "fall back to CPU demucs" advice.

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
| Deploy proves the required device and holds GPU driver packages; CPU-downgrade advice removed | `deploy/worker-deploy-baremetal.flow.md` ST3 subsection + Failure Modes row (same commit as the code) |

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
- **Third commit:** `24923d5f`, pushed. Fleet on `24923d5f`, 9 workers OK. Demucs + audio-pipeline suites 53 pass; `TestAudioPipelineNoSilentFallback::test_audio_filter_emitter_routes_review_through_disposition_resolver` fails on `AudioFilterEmitter.py`, a file this directive does not touch.
- **8, live 2026-10-11:**
  - wakko-worker-1, attempt 99829 (S32E07): failed at once with `Demucs daemon did not start on device 'xpu': DEMUCS_DEVICE_ERROR required device 'xpu' is not usable by torch 2.6.0+xpu on client-b450m-01; refusing to separate on any other device`. No CPU run.
  - dot-worker-1, attempt 99830 (S32E06, 84 min): completed on cuda in 16.4 minutes wall, Dialog Boost emitted, placed, Compliant.
  - I9, real daemon: `--device cuda` starts in 1.1 s; `--device xpu` refused with the same error naming I9-2024.
  - CPU-only worker not run live (all four are Paused); covered by contract test.
- **wakko GPU restored 2026-10-11 (operator, BIOS):** Resizable BAR enabled; card memory window 256 MB -> 16 GB; Intel OpenCL lists `Intel(R) Arc(TM) B580 Graphics`; torch xpu available. Intel's tracker (intel/compute-runtime #872) states the runtime does not enable the card when Resizable BAR is off. The earlier kernel theory was wrong: booting 6.14 alone changed nothing.
- **8, wakko live after the fix:** attempt 99833, S28E05 (85 min), wakko-worker-1: daemon running with `--device xpu`, completed in 12.6 minutes wall (55.3 minutes on CPU earlier the same day for a 127-minute episode), Dialog Boost emitted, placed, Compliant. Cgroup peak 12.8 GiB of 14 GiB, no kernel memory kill, same boot id before and after.
- **Unexplained:** wakko reset without a clean shutdown twice within ten minutes of the BIOS change (boots at 15:23 and 15:33 MDT), the second seconds after attempt 99831 was claimed. Not reproduced since: stepped torch xpu test, Demucs on a 3-minute clip, and the full job above all ran with no reset.
- **Found, not fixed:** on boot after that reset, crash recovery logged `Unknown job type AudioFix` and `Failed to reset job ... in queue`; the job waited 31 minutes for stuck-job detection to release it.
- **Fourth commit:** `2a0d5e83`, pushed. Fleet on `2a0d5e83`, 9 workers OK.
- **10, live fleet deploy 2026-10-11:** `verify required device` OK on dot (`cuda`), wakko (`xpu`), mediavortex-workers (`cpu`). Negative: the same step asked for `xpu` on dot printed `[FAIL] ... torch cannot use 'xpu': ... Torch not compiled with XPU enabled` and returned False.
- **11, live:** `hold GPU packages` held 23 packages on dot and 11 on wakko; `apt-mark showhold` on each host lists them. CPU host skipped.
- **9:** contract tests (no block, missing field, no level, unreadable value all raise; `-inf` stays a value).
- **wakko GPU cause (evidence):** apt history shows kernel 6.14.0-37 -> 7.0.0-31 on 2026-09-22; current boot is 7.0.0-31; Intel OpenCL lists only the CPU device; torch reports zero xpu devices; BIOS P3.10 (2022) unchanged. Audio wall time on wakko: 7.3-8.0 min per hour of audio for weeks of 2026-08-10 through 2026-09-14, 30.0 for week of 2026-10-05.

### Decisions Made

- Chunking was absorbed into this directive rather than opened as its own: the liveness criterion could not be shown live without it.
- Liveness uses two signals, stderr output and CPU time, because the separator prints nothing while it writes its output files.
- Pieces go to the separator in one call, so the model loads once per episode as before.
- Split and join use the standard library and numpy; no new dependency.
- Chunked output is not sample-identical to whole-file output; the operator approved building it after seeing the measurements.
