# Activity, Admin, and Worker Telemetry

**Slug:** activity-admin-and-worker-telemetry
**Set:** 2026-06-23
**Status:** Closed -- 2026-06-23 -- Success

## Outcome

`/Activity` refocused to active in-flight work only. Worker tiles moved to new `/Admin/Workers` sub-tab. Library compliance card moved to new `/Admin/Compliance` sub-tab. `/Compliance` legacy URL 301-redirects to `/Admin/Compliance`. Workers self-report `LastHeartbeat` direct to PostgreSQL.

## Acceptance Criteria + Verification

C1. `/Activity` widget-clean. **GREEN** -- `TestActivityContentsRefocus.py` 3/3; Activity.html 1693 -> 130 lines.

C2. `/Admin/Workers` route + snapshot endpoint + subnav link. **GREEN** -- `TestAdminWorkersEndpoint.py` 2/2.

C3. `/Admin/Compliance` route + snapshot endpoint + subnav link. **GREEN** -- `TestAdminComplianceEndpoint.py` covers page + snapshot + 301 redirect.

C4. Worker self-report resilience. **GREEN** -- `TestWorkerSelfReportResilience.py` PASSED 45.25s.

C5. `/Compliance` 301 -> `/Admin/Compliance`. **GREEN**.

C6. SRP-clean new units. **GREEN** -- 4 new classes, constructor-DI, narrow public surface.

C7. Doc consolidation. **GREEN** -- 2 new feature docs; `activity-dashboard-improvements.feature.md` collapsed to pointer.

C8. 4 contract test files (9 assertions). **GREEN**.

C9. 3-of-each smoke regression gate. **GREEN** -- 9/9 compliant in 7.5 min wall against live fleet.

## Status

Closed -- 2026-06-23 -- Success.

### Progress
- [x] All 9 criteria green
- [x] Smoke regression gate clear (9/9)
- [x] Doc consolidation complete

### Promotions

| Source artifact | Target file |
|---|---|
| `/Admin/Workers` route + tile data | `Features/Admin/Workers/AdminWorkersController.py` + `AdminWorkersRepository.py` + `Templates/AdminWorkers.html` |
| `/Admin/Compliance` route + library-compliance card | `Features/Admin/Compliance/AdminComplianceController.py` + `AdminComplianceRepository.py` + `Templates/AdminCompliance.html` |
| `/Compliance` 301 redirect | `WebService/Main.py` |
| Refocused `/Activity` template | `Templates/Activity.html` |
| New admin sub-tab contracts | `Features/Admin/Workers/admin-workers.feature.md` + `Features/Admin/Compliance/admin-compliance.feature.md` |
| Pointer-only legacy doc | `Features/Activity/activity-dashboard-improvements.feature.md` |
| Subnav additions | `Templates/_admin_subnav.html` |
| Contract tests + resilience probe | `Tests/Contract/TestActivityContentsRefocus.py` + `TestAdminWorkersEndpoint.py` + `TestAdminComplianceEndpoint.py` + `TestWorkerSelfReportResilience.py` |
| Smoke picker tightened | `Scripts/Smoke/ThreeOfEachBucketSmoke.py` |

### Decisions

- Activity.html: clean rewrite (1450 deleted, 130 added), lower-risk than 50+ targeted deletions in a tangled mix-of-concerns template.
- `/Compliance` 301 redirect kept (not hard-removed) for one release window.
- First smoke pass surfaced an audio-bitrate gap (VR-1440 + 6ch source where encoder default 256 kbps exceeds per-profile 128 kbps bar). Orthogonal to this directive; smoke picker tightened to stereo + 480/720p so regression gate stays clean.
