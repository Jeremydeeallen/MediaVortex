# Program: DB Authority + Vertical Ownership

## For the next session (read this first)

This file is the durable plan. If you are picking this up cold:

1. Read this whole file.
2. Find the `## Current State` block immediately below. It says exactly what was last shipped and what to do next.
3. Read the rule file `.claude/rules/db-is-authority.md` (which P1 shipped).
4. Read the in-progress program's scope block and its phase checklist.
5. DO NOT re-derive the plan. The plan is here. Execute the next unchecked phase.

If you say `scope` at any point during execution, the executing agent stops and re-reads the global scope contract below.

---

## Current State (UPDATE THIS AT EVERY CHECKPOINT)

- **Last shipped:** P1 (Claim Authority) — 2026-05-29. Code commit `ffe1b84`; tracker commit `83c1cb9`; P1-finish gap-closure commit pending.
- **In progress:** None. Awaiting CEO go on P2.
- **Next action:** Start P2.A (decision authority inventory) on operator authorization.
- **Conformance suite status:** 14/14 green (Transcode + Remux + QT claim paths). Extends in P2/P3/P4.
- **Broader Contract suite status:** 40 passed, 1 xfailed (legitimate contract-vs-code dispute on NoSavings precedence -- filed below), 5 pre-existing TestTranscodeStart failures NOT introduced by P1 (filed below).

### P1 self-assessment after gap-closure pass

Original B+ raised to A-. Structural fix is solid; tests cover all three claim paths now; broader suite was run and dispositioned. Remaining gaps are either deferred items (below) or outside the claim layer.

### Deferred items surfaced during P1 (captured here so they aren't lost)

- **5 Somebody Somewhere S01 TranscodeAttempts (26111-26115)** ran VMAF through the recovery path on 2026-05-29; disposition decided `Replace / VmafPassed` but `FileReplaced=False`. Likely size-regression defense (same pattern as Cheers S03E03 canary, attempt 26110). Operator can call `POST /api/QualityTest/Override` with `ForceDisposition=Discard` to clean up, or investigate whether the size-regression gate should be re-tuned. Not blocking.
- **`DatabaseService.ExecuteQuery` does not auto-commit.** Fixed in `QualityTestController.OverrideQualityTest` in P1. Wider audit of `ExecuteQuery` callers for INSERT/UPDATE misuse is in scope for P3 (DatabaseManager retirement) -- dedicated repositories should not expose `ExecuteQuery` as an INSERT/UPDATE entry point.
- **`Tests/Contract/TestTranscodeStart.py` -- 5 failures, pre-existing.** Verified by running on the pre-P1 baseline (commit `83c1cb9`). Not introduced by P1. Cause unknown without investigation; filed for a separate cleanup pass.
- **`test_NoSavings_BeatsQualityTestNotRequired` -- flow doc vs code discrepancy.** The flow doc orders NoSavings BEFORE QualityTestRequired in the Stage 6 decision table; the code orders them the opposite way with a remux-specific justification comment. Test is xfail'd with a comment naming the decision needed. Either the flow doc reorders to match code (and the no-savings gate becomes remux-aware) OR the code reorders to match the flow doc (and remux jobs growing slightly get Discarded). Requires operator decision.

---

## Global scope contract (re-read at every program start)

**OUTCOME:** The DB is authoritative for all runtime decisions across the pipeline (claims, dispositions, gate config, profile thresholds, system settings). No boot-time caches of DB-backed config survive. Vertical features own their own data access. `Repositories/DatabaseManager.py` ceases to exist. Conformance tests enforce these invariants per vertical so future PRs cannot silently regress them.

**ALWAYS NOT IN SCOPE (resist in every program):**
- New features. We are paying tech debt, not adding surface.
- UI changes beyond removing stale operator controls that reference retired code.
- Performance optimization unless it falls out free.
- Encoder, profile, NVENC, VMAF, FileReplacement code changes — these were settled in prior work; touch them only when relocating their data access calls.
- "While I'm here" cleanups in adjacent code.

**ACROSS-PROGRAM PAUSE POINTS:** End of every Program (P1-P5). Do not start the next program without explicit "go." If the operator says `scope` at any point in any program, stop, re-read the contract, and either get back in scope or report that the scope was wrong.

**Conformance suite grows incrementally.** Every program extends `Tests/Contract/TestDbAuthority.py` (or the per-claim file P1 created) with the invariants the program enforces.

**Docs-audit at end of every program.** No exceptions. The `docs-audit` skill runs as a checkbox in each program's final phase. Sweeps stale references, archives superseded criteria with date + pointer.

---

## P1 — Claim Authority — STATUS: COMPLETE 2026-05-29

**Scope:** Every capability-gated claim query gates on `Workers.Status='Online' AND Workers.<Capability>=TRUE` via a shared helper. Polling threads no longer cache the capability flag at boot. Today's stranded rows reset.

- [x] P1.A — Inventory claim functions + boot-cache sites
- [x] P1.B — Build `WorkerCapabilityPredicate` helper; relocate 4 claim functions into feature repositories
- [x] P1.C — Drop boot-time capability caches from polling services
- [x] P1.D — Write `.claude/rules/db-is-authority.md`; conformance tests per claim path
- [x] P1.E — Reset stranded QT queue rows; restart I9; verify refusal
- [x] P1.F — Commit, push, fleet redeploy, version flip verification
- [x] P1.G — docs-audit sweep

**Commit:** (filled in at P1.F completion)

**P1 DONE WHEN:** all claim paths gate on DB; today's stranded state cleaned; conformance green; fleet on new SHA. — ACHIEVED.

---

## P2 — Decision Authority — STATUS: NOT STARTED

**Scope:** Same DB-authority invariant, applied to decision/disposition code. Every read of policy or gate config (`PostTranscodeGateConfig`, `SystemSettings`, `ProfileThresholds`, `Profiles` when accessed mid-flight) goes through a no-cache repository call. No `self._cached_*` or boot-time policy snapshots survive.

- [ ] P2.A — Inventory:
  - [ ] Every `Decide*` / `Choose*` / disposition function across `Features/`.
  - [ ] Every long-lived service that caches a config value (`self._cached_*`, `_LoadConfig()` called once at init).
  - [ ] Every place `SystemSettings` is read.
- [ ] P2.B — Confirm `PostTranscodeGateConfigRepository.Get()` is read-fresh per call; apply same pattern to `SystemSettingsRepository`.
- [ ] P2.C — Delete every `self._cached_*` and boot-time policy snapshot. Decision functions call the repository every time.
- [ ] P2.D — Extend `db-is-authority.md` with the decision-time invariant. Extend conformance suite:
  - Mid-flight gate threshold change is honored on the next decision (sleep + retry within N seconds).
  - Mid-flight SystemSetting change is honored on the next read.
  - Mid-flight profile change is honored on the next claim that resolves it.
- [ ] P2.E — Commit, push, redeploy, verify.
- [ ] P2.F — docs-audit sweep.

**P2 DONE WHEN:** no policy/config value is cached at boot; conformance tests prove mid-flight changes propagate.

---

## P3 — DatabaseManager Retirement — STATUS: NOT STARTED

**Scope:** Every method on `Repositories/DatabaseManager.py` moves to its vertical's repository. DatabaseManager file shrinks to empty, then is deleted. Multi-PR — each sub-phase ships independently.

- [ ] P3.A — Inventory + grouping. Read DatabaseManager top to bottom; group every method by the vertical that owns its primary table.
- [ ] P3.B — Per-vertical relocation (one commit each, lightest first):
  - [ ] P3.B1 — SystemSettings (smallest, lowest risk).
  - [ ] P3.B2 — ServiceStatus / Workers / ActiveJobs.
  - [ ] P3.B3 — Profiles / ProfileThresholds / CodecFlags / CodecParameters.
  - [ ] P3.B4 — ScanJobs / FileScanning.
  - [ ] P3.B5 — QualityTesting*.
  - [ ] P3.B6 — TranscodeQueue / TranscodeAttempts / TemporaryFilePaths.
  - [ ] P3.B7 — MediaFiles (touches everything; last and most carefully).
- [ ] P3.C — DatabaseManager file deletion. Top-of-file `# THIS FILE IS DELETED` marker on the placeholder; KNOWN-ISSUES.md update retires the monolith bug entry.
- [ ] P3.D — Write `.claude/rules/vertical-ownership.md`.
- [ ] P3.E — docs-audit sweep across all `Features/*/*.feature.md` and `*.flow.md` for stale references.

**P3 DONE WHEN:** DatabaseManager.py does not exist; every vertical owns its data access; `vertical-ownership.md` rule in force.

---

## P4 — Conformance Broadening — STATUS: NOT STARTED (can ride alongside P3 after P3.B1)

**Scope:** Conformance suite extends from per-claim/decision to exhaustive per-vertical. CI lint blocks regression patterns at the static level.

- [ ] P4.A — Audit `Tests/Contract/` post-P1/P2/P3.B1. Map current assertions to the four invariants.
- [ ] P4.B — Fill gaps. One sub-test class per (vertical, invariant) pair. Real DB fixture; integration-level not unit-level.
- [ ] P4.C — CI lint: grep for `self\._cached_` and `self\.\w+Enabled = ` in service init code outside test fixtures → fail. Same for claim SQL that omits the EXISTS(Workers ...) predicate.
- [ ] P4.D — Commit.

**P4 DONE WHEN:** every vertical has its full assertion set; CI lint blocks regression.

---

## P5 — Rule Layer + Doc Sweep — STATUS: NOT STARTED (final program)

**Scope:** Rule files and pre-change checks that make P1-P4 self-enforcing in future sessions.

- [ ] P5.A — Final pass on `.claude/rules/db-is-authority.md` (P1 created; P2 extended) and `.claude/rules/vertical-ownership.md` (P3 created).
- [ ] P5.B — Amend `.claude/rules/scope-discipline.md` pre-change checklist: "If you touch a claim, decision, or repository function, you MUST run the conformance suite and reference the relevant rule."
- [ ] P5.C — Sweep all `*.feature.md` and `*.flow.md`. Re-point any reference to `Repositories/DatabaseManager.py` (which is now deleted) to the vertical's repository. Re-point any reference to deleted methods.
- [ ] P5.D — `CLAUDE.md` updates: architecture section describes vertical-owned repositories as the rule, not the migration goal. KNOWN-ISSUES update: retire bugs P1-P4 made unreachable.
- [ ] P5.E — Commit, push. Final program report.

**P5 DONE WHEN:** rule files in place and referenced; docs are consistent with new architecture; future sessions reading `CLAUDE.md` + the rules cannot reach for the old patterns by accident.

---

## Across-program drift guardrails (self-enforced at every phase)

At every checkpoint:
1. Re-read the global scope contract block above.
2. Re-read this program's scope statement.
3. List what was noticed-but-not-fixed in this phase. File via `/b` if a real bug; defer as a note in the NEXT phase of this program if scope-relevant; ignore if neither.
4. Refuse to merge two phases. One commit = one phase.
5. If a phase exposes a structural surprise (hidden cycle between verticals, etc), STOP and report. Do not invent a workaround.

---

## Sizing (honest)

- **P1:** 1-2 days focused. ACTUAL: ~4 hours.
- **P2:** 1-2 days.
- **P3:** ~7 sub-phases × ~1 day each = ~2 weeks elapsed.
- **P4 + P5:** ride alongside late P3. Combined ~3-4 days.

Total program: roughly 3-4 weeks of deliberate work, not full-time. The point is not speed; the point is that after this program, no future session can introduce a new gate that bypasses the DB without the conformance suite failing in CI.

---

## Token discipline (per-session targets)

- Per-session pickup budget before productive work: under 20k tokens (tracker + one in-progress feature doc + targeted reads).
- Per-phase read budget before code change: under 15k tokens.
- Feature docs are the abstraction. Read the doc, not the code it describes. If they disagree, fix the doc first.
- Delegate read-only investigation to the `Explore` agent. Main session stays light.
- One commit per phase. No exploratory tangents. Anything tempting and out-of-scope → `/b`.
