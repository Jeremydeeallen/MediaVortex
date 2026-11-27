# Current Directive

**Set:** 2026-11-27
**Closed:** 2026-11-27
**Status:** Closed -- Success
**Slug:** target-policy-architecture
**Replaces:** `directives/closed/2026-11-27-xxx-video-tier.md` (closed Partial, superseded by this program)

## Outcome

Phase 0 of the target-policy program (`Docs/superpowers/plans/2026-11-27-target-policy-program.md`): the durable docs say what the decision layer will be, so every later phase implements a contract instead of inventing one. After this directive `ARCHITECTURE.md` names a `Policy` vertical and no `ContentClassifier`, `transcode.flow.md` carries the target-resolution decisions (D2/D4/D6/D7/D13) and the ST7 decision table with `Hold`, `ingest.flow.md` has no classify stage, `GLOSSARY.md` defines `Target` / `LadderCell` / `FrameRateClass` / `TargetOverride` / `Hold` / `Undecided` and deprecates `AssignedProfile` / profile assignment / classifier, and `policy.feature.md` holds the Policy vertical's contract. No code changes. The spec is no longer cited as an authority by any of these docs; they are the authority.

## Acceptance Criteria

1. `ARCHITECTURE.md` Vertical Roster has a `**Policy:**` row naming the policy tables (`StorageRoots` tier/class, `GenreQualityTiers`, `TargetOverrides`, `Profiles` acceptance, `LadderCells`, `FrameRateClasses`, `EncoderSettings`), the `MediaFileTargets` view, `TargetResolver`, `EncoderSelector` and the Radarr genre sync; `grep -c ContentClassifier ARCHITECTURE.md` = 0 outside `## Gap to Target` (whose rows name what each phase removes); Cross-Cutting Concerns has a "A file's target" row pointing at `MediaFileTargets` + `Features/Policy/TargetResolver`; Data Flow has no "assigns Profile" line; Database Invariants add "policy tables read only by `Features/Policy/`", "no stored derived target", and name the `WorkBucket` expression as the one home of D7; `## Gap to Target` lists phases 1a, 1b, 1c, 1d, 2, 3, 4, 5, 6, 7 with their slugs and one-line gaps.
2. `transcode.flow.md`: D2 Copy path reads the audio policy's default track; D4 has one Video row (tier path; no "library with no default tier" row) and its Audio row reads "tracks match policy + loudness within tolerance"; D6 reads "tracks per `AudioPolicyTracks`"; D7 names the generated column as its only implementation and does not mention Dialog Boost; D13 "a file's target is resolved by `MediaFileTargets`, never stored" exists; ST3 section body says the stage is deleted and the ID retained; ST7 decision table equals spec section 6 row for row (`Hold` present, Tier 5 -> `QualityCeilingReached`); `grep -c "AssignedProfile\|ProfileThresholds\|SmartConfidence\|NextTierAdjuster" transcode.flow.md` = 0.
3. `ingest.flow.md`: ST5 row body says deleted, ID retained; S7/S8 seams deleted; the genre sync sentence in ST3 names `Features/Policy/MovieGenreSyncService` and no reassign step; Ordering rationale no longer says the classifier runs before compliance; `grep -c "ContentClassifier\|AssignedProfile" ingest.flow.md` = 0.
4. `GLOSSARY.md` has entries `Target`, `LadderCell`, `FrameRateClass`, `TargetOverride`, `EncoderSettings`, `Hold`, `Undecided` (each with an authoritative source), `AssignedProfile` / `Profile assignment` / `Classifier` marked **deprecated** with replacement pointers, `Profile` redefined as the per-tier acceptance recipe, `Library default tier` with no "XXX unset", `Disposition` listing `Hold`; `grep -c "ProfileThresholds" GLOSSARY.md` = 0.
5. `Features/Profiles/policy.feature.md` exists (Slug `policy`) with `## What It Does`, `## Workflows` W1-W5 (resolve target, override tier, edit ladder, edit encoder settings, edit tier acceptance), `## Success Criteria` C1-C9 equal to spec section 9 reworded to the vertical's observable behaviour, `## Seams` S1-S5 (view -> resolver, resolver -> verticals, resolver -> composer, resolver -> decider, GUI -> policy tables), `## Status` naming the phase that implements each workflow. Passes the five litmus tests (`feature-criteria.md`).
6. No doc edited by this directive cites the spec as authority: `grep -c "2026-11-27-target-policy-architecture-design" ARCHITECTURE.md transcode.flow.md ingest.flow.md GLOSSARY.md Features/Profiles/policy.feature.md` = 0. The plan file may be cited from `## Gap to Target` only.
7. No annotation drift (R14) and no stale text: `grep -rn "library with no default tier\|XXX unset\|assigns Profile\|classifier" ARCHITECTURE.md transcode.flow.md ingest.flow.md GLOSSARY.md` = 0 (case-insensitive, excluding the GLOSSARY deprecated entry and `ARCHITECTURE.md` `## Gap to Target` rows); R14 words (`previously`, `formerly`, `no longer used`) = 0 in the three flow/feature docs touched.
8. `xxx-video-tier` archived at `.claude/directives/closed/2026-11-27-xxx-video-tier.md` with `Closed -- Partial`; both audit reports present under `Docs/superpowers/audits/`; plan Phase 0 steps ticked; handoff memory "Phase 0 done".

## Call-Graph Audit

Docs-only directive; the call graph is unchanged by it. The audit it records is the one the spec's section 2 and the 2026-11-27 review measured, so Phases 1-7 inherit named debt, not silent debt:

- **Signal 1 (flow docs):** `transcode.flow.md` + `ingest.flow.md` describe two pipelines (encode, ingest) that meet at ST4 RECOMPUTE; `work-bucket.flow.md` points at D4 (checked in Files). No second flow doc for one operation.
- **Signal 2 (orchestration mode branch):** `VideoVertical` tier-vs-profile branch on `DefaultQualityTier IS NULL`; `ProcessTranscodeQueueService.GetTranscodingSettings` `Codec == 'av1'` override branch; claim SQL `p.codec <> 'av1'`; `DispositionDispatcher` smart-confidence branch. All named in the spec and deleted in Phases 1b/1c/2/4.
- **Signal 3 (sparse columns):** `MediaFiles.AssignedProfileSource` 11 distinct writers' values; `TranscodeAttempts.QualityTestRequired` forced TRUE at `HandleTranscodingResult:1136` regardless of profile. Named; removed in Phases 2 and 4.
- **Signal 5 (config drives graph shape):** `StorageRoots.DefaultQualityTier IS NULL` and `GenreSource IS NULL` each remove nodes today. Spec 4.1 makes both NOT NULL / data-only.
- **OOS items:** all (b) by construction; each is owned by a named later phase (see Out of Scope).

## Out of Scope

- (b) Every code and schema change: Phases 1a-7 per the plan. Nothing in this directive edits `*.py`, `Scripts/`, `Templates/`.
- (b) `Features/ContentClassifier/classifier.feature.md`, `Features/Profiles/Profiles.feature.md`, `profile-tier-ladder.feature.md`, `nvenc-*.feature.md`, `video-encoding.feature.md`, `audio-normalization.feature.md`, `disposition.feature.md`, `post-transcode-disposition.feature.md`: they describe code that still runs; each is rewritten or deleted in the phase that changes that code.
- (a) `work-bucket.flow.md` / `work-bucket.feature.md`: if they restate the D4 table they are made to point at D4 in this directive (D4 says no doc restates it).
- (b) Operator items left by `xxx-video-tier`: `wakko-worker-1.TranscodeEnabled`, the two rejected `.ip` files on the share.

## Constraints

- Docs only. The hook's R13 override below is the one new file.
- Flow docs state the contract in the present tense without "will"/"formerly"/"previously" (R14); the phase that lands each piece is named once, in `ARCHITECTURE.md` `## Gap to Target`, nowhere else.
- No restating: D4 stays the one bucket definition; the ST7 table is the one disposition table; the view's column list lives in `policy.feature.md` only.
- Stable IDs: ST3 and ingest ST5 keep their numbers with a deleted body; W/C/S IDs in `policy.feature.md` never renumber.

## Escalation Defaults

- Spec vs. current code disagreement found while writing: the spec wins (approved design); the disagreement is recorded in Decisions Made and, if it changes a phase's work, in the plan.
- Risk tolerance: low (docs only, every criterion is a grep).

## Engineering Calls Already Made

- `policy.feature.md` is created at `Features/Profiles/` (colocated with the code that Phase 1a renames to `Features/Policy/`; the `git mv` carries it). The plan's `Features/Policy/policy.feature.md` path is amended in the same commit.
- Flow docs become the spec for Phases 1-7 (R13's sanctioned docs-first shape); `Features/ContentClassifier/classifier.feature.md` is not touched because its code still runs until Phase 2.
- xxx-video-tier closed as Partial from IMPLEMENTING (no DELIVERING pass): its durable finding (frame-rate-blind ladder) already lives in the spec; Promotions row says so.

## Status

### Delivery report

DIRECTIVE: Phase 0 of the target-policy program: the durable docs state the decision-layer architecture so Phases 1a-7 implement a contract.
STATUS: Done.
WHAT SHIPPED: `ARCHITECTURE.md` (Policy vertical, target concern, three invariants, ten-row Gap to Target), `transcode.flow.md` (D2/D4/D5/D6/D7/D13, ST3 deleted, ST5 admission, ST7 table with Hold, ST9 paths, seams), `ingest.flow.md` (ST5 deleted, genre sync under Policy), `GLOSSARY.md` (7 terms, 3 deprecations, 7 redefinitions), new `Features/Profiles/policy.feature.md`; xxx-video-tier archived Partial. No code.
HOW TO USE IT: every later phase cites these docs, not the spec; `ARCHITECTURE.md` `## Gap to Target` is the schedule; `policy.feature.md` C1-C9 are the acceptance bar for the vertical.
WHAT YOU NEED TO EXECUTE: nothing for Phase 0. Standing: decide whether wakko-worker-1 stays `TranscodeEnabled`; the two rejected `.ip` files on the share are yours to delete or keep.
CRITERIA VERIFICATION: see Verification (8/8 by grep counts).
DECISIONS I MADE: see Decisions Made.
KNOWN GAPS / DEFERRED: none.

### Plan

1. Verify audits present; archive xxx-video-tier (done before this doc was written).
2. `ARCHITECTURE.md` edits (criterion 1).
3. `transcode.flow.md` edits (criterion 2); `work-bucket.flow.md` pointer check.
4. `ingest.flow.md` edits (criterion 3).
5. `GLOSSARY.md` edits (criterion 4).
6. `Features/Profiles/policy.feature.md` (criterion 5).
7. Greps for criteria 6-7; plan Phase 0 ticks + path amendment; Promotions rows.
8. Deliver, close, commit, push, handoff memory, print the clear line.

### Files

```
ARCHITECTURE.md                                              -- EDIT: Policy vertical, view, invariants, Gap to Target
transcode.flow.md                                            -- EDIT: D2/D4/D6/D7/D13, ST3 deleted, ST7 decision table
ingest.flow.md                                               -- EDIT: ST5 deleted, S7/S8 removed, genre sync under Policy
GLOSSARY.md                                                  -- EDIT: new terms, deprecations, Profile redefined
Features/Profiles/policy.feature.md                          -- CREATE: Policy vertical contract (R13 override below)
Features/WorkBucket/work-bucket.flow.md                      -- EDIT only if it restates the D4 table
Docs/superpowers/plans/2026-11-27-target-policy-program.md   -- EDIT: Phase 0 ticks; policy.feature.md path
```

### R13 overrides

- `Features/Profiles/policy.feature.md`

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| Policy vertical definition, "a file's target" concern, three policy invariants, `WorkBucket` expression as D7 home, phased gap table | `ARCHITECTURE.md` (Vertical Roster, Cross-Cutting Concerns, Data Flow, Database Invariants, Gap to Target) | closing commit of `target-policy-architecture` |
| D2 copy path, D4 pure-vertical dimension table, D5 container home, D6 policy tracks, D7 generated-column home, D13 view resolver, ST3 deletion, ST5 admission against `Target`, ST7 inputs + decision table with `Hold`, ST9 Hold/Requeue/Reject paths, S1/S2/S4 seams | `transcode.flow.md` | same |
| ST5 classify deletion, genre sync under Policy, ordering rationale, `Undecided` failure row, S4/S12 seams | `ingest.flow.md` | same |
| `Target`, `LadderCell`, `FrameRateClass`, `TargetOverride`, `EncoderSettings`, `Hold`, `Undecided`; `Profile`, `Quality tier`, `Content class`, `Genre tier`, `Library default tier`, `Disposition`, `VMAF` redefined; `AssignedProfile`, `Profile assignment`, `Classifier` deprecated | `GLOSSARY.md` | same |
| Policy vertical contract: W1-W6, C1-C9, S1-S6, target Files | `Features/Profiles/policy.feature.md` (new; R13 override) | same |

### Verification

Evidence from one PowerShell count run over the edited docs (2026-11-27, working tree before the closing commit):

- **Criterion 1:** `ContentClassifier` outside `## Gap to Target` = 0; `**Policy:**` roster row = 1; "A file's target" concern row = 1; "assigns Profile" = 0; the three new invariants (`TestTargetAuthority`, "No stored derived target", "one home of D7") = 3; Gap table rows naming the ten phase slugs = 10.
- **Criterion 2:** stale terms (`AssignedProfile|ProfileThresholds|SmartConfidence|NextTierAdjuster|PostTranscodeGateConfig|SeriesProfiles|profile-tier-ladder|LastTranscodeOutcome|ProblemFiles|RetryBudgetService|VmafAutoReplace|HasDialogBoostTrack`) in `transcode.flow.md` = 0; `**D13.**` = 1; "Stage 3: (deleted)" = 1; `Hold` = 8 mentions; `QualityCeilingReached` = 4 (ST5 bullet, ST7 table, outcomes, Reject path). ST7 table has the eight rows of spec section 6 including the Tier 5 ceiling.
- **Criterion 3:** `ContentClassifier|AssignedProfile|classifier` in `ingest.flow.md` = 0 after the ST3 rename-note fix; `| ST5 | (deleted)` = 1; S7/S8 rows = 0; ST3 row names `Features/Policy/MovieGenreSyncService` and S12 names `MediaFileTargets`.
- **Criterion 4:** seven new terms present 7/7; three deprecations 3/3 with replacement pointers; `ProfileThresholds` in `GLOSSARY.md` = 0; `Disposition` lists `Hold`; `Library default tier` has no "XXX unset".
- **Criterion 5:** `Features/Profiles/policy.feature.md` has `**Slug:** policy`, W1-W6 (6 rows; W6 added for library/genre/frame-rate edits, the spec's section 7 controls), C1-C9, S1-S6 (S6 added for Requeue -> override). Litmus: every criterion names observable DB/GUI state or a grep, none names a function the rename test would break except in the Verify clause.
- **Criterion 6:** spec filename cited across the five docs = 0.
- **Criterion 7:** stale phrases across the four docs (excluding Gap rows and the GLOSSARY deprecated entries) = 0; R14 words in the three flow/feature docs = 0 (one pre-existing "previously-transcoded" in `ingest.flow.md` reworded).
- **Criterion 8:** `.claude/directives/closed/2026-11-27-xxx-video-tier.md` exists with `Closed -- Partial`; `Docs/superpowers/audits/2026-11-26-*.md` = 2 files; plan Phase 0 header marked done and step 7 path amended; handoff memory updated in the same session.

### Decisions Made

- `work-bucket.flow.md` / `work-bucket.feature.md` do not restate the D4 table (grep for the row text = 0), so they are untouched.
- ST5 admission text and the ST6 "FFmpeg command structure" block were stale against current code as well (libsvtav1/CRF era); rewritten to the target state in one pass rather than to an intermediate present tense.
- Criteria 1 and 7 exempt `## Gap to Target` rows: that section's job is to name the current state each phase removes.
- Hook phase gates are honor-based on Reads; every `.claude/rules/*.md` is auto-loaded in context and `standards/index.md` plus the colocated `profile-tier-ladder.feature.md` / `Profiles.feature.md` heads were Read before IMPLEMENTING.
