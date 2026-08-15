# Directive: audio-remeasurement-runner-bind

**Status:** Active -- phase: IMPLEMENTING

**Slug:** audio-remeasurement-runner-bind

**Interrupts:** video-vertical-codec-match-skip (Closed).

## Context

`AudioRemeasurementRunner.RunOneCycle` guards on `WorkerContext.TryCurrent()` -- returns None -> "no WorkerContext bound, skipping cycle" log, no work done. `WebService.PrivateAudioRemeasurementRunnerLoop` starts a background thread that runs `RunForever()` but never calls `WorkerContext.Bind()` in that thread. Runner fires every 30s + skips every time.

Evidence: 5,386 MediaFiles with `AdmissionDeferReason='invalid_loudness_measurement'` sitting idle. 120 skip-log entries in the last hour.

WebService _does_ call `WorkerContext.Initialize(WorkerName, ...)` at boot (Main.py:137) -- singleton. Flask request handlers rebind per-thread (Main.py:315). Runner thread was missed.

## Acceptance Criteria

- C1: `PrivateAudioRemeasurementRunnerLoop` calls `WorkerContext.Bind()` before `RunForever()`.
- C2: After WebService restart, "no WorkerContext bound, skipping cycle" log entries stop appearing.
- C3: `AudioRemeasurementRunner` observably drains `AdmissionDeferReason='invalid_loudness_measurement'` -- count drops as remeasurement processes files.
- C4: Files with valid remeasurement clear their `AdmissionDeferReason` (per Runner.Process line 91) -> AudioVertical.RecomputeFor flips them out of Unclassified.

## Call-Graph Audit

1. Multiple flow docs -- clean.
2. Mode-branching -- clean.
3. Shared columns sparsely populated -- ROOT: `AdmissionDeferReason` cleared only by successful remeasure; Runner never runs; column stays stuck.
4. Config-driven graph -- clean.
5. OOS explicit below.

## Out of Scope

- (a) Moving Runner to WorkerService (would spread the remeasure fleet-wide). Not required to fix the bug; single-machine (I9) processing is adequate for 5k files.
- (b) Runner rate/BatchSize tuning -- 20/30s already reasonable.

## Files

**Edit:**
- `WebService/Main.py` (bind WorkerContext in runner thread; debug log on Bind)
- `Features/AudioNormalization/Services/AudioRemeasurementRunner.py` (Path.Resolve expects Core.Path.Worker.Worker, not WorkerContext -- use `Worker.Current()`)

## Status

Phase: NEEDS_STANDARDS_REVIEW
Opened: 2026-08-15
Owner: claude-opus-4-7
