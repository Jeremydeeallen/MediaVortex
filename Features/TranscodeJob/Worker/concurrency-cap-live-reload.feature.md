# Concurrency Cap Live Reload

**Slug:** concurrency-cap-live-reload

## Interrupts: e2e-bug-fixes

## What It Does

Removes the boot-time cache of `Workers.MaxConcurrentJobs` in `WorkerLoopService` so operator edits to that column take effect on the next claim cycle without worker restart. Restores compliance with `.claude/rules/db-is-authority.md` (DB is SoT; no per-loop caches of DB values).

Current defect: `WorkerLoopService.__init__` seeds a `threading.BoundedSemaphore(MaxConcurrentJobs)` once at boot (`Features/TranscodeJob/Worker/WorkerLoopService.py:24-30`). All later claim decisions gate on that cached semaphore capacity. `Workers.MaxConcurrentJobs` UPDATE at runtime is a no-op until worker restart. `worker-loop.feature.md` C4 currently documents this as required behavior ("Mid-flight resize of `MaxConcurrentJobs` requires worker restart -- semaphore capacity is boot-fixed"). Amended at DELIVERING.

KISS shape (revised from Option C, 2026-08-05): no new class. `ProcessQueueLoop` inlines two lines -- fresh SELECT of `MaxConcurrentJobs` via `WorkersRepository.GetMaxConcurrentJobs(WorkerName)`, live count of `ActiveJobs` via `Thread.is_alive()`. `BoundedSemaphore` deleted. DB gate (`Core.Database.WorkerCapabilityPredicate.BuildInflightCapPredicate`) untouched; hard invariant preserved.

Symmetric defect confirmed in `Features/QualityTesting/ProcessQualityTestQueueService.py` -- `self.MaxConcurrentJobs` cached in `__init__` at line 28, checked in loop at line 144. Same 2-line fix using `WorkersRepository.GetMaxConcurrentQualityTestJobs`. Bundled in C10 -- "never touch again" beats filing BUG-NNNN to redo the same fix later.

## Success Criteria

C1. **Boot-cache eliminated in transcode claim path.** `grep -rn "BoundedSemaphore\|SlotSemaphore\|self\.MaxConcurrentJobs\s*=" Features/TranscodeJob/Worker/` returns 0 production hits. Kills both the `BoundedSemaphore` and any regression that re-caches the cap under a different name. Verifiable: `Tests/Contract/TestWorkerLoopSlotCap.py::test_no_boot_cache`.

C2. **Transcode cap read fresh per iteration.** `WorkerLoopService.ProcessQueueLoop` calls `WorkersRepo.GetMaxConcurrentJobs(WorkerName)` at the top of every iteration; live in-flight count = `sum(1 for T in self.ActiveJobs if T.is_alive())`. No cached integer on `self`. Verifiable: `Tests/Contract/TestWorkerLoopSlotCap.py::test_fresh_read_per_iteration` mocks repo, counts calls under N iterations, asserts equality.

C3. **Live upshift (transcode).** Worker running 1 job with `MaxConcurrentJobs=1`. `UPDATE Workers SET MaxConcurrentJobs=2 WHERE WorkerName='I9-2024'`. Within one poll cycle (`ProcessQueueLoop` sleep = 2s + one claim), a second in-flight claim observable in `ActiveJobs WHERE WorkerName='I9-2024'`. Verifiable: operator smoke report on I9 (see C9).

C4. **Live downshift (transcode).** Worker running 2 jobs with `MaxConcurrentJobs=2`. `UPDATE Workers SET MaxConcurrentJobs=1`. Both in-flight jobs run to completion (no mid-flight kill). New claims blocked until in-flight count < 1. Verifiable: `Tests/Contract/TestWorkerLoopSlotCap.py::test_downshift_lets_inflight_drain` fakes ActiveJobs list, drops cap via mock repo, asserts claim path skips.

C6. **Zero-cap and negative-cap fail loud.** `WorkersRepository.GetMaxConcurrentJobs` raises `ValueError` when `Workers.MaxConcurrentJobs IS NULL` or `<= 0`. No silent `max(1, ...)` coercion in the claim path (per `fail-loud.md`). Verifiable: `Tests/Contract/TestWorkerLoopSlotCap.py::test_fail_loud_on_bad_cap`.

C7. **DB gate untouched.** `Core.Database.WorkerCapabilityPredicate.BuildInflightCapPredicate` returns the same SQL before and after. Diff across the directive is 0 lines. `Tests/Contract/TestClaimAuthority.py` still 100% green. Verifiable: diff review + test run.

C8. **worker-loop.feature.md C4 amended (at DELIVERING).** Sentence "Mid-flight resize of `MaxConcurrentJobs` requires worker restart -- semaphore capacity is boot-fixed" replaced with "Mid-flight resize of `MaxConcurrentJobs` takes effect on the next iteration; `ProcessQueueLoop` reads the cap fresh from `Workers` per iteration (see `concurrency-cap-live-reload.feature.md`)." Verifiable: grep of old sentence returns 0 in amended tree.

C9. **Live smoke on I9.** With I9 worker running at `MaxConcurrentJobs=1`, `UPDATE Workers SET MaxConcurrentJobs=2 WHERE WorkerName='I9-2024'` (no restart). Within one poll cycle, `ActiveJobs WHERE WorkerName='I9-2024'` reaches 2 when transcode queue has pending jobs. Then flip to 3, observe 3rd within one cycle. Evidence: operator smoke report in directive close.

C10. **QT worker same fix (bundled).** `ProcessQualityTestQueueService.ProcessQueueLoop` (line 144) reads `WorkersRepo.GetMaxConcurrentQualityTestJobs(WorkerName)` fresh per iteration. `self.MaxConcurrentJobs` field deleted from `__init__` (line 28). `grep "self\.MaxConcurrentJobs\s*=" Features/QualityTesting/` returns 0. Same live-upshift/downshift semantics as C3/C4. Verifiable: existing QT test file extended (locked at IMPLEMENTING).

## Scope

**In scope:**
- `WorkerLoopService` slot gate rewrite (delete BoundedSemaphore; introduce `LiveSlotGate`).
- New repo method `WorkersRepository.GetMaxConcurrentJobs(WorkerName)` (SELECT-one against `Workers`).
- Contract + live tests per C1-C9.
- `worker-loop.feature.md` C4 amendment (at DELIVERING).

**Out of scope (categorized per `call-graph-audit.md`):**

- **(a) In-flight resolved:** QT worker `MaxConcurrentQualityTestJobs` cache -- confirmed same shape at NEEDS_PLAN, moved in-scope as C10. No divergent duplicate survives.
- **(b) Tolerated debt (filed):** `Workers.MaxCpuThreads` cache in encoder path -- same antipattern class. Filed as new BUG-NNNN at IMPLEMENTING to keep visible.
- **(b) Tolerated debt (filed):** `Workers.AcceptsInterlaced` / `TranscodeEnabled` / `RemuxEnabled` boot-cached in `WorkerLoopService.__init__` -- capability poller handles the Enabled flags (starts/stops loops); `AcceptsInterlaced` is boot-fixed but rarely changes. Same BUG-NNNN as MaxCpuThreads.
- **(b) Tolerated debt:** GUI editor for `MaxConcurrentJobs` -- BUG-0025 already tracks UI-uneditable flags. Not a new file.
- **(a) In-flight preserved:** `worker-loop.feature.md` C4 -- only the restart-required clause changes (C8). Rest of C4 preserved.

## Files

**Edit:**
- `Features/TranscodeJob/Worker/WorkerLoopService.py` -- delete `SlotSemaphore`; inject + use `LiveSlotGate`
- `Features/Workers/WorkersRepository.py` -- add `GetMaxConcurrentJobs(WorkerName) -> int` (fail-loud on NULL / <=0)
- `Composition/WorkerCompositionRoot.py` -- inject repo + gate into `WorkerLoopService`
- `Tests/Contract/TestWorkerLoopSlotCap.py` -- update C4-shape assertions to match new gate
- `Features/TranscodeJob/Worker/worker-loop.feature.md` -- amend C4 (at DELIVERING)

**Create:**
- `Features/TranscodeJob/Worker/concurrency-cap-live-reload.feature.md` (this)
- `Features/TranscodeJob/Worker/LiveSlotGate.py` -- SRP class: `TryAcquire() / Release() / InFlight()` reading cap fresh per acquire
- `Tests/Contract/TestSlotCapLiveReload.py`
- `Tests/Live/TestConcurrencyLiveReloadUpshift.py` (optional if C9 operator smoke suffices)

## Status

**Phase:** NEEDS_STANDARDS_REVIEW
**Owner:** claude-opus-4-7
**Opened:** 2026-08-05
**Stack position:** top (interrupts e2e-bug-fixes)

### Progress

- [ ] NEEDS_STANDARDS_REVIEW: read `.claude/rules/*.md` (esp `db-is-authority.md`, `claim-authority.md`, `fail-loud.md`); call-graph audit five signals against WorkerLoopService + WorkersRepository + ProcessQualityTestQueueService (symmetric case)
- [x] NEEDS_PLAN: `## Files` locked; `## Seams` populated per `seam-verification.md`
- [x] NEEDS_PLAN: QT worker MaxConcurrentQualityTestJobs bundled as C10
- [x] NEEDS_PLAN: KISS audit -- C5 dropped (single-poll-thread; no contention path); C1/C10 grep hardened against boot-cache regression
- [ ] IMPLEMENTING: file BUG-NNNN for broader Workers-cached-column antipattern (MaxCpuThreads / AcceptsInterlaced)
- [ ] IMPLEMENTING: grep for other MaxConcurrentJobs read sites; lock Files
- [ ] NEEDS_DOC_PREREAD: read `worker-loop.feature.md`, `WorkerService.feature.md`, `claim-authority.md`
- [ ] IMPLEMENTING: `LiveSlotGate.py` + `WorkersRepository.GetMaxConcurrentJobs`
- [ ] IMPLEMENTING: `WorkerLoopService` rewrite (delete SlotSemaphore, inject gate)
- [ ] IMPLEMENTING: `WorkerCompositionRoot` wiring
- [ ] IMPLEMENTING: contract test `TestSlotCapLiveReload` (C1-C6)
- [ ] IMPLEMENTING: update `TestWorkerLoopSlotCap` (C7 still-green)
- [ ] VERIFYING: contract tests all green
- [ ] VERIFYING: live smoke on I9 -- restart with cap=2, observe 2 concurrent; flip to 3 mid-flight, observe 3rd (C9)
- [ ] DELIVERING: `worker-loop.feature.md` C4 amended (C8)
- [ ] DELIVERING: `### Promotions` populated; close report; stack pop
