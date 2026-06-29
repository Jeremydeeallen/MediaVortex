# Admin / Compliance

**Slug:** admin-compliance

## What It Does

Renders the operator-facing compliance overview at `/Admin/Compliance`. Surfaces library-wide compliance counts (Compliant / Non-compliant / Undecided), WorkBucket breakdown (Transcode / Remux / AudioFix / none), and audio state breakdown (AudioComplete true/false/null, AudioCorruptSuspect).

Top-level `/Compliance` URL responds with HTTP 301 redirect to `/Admin/Compliance`.

## Surface

- Operator visits `/Admin/Compliance`.
- Page polls `/api/Admin/Compliance/Snapshot` every 5s.
- Subnav link in `Templates/_admin_subnav.html`.
- Audio / Video / Container rule-editing tabs point operators at the per-profile editors at `/settings -> Profiles` (where the compliance bar lives post-compliance-symmetry) and `/AudioNormalization` (per-scope loudness policy).

## Success Criteria

C1. `/Admin/Compliance` returns HTTP 200. Verifiable: `curl -I /Admin/Compliance` -> 200.

C2. `/api/Admin/Compliance/Snapshot` returns `{Success, Data: {Compliance, Mode, Audio}}`. Each key is a dict with the counts named in C3-C5.

C3. `Compliance` counts: `Total`, `True`, `False`, `Null`. Sourced from `MediaFiles.IsCompliant` aggregations.

C4. `Mode` counts: `Transcode`, `Remux`, `AudioFix`, `None`. Sourced from `MediaFiles.WorkBucket` GROUP BY.

C5. `Audio` counts: `CompleteTrue`, `CompleteFalse`, `CompleteNull`, `Suspect`. Sourced from `MediaFiles.AudioComplete` + `AudioCorruptSuspect`.

C6. Legacy `/Compliance` URL responds with `HTTP 301` + `Location: /Admin/Compliance`.

## Files

| File | Role |
|------|------|
| `Features/Admin/Compliance/AdminComplianceController.py` | Blueprint with `/Admin/Compliance` route + `/api/Admin/Compliance/Snapshot` endpoint |
| `Features/Admin/Compliance/AdminComplianceRepository.py` | Counts via single-method SQL (SRP) |
| `Templates/AdminCompliance.html` | Library compliance card + rule-tab placeholders pointing at canonical editors |
| `Templates/_admin_subnav.html` | Compliance link |
| `WebService/Main.py` | `/Compliance` 301 redirect to `/Admin/Compliance` |

## Status

ACTIVE 2026-06-23. Tests: `Tests/Contract/TestAdminComplianceEndpoint.py` covers the page + snapshot shape + 301 redirect.
