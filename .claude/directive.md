# Concurrency Cap Live Reload

**Slug:** concurrency-cap-live-reload
**Status:** Active -- phase: IMPLEMENTING
**Opened:** 2026-08-05
**Interrupts:** e2e-bug-fixes

## Ask

`Workers.MaxConcurrentJobs` is DB-authoritative per `db-is-authority.md`, but `WorkerLoopService` caches it into a `threading.BoundedSemaphore` at boot. Operator edits (GUI or SQL) don't take effect until worker restart -- violates the rule.

## Fix shape (KISS pass, 2026-08-05)

No new class. Two inline lines in `ProcessQueueLoop`:

```python
Cap = self.WorkersRepo.GetMaxConcurrentJobs(self.WorkerName)
if sum(1 for T in self.ActiveJobs if T.is_alive()) >= Cap:
    time.sleep(2); continue
```

- Delete `BoundedSemaphore` from `WorkerLoopService`.
- `WorkersRepository.GetMaxConcurrentJobs(WorkerName) -> int` reads fresh; fail-loud on NULL / <=0.
- Live thread count via `Thread.is_alive()` on existing `ActiveJobs` list. No new counter.
- DB gate (`BuildInflightCapPredicate`) untouched. Hard invariant preserved.

Symmetric defect in `ProcessQualityTestQueueService` bundled -- same 2-line fix. Confirming shape at NEEDS_PLAN; if same, in-scope for C10.

## Contract

Full success criteria + Files + Progress live in `Features/TranscodeJob/Worker/concurrency-cap-live-reload.feature.md`. Promotion target at DELIVERING: amend `worker-loop.feature.md` C4 restart-required clause.

## Criteria (delta from feature doc)

C1-C9 per feature doc. C10 added at NEEDS_PLAN: `ProcessQualityTestQueueService` gets same fix if same shape confirmed at NEEDS_STANDARDS_REVIEW audit.

## Phase machine

NEEDS_STANDARDS_REVIEW -> NEEDS_PLAN -> NEEDS_DOC_PREREAD -> IMPLEMENTING -> VERIFYING -> DELIVERING

## Files

See feature doc `## Files` section.

## Call-Graph Audit

_Populated at NEEDS_STANDARDS_REVIEW exit. Five signals to check:_
- Multiple flow docs for one conceptual operation
- Mode-branching at orchestration level
- Shared output columns mode-sparse
- OOS ambiguity
- Config-driven call-graph shape

## Out of Scope

- QT worker `MaxConcurrentQualityTestJobs` cache (audit at NEEDS_STANDARDS_REVIEW; expand or file separately) -- category (a) if cheap, (b) if not
- Other cached-DB-value anti-patterns in worker path -- separate directive
- `MaxCpuThreads` cache -- separate directive
- GUI editor for MaxConcurrentJobs -- BUG-0025 scope

### Promotions

_Populated at DELIVERING. Each row: `<directive artifact> -> <target *.feature.md / *.flow.md>`._
