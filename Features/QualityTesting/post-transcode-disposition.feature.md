# Feature: Post-Transcode Disposition (unified, data-driven, auditable)

**Slug:** post-transcode-disposition

## What It Does

Replaces the five split decision sites in the post-transcode pipeline with a single function `DecidePostTranscodeDisposition(TranscodeAttemptId)` that returns `(Disposition, Reason, AuditPayload)`. Every gate input lives in a typed DB column (no `SystemSettings` KV rows for thresholds, no Python constants). Every disposition records the reason on `TranscodeAttempts` so an operator can answer "why didn't this replace?" with a single SQL query instead of grepping logs.

Retires the legacy chain (`ShouldQualityTestService`, `_ReplaceFileDirectly`, `BypassVMAFCheck` parameter, `ProcessFileReplacementWithVMAF`, three `SystemSettings` rows) entirely. No backwards-compat shims.

## Concern

Operator dogfood, 2026-05-10. Sister Wives S04E05 transcode succeeded but VMAF never ran -- `ServiceStatus.QualityTestService='Paused'` silently routed to bypass-replace, which then silently failed. The 720p output was deleted by failure cleanup, no detail logs, no audit trail. Three layered failures all hid behind the same vague "Quality test processing failed" log. The decisions are spread across `ShouldQualityTestService` (paused?), `QualityTestingBusinessService.UpdateQualityTestResults` (PassesThreshold), `CheckAndTriggerAutoReplace` (auto-fire replace), `FileReplacementBusinessService.ProcessFileReplacement` (BypassVMAFCheck branch), `ProcessFileReplacementWithVMAF` (the duplicate). No place says "given X state, the disposition is Y because Z". This feature creates that place.

## Success Criteria

### A. Single decision function

1. There is exactly one function `DecidePostTranscodeDisposition(TranscodeAttemptId) -> (Disposition: str, Reason: str, AuditPayload: dict)` in the codebase. Verifiable: `grep -rn "def DecidePostTranscodeDisposition" --include="*.py"` returns exactly one definition; no callers invoke any of the legacy decision functions.

2. The function is **idempotent** for non-`Pending` dispositions: calling it twice on a TranscodeAttempt that already has a final disposition returns the same `(Disposition, Reason)` and does NOT trigger any side effect (no second replace, no log spam beyond a single DEBUG line). Verifiable: integration test invokes the function twice, asserts the second call returns the cached decision and produces no new `MediaFilesArchive` row.

3. The function is the **only** code path that decides whether a transcoded file gets replaced, requeued, or discarded. `FileReplacementBusinessService.ProcessFileReplacement` never makes a VMAF-related decision itself; it executes the disposition the function already committed. Verifiable: `ProcessFileReplacement` has no `BypassVMAFCheck` parameter, no read of any VMAF threshold, and refuses to run unless `TranscodeAttempts.Disposition = 'Replace'`.

### B. Decision-table conformance

4. For every row in the canonical decision table in `transcode.flow.md` Stage 6, an integration test asserts the corresponding `(Disposition, Reason)` is returned. Adding/removing/changing a row in the code MUST be accompanied by the matching flow-doc edit (PR review check). Verifiable: the test suite has at least one assertion per documented row; CI fails if a row's expected outcome and actual outcome diverge.

5. The decision is **deterministic**: the same inputs always produce the same `(Disposition, Reason)`. There is no time-of-day-dependent or worker-identity-dependent branch. Verifiable: a unit test runs each table row twice with a fixed clock and asserts identical output.

### C. Database schema (typed, no KV)

6. New table `PostTranscodeGateConfig` exists as a single-row scalar-config table with typed columns:
   ```
   Id INT PRIMARY KEY DEFAULT 1
   VmafAutoReplaceMinThreshold NUMERIC NOT NULL DEFAULT 88
   VmafAutoReplaceMaxThreshold NUMERIC NOT NULL DEFAULT 98
   WhenVmafUnavailable TEXT NOT NULL DEFAULT 'block' CHECK (WhenVmafUnavailable IN ('block','bypass'))
   LastUpdated TIMESTAMP DEFAULT NOW()
   CHECK (Id = 1)
   CHECK (VmafAutoReplaceMinThreshold <= VmafAutoReplaceMaxThreshold)
   ```
   Verifiable: `\d PostTranscodeGateConfig` shows the columns and constraints; `INSERT INTO PostTranscodeGateConfig (Id) VALUES (2)` fails the single-row CHECK.

7. `TranscodeAttempts` gains three columns:
   ```
   Disposition TEXT NULL
       CHECK (Disposition IS NULL OR Disposition IN
              ('Pending','Replace','Reject','NoReplace','Requeue','Discard'))
   DispositionReason TEXT NULL
   DispositionDecidedAt TIMESTAMP NULL
   ```
   Index on `(Disposition, DispositionDecidedAt)` for the operator audit query. Verifiable: `\d TranscodeAttempts` shows the columns and CHECK; the index exists.

8. The legacy `SystemSettings` rows are deleted by the migration:
   - `VMAFAutoReplaceMinThreshold`
   - `VMAFAutoReplaceMaxThreshold`
   - `QualityTestEnabled` (global; per-worker `Workers.QualityTestEnabled` covers the use case)
   Verifiable: `SELECT * FROM SystemSettings WHERE SettingKey IN ('VMAFAutoReplaceMinThreshold','VMAFAutoReplaceMaxThreshold','QualityTestEnabled')` returns zero rows post-migration.

### D. Audit trail (queryable)

9. Every disposition decision (other than `Pending`) writes the three new columns on `TranscodeAttempts` in a single UPDATE. Verifiable: query a few hours after a populate run -- every successful transcode attempt has `Disposition NOT NULL` and `DispositionReason NOT NULL`; failed attempts have `Disposition='Discard'` with `Reason='TranscodeFailed'`.

10. The reason vocabulary is closed. Allowed values: `TranscodeFailed`, `NoSavings`, `QualityTestNotRequired`, `AwaitingVmaf`, `VmafBelowMin`, `VmafPassed`, `VmafAboveMax`, `VmafServicePaused`, `VmafServicePausedBypassed`, `VmafCapabilityNotConfigured`, `QualityTestingGloballyDisabled`. No free-text reasons. Verifiable: `SELECT DISTINCT DispositionReason FROM TranscodeAttempts WHERE DispositionReason IS NOT NULL` returns only values from this list.

11. The "why didn't this replace?" query works: `SELECT FilePath, Disposition, DispositionReason FROM TranscodeAttempts WHERE Success=true AND FileReplaced=false AND Disposition <> 'Pending'` returns one row per stuck attempt with an enumerable reason. Verifiable: induce three stuck cases (NoSavings, VmafBelowMin, VmafServicePaused), run the query, observe three rows with the expected reasons.

### E. Logs (one per decision)

12. Every disposition decision logs exactly one INFO line:
    `Disposition for TranscodeAttempt <id>: <Disposition> (Reason=<Reason>) inputs=<json>`
    where `<json>` enumerates QualityTestRequired, ServiceStatus, VMAF score, MinThreshold, MaxThreshold, WhenVmafUnavailable. No additional log noise per decision (the `LogFunctionEntry` boilerplate is gone). Verifiable: a test transcode produces a single matching log line on `Logs.Message`; the JSON payload is parseable.

13. The opaque "Quality test processing failed for TranscodeAttempt <id>: File replaced automatically because Quality testing service is paused" message pattern is gone. Verifiable: post-deploy, `SELECT COUNT(*) FROM Logs WHERE Message LIKE '%Quality test processing failed%'` does not grow.

### F. Legacy code removal (no backward-compat)

14. The following symbols are deleted from the codebase:
    - `Features/QualityTesting/ShouldQualityTestService.py` (entire file)
    - `_ReplaceFileDirectly` helper
    - `BypassVMAFCheck` parameter on `FileReplacementBusinessService.ProcessFileReplacement`
    - `FileReplacementBusinessService.ProcessFileReplacementWithVMAF` (collapse into single `ProcessFileReplacement`)
    - `QualityTestingBusinessService.CheckAndTriggerAutoReplace`
    - The hardcoded `>= 80.0` (and the new DB-fallback variant) in `QualityTestingBusinessService.UpdateQualityTestResults`'s `PassesThreshold` calculation -- the disposition function owns the comparison
    - `IsQualityTestEnabled` on `ProcessTranscodeQueueService` (replaced by per-worker capability + disposition logic)
    - `Workers.WorkerQualityTestEnabled` cached attribute on the long-lived service instance
   Verifiable: `grep -rn "ShouldQualityTestService\|_ReplaceFileDirectly\|BypassVMAFCheck\|ProcessFileReplacementWithVMAF\|CheckAndTriggerAutoReplace" --include="*.py"` returns zero hits in `Features/`, `Services/`, `Repositories/`, `WorkerService/` (the feature doc and KNOWN-ISSUES are exempt).

15. The legacy `Features/FileReplacement/post-transcode-pipeline.feature.md` is updated: criteria 1-3 (the `ShouldQualityTestService` bridge decisions) are marked **superseded by `post-transcode-disposition.feature.md`**. The mechanical criteria (path translation, atomic rename, archive-before-delete) remain in force and are referenced by Stage 8 of the flow doc.

### G. GUI (single source of truth)

16. **[VERIFIED 2026-05-12]** The `/settings` page contains a "Post-Transcode" card (sibling to "Queue Tuning") with editable controls for the three `PostTranscodeGateConfig` columns: `VmafAutoReplaceMinThreshold`, `VmafAutoReplaceMaxThreshold`, `WhenVmafUnavailable`. Saving an edit updates the table and the next disposition call reads the new value (no caching, per the standing rule). Verifiable: change the threshold to 90, run a transcode that produces VMAF=89, observe `Disposition='NoReplace', Reason='VmafBelowMin'`; change back to 88, re-decide via test endpoint, observe `Replace`.

17. Endpoints under existing `/api/SystemSettings/` namespace: `GET /api/SystemSettings/PostTranscodeGateConfig`, `PUT /api/SystemSettings/PostTranscodeGateConfig`. No separate controller -- consistent with the QueueTuning pattern.

### H. Content-aware gate (amendment 2026-05-16)

18. **[BUG 2026-05-16]** The single-threshold gate (`VmafAutoReplaceMinThreshold >= 88` against `TranscodeAttempts.VMAF`, the filtered Mean) systematically false-rejects visually-clean encodes of held-frame content. Cross-checked against production-DB attempts (`memory/KNOWN-ISSUES.md` "VMAF distribution becomes bimodal on held-frame content"): Minnie's filtered Mean=84 but filtered P25=94 (75% of unique frames score 94+) -- the encode is visually identical to source per PNG comparison, but the gate fires `VmafBelowMin` and Requeues forever. Same pattern on Pokémon (anime, Mean=71.5), Steven Universe (2D animation, 76.8), Real Housewives (reality TV, 76.6), Bunk'd (sitcom, 78.3), The Bear (drama, 79.4). Modern CGI (Garfield, 97.7) and continuous-motion live action (Outlander, 96.7) gate cleanly. Root cause documented in `QualityTesting.feature.md` criterion 2b: VMAF model 0.6.1 mis-scores byte-identical reference frames; motion filter in `ParseVMAFMetrics` improves but doesn't fully correct the metric on this content class. "Fixed" means the gate distinguishes content type via the `MotionZeroFraction` signal already produced by `ParseVMAFMetrics` and applies appropriate floors per type, with a feedback loop (criterion 22) that lets us tune the thresholds from data instead of guesswork.

19. **Content-aware decision logic.** The disposition function reads `QualityTestResults.MotionZeroFraction` for the attempt and branches:
    - **Held-frame** (`MotionZeroFraction > VmafHeldFrameDetectionThreshold`, default 0.15): pass requires `VMAFP25 >= VmafHeldFrameP25MinThreshold` **AND** `VMAF (filtered Mean) >= VmafHeldFrameMeanMinThreshold`. Twin floor: P25 catches "most unique frames must be very-good," Mean catches "encoder did not catastrophically fail." Either failing → `Requeue`.
    - **Live action** (or NULL MotionZeroFraction on legacy attempts): pass requires `VMAFP10 >= VmafLiveActionP10MinThreshold`. Stricter — "90% of frames must be very-good-or-better" — because the metric is reliable here and the operator wants good quality throughout.
    - The legacy `VmafAutoReplaceMinThreshold` is **retired** in this amendment (was a single-path gate; the two-path gate above subsumes it). `VmafAutoReplaceMaxThreshold` remains in force on both paths (a too-high VMAF still signals a suspicious encode regardless of content type).
    Verifiable: integration tests in `Tests/Contract/TestPostTranscodeDisposition.py` add held-frame and live-action rows to the conformance set; the test asserts each path's pass/fail decision against synthetic inputs at both sides of every threshold.

20. **Extended `PostTranscodeGateConfig` schema.** The single-row config table gains four columns:
    ```
    VmafLiveActionP10MinThreshold    NUMERIC NOT NULL DEFAULT 85
    VmafHeldFrameP25MinThreshold     NUMERIC NOT NULL DEFAULT 88
    VmafHeldFrameMeanMinThreshold    NUMERIC NOT NULL DEFAULT 80
    VmafHeldFrameDetectionThreshold  NUMERIC NOT NULL DEFAULT 0.15
        CHECK (VmafHeldFrameDetectionThreshold > 0 AND VmafHeldFrameDetectionThreshold < 1)
    ```
    Idempotent ADD COLUMN IF NOT EXISTS migration; defaults pre-seed the threshold values derived from the production-DB analysis (live-action P10=85 ≈ 90% of frames at "very good," held-frame P25=88 ≈ 75% of unique frames at "very good," held-frame Mean=80 ≈ "encoder did not collapse"). Existing `VmafAutoReplaceMinThreshold` column may stay for one release as a no-op (avoid breaking out-of-fleet clients reading the column) and is dropped in a follow-up migration once nothing reads it. Verifiable: `\d PostTranscodeGateConfig` shows the four new columns; migration runs twice cleanly; defaults match.

21. **`QualityTestResults.MotionZeroFraction` column.** Persists the detection signal the gate needs:
    ```
    MotionZeroFraction DOUBLE PRECISION NULL
        CHECK (MotionZeroFraction IS NULL OR (MotionZeroFraction >= 0 AND MotionZeroFraction <= 1))
    ```
    Written by `UpdateQualityTestResultsWithScore` from the existing `Metrics` dict (the value `ParseVMAFMetrics` already computes post-fix). NULL on legacy/historical rows -- the gate treats NULL as "unknown, default to live-action path" which is the conservative choice (stricter threshold). Verifiable: a fresh VMAF run populates the column; the value matches the fraction computed by reparsing the same XML.

22. **Gate-outcome telemetry, data-driven threshold tuning.** The audit trail already records per-decision outcomes (`Disposition`, `DispositionReason`); this criterion exposes the aggregate so operators can decide whether to tune the four thresholds from criterion 20 without guesswork.

    - A SQL view `GateDecisionRates` summarizes, over a rolling window:
      ```sql
      CREATE OR REPLACE VIEW GateDecisionRates AS
      SELECT
        CASE WHEN qtr.MotionZeroFraction > gc.VmafHeldFrameDetectionThreshold
             THEN 'HeldFrame' ELSE 'LiveAction' END AS Path,
        ta.DispositionReason,
        COUNT(*) AS Decisions,
        COUNT(*) FILTER (WHERE ta.Disposition = 'Replace') AS Passes,
        COUNT(*) FILTER (WHERE ta.Disposition IN ('Requeue','Reject','NoReplace','Discard')) AS Fails,
        ROUND(100.0 * COUNT(*) FILTER (WHERE ta.Disposition = 'Replace')
              / NULLIF(COUNT(*), 0), 1) AS PassRatePct
      FROM TranscodeAttempts ta
      LEFT JOIN QualityTestResults qtr ON qtr.TranscodeAttemptId = ta.Id
      CROSS JOIN PostTranscodeGateConfig gc
      WHERE ta.DispositionDecidedAt > NOW() - (gc.GateMonitoringWindowDays || ' days')::INTERVAL
      GROUP BY 1, 2;
      ```
    - Two new columns on `PostTranscodeGateConfig` configure the telemetry (DB-driven per the user-instruction memory note):
      ```
      GateMonitoringWindowDays                NUMERIC NOT NULL DEFAULT 30
          CHECK (GateMonitoringWindowDays > 0 AND GateMonitoringWindowDays <= 365)
      GateMonitoringAlertFailRateThreshold    NUMERIC NOT NULL DEFAULT 0.50
          CHECK (GateMonitoringAlertFailRateThreshold >= 0 AND GateMonitoringAlertFailRateThreshold <= 1)
      ```
    - The disposition function emits a **one-per-hour-per-path** WARN log line when either path's rolling fail rate exceeds `GateMonitoringAlertFailRateThreshold`:
      `Gate fail rate elevated: path=<HeldFrame|LiveAction> failRate=<X.YZ> threshold=<X.YZ> window=<N>d topReason=<reason> -- consider tuning <threshold-name>`
      Rate-limit by storing a `LastAlertedAt` per-path in memory (the disposition function is a hot path; we do not want a Logs flood). Verifiable: induce >50% fail rate on the held-frame path via test fixtures; observe exactly one WARN entry per hour per path; observe the JSON payload names the highest-frequency reason so the operator knows which threshold to relax.

    - The view is operator-readable from the SQL Queries page and underpins the GUI display in criterion 23. Verifiable: `SELECT * FROM GateDecisionRates ORDER BY Path, Decisions DESC` returns per-path per-reason rates; sums reconcile with `SELECT COUNT(*) FROM TranscodeAttempts WHERE DispositionDecidedAt > NOW() - INTERVAL '30 days'`.

23. **`/settings` "Post-Transcode" card extension.** The existing card (criterion 16) adds:
    - Editable controls for the four new thresholds: `VmafLiveActionP10MinThreshold`, `VmafHeldFrameP25MinThreshold`, `VmafHeldFrameMeanMinThreshold`, `VmafHeldFrameDetectionThreshold`.
    - Editable controls for the two telemetry settings: `GateMonitoringWindowDays`, `GateMonitoringAlertFailRateThreshold`.
    - A read-only "Gate Performance" panel under the editor that renders the current `GateDecisionRates` view as a small table (Path × top-3 reasons × pass-rate). Refreshes on page load. Lets the operator see "the live-action path is passing 92% of decisions; the held-frame path is passing 41% with top reason VmafHeldFrameP25BelowMin -- I should consider lowering VmafHeldFrameP25MinThreshold."
    - Existing legacy control for `VmafAutoReplaceMinThreshold` is removed from the GUI (the column may persist in the DB for one release per criterion 20 but the operator no longer sees / edits it).
    Verifiable: change `VmafHeldFrameP25MinThreshold` from 88 to 80 via the editor; the next disposition call applies the new value; the "Gate Performance" panel reflects the new pass rate within the rolling window. The legacy control no longer appears.

24. **Extended reason vocabulary** (closed list, additive to criterion 10). New values:
    `VmafLiveActionPassed`, `VmafLiveActionP10BelowMin`,
    `VmafHeldFramePassed`, `VmafHeldFrameP25BelowMin`, `VmafHeldFrameMeanBelowMin`.
    Existing `VmafBelowMin` and `VmafPassed` reasons are deprecated for new attempts (the new vocabulary is more precise about which floor failed and which path the attempt took). The closed-list check (criterion 10) is updated; `SELECT DISTINCT DispositionReason` still returns only the union of allowed values. Verifiable: integration test asserts each new reason fires on synthetic inputs at the relevant threshold boundary.

25. **Flow-doc and integration-test conformance.** Per criterion 4, the decision table in `transcode.flow.md` Stage 6 is amended with the two new rows (held-frame and live-action branches) and the legacy "VMAF Mean vs MinThreshold" row is removed. `Tests/Contract/TestPostTranscodeDisposition.py` adds at least one assertion per new row (held-frame pass, held-frame Mean-floor fail, held-frame P25-floor fail, live-action pass, live-action P10-floor fail), run twice each per the determinism rule (criterion 5). Verifiable: the test count rises from 14 to >=19; CI is green.

### J. Per-profile VMAF skip (amendment 2026-06-03)

30. **`TranscodeAttempts.QualityTestRequired` is sourced from `Profiles.qualitytestrequired` at attempt creation, not hardcoded.** New column `Profiles.qualitytestrequired BOOLEAN NOT NULL DEFAULT TRUE` carries the per-profile decision: trusted profiles (today: all 11 `usenvidiahardware=1` NVENC profiles) set FALSE and skip VMAF via the dispositioner (`QualityTestNotRequired -> Replace` post `transcode-flow-canonical` C6); the default TRUE preserves prior behavior for every other profile. Per-file granularity is reachable today by pointing `MediaFiles.AssignedProfile` at a profile with the desired flag. Verifiable: (a) `SELECT qualitytestrequired FROM profiles WHERE Id=<N>` matches `SELECT QualityTestRequired FROM TranscodeAttempts WHERE Id=<M>` for any attempt M whose source MediaFile has that profile assigned; (b) `SELECT COUNT(*) FROM profiles WHERE usenvidiahardware=1 AND qualitytestrequired=TRUE` returns 0; (c) a transcode against any NVENC profile completes with `Disposition='Replace', DispositionReason='QualityTestNotRequired'` and no `QualityTestingQueue` row is created.

### I. Operator master switch (amendment 2026-05-16)

26. **Global operator master switch: `PostTranscodeGateConfig.QualityTestEnabled BOOLEAN NOT NULL DEFAULT TRUE`.** Advisory gate: workers with `QualityTestEnabled=FALSE` don't CLAIM VMAF jobs. Post `transcode-flow-canonical` C6 (Reset 9) `QualityTestingGloballyDisabled` no longer short-circuits to a replace disposition -- attempts still land `Pending/AwaitingVmaf` in `QualityTestingQueue`, visible to the operator, who can bring a capable worker online or force-override via `/api/QualityTest/Override`. Editable on `/settings` Post-Transcode card. Mid-flight flip is safe because the disposition reads `GateConfig` fresh per call.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `Profiles.qualitytestrequired -> TranscodeAttempts.QualityTestRequired` | `ProcessTranscodeQueueService.CreateTranscodeAttempt` reads `qualitytestrequired` from `profiles` WHERE `profilename = MediaFile.AssignedProfile` and copies into the attempt row | `BOOLEAN NOT NULL` on `profiles`; `BOOLEAN` on `TranscodeAttempts` | `PostTranscodeDispositionDecider.Decide` Row 3 (`if not QualityTestRequired: return Disposition(Action='Replace', Reason='QualityTestNotRequired')`) | C30 verification (a)+(b)+(c); `Tests/Contract/TestPostTranscodeDisposition.py` Row 3 case |

## Status

**Core (criteria 1-17): IMPLEMENTED** -- shipped 2026-05-10. All 16 Progress steps complete. Live-verified against TranscodeAttempt 4392 (the originating Sister Wives S04E05 failure): the disposition function returned `(NoReplace, VmafServicePaused)`, persisted the audit columns, and the operator audit query surfaces the stuck row with an enumerable reason. Decision-table conformance test (`Tests/Contract/TestPostTranscodeDisposition.py`) is green at 14/14.

**Amendment (criteria 18-25, content-aware gate): IN PROGRESS** -- approved 2026-05-16. Builds on the motion-filter fix in `QualityTesting.feature.md` criterion 2b (also 2026-05-16). The legacy single-threshold gate is retired by criterion 19 and replaced with the content-aware twin-floor / strict-P10 logic. Telemetry view + DB-driven monitoring config (criterion 22) lets the operator tune thresholds from data instead of guesswork. The existing 14 conformance assertions remain valid for the function-shape criteria (1-3, 5, 9-13); the gate-logic assertions for criteria 4, 14-15 require update per criterion 25.

### Amendment Progress

- [x] Operator articulation of goal ("good quality throughout the video") and threshold trade-offs reviewed 2026-05-16
- [x] Production-DB cross-check that the single-threshold gate fails on held-frame content (Pokémon, Steven Universe, Real Housewives, Bunk'd, The Bear) and modern CGI is the outlier that passes (Garfield)
- [x] Feature-doc amendment drafted (this section -- criteria 18-25)
- [ ] Operator approval of criteria 18-25
- [ ] SQL migration `Scripts/SQLScripts/AddContentAwareGate.py`: 4 threshold columns + 2 monitoring columns on `PostTranscodeGateConfig` (criterion 20); `MotionZeroFraction` column on `QualityTestResults` (criterion 21); `GateDecisionRates` view (criterion 22).
- [ ] `UpdateQualityTestResultsWithScore` writes `MotionZeroFraction` from the existing Metrics dict (criterion 21).
- [ ] `PostTranscodeGateConfigModel` + `PostTranscodeGateConfigRepository` extended with the six new columns (criteria 20, 22).
- [ ] `PostTranscodeDispositionService._DecideFromInputs` reads `MotionZeroFraction` (via JOIN to QualityTestResults) and branches per criterion 19. Retire the `VmafScore < VmafAutoReplaceMinThreshold` branch.
- [ ] Reason vocabulary extension (criterion 24) -- update the closed-list check.
- [ ] Telemetry alert (criterion 22 second half) -- one-per-hour-per-path WARN line with in-memory rate limit.
- [ ] `transcode.flow.md` Stage 6 decision-table rewrite per criterion 25 -- same PR.
- [ ] `Tests/Contract/TestPostTranscodeDisposition.py` extended to 19+ assertions covering the new rows (criterion 25).
- [ ] `/settings` "Post-Transcode" card editor + read-only "Gate Performance" panel (criterion 23). Remove the legacy `VmafAutoReplaceMinThreshold` control.
- [ ] Live verify on Minnie's post-WebService restart: same encode that previously Requeued now `Replace` with reason `VmafHeldFramePassed`.
- [ ] Live verify on Outlander: still gates cleanly via the live-action path (P10 path, no behavior change).
- [ ] Re-VMAF Pokémon / Steven Universe / Real Housewives via smoke harness or live transcode and confirm filtered-pool numbers + correct path classification + correct disposition.
- [ ] Tune defaults from `GateDecisionRates` after one rolling window of production data (criterion 22 feedback loop).

NEXT: operator approval of the 8 new criteria. Then start with the migration (criterion 20+21+22) because everything downstream reads the new columns.

### Progress

- [x] 1. Read existing related docs (`post-transcode-pipeline.feature.md`, `transcode.flow.md` Stages 6+7, `QualityTesting.feature.md`)
- [x] 2. Identify the five split decision sites and the five+ scattered config sources
- [x] 3. Draft this feature doc with the canonical decision table
- [x] 4. Update `transcode.flow.md` Stages 6+7 with the unified disposition flow + decision table (committed in this `/n`)
- [x] 5. Operator approval of criteria 1-17
- [x] 6. SQL migration `Scripts/SQLScripts/AddPostTranscodeDisposition.py` (criteria 6, 7, 8) -- creates `PostTranscodeGateConfig` (single row, typed columns); adds `Disposition`, `DispositionReason`, `DispositionDecidedAt` to `TranscodeAttempts` with CHECK + index; deletes the three legacy `SystemSettings` rows.
- [x] 7. New repository: `PostTranscodeGateConfigRepository.Get() / Update()`. Read-fresh per call. (Criterion 6.)
- [x] 8. Implement `DecidePostTranscodeDisposition(TranscodeAttemptId)` in a new module `Features/QualityTesting/PostTranscodeDispositionService.py`. Returns `(Disposition, Reason, AuditPayload)`. Idempotent. (Criteria 1, 2, 5.)
- [x] 9. Wire the function as the **only** post-transcode call from `ProcessTranscodeQueueService.ProcessJob` and `QualityTestingBusinessService.ProcessQualityTestQueue` (re-decide after VMAF lands). (Criterion 3.)
- [x] 10. Update `FileReplacementBusinessService.ProcessFileReplacement` to require `Disposition = 'Replace'` on the attempt, refuse otherwise. Drop `BypassVMAFCheck` parameter. Delete `ProcessFileReplacementWithVMAF` (collapse). (Criterion 14.)
- [x] 11. Implement the audit-trail UPDATE in the disposition function (Disposition, DispositionReason, DispositionDecidedAt). (Criteria 9, 11.)
- [x] 12. Add the rolled-up INFO log line. Remove the opaque "Quality test processing failed" pattern. (Criteria 12, 13.)
- [x] 13. Delete the legacy symbols listed in criterion 14. Update `post-transcode-pipeline.feature.md` per criterion 15.
- [x] 14. Add `/settings` "Post-Transcode" card and the two new endpoints. (Criteria 16, 17.)
- [x] 15. Integration tests: one per decision-table row (criterion 4); idempotency test (criterion 2); audit-query test (criterion 11). `Tests/Contract/TestPostTranscodeDisposition.py` -- 14 assertions covering all 9 rows + edge precedence cases, each run twice for determinism (criterion 5). Audit-query test verified live against TranscodeAttempts row 4392 returning `(NoReplace, VmafServicePaused)`. Idempotency was verified live before commit; not formalized as a unit test because it requires real DB fixture lifecycle.
- [x] 16. Smoke test: re-run the Sister Wives S04E05 scenario that motivated this feature. Verified live 2026-05-10: TranscodeAttempt 4392 (`Sister Wives - S04E05 - Infertility`) ran through the new disposition function, output `Disposition='NoReplace', Reason='VmafServicePaused', DispositionDecidedAt='2026-05-10 13:45:29'`. Operator audit query (`WHERE Success=true AND FileReplaced=false AND Disposition <> 'Pending'`) surfaces the row with the single enumerable reason -- the original opaque failure mode is gone.

NEXT: operator approval of the 17 criteria. Then implement step 6 (schema + migration) first since downstream depends on the new columns / table existing.

## Scope

```
Scripts/SQLScripts/AddPostTranscodeDisposition.py                  -- NEW: migration + seed + delete legacy SystemSettings rows
Features/QualityTesting/PostTranscodeDispositionService.py         -- NEW: DecidePostTranscodeDisposition
Features/QualityTesting/Models/DispositionResult.py                -- NEW: dataclass for return value (Disposition, Reason, AuditPayload)
Features/QualityTesting/PostTranscodeGateConfigRepository.py       -- NEW
Features/QualityTesting/Models/PostTranscodeGateConfigModel.py     -- NEW
Features/QualityTesting/post-transcode-disposition.feature.md      -- this file
Features/QualityTesting/ShouldQualityTestService.py                -- DELETE (entire file)
Features/QualityTesting/QualityTestingBusinessService.py           -- delete CheckAndTriggerAutoReplace, simplify UpdateQualityTestResults
Features/FileReplacement/FileReplacementBusinessService.py         -- drop BypassVMAFCheck, collapse ProcessFileReplacementWithVMAF, gate on Disposition
Features/FileReplacement/post-transcode-pipeline.feature.md        -- supersede criteria 1-3, keep mechanical criteria
Features/TranscodeJob/ProcessTranscodeQueueService.py              -- replace ShouldQualityTestService call with DecidePostTranscodeDisposition; delete IsQualityTestEnabled / WorkerQualityTestEnabled
Features/SystemSettings/SystemSettingsController.py                -- new endpoints for PostTranscodeGateConfig (criteria 16, 17)
Features/SystemSettings/SystemSettingsViewModel.py                 -- editor view-model methods
Templates/Settings.html                                            -- new "Post-Transcode" card
transcode.flow.md                                                  -- Stages 6+7 rewrite (already done in this /n)
memory/KNOWN-ISSUES.md                                                    -- record the messy state being fixed (this /n)
```

## Files

| File | Role |
|------|------|
| `Scripts/SQLScripts/AddPostTranscodeDisposition.py` | Idempotent migration: create `PostTranscodeGateConfig` (single-row CHECK), add `Disposition`/`DispositionReason`/`DispositionDecidedAt` to `TranscodeAttempts` with CHECK constraints + index, delete legacy `SystemSettings` rows for VMAFAutoReplaceMinThreshold/MaxThreshold/QualityTestEnabled. |
| `Features/QualityTesting/PostTranscodeDispositionService.py` | The single decision function. No I/O beyond the three repository calls + the `TranscodeAttempts` UPDATE. Idempotent. |
| `Features/QualityTesting/PostTranscodeGateConfigRepository.py` | `Get() -> PostTranscodeGateConfigModel`, `Update(Min, Max, WhenVmafUnavailable)`. No caching. |
| `Features/QualityTesting/Models/DispositionResult.py` | Dataclass: `Disposition`, `Reason`, `AuditPayload` (dict). |
| `Features/QualityTesting/Models/PostTranscodeGateConfigModel.py` | Dataclass: `Id`, `VmafAutoReplaceMinThreshold`, `VmafAutoReplaceMaxThreshold`, `WhenVmafUnavailable`, `LastUpdated`. |
| `Features/FileReplacement/FileReplacementBusinessService.py` | `ProcessFileReplacement(TranscodeAttemptId)` -- single entry point. Reads `Disposition` from `TranscodeAttempts`, refuses unless `Disposition = 'Replace'`. No threshold reads. |
| `Features/QualityTesting/QualityTestingBusinessService.py` | After writing a VMAF score, calls `DecidePostTranscodeDisposition` to re-decide and act on the result. `UpdateQualityTestResults` no longer computes `PassesThreshold` -- it just stores the score. |
| `Features/TranscodeJob/ProcessTranscodeQueueService.py` | After successful transcode, calls `DecidePostTranscodeDisposition`. No more `ShouldQualityTestService`, no more `IsQualityTestEnabled`. |
| `Templates/Settings.html` | "Post-Transcode" card with three editable controls (Min, Max, WhenVmafUnavailable). |
| `Features/SystemSettings/SystemSettingsController.py` | `GET/PUT /api/SystemSettings/PostTranscodeGateConfig`. |
| `transcode.flow.md` | Stages 6, 7, 8 rewritten (Stage 6=Disposition, 7=VMAF, 8=Action). Decision table is canonical. |

## Deviation from conventions

**Criteria 1, 2, 3, and 14 reference specific function/parameter/file names** (`DecidePostTranscodeDisposition`, `ShouldQualityTestService`, `_ReplaceFileDirectly`, `BypassVMAFCheck`, `ProcessFileReplacementWithVMAF`, `CheckAndTriggerAutoReplace`, `IsQualityTestEnabled`). This violates the rename test in `.claude/rules/feature-criteria.md`. The deviation is intentional: the operator requirement is explicit legacy-code removal ("remove all legacy code it's worthless"). Without naming the symbols, the "is the legacy gone?" check has no anchor. The behavior criteria (4, 5, 9-13, 16, 17) are name-agnostic and survive renames; the structural cleanup criteria are tied to the symbols by design.

If a future rename happens, criteria 1, 2, 3, 14 must be edited along with the rename in the same PR. The grep pattern in criterion 14 makes this discoverable.

Every other criterion is externally verifiable: SQL queries, log-line presence, integration-test assertions. The "single source of truth" rule (one decision function, one config table, one log line per decision, one column triplet for audit) directly addresses the Cursor-era pattern recorded in `memory/KNOWN-ISSUES.md` of split decisions across multiple files.
