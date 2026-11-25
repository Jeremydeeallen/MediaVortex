# XXX Program Plan (Stash -> profile-row lookup -> video tier -> audio rule -> cull)

> **For agentic workers:** execute one phase per session. Each phase ends with a commit, a push, a memory handoff update, and a `/clear`. Do not start the next phase in the same context. The spec is `Docs/superpowers/specs/2026-10-28-xxx-stash-cull-audio-design.md`; Unit 1 detail is `Docs/superpowers/plans/2026-10-28-stash-lxc.md`.

**Goal:** xxx 4K videos are AV1 at about 8 Mbps; xxx audio is one normalized track at -26 LUFS with no Dialog Boost; low-quality videos and unwanted performers are deleted through one confirmed action; TV and Movies are verified unchanged; every doc, comment and line of code left behind is correct.

**Operating rules for every phase**
- Read only: `.claude/rules/*.md` (auto), this file, the phase's named docs. Nothing else until a step needs it.
- Infra work happens in `C:\Code\infrastructure`, MediaVortex work in `C:\Code\MediaVortex`. Each repo gets its own commits.
- Hygiene is part of every phase, not a final sweep. The **Phase Exit Checklist** below runs at the end of every phase, in full, before the clear. Phase 7 only re-runs the same checks and must find nothing.

**Resume protocol (start of every session)**
1. Read memory `project_handoff_xxx_program.md` (it is the RESUME HERE entry in `MEMORY.md`).
2. Open this plan, go to the phase the handoff names, start at its first unticked step.
3. Operator trigger phrase: "continue xxx program". Nothing else is needed from the operator to resume.

**Phase Exit Checklist (mandatory, every phase)**
1. **Criteria**: every criterion the phase owns is verified live and its evidence line is written in the owning feature doc.
2. **Design decisions, single-sourced**: every decision the phase made lives in exactly one durable doc (infra: `docs/architecture/xxx-curation.md`; MediaVortex: `transcode.flow.md` Domain Decisions or the vertical's `*.feature.md`). Grep the repo for a second statement of the same decision; delete the copy, leave a one-line pointer.
3. **Stale text deleted**: every comment, docstring, feature-doc sentence, flow-doc row or memory line that the phase made false is deleted, not annotated. Grep for the old term (examples: `AuthorizedKeysFile`, `no_dialog_boost`, `HasDialogBoostTrack` as a compliance test, `GetProfileMaxTarget`, `'live_action'` as a code default, `larry` as the Stash host, `10.0.0.44`).
4. **Dead code removed**: for every function or script the phase bypassed or replaced, `grep -rn "<Name>" --include='*.py'` across the production tree; zero callers means delete in the same commit.
5. **Tests**: contract tests for the touched verticals pass; the command and result are in the feature doc evidence.
6. **Commit + push**: one logical change per commit, every commit pushed, `git status --short` clean except operator-owned untracked files.
7. **Summary**: append a dated "Phase N done" paragraph to memory `project_handoff_xxx_program.md`: what shipped, operator-visible behaviour, decisions made, explicitly "nothing deferred". Set the "Next" line to the following phase and its first step.
8. **Tell the operator to clear**, verbatim shape:
   > Phase N complete and pushed. Clear now (`/clear`). To resume: say "continue xxx program". Next session starts Phase N+1 step 1: <one line>.

Only after step 8 is printed does the session end. If any item in 1 to 7 cannot be completed, the phase is not done: say which item and why, and do not print step 8.

---

## Phase 1: Stash identify + close Unit 1  (infra repo)

**Status 2026-10-29:** steps 1, 2, 3 and 5 done; Identify (job 4) running; step 7 hygiene done except the criterion 8/9 evidence lines. StashDB pending an invite code (optional). Step 6 (performer rating) gates Phase 6 only; Phases 3 to 5 do not wait on it.

1. Wait for the scan queue to empty: `curl -s -X POST http://10.0.0.45:9999/graphql -H 'Content-Type: application/json' -d '{"query":"{ jobQueue { id status progress } }"}'` returns `null` (Stash reports an empty queue as null).
2. Verify scene count = file count (9,097 video files under `/mnt/xxx/Videos` at scan start; recount if it differs).
3. Start Identify: `mutation { metadataIdentify(input:{sources:[{source:{stash_box_endpoint:"https://theporndb.net/graphql"}}], options:{setOrganized:false, includeMalePerformers:true, fieldOptions:[{field:"performers", strategy:MERGE, createMissing:true},{field:"studio", strategy:MERGE, createMissing:true},{field:"tags", strategy:MERGE, createMissing:true}]}}) }`. Without `createMissing` Stash attaches zero performers. Wait for the queue to empty.
4. Record counts: scenes with performers, distinct performers, unmatched scenes. Criterion 8 target is 1,500 or more scenes with a performer.
5. Explain the 9,097 vs 3,880 gap: `SELECT split_part(RelativePath,'/',2), count(*) FROM MediaFiles WHERE StorageRootId=3 GROUP BY 1` against `find /mnt/xxx/Videos -mindepth 1 -maxdepth 1 -type d -exec sh -c 'echo "$(find "$1" -type f | wc -l) $1"' _ {} \;` inside the CT. Write the finding into `docs/architecture/xxx-curation.md` under Deferred or Invariants, whichever fits. If MediaVortex is missing folders it should scan, file a MediaVortex bug with `/b`; do not fix it here.
6. Operator rates performers (criterion 9). Verify with the `findPerformers` rating query.
7. Hygiene: `docs/features/stash-deploy.feature.md` criteria 7 to 9 set with evidence, Status COMPLETE, Progress ticked. Delete the two stale `ssh-keys/config.json.*` copies and `terraform/stash/stash.tfplan` (operator confirms the deletes). Remove the `--no-reload` reload-only path assumption from `terraform/register-monitoring.py` docstring if it still claims reload suffices for a single-file bind mount; add the restart note instead.
8. Commit, push, update handoff memory, `/clear`.

## Phase 2: Close `movies-video-rule`  (MediaVortex)

**Done 2026-11-11** (`directives/closed/2026-11-11-movies-video-rule.md`, Success).

## Phase 3: `profile-row-lookup` directive  (MediaVortex, spec Unit 0)

**Status 2026-11-25:** directive open at IMPLEMENTING; hook fix, spec and this plan are its steps 1 and 2.

1. Hook: `Get-SessionState` ignores the stale state file when the directive is the template. Verify criterion 8 by hand (template directive + stale state -> "No active directive").
2. Spec and plan rewritten (this commit). Operator reviews the spec before step 3.
3. Migration `AddContentClassDefaults_2026_11_25.py` (two nullable CHECK columns + seeds); regenerate `.claude/schema/snapshot.json`.
4. `ContentClassResolver`; `LibraryDefaultTierRepository` + `GenreQualityTierRepository` carry the class.
5. `TierLadderRepository.GetProfileRow` + `ProfileRow`; `GetProfileTarget` / `GetTierEncodeKbps` over it.
6. Consumers switched; four duplicate lookups deleted (`GetProfileMaxTarget`, `GetProfileSettingsForTargetResolution`, `GetProfileQualityForTargetResolution`, `_ResolveTargetResolution`); `VideoVertical` default removed; `ProcessTranscodeQueueService` passes the class; `RecalculateQueuePriorities.py` caller updated.
7. GUI: library table "Default content class", genre table class column; both saves recompute the library.
8. Tests: `TestProfileRowLookup.py` (criteria 1, 3, 4); `TestUpscaleBlockEnforcement` on row targets; mocks in `TestTvVideoRuleTier1`, `TestMoviesVideoRule`, `TestVerticalsAreProfileIndependent`, `TestEncoderKnobNormalizeResolution`, `TestWorkerEncoderResolver`.
9. Docs: `profile-tier-ladder.feature.md`, `marginal-savings-gate.feature.md` 2b, `video-encoding.feature.md`, `classifier.feature.md`, `transcode.flow.md` ST4/ST5 pointers, GLOSSARY "content class"; close BUG-0120 and BUG-0121.
10. Deploy server + fleet (`py deploy/deploy-server.py`, `py deploy/deploy-fleet.py`). Smoke: `AddJob` admits 751839 and 751897 without `ForceAdd`; one TV 1080p file transcodes to 720p; TV/Movies `VideoCompliant` delta reported (criterion 7).
11. Deliver, close, commit, push, handoff memory, `/clear`.

## Phase 4: `xxx-video-tier` directive  (MediaVortex, spec Unit 2)

1. `/n xxx-video-tier`. Criteria from the spec: every xxx file on `AV1 Tier 3 Better` after the save; one 12+ Mbps xxx 4K file transcodes to 2160p AV1 at about 8 Mbps and passes VMAF; a 7 Mbps xxx 4K file is refused `MarginalSavings`; TV and Movies assignments unchanged.
2. `ReassignTierProfiles`: acts for any library with a default tier (drop the `GenreSource IS NOT NULL` filter); accepts `IncludeOverrides`.
3. `PUT /api/SystemSettings/LibraryTiers` accepts `ReplaceOverrides`; Settings.html checkbox "replace per-file and per-series overrides", default off; passes through to the recompute.
4. Operator (GUI): xxx tier 3 with the checkbox ticked; delete rule `XxxPinTier2Good`. Confirm the assignment count query.
5. Smoke on a worker per criteria; record sizes before/after for the smoked file.
6. Hygiene: `classifier.feature.md` C9 evidence line; `video-encoding.feature.md` library-tier text; nothing says tiered libraries skip reassign.
7. Deliver, close, commit, push, handoff memory, `/clear`.

## Phase 5: `xxx-audio-rule` directive  (MediaVortex, spec Unit 3)

Order inside the phase is the TV safeguard. Do not reorder.

1. `/n xxx-audio-rule`. Criteria from the spec: TV golden audio args unchanged; TV and Movies `AudioCompliant` counts unchanged; one live TV AudioFix unchanged (two tracks, same codecs and loudness); one xxx AudioFix yields one aac stream at -26 within tolerance, compliant, no Demucs step; `no_dialog_boost` gone from code and from xxx rows.
2. NEEDS_STANDARDS_REVIEW call-graph audit over `AudioFilterEmitter.EmitTracks`, `PreEncodeAudioPipeline`, `AudioPreEncodeFacade`, `AudioStrategyClassifier`, `AudioVertical.Evaluate`, `AudioPolicyAdmissionGate`, `TranscodedOutputPlacement` (writer of `HasDialogBoostTrack`), `PostEncodeMeasurementService` (writer of `AudioTracksEmittedJson`). Name every place a rules-row field decides a track property.
3. Migration: copy live rules values into the global policy row's tracks (Original opus 48 kbps/channel -23; Dialog Boost opus 64 kbps -14 / LRA 9). Record the before/after `AudioCompliant` counts for TV and Movies in the directive.
4. Golden contract test: TV fixture -> emitter -> ffmpeg audio args, captured against current code. Commit before touching the emitter.
5. Emitter iterates `Policy.EmitTracks`; pre-encode runs Demucs only when a `Dialog Boost` track is in the policy; strategy classifier defaults removed. Golden test passes byte-for-byte.
6. Compliance: labels equal policy labels per kept language, loudness within tolerance per track. Snapshot counts identical to step 3 or the directive does not advance.
7. Drop the eight duplicated fields from `AudioComplianceRules`, repository and both GUI panels; regenerate snapshot.
8. Docs: `transcode.flow.md` D2/D6/D7 + AudioFix verification row; `audio-normalization.feature.md` C1/C43; Promotions rows as content moves.
9. Deploy server + fleet. Live: one TV AudioFix on a worker, compare to a pre-change attempt's `AudioTracksEmittedJson`.
10. Operator (GUI): `/AudioNormalization` library row ScopeKey 3: one `Original`, aac 128k, TargetLufs -26, default. Review tab bulk re-measure for the deferred xxx rows.
11. Live: one xxx AudioFix on a worker per criteria.
12. Deliver, close, commit, push, handoff memory, `/clear`.

## Phase 6: `xxx-cull` directive  (MediaVortex, spec Unit 4)

Opens only after Phase 1 step 6 (performers rated).

1. `/n xxx-cull`. Criteria from the spec: candidates carry one or more rule reasons; cull rules editable on `/settings` (performer max rating, min height, min kbps, min minutes); `/Admin/Cull` lists candidates with reason, performers and thumbnail; one confirmed delete removes file + `MediaFiles` row + one Jellyfin notify; a file with no Stash match above every floor is never a candidate.
2. Stash read: GraphQL `http://10.0.0.45:9999/graphql`, fresh per request, join on `RelativePath` under `StorageRootId = 3`. Stash paths are `/mnt/xxx/Videos/...`; MediaVortex `RelativePath` is `Videos/...`.
3. Delete path reuses the existing file-removal code; grep callers before touching it.
4. Hygiene: feature doc for the vertical, flow doc only if it is pipeline-shaped (it is not; one request path), GLOSSARY entries for "cull candidate" and "performer rating".
5. Deliver, close, commit, push, handoff memory, `/clear`.

## Phase 7: Program close-out  (both repos, verification only)

If Phases 1 to 6 ran their exit checklists, this phase changes nothing. It re-runs the checks and proves it.

1. Spec file status line reads complete (set in Phase 6's exit).
2. Re-run checklist items 2, 3 and 4 across both repos with the full grep list: `AuthorizedKeysFile`, `no_dialog_boost`, `HasDialogBoostTrack` as a compliance test, `GetProfileMaxTarget`, `GetProfileSettingsForTargetResolution`, `_ResolveTargetResolution`, `'live_action'` as a code default, `TargetIntegratedLufs` on the rules row, `10.0.0.44`, `larry` near `stash`, `Debian 12` near `stash`, `DialogBoost` helpers with zero callers, duplicated xxx path translation between repos. Expected: zero hits that need action.
3. `git status --short` clean in both repos; `git log origin/main..HEAD` empty in both.
4. Write the program summary into memory `project_handoff_xxx_program.md` (one paragraph per phase, already present from each exit) and print it to the operator. State plainly: no deferred work, no known gaps.
5. If step 2 or 3 finds anything, that is a defect in an earlier phase's exit: fix it here, commit, push, and note which phase missed it.
