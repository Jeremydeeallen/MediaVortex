# Directive (backlog): VMAF Flow Document

**Slug:** vmaf-flow-doc

## Outcome

Stand up a dedicated `Features/QualityTesting/vmaf.flow.md` with stable `ST<N>` stage IDs and a `## Seams` table. Current state: the VMAF flow is described inside `transcode.flow.md` Stage 7. That is not the right home -- VMAF is conditional (gate-driven via `PostTranscodeDispositionService.QualityTestRequired` + `PostTranscodeGateConfig.QualityTestEnabled`), branches both ways at completion (`Replace` / `NoReplace` / `Requeue`), and runs in a separate worker process from the transcode. A pipeline-shaped flow doc is what the system actually has; `transcode.flow.md` should keep the disposition decision (one stage, gate on QualityTestRequired) but the VMAF execution body belongs in its own flow.

## Acceptance Criteria

1. `Features/QualityTesting/vmaf.flow.md` exists with `**Slug:** vmaf` and the standard flow-doc shape (entry point, ST1..ST<N> stages, `## Seams` table). New stable IDs start at `ST1`; do not reuse the ST7/ST8 numbering from transcode.flow.md.
2. The flow doc owns the claim-to-completion chain: Claim (`DatabaseManager.ClaimQualityTestJob`) -> CreateProgressRecord -> TFP read (typed pair) -> Path resolution (`Path.FromRow` + `Resolve(Worker)`) -> existence check (`PathFs.Exists`) -> ffmpeg libvmaf -> ParseVMAFMetrics -> UpdateQualityTestResultsWithScore -> re-call `PostTranscodeDispositionService.Decide` -> lifecycle close.
3. `transcode.flow.md` Stage 7 is rewritten as a one-stage pointer: "If `Disposition='Pending' / 'AwaitingVmaf'`, enqueue to `QualityTestingQueue` and hand off to `vmaf.flow.md` ST1; otherwise advance to Stage 8 ACTION." Decision table for the gate stays here; VMAF execution body moves out.
4. Every existing reference in feature docs / code anchors to "Stage 7" or `transcode.ST8` continues to resolve via the unchanged decision label. The new flow doc's `vmaf.ST<N>` anchors are additive.
5. Seams table in `vmaf.flow.md` enumerates the cross-stage seams with path-class IDs from `path.feature.md` (S1 Path.FromRow, S5 Path.Resolve, S8 CanonicalDisplay, S10 PathFs, S11 Worker.ResolveStorageRoot).
6. `QualityTesting.feature.md` "VMAF claim-to-completion chain (path-class anchors)" section (added 2026-06-05 by vmaf-restoration) is collapsed to a one-line pointer at `vmaf.ST1`; the per-step table moves into the flow doc.
7. Code anchors `# see vmaf.ST<N>` added above each touched def in `QualityTestingBusinessService` + `ProcessQualityTestQueueService` + `PostTranscodeDispositionService` (the parts that handle VMAF specifically, not the disposition-decision parts).

## Out of Scope

- Changing the post-transcode-disposition decision logic. That stays in `post-transcode-disposition.feature.md`.
- Renumbering the existing `transcode.flow.md` `ST<N>` IDs (R16 forbids renumbering).
- Adding a separate per-stage feature doc for VMAF; `QualityTesting.feature.md` remains the feature contract.

## Why this is backlog, not active

The current state works (verified 2026-06-05: end-to-end VMAF on dot + larry, scores landing, dispositions firing). The cost of leaving VMAF inside `transcode.flow.md` is documentation clarity, not correctness. A dedicated flow doc is the right architecture but not blocking.

## Estimated scope

Small. One new flow doc (~80 lines), one edit to `transcode.flow.md` Stage 7 (collapse to ~20 lines), one edit to `QualityTesting.feature.md` to point at the new flow doc, ~5 code anchors added. No code changes.
