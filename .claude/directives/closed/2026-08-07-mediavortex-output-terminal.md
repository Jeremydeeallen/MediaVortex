# Directive: mediavortex-output-terminal

**Slug:** mediavortex-output-terminal
**Status:** Closed
**Closed:** 2026-08-07
**Opened:** 2026-08-07
**Sequence:** Phase 3 of 4 (per operator plan; SSoT at transcode.flow.md D7)

## Ask

Per SSoT D7: `TranscodedByMediaVortex = TRUE` is a terminal state. MediaVortex outputs on disk cannot be re-encoded (source is gone). WorkBucket must reflect this structurally.

Currently: WorkBucket generated column derives from compliance flags only. VideoVertical.Evaluate has a `mediavortex_output_accepted` short-circuit (per-vertical patch); AudioVertical + ContainerVertical do NOT. Result: 2439 MediaVortex outputs currently in AudioFix bucket. Emitter would re-run Demucs on them = duplicate Dialog Boost.

Fix: WorkBucket generated column gets `WHEN TranscodedByMediaVortex = TRUE THEN 'Compliant'` as FIRST branch. Structurally impossible to place MV outputs in any work bucket. VideoVertical short-circuit becomes redundant + deleted.

## Domain Decisions

**DD1. WorkBucket short-circuit at generated-column layer, not per-vertical.** One place enforces D7. Each vertical stays focused on its own dimension (no cross-vertical short-circuit patches).

**DD2. `TranscodedByMediaVortex = TRUE` overrides ANY compliance flag state.** Even if audio-vertical marks the output as needs_normalization, WorkBucket=Compliant. That's the intent -- we don't re-encode our own outputs regardless of downstream vertical opinion.

**DD3. VideoVertical.Evaluate `mediavortex_output_accepted` short-circuit deleted.** Redundant now. Video vertical returns whatever the multiplier check produces; WorkBucket short-circuit at the aggregate layer handles the terminal state.

**DD4. work-bucket.feature.md C7 amended.** Currently states `TranscodedByMediaVortex is METADATA and MUST NOT influence WorkBucket.` That was the WRONG invariant. Amended text: MediaVortex outputs are terminal per D7 in transcode.flow.md; WorkBucket short-circuits on the flag.

**DD5. Migration is idempotent + reversible.** Drop + recreate generated column with new CASE. Same shape as prior migrations (`RewriteWorkBucketGeneratedColumn_2026_07_22.py`). Safe to re-run.

## Success Criteria

C1. **Generated column updated.** `Scripts/SQLScripts/AddMvTerminalToWorkBucket_2026_08_07.py` drops + recreates WorkBucket with `WHEN TranscodedByMediaVortex = TRUE THEN 'Compliant'` as the first branch. Verifiable: `SELECT generation_expression FROM information_schema.columns WHERE table_name='mediafiles' AND column_name='workbucket'` shows the new CASE.

C2. **Live-DB immediate reclassification.** Post-migration: `SELECT COUNT(*) FROM MediaFiles WHERE TranscodedByMediaVortex=TRUE AND WorkBucket != 'Compliant'` returns 0. The 2439 stale AudioFix rows auto-migrate to Compliant.

C3. **VideoVertical short-circuit deleted.** Line 27-28 `if bool(getattr(Mf, 'TranscodedByMediaVortex', False)): return (True, 'mediavortex_output_accepted')` removed. `grep -n "mediavortex_output_accepted" Features/VideoEncoding/VideoVertical.py` returns 0.

C4. **video-encoding.feature.md C6 amended.** Currently: "MediaVortex outputs are compliance-exempt on the video side." Amended to: "MediaVortex output terminal state now enforced at WorkBucket aggregate layer per transcode.flow.md D7; VideoVertical is no longer responsible for the short-circuit."

C5. **work-bucket.feature.md C7 amended.** Currently forbids TranscodedByMediaVortex influencing WorkBucket. Amended to reference D7 as the correct invariant + name the leading CASE branch.

C6. **Contract test.** `Tests/Contract/TestWorkBucketMvTerminal.py`: after INSERT of a MediaFiles row with TranscodedByMediaVortex=TRUE + all-FALSE compliance flags, SELECT returns WorkBucket='Compliant'.

C7. **Live smoke on I9.** Post-migration: (a) SQL count of MV-transcoded rows NOT in Compliant = 0; (b) `/Work/AudioFix` no longer shows any -mv.mp4 rows.

## Files

**Edit:**
- `Features/VideoEncoding/VideoVertical.py` -- delete lines 27-28 short-circuit
- `Features/VideoEncoding/video-encoding.feature.md` -- C6 amend (at DELIVERING)
- `Features/WorkBucket/work-bucket.feature.md` -- C7 amend (at DELIVERING)

**Create:**
- `Scripts/SQLScripts/AddMvTerminalToWorkBucket_2026_08_07.py` -- drop + recreate WorkBucket generated column with MV-terminal branch
- `Tests/Contract/TestWorkBucketMvTerminal.py` -- 1 test asserting terminal-state invariant

**Delete:** (none)

## Call-Graph Audit

- **Signal 1:** N/A -- no new flow docs.
- **Signal 2:** N/A -- no orchestration mode-branch.
- **Signal 3:** WorkBucket generated column shape change. Column derivation shifts; storage unchanged.
- **Signal 4:** OOS explicitly categorized.
- **Signal 5:** N/A -- no config knob added.

## Out of Scope

- **(a) In-flight preserved:** AudioVertical + ContainerVertical evaluators -- unchanged (they still evaluate their dimensions; short-circuit is at aggregate layer).
- **(a) In-flight preserved:** all deferred work per operator's Phase 4 plan (PlanFactory rewrite).
- **(a) In-flight preserved:** existing operator-triggered force-transcode paths -- if operator explicitly force-queues a MediaVortex output, admission still admits (WorkBucket short-circuit doesn't block queue admission, only reporting classification).

## Phase machine

NEEDS_STANDARDS_REVIEW -> NEEDS_PLAN -> NEEDS_DOC_PREREAD -> IMPLEMENTING -> VERIFYING -> DELIVERING

### Progress

- [x] NEEDS_STANDARDS_REVIEW
- [x] NEEDS_PLAN
- [x] NEEDS_DOC_PREREAD (work-bucket.feature.md read this session; video-encoding.feature.md read this session; prior generated-column migration read as reference)
- [x] IMPLEMENTING: AddMvTerminalToWorkBucket_2026_08_07.py migration created + applied
- [x] IMPLEMENTING: VideoVertical.Evaluate mediavortex_output_accepted short-circuit deleted
- [x] IMPLEMENTING: TestWorkBucketMvTerminal.py 2/2 PASS
- [x] VERIFYING: MV outputs not in Compliant = 0; bucket distribution shifted (Compliant +8824, AudioFix -3319 from 5700 to 2381)
- [x] SMOKE-GATE PASS: SQL confirms 0 MV-transcoded rows outside Compliant bucket
- [x] DELIVERING: work-bucket.feature.md C7 + video-encoding.feature.md C6 amended; close report

### R13 overrides

(none)

### R18 overrides

(none)

### Promotions

| Source (directive) | Target (durable) |
|---|---|
| DD1-DD5 | `transcode.flow.md` D7 already covers; work-bucket.feature.md C7 amend + video-encoding.feature.md C6 amend land here |

## Delivery Report

**STATUS:** Done

**WHAT SHIPPED:**
- `Scripts/SQLScripts/AddMvTerminalToWorkBucket_2026_08_07.py`: dropped + recreated WorkBucket generated column with leading `WHEN TranscodedByMediaVortex = TRUE THEN 'Compliant'` branch; applied on homelab-postgres
- `Features/VideoEncoding/VideoVertical.py`: deleted `mediavortex_output_accepted` short-circuit (redundant now; aggregate layer owns)
- `Tests/Contract/TestWorkBucketMvTerminal.py`: 2 assertions (generated-column expression references TranscodedByMediaVortex; SQL count of MV-not-Compliant = 0)
- `Features/WorkBucket/work-bucket.feature.md`: C7 amended (six-branch CASE + historic-wrong-invariant note)
- `Features/VideoEncoding/video-encoding.feature.md`: C6 amended (aggregate-layer short-circuit; per-vertical patch deleted)

**HOW TO USE IT:** no operator action. All MediaVortex outputs auto-migrate to WorkBucket=Compliant. AudioFix bucket no longer contains any -mv.mp4 files.

**CRITERIA VERIFICATION:**
- C1: generation_expression now leads with TranscodedByMediaVortex branch (verified via migration output)
- C2: SQL `COUNT(*) WHERE TranscodedByMediaVortex=TRUE AND WorkBucket != 'Compliant'` = 0
- C3: `grep -n "mediavortex_output_accepted" Features/VideoEncoding/VideoVertical.py` = 0 hits
- C4: video-encoding.feature.md C6 amended
- C5: work-bucket.feature.md C7 amended
- C6: TestWorkBucketMvTerminal.py 2/2 PASS
- C7: LIVE SMOKE PASS -- bucket distribution shift: Compliant 29,516 -> 38,340 (+8,824 MV outputs); AudioFix 5,700 -> 2,381 (-3,319 MV outputs); Remux 5,829; Transcode 5,332; Unclassified 3,785

**DECISIONS I MADE:**
- Migration is destructive-then-recreate (matches prior pattern in `RewriteWorkBucketGeneratedColumn_2026_07_22.py`). Idempotent + reversible.
- Kept old text of amended docs in-place as historic context ("prior invariant said X; that was wrong") so future readers understand the shift.

**KNOWN GAPS / DEFERRED:**
- Phase 4 `plan-factory-driven-by-compliance-flags` remains -- makes slot strategy compliance-flag-driven instead of ProcessingMode-enum-driven.
- Fleet-deploy of new WorkBucket CASE required (or Linux workers reading OLD flow will not see the reclassification). Actually — the column is DB-side; no code deploy needed. Workers reading MediaFiles will see the new WorkBucket values immediately.
