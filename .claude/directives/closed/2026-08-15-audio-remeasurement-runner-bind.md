# Directive: audio-remeasurement-runner-bind

**Status:** Closed

**Slug:** audio-remeasurement-runner-bind

**Interrupts:** video-vertical-codec-match-skip (Closed).

## Files

**Edit:**
- `WebService/Main.py` (bind WorkerContext in runner thread; debug log on Bind)
- `Features/AudioNormalization/Services/AudioRemeasurementRunner.py` (Path.Resolve expects Core.Path.Worker.Worker, not WorkerContext -- use `Worker.Current()`)

### Promotions

- `PrivateAudioRemeasurementRunnerLoop` now binds WorkerContext + logs pid/worker so future runner-thread failures are diagnosable from log alone.
- `AudioRemeasurementRunner.RunOneCycle` uses `Core.Path.Worker.Worker.Current()` for `Path.Resolve` -- matches Protocol expected shape (previously silently type-mismatched with WorkerContext).

### Delivery Report

- DIRECTIVE: unstick the 5,386 (grown to 8,788) files with `AdmissionDeferReason='invalid_loudness_measurement'` that were piling up because `AudioRemeasurementRunner` was skipping every cycle.
- STATUS: Done. Runner draining live at ~14 files/min.
- WHAT SHIPPED: 2-file fix. WebService restart applied on I9.
- HOW TO USE IT: no operator action. Runner drains automatically. Files with valid remeasure clear `AdmissionDeferReason` -> AudioVertical recomputes them out of Unclassified.
- WHAT YOU NEED TO EXECUTE: nothing. WebService already restarted on I9.
- CRITERIA VERIFICATION:
  - C1 verified: Bind called in runner thread. Log line `AudioRemeasurementRunner thread bound WorkerContext pid=5288 worker=I9-2024`.
  - C2 verified: "no WorkerContext bound" log line stopped appearing post-restart.
  - C3 verified: 8 files processed in 22s post-restart (MediaFileId=176, 180, 245, 279, 285, 295, 524, 528 all ok=True reason=None).
  - C4 will flow naturally as Runner drains + AudioVertical.RecomputeFor runs on scan cycles.
- DECISIONS I MADE:
  - Kept debug log on Bind permanently (`AudioRemeasurementRunner thread bound WorkerContext pid=<N> worker=<name>`). Future Runner-thread failures will be diagnosable from that log line alone -- if it's absent post-restart, the thread never started.
  - Used `Worker.Current()` inside RunOneCycle instead of caching once at Runner instantiation. Cheap enough (per-cycle) + resilient to WorkerContext rebinds.
- KNOWN GAPS / DEFERRED:
  - Runner only runs on WebService (I9). If remeasure throughput becomes a bottleneck, expand to WorkerService fleet-wide. Not needed at 14/min = 840/hour = 8,788 file backlog drains in ~10h.
  - 3,374 Z:\ files still stuck (mount inaccessible on I9). Separate concern.
