# XXX Program Plan (Stash -> audio rule -> cull)

> **For agentic workers:** execute one phase per session. Each phase ends with a commit, a push, a memory handoff update, and a `/clear`. Do not start the next phase in the same context. The spec is `docs/superpowers/specs/2026-10-28-xxx-stash-cull-audio-design.md`; Unit 1 detail is `docs/superpowers/plans/2026-10-28-stash-lxc.md`.

**Goal:** xxx library audio is normalized with no Dialog Boost; low-quality videos and unwanted performers are deleted through one confirmed action; every doc, comment and line of code left behind is correct.

**Operating rules for every phase**
- Read only: `.claude/rules/*.md` (auto), this file, the phase's named docs. Nothing else until a step needs it.
- Infra work happens in `C:\Code\infrastructure`, MediaVortex work in `C:\Code\MediaVortex`. Each repo gets its own commits.
- Hygiene is part of every phase, not a final sweep: delete stale comments and docs the phase touched, remove dead code it orphaned, commit with the phase.
- Phase exit = criteria verified live + docs updated + commit + push + memory `project_handoff_xxx_program.md` updated + `/clear`.

---

## Phase 1: Stash identify + close Unit 1  (infra repo)

**Status:** CT 233 live, scan running (started 2026-10-29 12:32 UTC, ~90 min). ThePornDB endpoint configured and validated. StashDB pending an invite code (optional).

1. Wait for the scan queue to empty: `curl -s -X POST http://10.0.0.45:9999/graphql -H 'Content-Type: application/json' -d '{"query":"{ jobQueue { id status progress } }"}'` returns `[]`.
2. Verify scene count = file count (9,097 video files under `/mnt/xxx/Videos` at scan start; recount if it differs).
3. Start Identify: `mutation { metadataIdentify(input:{sources:[{source:{stash_box_endpoint:"https://theporndb.net/graphql"}}], options:{setOrganized:false}}) }`. Wait for the queue to empty.
4. Record counts: scenes with performers, distinct performers, unmatched scenes. Criterion 8 target is 1,500 or more scenes with a performer.
5. Explain the 9,097 vs 3,880 gap: `SELECT split_part(RelativePath,'/',2), count(*) FROM MediaFiles WHERE StorageRootId=3 GROUP BY 1` against `find /mnt/xxx/Videos -mindepth 1 -maxdepth 1 -type d -exec sh -c 'echo "$(find "$1" -type f | wc -l) $1"' _ {} \;` inside the CT. Write the finding into `docs/architecture/xxx-curation.md` under Deferred or Invariants, whichever fits. If MediaVortex is missing folders it should scan, file a MediaVortex bug with `/b`; do not fix it here.
6. Operator rates performers (criterion 9). Verify with the `findPerformers` rating query.
7. Hygiene: `docs/features/stash-deploy.feature.md` criteria 7 to 9 set with evidence, Status COMPLETE, Progress ticked. Delete the two stale `ssh-keys/config.json.*` copies and `terraform/stash/stash.tfplan` (operator confirms the deletes). Remove the `--no-reload` reload-only path assumption from `terraform/register-monitoring.py` docstring if it still claims reload suffices for a single-file bind mount; add the restart note instead.
8. Commit, push, update handoff memory, `/clear`.

## Phase 2: Close `movies-video-rule`  (MediaVortex)

The open directive sits at DELIVERING. Unit 2 cannot open until it closes.

1. Read `.claude/directive.md` Status block and `### Promotions`. Confirm every criterion has evidence and every Promotions row landed in its feature or flow doc.
2. Run the directive's named contract tests. Fix only verification blockers.
3. Close per `.claude/rules/ceo-mode.md`: Status to Closed, move to `.claude/directives/closed/2026-10-29-movies-video-rule.md`. Hook enforces the Promotions and size gates.
4. Commit, push, handoff memory, `/clear`.

## Phase 3: `xxx-audio-rule` directive  (MediaVortex)

Spec Unit 2. One directive, one conceptual change: audio compliance judged against resolved policy.

1. `/n xxx-audio-rule`. Criteria from the spec: compliance = emitted tracks match the resolved policy's `EmitTracks` labels and achieved loudness within `LoudnessTolerance`; admission SQL honors `folder` scope; 0 xxx rows with reason `no_dialog_boost`; Movies and TV compliance snapshot unchanged.
2. NEEDS_STANDARDS_REVIEW: call-graph audit over `AudioVertical.Evaluate`, `AudioPolicyAdmissionGate` SQL, `AudioPolicyResolver`, `TranscodedOutputPlacement` (writer of `HasDialogBoostTrack`). Name every orchestration-level mode branch found.
3. Plan, doc preread, implement with contract tests (`Tests/Contract/TestAudioVertical*.py`), verify live: one xxx file through AudioFix on I9, observe compliant with one Original track.
4. Operator adds the `library` row ScopeKey `3` on `/AudioNormalization` Settings: one `Original` track, aac, TargetLufs -23, TargetLra null, default. Confirm xxx rows flip to AudioFix once and settle compliant.
5. Hygiene: `audio-normalization.feature.md` C1 rewritten to the policy-based rule; delete any sentence that still says "compliant iff HasDialogBoostTrack"; `transcode.flow.md` D-decisions updated once; Promotions rows added as content moves.
6. Deliver, close, commit, push, handoff memory, `/clear`.

## Phase 4: `xxx-cull` directive  (MediaVortex)

Spec Unit 3. Opens only after Phase 1 step 6 (performers rated).

1. `/n xxx-cull`. Criteria from the spec: candidates carry one or more rule reasons; cull rules editable on `/settings` (performer max rating, min height, min kbps, min minutes); `/Admin/Cull` lists candidates with reason, performers and thumbnail; one confirmed delete removes file + `MediaFiles` row + one Jellyfin notify; a file with no Stash match above every floor is never a candidate.
2. Stash read: GraphQL `http://10.0.0.45:9999/graphql`, fresh per request, join on `RelativePath` under `StorageRootId = 3`. Stash paths are `/mnt/xxx/Videos/...`; MediaVortex `RelativePath` is `Videos/...`.
3. Delete path reuses the existing file-removal code; grep callers before touching it.
4. Hygiene: feature doc for the vertical, flow doc only if it is pipeline-shaped (it is not; one request path), GLOSSARY entries for "cull candidate" and "performer rating".
5. Deliver, close, commit, push, handoff memory, `/clear`.

## Phase 5: Program close-out  (both repos)

1. Spec file: status line set to complete; delete the "Deviations" prose that the body already states once.
2. Infra: `docs/architecture/xxx-curation.md` is the only place the domain decisions live; `stash-deploy.feature.md` COMPLETE; the pipeline fixes made in Phase 1 (`ro` flag, quoted tags, host enum, node-name lookup, AuthorizedKeysCommand, `sys.executable`, Git Bash, URL packages) each have their rationale in the code comment or the colocated doc, nowhere else.
3. MediaVortex: `ARCHITECTURE.md` lists the Cull vertical; `GLOSSARY.md` terms added; `memory/KNOWN-ISSUES.md` entries this program closed are moved to the archive with `/bs`.
4. Dead code: grep for `DialogBoost` helpers with zero callers after Phase 3; grep for any `xxx` path translation helper duplicated between repos.
5. Commit, push both repos. Write the summary: what shipped per phase, operator-visible behaviour, decisions made, nothing deferred.
