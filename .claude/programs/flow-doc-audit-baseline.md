# Flow-Doc Audit Baseline

# directive: flow-docs-as-hub

One-shot artifact produced at the start of the `flow-docs-as-hub` directive. Captures the as-of-this-commit state of every `*.flow.md` in the tree against the gold-standard shape (stable `ST<N>` stage IDs + `## Seams` table) and enumerates pipelines that should have a flow doc but don't.

After this directive closes (`Status: Closed -- Success`), this file may be deleted or moved to a closed-programs archive. It carries no durable contract.

## Existing flow docs

| # | Path | Has-ST-IDs | Has-Seams-Table |
|---|---|---|---|
| 1 | `transcode.flow.md` | no (uses `(N)` parenthesized tokens) | yes (5-column shape; will migrate to 6-column `\| ID \| ...\|` per `.claude/rules/flow-docs.md`) |
| 2 | `path-storage.flow.md` | no | no |
| 3 | `deploy/worker-deploy-linux.flow.md` | no | no |
| 4 | `deploy/worker-deploy-windows.flow.md` | no | no |
| 5 | `Docs/bottleneck-analysis.flow.md` | no | no |
| 6 | `Features/AudioCompletion/audio-completion.flow.md` | no | no |
| 7 | `Features/ContentClassifier/content-classifier.flow.md` | no | no |
| 8 | `Features/ContentSignals/content-signals.flow.md` | no | no |
| 9 | `Features/FileScanning/FileScanning.flow.md` | no | no |
| 10 | `Features/LoudnessAnalysis/linear-loudnorm.flow.md` | no | no |
| 11 | `Features/Optimization/Optimization.flow.md` | no | no |
| 12 | `Features/ServiceControl/orphan-cleanup.flow.md` | no | no |
| 13 | `Features/ServiceControl/stuck-job-detection.flow.md` | no | no |
| 14 | `Features/ShowSettings/smart-populate.flow.md` | no | no |
| 15 | `Features/SystemSettings/display-timezone.flow.md` | no | no |
| 16 | `Features/TeamStatus/TeamStatus.flow.md` | no | no |
| 17 | `Features/TranscodeQueue/media-tabs.flow.md` | no | no |
| 18 | `Features/TranscodeQueue/remux.flow.md` | no | no |
| 19 | `WebService/startup.flow.md` | no | no |
| 20 | `WorkerService/WorkerService.flow.md` | no | no |

Confirmed via `grep -E 'ST[0-9]+' <file>` (no matches across all 20) and `grep -l "^## Seams" *.flow.md` (only `transcode.flow.md` matches).

Net: 19 of 20 require both ST<N> stage IDs and a new `## Seams` table. `transcode.flow.md` requires a `(N)`-to-`ST<N>` migration and a Seams-table column-shape change (5 -> 6 columns).

## Missing pipelines

Each row identifies a pipeline-shaped concern in the codebase that has a `*.feature.md` (or operator-visible surface) but no colocated `*.flow.md`. Drafted at DELIVERING per `.claude/rules/doc-layering.md` (R13 relaxes for promotion).

| Pipeline | Entry point (proposed home) | Owns | Why a flow doc |
|---|---|---|---|
| Capability control plane | `Features/ServiceControl/capability-control-plane.flow.md` | The poll loop that translates `Workers.<Cap>Enabled + Status + LastHeartbeat` into "loop running / loop stopped" on every worker. Today described entirely in `capability-control-plane.feature.md` prose. | Cross-stage seams (Workers row -> capability poller -> per-capability service start/stop) are exactly the shape this directive mandates be materialized. |
| Jellyfin push-notify | `jellyfin-push-notify.flow.md` (colocated with `jellyfin-push-notify.feature.md` at repo root) | The fire-and-forget POST pipeline triggered by every file-mutation choke point (FileReplacement, FileScanning rename/delete, ShowSettings delete). | Six producer sites, one consumer endpoint with documented coalescing behavior (memory: `reference_jellyfin_notify_api.md`); pure seam concern. |
| Audio-fix priority hints | `Features/TranscodeQueue/audio-fix-priority-hints.flow.md` | The folder-pinning -> reprioritize -> claim-order pipeline added by `media-tabs-and-loudness.feature.md`. Operator pins a folder; rows for that folder rise to the top of the AudioFix tab. | Producer (UI pin) -> state (`AudioFixPriorityHints` or extension) -> consumer (claim-order ORDER BY) is a multi-stage seam that today exists only as a feature-doc bullet. |

## Out of scope (not "missing" -- already covered)

Pipelines that might look missing on a casual scan but are intentionally folded into existing flows:

- **Marginal-savings gate** -- `transcode.flow.md` Stage 4 (queue-population filter).
- **Priority materialization** -- `transcode.flow.md` Stage 3.5.
- **Transcode-vs-remux routing** -- `transcode.flow.md` Stage 4 + Stage 7 post-flight recompute.
- **FileReplacement** -- `transcode.flow.md` Stage 7 + `remux.flow.md` rename-before-encode safety contract.
- **Quality testing (VMAF)** -- `transcode.flow.md` Stage 6.
- **Windows UNC path translation** -- `path-storage.flow.md` (Windows worker = `StorageRootResolutions.Platform='windows'`; same Resolve seam).
- **CommandBuilder / nvenc-profiles / nvenc-rate-anchored / Profiles** -- utility / config concerns, not pipeline stages. Stay as `*.feature.md` only.
- **ClipBuilder / SQLQueries / Settings** -- non-pipeline UI surfaces. Stay as `*.feature.md` only.
- **Worker deploy** -- already covered by `deploy/worker-deploy-{linux,windows}.flow.md`.

## How to use this baseline

1. During this directive's IMPLEMENTING phase, the 20 existing flow docs are upgraded in place to add ST<N> IDs + Seams tables (criteria 2, 3).
2. At DELIVERING, the 3 Missing pipelines get new colocated `*.flow.md` files created per R13's promotion relaxation (criterion 4). Each Missing row above becomes a `Promotions` table entry in `.claude/directive.md`.
3. After close: this file may be removed. Its content has been promoted into the per-flow-doc upgrades and the new flow docs themselves.
