# Compliance Tabbed UI

**Slug:** compliance-tabbed-ui
**Set:** 2026-06-24
**Status:** Drafted (backlog) -- prerequisite for resuming `compliance-cutover-and-rip`
**Position in chain:** Step 3 of 3 prerequisites named in `compliance-cutover-and-rip.md` Resume Conditions
**Sequencing:** depends on `effective-profile-to-profiles` + `video-vertical-inline` closing first.

## Outcome

`/Compliance` is a thin shell template with three tabs (Audio / Video / Container). Each tab is served by the owning vertical's controller. The current `/Compliance` operator surface (rule editing, gate visibility, equivalence diff display) is preserved during the cutover but routes to per-vertical owners. After `compliance-cutover-and-rip` lands, the shell becomes the only `/Compliance` surface and the old `/api/Compliance/*` routes return 404.

## Why

`vertical-owned-compliance.md` decision 2 was three separate settings pages vs one tabbed shell. Operator deferred to the tabbed-shell path: "one `/Compliance` tabbed page that's a thin shell over three sub-tabs." This directive builds that shell so the rip can land without losing operator-facing rule editing.

## SOLID + DDD Shape

**SRP:** the shell template owns layout + tab routing; each tab body is rendered by the vertical that owns the policy. No "compliance controller" exists post-rip.

**OCP:** adding a fourth tab (future hypothetical vertical) is a register-controller + register-tab change; the shell does not list verticals statically.

**ISP:** the shell consumes a `ITabContentProvider` per vertical; verticals expose only their tab's render contract.

## Acceptance Criteria

C1. `Templates/Compliance.html` is a thin shell (target < 80 lines) rendering three tabs by reading a `ITabContentProvider` registry.
C2. Each vertical's controller exposes `/Compliance/Audio`, `/Compliance/Video`, `/Compliance/Container` tab-body endpoints. `Features/AudioNormalization/AudioNormalizationController.py` handles Audio (existing controller extended); `Features/VideoEncoding/VideoEncodingController.py` handles Video (new); `Features/ContainerFormat/ContainerFormatController.py` handles Container (new).
C3. Tab routing preserves operator state via URL fragment (`/Compliance#audio`, `/Compliance#video`, `/Compliance#container`). Default tab is operator-tunable via `SystemSettings.ComplianceDefaultTab` (default `audio`).
C4. `Tests/Integration/TestComplianceTabbedUiRoutes.py` asserts all three tab-body endpoints return 200 with vertical-owned content + the shell renders at `/Compliance`.

## Files (planned)

| File | Role |
|---|---|
| `Templates/Compliance.html` | NEW. Thin tabbed shell. |
| `WebService/Controllers/ComplianceShellController.py` | NEW. Serves `/Compliance` shell; reads tab registry; no policy logic. |
| `Features/VideoEncoding/VideoEncodingController.py` | NEW. `/Compliance/Video` tab body. |
| `Features/ContainerFormat/ContainerFormatController.py` | NEW. `/Compliance/Container` tab body. |
| `Features/AudioNormalization/AudioNormalizationController.py` | EDIT. Add `/Compliance/Audio` tab-body endpoint. |
| `Core/UI/ITabContentProvider.py` | NEW. Interface for tab-body registration. |
| `Scripts/SQLScripts/AddComplianceDefaultTabSetting_2026_06_24.py` | NEW migration. SystemSettings.ComplianceDefaultTab default `audio`. Idempotent (R11). |
| `Tests/Integration/TestComplianceTabbedUiRoutes.py` | NEW. C4 contract test. |
| `Features/AudioNormalization/audio-normalization.feature.md` | EDIT. Add Workflow row for `/Compliance/Audio` tab. |
| `Features/VideoEncoding/video-encoding.feature.md` | EDIT at DELIVERING. Add Workflow + tab-body endpoint. |
| `Features/ContainerFormat/container-format.feature.md` | EDIT at DELIVERING. Add Workflow + tab-body endpoint. |

## Out of Scope

- Deleting the old `/api/Compliance/*` routes -- happens in `compliance-cutover-and-rip` after this directive closes.
- Per-vertical rule-editing UI changes -- this directive only moves what exists into the new shell.

## Status

(Populated at IMPLEMENTING.)

## Activation Protocol

```powershell
git mv .claude/directives/backlog/compliance-tabbed-ui.md .claude/directive.md
# Edit Status: Active -- phase: NEEDS_STANDARDS_REVIEW
```
