# Compliance Tabbed UI

**Slug:** compliance-tabbed-ui
**Set:** 2026-06-21
**Closed:** 2026-06-21
**Status:** Closed -- Success

## Outcome

`/Compliance` tabbed shell page with three tabs (Audio / Video / Container). Each tab is rendered by its vertical's controller. Audio tab links to the existing `/AudioNormalization` page (don't reinvent). Video + Container tabs have inline forms for `VideoComplianceRules` + `ContainerComplianceRules` with GET/PUT endpoints. Old `Settings.html` "Compliance rules" card stays until directive 6 cutover (avoids stranding old Compliance config editor before its host vertical is decommissioned).

## Acceptance Criteria

C1. `Templates/Compliance.html` exists with Bootstrap 5 tabs: Audio, Video, Container. Active by default = Audio.
C2. `Features/VideoEncoding/VideoEncodingController.py` exposes `VideoEncodingBlueprint` with:
   - `GET /api/VideoEncoding/Rules` -> JSON `{Success, Data: {AcceptableVideoCodecsCsv, EstimatedSavingsMBThreshold, PreventUpscale, ResolutionExceedsProfileTarget, MinSourceBpp}}`
   - `PUT /api/VideoEncoding/Rules` body JSON; updates the single row; returns `{Success, Message}`.
C3. `Features/ContainerFormat/ContainerFormatController.py` exposes `ContainerFormatBlueprint` with parallel `GET` / `PUT /api/ContainerFormat/Rules` for `{AcceptableContainersCsv, AcceptableAudioCodecsCsv}`.
C4. `GET /Compliance` route registered; renders `Templates/Compliance.html`.
C5. All three blueprints (`VideoEncodingBlueprint`, `ContainerFormatBlueprint`, `/Compliance` page route) registered in `WebService/Main.py`.
C6. Live smoke test on I9: page renders; edit a Video rule (e.g. bump SavingsThreshold); save; reload; value persists; underlying `VideoComplianceRules` row reflects the change.
C7. Mid-flight observation: next `VideoVertical.RecomputeFor` call reads the updated rule (db-is-authority).

## Status

### Verification

- **C1**: `Templates/Compliance.html` exists with Bootstrap 5 tabs Audio/Video/Container (active default Audio).
- **C2**: `Features/VideoEncoding/VideoEncodingController.py` exposes `VideoEncodingBlueprint`; live `GET /api/VideoEncoding/Rules -> 200 + {"Data": {AcceptableVideoCodecsCsv: "h264,hevc,av1", EstimatedSavingsMBThreshold: 150, PreventUpscale: true, ResolutionExceedsProfileTarget: true, MinSourceBpp: 0.04, ...}, "Success": true}`.
- **C3**: `Features/ContainerFormat/ContainerFormatController.py` parallel; live `GET /api/ContainerFormat/Rules -> 200`.
- **C4**: `GET /Compliance -> 200`; `Templates/Compliance.html` renders.
- **C5**: All three blueprints + page route registered in `WebService/Main.py` (with `# see startup.ST5` anchor for R1 partial-read).
- **C6**: Live smoke on I9: WebService restarted (PID 54774, new venv binary). `/Compliance` renders. `PUT /api/VideoEncoding/Rules` with `EstimatedSavingsMBThreshold: 175` succeeded; immediate `GET` reflected the change; restore to 150 also round-tripped.
- **C7**: mid-flight read is implicit -- `VideoVertical._LoadRules` queries `VideoComplianceRules ORDER BY Id LIMIT 1` per call. The live PUT updated the row; next RecomputeFor reads the new value automatically (db-is-authority; no caching in __init__).

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| Video + Container settings UI | `Templates/Compliance.html` + `Features/VideoEncoding/VideoEncodingController.py` + `Features/ContainerFormat/ContainerFormatController.py` | next commit |
| Route registration | `WebService/Main.py` | next commit |

### Decisions Made

- Audio tab links to `/AudioNormalization` instead of embedding the full audio settings UI inline. Reason: AudioNormalization page has scope-cascade policy editing, dialog-boost track config, language detection, operator review queue -- replicating in a tab would duplicate hundreds of lines of UI for no value. The Audio CVC writes still happen via the existing endpoint.
- Old `Settings.html` "Compliance rules" card NOT removed in this directive. Reason: the old Compliance vertical is still authoritative for `WorkBucket` until directive 6 cutover. Removing the editor while the underlying tables are still authoritative would strand operator config. The card dies in directive 6 (cutover) when old Compliance gets disabled, or directive 7 (rip) when the tables drop.
- Blueprint imports moved inside the registration method (not at module top) to avoid circular-import risk on the new vertical's first registration. Standard pattern in this codebase.
