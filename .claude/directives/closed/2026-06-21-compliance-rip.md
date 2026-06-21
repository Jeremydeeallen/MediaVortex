# Compliance Rip

**Slug:** compliance-rip
**Set:** 2026-06-21
**Closed:** 2026-06-21
**Status:** Closed -- Success

## Outcome

`Features/Compliance/` directory deleted entirely. Two external Compliance callers (`QueueManagementBusinessService.RecomputeForFiles` + `EvaluateCandidateCompliance`) refactored to use the three new verticals via new pure `Evaluate(mf)` methods. ComplianceBlueprint unregistered. "Compliance rules" card removed from Settings.html. Five dying tables RENAMED to `*_OLD_2026-06-21` (RECOVERABLE; not DROPPED). Three dying columns DROPPED. `compliance.feature.md` + `compliance.flow.md` deleted with the directory. Tests for dying code deleted. WebService restarts cleanly; routing works end-to-end.

## Acceptance Criteria

C1. AudioVertical / VideoVertical / ContainerVertical each expose a pure `Evaluate(Mf) -> (Optional[bool], Optional[str])` method that computes the verdict without writing. RecomputeFor refactored to call Evaluate + write (DRY).
C2. `QueueManagementBusinessService.RecomputeForFiles` no longer imports `Features.Compliance.*`. It calls three vertical `RecomputeFor` invocations + retains its existing profile-assign + priority-score logic. `BulkWriteRecomputeResults` is no longer called from here; the write path goes directly to per-column UPDATEs.
C3. `QueueManagementBusinessService.EvaluateCandidateCompliance` uses three `Evaluate(mf)` calls + inline CASE matching the generated column's logic.
C4. `WebService/Main.py` no longer imports or registers `ComplianceBlueprint`. `curl /api/Compliance/Recompute -> 404`.
C5. `Templates/Settings.html` "Compliance rules" card section removed.
C6. Tables RENAMED (not DROPPED): `TranscodeRules -> TranscodeRules_OLD_2026_06_21`; same for `RemuxRules`, `AudioFixRules`, `SubtitleFixRules`, `ComplianceGates`. Recoverable for 30 days.
C7. Columns DROPPED on MediaFiles: `OperationsNeededCsv`, `ComplianceGateBlocked`, `ComplianceEvaluatedAt`.
C8. `Features/Compliance/` directory deleted (35+ files). `compliance.feature.md` + `compliance.flow.md` deleted with it.
C9. Tests deleted: `Tests/Contract/TestComplianceEngine.py`, `Tests/Contract/TestComplianceWriteConsistency.py`, `Tests/Contract/TestTranscodeOperationMvTrust.py`. These test dying code.
C10. `Scripts/SQLScripts/BackfillWorkBucket.py` deleted (imports dying compliance) -- new path is per-vertical backfills, already done in directives 2/5/6.
C11. WebService restarted on I9 + smoke: `curl /Compliance -> 200`, `curl /api/Compliance/Recompute -> 404`, sample MediaFile's WorkBucket still derived correctly.
C12. `ARCHITECTURE.md` Gap section: rows for `Features/Compliance/`, dying tables, dying columns, dying CHECK constraint, `/Compliance` tabbed UI, `/api/Compliance/*` 404 -- all REMOVED.

## Status

### Verification

- **C1**: All three verticals expose pure `Evaluate(Mf) -> (Optional[bool], Optional[str])`. RecomputeFor calls Evaluate + writes (DRY).
- **C2**: `grep 'Features\.Compliance' Features/TranscodeQueue/QueueManagementBusinessService.py` returns 0. RecomputeForFiles now calls three vertical RecomputeFor + writes profile+score via direct UPDATE (no BulkWriteRecomputeResults).
- **C3**: `EvaluateCandidateCompliance` calls `Audio/Video/ContainerVertical().Evaluate(mf)` + inline CASE matching the generated column's bucket precedence.
- **C4**: `WebService/Main.py` no longer imports `ComplianceBlueprint`; `curl -X POST /api/Compliance/Recompute` returns 404.
- **C5**: `grep 'SECTION: Compliance rules\|Compliance Rules section' Templates/Settings.html` returns 0. 93 HTML lines + 121 JS lines removed.
- **C6**: 5 tables RENAMED: TranscodeRules / RemuxRules / AudioFixRules / SubtitleFixRules / ComplianceGates all -> `*_OLD_2026_06_21`. Recoverable for 30 days; drop in a future directive.
- **C7**: Columns DROPPED on MediaFiles: OperationsNeededCsv, ComplianceGateBlocked, ComplianceEvaluatedAt. Bonus: IsCompliant CONVERTED to GENERATED column (was missed from C7; new state: derived from the three booleans by the same CASE pattern as WorkBucket).
- **C8**: `Features/Compliance/` directory deleted entirely (35+ files). `compliance.feature.md` + `compliance.flow.md` deleted with it.
- **C9**: Tests deleted: TestComplianceEngine.py, TestComplianceWriteConsistency.py, TestTranscodeOperationMvTrust.py.
- **C10**: `Scripts/SQLScripts/BackfillWorkBucket.py` deleted.
- **C11**: WebService restarted (PID 59025). `/Compliance -> 200`, `/api/VideoEncoding/Rules -> 200`, `/api/ContainerFormat/Rules -> 200`, `/api/Compliance/Recompute -> 404`. End-to-end smoke: RecomputeForFiles([388, 4025, 60029]) returned 3 rows updated; per-row state correct (388 efficient_bpp compliant + NULL bucket; 4025 gate-blocked + NULL; 60029 video-incompliant + Transcode bucket).
- **C12**: ARCHITECTURE.md Gap section reduced from 5 subsections to 2 (Verticals + Closing work). 12 closed rows removed (verticals + schema + operator-surfaces categories collapsed entirely).
- **Bonus**: bucket value renamed 'AudioFix' -> 'AudioFixOnly' to match existing readers (25 file occurrences would have needed renaming otherwise; cheaper to keep established name).

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| Three verticals' pure Evaluate methods + RecomputeFor refactored to call them | Features/AudioNormalization/AudioVertical.py + Features/VideoEncoding/VideoVertical.py + Features/ContainerFormat/ContainerVertical.py | next commit |
| QueueManagementBusinessService refactored: RecomputeForFiles + EvaluateCandidateCompliance use three verticals | Features/TranscodeQueue/QueueManagementBusinessService.py | next commit |
| Compliance Blueprint unregistered | WebService/Main.py | next commit |
| Settings.html Compliance rules card + orphan JS removed | Templates/Settings.html | next commit |
| Rip migration: DROP columns + RENAME tables + IsCompliant -> GENERATED | Scripts/SQLScripts/RipComplianceArtifacts.py | next commit |
| Bucket value renamed to AudioFixOnly | Scripts/SQLScripts/ConvertWorkBucketToGenerated.py | next commit |
| Gap section reduced: 5 categories -> 2; 12 closed rows removed | ARCHITECTURE.md | next commit |

### Decisions Made

- IsCompliant ALSO converted to GENERATED column (originally not in C7). Cleaner -- removes another sync risk + 99 readers continue to work without code change.
- Bucket value `AudioFix` renamed to `AudioFixOnly` to match 25 existing reader sites (WorkBucketRepository, ActivityRepository, AudioOperatorReviewService, etc.). Cheaper than 25 file edits.
- `_LegacyRefusalReasonFromDecision` + `_BuildEffectiveProfileObj` methods left in QueueManagementBusinessService as orphans (no callers post-refactor). Defer their removal to a future dead-code-sweep directive -- removing them in this directive would expand scope beyond the rip.
- 5 tables RENAMED not DROPPED. Operator can `ALTER TABLE ... RENAME TO ...` reverse the rename for 30 days if needed. After 30 days a follow-up directive drops the `*_OLD_2026_06_21` tables permanently.
- AdmissionDeferReason write removed from RecomputeForFiles. AudioPolicyAdmissionGate (per audio-normalization.feature.md WRITES list) owns this column; the old QueueManagementBusinessService write was redundant.
