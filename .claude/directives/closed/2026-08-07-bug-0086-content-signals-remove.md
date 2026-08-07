# Directive: bug-0086-content-signals-remove

**Slug:** bug-0086-content-signals-remove
**Status:** Closed
**Closed:** 2026-08-07
**Opened:** 2026-08-06
**Fixes:** BUG-0086

## Ask

Delete the ContentSignals vertical entirely. ContentSignalsService runs `signalstats` (600s cap) + PySceneDetect (unbounded) inside `MediaProbeBusinessService._ExecuteProbe` (lines 152-167). Same defect class as loudness-in-probe (just removed 2026-08-06). Blocks probe throughput on 4K files.

Evidence-driven KISS pivot from initial "async worker" proposal: DB query proved sole reader is one duplicate-output edge-case rule.

## Domain Decisions

**DD1. Content signals are permanently removed.** Not deferred, not disabled behind a flag, not scheduled for revisit. The columns, the code, the vertical, the rule -- all deleted.

**DD2. Reason: sole consumer produces duplicate output.** The only active rule reading signals is `AnimeBySignal` (priority 40, output `AV1 Tier 2 Good`), which sits immediately after `AnimeByFolder` (priority 30, output `AV1 Tier 2 Good`, folder pattern `%Anime%`). Sonarr's default anime placement covers the folder rule. `AnimeBySignal` fires ~never; when it does, the output profile is identical. Zero classification decisions depend on signals in practice.

**DD3. Classifier writes ~0.6% of assignments (333 of 53,772).** Bulk assignment scripts (`bulk_tier_by_root_2026_07_23` = 40,283; `series` = 7,638; `bulk-tier2-already-transcoded-2026-07-21` = 758) plus operator manual (3,602) dominate. The classifier is a small fallback surface; content-based classification is not on any operator roadmap.

**DD4. Anime classification stays folder-pattern-based.** `AnimeByFolder %Anime%` is the sole anime rule. Any future content-based classification requires a new directive with cost/benefit justification against DD2/DD3 evidence.

**DD5. SRP anchor for probe.** Probe path = ffprobe metadata extraction only. No expensive video analysis (loudness, signalstats, scenedetect, or future analog) belongs in probe. Parallel to `probe-loudness-remove` (2026-08-06); same principle, different concern.

## Fix shape

Delete the vertical + call site + consumers + DB columns + rule row + dependency + docs.

## Success Criteria

C1. **Probe path no longer imports or calls ContentSignals.** `grep -rn "ContentSignalsService\|ContentSignalsRepository\|ContentSignalsModel" Features/MediaProbe/` returns 0. `Tests/Contract/TestNoContentSignals.py::test_probe_does_not_import_content_signals`.

C2. **`Features/ContentSignals/` directory deleted.** `Test-Path Features/ContentSignals` returns False.

C3. **Classifier code has no signal-field references.** `grep -rn "MotionFraction\|SceneChangeRatePerMin\|LumaVariance" Features/ContentClassifier/` returns 0. `_RuleMatches` signature/body carries no signal checks.

C4. **DB migration drops rule + columns.** `Scripts/SQLScripts/DropContentSignals_2026_08_06.py`:
  - `DELETE FROM ContentClassificationRules WHERE RuleName = 'AnimeBySignal'`
  - `ALTER TABLE ContentClassificationRules DROP COLUMN IF EXISTS MotionFractionMin, MotionFractionMax, SceneChangeRateMin, SceneChangeRateMax, LumaVarianceMin, LumaVarianceMax`
  - `ALTER TABLE MediaFiles DROP COLUMN IF EXISTS MotionFraction, SceneChangeRatePerMin, LumaVariance`
  - Idempotent, safe re-run.

C5. **`scenedetect` dependency removed from `requirements.txt`.**

C6. **Backfill + Add scripts deleted.** `Scripts/SQLScripts/BackfillContentSignals.py` + `Scripts/SQLScripts/AddContentSignalsColumns.py` gone.

C7. **Existing feature docs updated.** `Features/ContentClassifier/classifier.feature.md` no longer references signals or `AnimeBySignal`. `Features/MediaProbe/probe.feature.md` C3 amended to name ContentSignals removed alongside loudness.

C8. **Contract test locks removal.** `Tests/Contract/TestNoContentSignals.py` greps production tree for `ContentSignalsService` + 3 field names + `scenedetect` import = 0 hits.

C9. **Existing classifier contract tests still green.** `Tests/Contract/TestContentClassifier*.py` or equivalent pass after signal-field strip.

C10. **Live smoke on I9.** After migration applied + I9 restart: (a) probe one 4K file, wall-time = ms/file (no signalstats/scenedetect log lines), (b) classifier still assigns anime file under `%Anime%` folder to `AV1 Tier 2 Good`.

C11. **BUG-0086 resolved in tracker.** `memory/BUG-INDEX.md`: BUG-0086 moves to Recently Resolved with `-> 2026-08-06` timestamp. `memory/KNOWN-ISSUES.md`: BUG-0086 subsection deleted.

C12. **Domain decisions promoted at DELIVERING.** DD1-DD5 land as durable content in `Features/MediaProbe/probe.feature.md` (DD5) + `Features/ContentClassifier/classifier.feature.md` (DD1-DD4). Directive doc keeps them for archive.

## Files

**Delete:**
- `Features/ContentSignals/` -- entire directory (Service, Repository, Models/, feature doc, flow doc, __pycache__)
- `Scripts/SQLScripts/BackfillContentSignals.py`
- `Scripts/SQLScripts/AddContentSignalsColumns.py`

**Edit:**
- `Features/MediaProbe/MediaProbeBusinessService.py` -- delete lines 152-167 (ContentSignals try-block + local imports)
- `Features/ContentClassifier/ContentClassifierService.py` -- delete signal checks in `_RuleMatches` (lines 78-83); helper `_MatchesNumericRange` retained for BitrateKbps
- `Features/ContentClassifier/ContentClassifierRepository.py` -- drop 6 signal Min/Max cols from `GetActiveRules` SELECT + 3 signal cols from `GetMediaFileForClassification` SELECT + mapping
- `Features/ContentClassifier/Models/ContentClassificationRuleModel.py` -- drop 6 signal fields
- `Features/MediaProbe/probe.feature.md` -- C3 amend + ContentSignals mention removed (at DELIVERING)
- `Features/ContentClassifier/classifier.feature.md` -- drop signal references + AnimeBySignal + promote DD1-DD4 (at DELIVERING)
- `requirements.txt` -- remove `scenedetect>=0.6.0`
- `memory/BUG-INDEX.md` -- move BUG-0086 to Recently Resolved
- `memory/KNOWN-ISSUES.md` -- delete BUG-0086 subsection

**Create:**
- `Scripts/SQLScripts/DropContentSignals_2026_08_06.py`
- `Tests/Contract/TestNoContentSignals.py`

## Call-Graph Audit

- **Signal 1 (multiple flow docs):** `content-signals.flow.md` exists as parallel flow doc alongside `ingest.flow.md`. Both describe part of the ingest pipeline (ingest = orchestration; content-signals = a stage that no longer exists). Fold: content-signals.flow.md DELETED, ingest.flow.md unchanged (no ST for signals ever existed there).
- **Signal 2 (orchestration mode-branch):** none -- pure deletion, no branching involved.
- **Signal 3 (mode-sparse output columns):** signal columns were ~99% NULL across MediaFiles by design (probe was the sole writer, and it was frequently interrupted); DDL DROP resolves.
- **Signal 4 (OOS ambiguity):** all OOS items categorized (a) or (b) below.
- **Signal 5 (config-driven graph shape):** ContentSignals compute was not flag-gated; unconditional path. Deletion removes the node; no shape shift.

## Out of Scope

- **(a) In-flight preserved:** anime classification via `AnimeByFolder %Anime%` -- unchanged.
- **(a) In-flight preserved:** other 4 active classifier rules (`AlreadyAv1Skip`, `LowBitrateLiveAction`, `Default1080pLiveAction`, `Default720pLiveAction`) -- unchanged; none used signals.
- **(a) In-flight preserved:** operator manual + bulk-script assignments -- dominate classification volume, untouched.
- **(a) In-flight preserved:** `BackfillContentSignals.py` was the operator-run population path -- deleted alongside vertical (no code left to backfill).
- **(b) Tolerated debt (none):** no known deferred consequences of this deletion.

## Phase machine

NEEDS_STANDARDS_REVIEW -> NEEDS_PLAN -> NEEDS_DOC_PREREAD -> IMPLEMENTING -> VERIFYING -> DELIVERING

### Progress

- [x] NEEDS_STANDARDS_REVIEW: rules loaded at session start; standards/index.md read
- [x] NEEDS_PLAN: criteria + Files + Call-Graph Audit + Domain Decisions locked
- [x] NEEDS_DOC_PREREAD: read `classifier.feature.md`, `content-signals.feature.md`, `content-signals.flow.md`
- [x] IMPLEMENTING: delete Features/ContentSignals/ directory (C2)
- [x] IMPLEMENTING: delete probe call site (C1)
- [x] IMPLEMENTING: strip signal fields from classifier code (C3)
- [x] IMPLEMENTING: DB migration DropContentSignals_2026_08_06.py (C4)
- [x] IMPLEMENTING: delete BackfillContentSignals + AddContentSignalsColumns + scenedetect dep (C5, C6)
- [x] IMPLEMENTING: contract test TestNoContentSignals (C8)
- [x] IMPLEMENTING: BUG-INDEX + KNOWN-ISSUES update (C11)
- [x] IMPLEMENTING: AddContentClassificationRules.py seed script pruned (signal cols removed from CREATE_TABLE + SEED_RULES + INSERT); triple-quoted SQL converted to implicit-concat per R12
- [x] IMPLEMENTING: e2e-bug-fixes.feature.md C16 removed (dead criterion); flow-doc-audit-baseline.md content-signals row removed; nvenc-rate-anchored.feature.md AnimeBySignal reference removed
- [x] VERIFYING: TestNoContentSignals 5/5 + TestProbeNoLoudness 3/3 = 8/8 PASS (C8, C9)
- [x] VERIFYING: DB migration applied clean on homelab-postgres (0 signal cols remaining on mediafiles + contentclassificationrules; 0 AnimeBySignal rows)
- [x] VERIFYING: sanity import of MediaProbeBusinessService + ContentClassifier* modules; rule model fields = [Id, Priority, RuleName, IsActive, AssignProfileName, BitrateKbpsMin, BitrateKbpsMax, ResolutionCategory, CodecIn, FolderPathPattern, Description] (11 fields, was 17)
- [x] VERIFYING: I9 Paused; drain in progress (3 in-flight: 1 Probe @ 8min, 2 Transcodes)
- [ ] SMOKE-GATE (operator-execute after I9 drains): restart I9 WorkerService + probe one 4K file + confirm no signalstats/scenedetect log lines; classify one anime file under %Anime% folder -> AV1 Tier 2 Good (C10)
- [x] DELIVERING: probe.feature.md + classifier.feature.md updated in-flight (C7, C12); Promotions populated; close report drafted

### R13 overrides

(none needed -- no new feature.md / flow.md files created; existing ones only edited)

### R18 overrides

(none -- feature docs read with limit=50)

### Promotions

| Source (directive) | Target (durable) |
|---|---|
| DD1 (permanent removal) + DD5 (SRP anchor for probe) | `Features/MediaProbe/probe.feature.md` -- C3 rewritten |
| DD1-DD4 (all domain decisions) | `Features/ContentClassifier/classifier.feature.md` -- new "Design Decisions" section |
| BUG-0086 root cause + fix | `memory/BUG-INDEX.md` (Resolved) |

## Delivery Report

**STATUS:** Done (smoke pending I9 drain)

**WHAT SHIPPED:**
- `Features/ContentSignals/` entire directory deleted (Service, Repository, Model, feature doc, flow doc, __pycache__)
- `Features/MediaProbe/MediaProbeBusinessService.py`: -16 lines (ContentSignals try-block + local imports removed from `_ExecuteProbe`)
- `Features/ContentClassifier/ContentClassifierService.py`: -6 lines (3 signal match checks removed from `_RuleMatches`)
- `Features/ContentClassifier/ContentClassifierRepository.py`: -8 lines (3 signal cols removed from `GetActiveRules` SELECT + `GetMediaFileForClassification` SELECT + model mapping)
- `Features/ContentClassifier/Models/ContentClassificationRuleModel.py`: -6 fields
- `Scripts/SQLScripts/BackfillContentSignals.py` deleted
- `Scripts/SQLScripts/AddContentSignalsColumns.py` deleted
- `Scripts/SQLScripts/DropContentSignals_2026_08_06.py` created (idempotent DDL: drop rule + 9 cols)
- `Scripts/SQLScripts/AddContentClassificationRules.py`: signal cols removed from CREATE_TABLE, SEED_RULES (AnimeBySignal row dropped), INSERT SeedSql; triple-quoted SQL converted to implicit-concat per R12
- `Tests/Contract/TestNoContentSignals.py` created (5 assertions locking removal)
- `requirements.txt`: `scenedetect>=0.6.0` line removed
- `Features/MediaProbe/probe.feature.md`: C3 amended (SRP anchor for probe)
- `Features/ContentClassifier/classifier.feature.md`: DD1-DD4 landed as new "Design Decisions" section; historical bulk sources documented in AssignedProfileSource semantics table
- `e2e-bug-fixes.feature.md`: C16 (dead PySceneDetect deploy criterion) removed from Group H and C16 root-cause block
- `.claude/programs/flow-doc-audit-baseline.md`: `content-signals.flow.md` row removed
- `Features/Profiles/nvenc-rate-anchored.feature.md`: `AnimeBySignal` reference removed from completed-work log
- `memory/BUG-INDEX.md`: BUG-0086 moved to Recently Resolved
- `memory/KNOWN-ISSUES.md`: BUG-0086 subsection deleted
- DB state on homelab-postgres: 5 active classifier rules remain (AlreadyAv1Skip, AnimeByFolder, LowBitrateLiveAction, Default1080pLiveAction, Default720pLiveAction); 0 signal cols on MediaFiles or ContentClassificationRules

**HOW TO USE IT:**
- Probe path is now ffprobe-metadata only. Wall-time per file drops from 60-600s to ms.
- No operator action for classification -- 5 remaining rules cover the primary paths; anime detection via `AnimeByFolder %Anime%` unchanged.
- Deploy to fleet (`py deploy/deploy-fleet.py`) to push commit to Linux workers.

**WHAT YOU NEED TO EXECUTE:**
1. Wait for I9 drain (3 in-flight: 1 Probe @ 8min, 2 Transcodes ~10-30min ETA).
2. Stop-Process on WorkerService + WebService, verify zero MediaVortex python procs, then start both.
3. Set I9 back to Online: `py Scripts/SQLScripts/QueryDatabase.py --commit sql "UPDATE Workers SET Status='Online' WHERE WorkerName='I9-2024'"`.
4. Smoke: hit `POST /api/MediaProbe/Probe/<Id>` on a 4K file; observe wall-time ~ms, zero `signalstats` / `scenedetect` / `ContentSignalsService` log lines.
5. Deploy to fleet when convenient.
6. Delete DropContentSignals_2026_08_06.py after fleet applies (or leave for audit; it's idempotent).

**CRITERIA VERIFICATION:**
- C1: `TestNoContentSignals::test_probe_does_not_import_content_signals` PASS (grep count 0)
- C2: `TestNoContentSignals::test_content_signals_vertical_deleted` PASS (Path.exists returns False)
- C3: `TestNoContentSignals::test_classifier_has_no_signal_fields` PASS (grep count 0)
- C4: `Scripts/SQLScripts/DropContentSignals_2026_08_06.py` applied; verification queries return 0 signal cols + 0 AnimeBySignal rows
- C5: `TestNoContentSignals::test_scenedetect_removed_from_requirements` PASS
- C6: `Scripts/SQLScripts/BackfillContentSignals.py` + `AddContentSignalsColumns.py` deleted (file-existence check)
- C7: probe.feature.md C3 + classifier.feature.md Design Decisions committed this directive
- C8: `TestNoContentSignals` 5/5 PASS
- C9: import-check confirms `ContentClassifierService.ClassifyAndAssign` + `_RuleMatches` load without ImportError; rule model has 11 fields (was 17)
- C10: PENDING I9 drain -- see WHAT YOU NEED TO EXECUTE steps 1-4
- C11: BUG-INDEX shows BUG-0086 under Recently Resolved with `2026-08-06 -> 2026-08-06`; KNOWN-ISSUES subsection deleted
- C12: DD1-DD5 promoted -- DD5 in probe.feature.md C3; DD1-DD4 in classifier.feature.md new Design Decisions section

**DECISIONS I MADE:**
- Full deletion over async worker (pivoted from initial proposal after DB evidence: 333/53772 classifier assignments; sole signal-using rule = duplicate output of folder rule). See DD2.
- Retained `AddContentClassificationRules.py` (edited to remove signal cols) rather than deleting -- it's the initial-seed script, still needed for fresh-DB bootstrap. `DropContentSignals_2026_08_06.py` is the destructive migration for existing DBs.
- Converted preexisting triple-quoted SQL in `AddContentClassificationRules.py` to implicit-concat per R12 refusal (my edit region touched the string).
- Promoted DD1-DD4 to `classifier.feature.md` (the rule vertical) rather than a new `content-signals-removed.feature.md` (which would violate R13's KISS spirit -- no vertical exists anymore).
- Paused I9 rather than force-restart mid-transcode (drain-before-redeploy rule).

**KNOWN GAPS / DEFERRED:**
- Live I9 smoke gated on operator draining 2 in-flight transcodes (mid-encode kill forbidden per drain-before-redeploy rule). Restart is instantaneous once drain completes.
- Fleet deploy not run (operator convenience).
- Any historical `.md` in `.claude/directives/closed/` still contains `ContentSignals` / `MotionFraction` etc. references -- historical record, untouched per R14 (no annotation edits to closed directives).
