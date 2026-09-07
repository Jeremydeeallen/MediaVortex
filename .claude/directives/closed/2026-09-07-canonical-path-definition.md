# canonical-path-definition

**Status:** Closed 2026-09-07

## Ask

Stop the scan-time drift bleeding + establish ONE public API for canonical-string filesystem checks. KISS + SSoT. No new feature.md, no speculative abstractions. Follow-up audit directive migrates the remaining suspects to the same API.

## Context

BUG-0098 problem 1: `Features/FileScanning/FileScanningBusinessService.py:793` `GetCanonicalPathFromFilesystem` calls `LocalExists(normalized_path)` on a canonical prefix (`Z:\`, `T:\`, `M:\`). On workers where `WorkerShareMappings.LocalMountPrefix` differs from the canonical prefix (I9: `Z` canonical -> `X:\` local after drive swap), the check fails and 7 identical warns/7d land in Logs.

Sibling helpers `_CanonicalToPath` / `_CanonicalExists` / `_CanonicalGetSize` (same file, lines 45/56/63) already encode the correct three-line dance: `Path.FromLegacyString(...)` -> `PathFs.Exists(P, worker)`. But they are **private** to `FileScanningBusinessService.py`. `Core/Path/LocalPath.py:15` even name-drops the private helpers in its error message. That is SSoT-by-accident -- one impl exists because no one else needed it yet. The moment other verticals need canonical-string existence checks (drift audit surfaces ~9 suspects: `BaseRepository.AddProblemFile` + callers in `TranscodedOutputPlacement` / `ComplianceGate` / `JobProcessor` / `QueueManagementBusinessService`), each site will either reinvent the dance, cross-import a private helper (module coupling), or open-code `Path.FromLegacyString + PathFs.Exists`. All three violate SSoT.

`Core/Path/path.feature.md` already defines canonical semantics: `Path` is the typed identity; `Path.Resolve(worker) -> str` is the sole boundary to I/O-safe strings. This directive does NOT redefine that -- it adds the missing SSoT public API for the specific "canonical string in hand, need FS check" call shape and ratifies it in the feature doc.

## Acceptance Criteria

**AC1.** New public API in `Core/Path/PathFs.py`: `CanonicalExists(canonical_str, worker) -> bool` and `CanonicalGetSize(canonical_str, worker) -> int`. Each is the ONE sanctioned way to run the named FS op given a canonical string. Additional `Canonical*` variants are added only when a call-site needs them (YAGNI).

**AC2.** `FileScanningBusinessService.py` private helpers (`_CanonicalExists`, `_CanonicalGetSize`) become 1-line delegates to the public API OR get deleted with call-sites migrated. `_CanonicalToPath` may remain private (module-local convenience over `Path.FromLegacyString`) or graduate -- callee's choice; document in the promotion.

**AC3.** `FileScanningBusinessService.GetCanonicalPathFromFilesystem` routes through `PathFs.CanonicalExists` + local-mount walk for the case-correction loop. Zero direct `LocalExists(canonical_str)` in the function body. Satisfies `scan.feature.md#C17`.

**AC4.** `Core/Path/LocalPath.py:15` error message updated to point at `PathFs.CanonicalExists` (public), not the private `_CanonicalExists`. Future guard trips route readers to the SSoT.

**AC5.** `Core/Path/path.feature.md` grows ONE new seam row under `## Seams` naming the public API: "canonical string -> FS check goes through `PathFs.CanonicalExists(str, worker)` / `PathFs.CanonicalGetSize(str, worker)` -- sole public API. Direct `LocalExists(canonical_str)` is a bug class." Also adds a criterion (or extends an existing one) making it testable.

**AC6.** Contract test `Tests/Contract/TestPathFsCanonicalExists.py`: seeds a worker whose `WorkerShareMappings.LocalMountPrefix` differs from the canonical prefix (e.g. `Z` canonical -> `X:\` local); asserts `PathFs.CanonicalExists('Z:\\Videos', worker)` returns True when the local path exists AND emits zero `Path does not exist, cannot get canonical case` warns; asserts `PathFs.CanonicalGetSize` returns the correct byte count.

**AC7.** Live smoke on I9: run one ContinuousScanService tick that touches the xxx StorageRoot; confirm zero new `Path does not exist, cannot get canonical case: Z:%` warns during the tick.

## Out of Scope

- **(b) acknowledged debt**: audit + migration of ~9 suspect `LocalExists(<possibly-canonical>)` sites -- `BaseRepository.AddProblemFile` + its 3 callers, plus sites in `TranscodedOutputPlacement`, `ComplianceGate`, `JobProcessor`, `QueueManagementBusinessService`. Filed as follow-up directive `canonical-input-drift-audit`. This directive establishes the SSoT API; the follow-up migrates callers -- each is a 1-line replacement, no re-invention.
- **(b) acknowledged debt**: grep-based contract test forbidding `LocalExists(<name-matching-canonical-hint>)`. Belongs in the audit directive that seeds the whitelist.
- **(b) acknowledged debt**: extending `TestLocalPathCanonicalGuard` to fire on Windows workers. Guard currently no-ops on `_IS_WINDOWS=True` because canonical drive letters often equal local drive letters on Windows. Fixing requires per-worker mappings at guard-time -- separate mission.
- **(b) acknowledged debt**: WorkerShareMappings GUI CRUD + Verify endpoint. BUG-0098 problem 2. Separate directive `config-gui-editable-testable`.
- **(a) collapsed in-flight**: none. Fix is localized to Core/Path + the one confirmed-bleeding site.

## Files

- `Core/Path/PathFs.py` -- add `CanonicalExists` + `CanonicalGetSize` public functions
- `Core/Path/LocalPath.py` -- update error message pointer
- `Core/Path/path.feature.md` -- add seam row + criterion per AC5
- `Features/FileScanning/FileScanningBusinessService.py` -- fix `GetCanonicalPathFromFilesystem`; migrate/delegate private helpers
- `Features/FileScanning/scan.feature.md` -- C17 already exists; satisfied at DELIVERING via test evidence
- `Tests/Contract/TestPathFsCanonicalExists.py` -- new

## Call-Graph Audit

Five signals per `.claude/rules/call-graph-audit.md`:

1. **Multiple flow docs for one conceptual operation?** No. Only `ingest.flow.md` covers scan. `path.feature.md` is feature-scope (typed identity + Path/PathFs API), not a flow doc. No parallel flow.
2. **Mode-branching at orchestration level?** No. `GetCanonicalPathFromFilesystem` has no mode branch today; fix does not add one. New `PathFs.CanonicalExists` is single-strategy (translation via `Path.FromLegacyString + Path.Resolve(worker)` -- platform variance lives inside `Worker`/`PathFs`, not at call-sites).
3. **Shared output columns sparsely populated?** N/A. Directive touches FS-check API, not DB columns. No shared output.
4. **OOS ambiguity?** Every OOS item marked (a) or (b) explicitly. All four items marked (b) acknowledged debt with named follow-up directive; one (a) row confirms no in-flight collapse.
5. **Config-driven call-graph shape?** No. `WorkerShareMappings.LocalMountPrefix` is data flowing through `Path.Resolve(worker)`. Same functions called regardless of mapping value; only the resolved string differs. Turning a mapping off/on does not add/remove nodes from the call graph.

Clean on all five. Advance to NEEDS_PLAN.

## Plan

Order minimizes hook-refusal risk: primitives first, callers after.

1. `Core/Path/PathFs.py` -- add `CanonicalExists(canonical_str, worker) -> bool` + `CanonicalGetSize(canonical_str, worker) -> int`. Each parses via `Path.FromLegacyString(str, GetStorageRoots())` (returns None-safe? no -- raises `PathError` on parse failure; wrap or propagate per fail-loud). Then delegates to existing `Exists(P, worker)` / `GetSize(P, worker)` primitives.
2. `Core/Path/LocalPath.py:15` -- update guard error message to name `PathFs.CanonicalExists` / `PathFs.CanonicalGetSize` as the public escape hatch.
3. `Features/FileScanning/FileScanningBusinessService.py` -- `_CanonicalExists` + `_CanonicalGetSize` become 1-line delegates to public API. `_CanonicalToPath` stays private (module convenience for other local uses). Line 752 caller keeps `_CanonicalExists` name (no cross-file churn); delegate handles the SSoT.
4. `Features/FileScanning/FileScanningBusinessService.py:793` `GetCanonicalPathFromFilesystem` -- rewrite. Translate canonical prefix ONCE at top via `Path.FromLegacyString(...).Resolve(worker)`; walk in local space; return canonical-display form (drive-letter reconstruction from resolved path is unnecessary because caller uses the return value only for display + subsequent `_ToLocalPath` calls that re-translate). Simpler: return the case-corrected LOCAL path; adjust callers if they compare against canonical (grep first).
5. `Tests/Contract/TestPathFsCanonicalExists.py` -- new. Seeds StorageRoot + WorkerShareMappings where LocalMountPrefix != DriveLetter; asserts CanonicalExists True + zero warns + CanonicalGetSize correct.
6. `Core/Path/path.feature.md` -- add seam row + criterion per AC5.
7. Run `TestPathFsCanonicalExists.py` + `TestLocalPathCanonicalGuard.py` + `TestScanCanonicalCaseUsesWorkerMapping.py` (if it exists per BUG-0098 fix scope; else defer to follow-up). Expect all green.
8. VERIFYING: restart WorkerService on I9, run one continuous scan tick touching xxx StorageRoot, query Logs for new `Path does not exist, cannot get canonical case: Z:%` -- expect zero.
9. DELIVERING: promote directive content -> `path.feature.md` (already touched in step 6) + close directive. Update KNOWN-ISSUES BUG-0098 (problem 1 resolved; problem 2 stays open under separate directive).

Risk / rollback: fix is additive (new PathFs functions) + one function rewrite. Revert = git revert; no schema, no data.

## Verification

- **AC1** -- `Core/Path/PathFs.py` gained `CanonicalExists(str, worker) -> bool` + `CanonicalGetSize(str, worker) -> int`. Each parses via `Path.FromLegacyString(str, GetStorageRoots())` then delegates to the existing `Exists`/`GetSize` primitive. CanonicalExists returns False on parse failure (parity with Exists); CanonicalGetSize raises PathError (parity with GetSize behavior on `Path.Resolve` failure).
- **AC2** -- `FileScanningBusinessService._CanonicalExists` + `_CanonicalGetSize` collapsed from 4-line dances to 2-line delegates over the public API. `_CanonicalToPath` kept private (still used elsewhere in module). L752 caller unchanged (name-stable delegate).
- **AC3** -- `GetCanonicalPathFromFilesystem` rewritten. Translates canonical prefix ONCE via `Path.FromLegacyString(...)` -> `worker.ResolveStorageRoot(...)`, walks LOCAL filesystem with `LocalIsDir` + `os.listdir` for case correction, rebuilds canonical output via `Path.CanonicalDisplay`. Zero direct `LocalExists(canonical_str)` in function body.
- **AC4** -- `Core/Path/LocalPath.py:15` error message now names `Core.Path.PathFs.CanonicalExists / CanonicalGetSize` (public) instead of `_CanonicalExists / _CanonicalGetSize` (private).
- **AC5** -- `Core/Path/path.feature.md` gained S16 (canonical-string -> FS check seam) + C28 (invariant naming direct `LocalPath.LocalExists(canonical_str)` a bug class).
- **AC6** -- `Tests/Contract/TestPathFsCanonicalExists.py` 6/6 PASS. Seeds fake worker with `LocalMountPrefix != DriveLetter`, asserts translation + parse-failure branches. `TestLocalPathCanonicalGuard.py` 7/7 PASS -- no regression.
- **AC7** -- Live smoke on I9-2024 (heartbeat 2026-09-07 23:19:04, restart PID 43256). Invoked `GetCanonicalPathFromFilesystem` for all 7 known Z: RootFolder paths under WorkerShareMappings `Z -> X:\` mapping. Each returned canonical-shape output; zero `Path does not exist, cannot get canonical case: Z:%` warns landed in Logs since restart (`SELECT COUNT(*) FROM logs WHERE message LIKE 'Path does not exist, cannot get canonical case: Z:%' AND timestamp > NOW() - INTERVAL '5 minutes'` returned 0).

## Promotions

| Source (directive) | Target (durable doc) | Rows |
|---|---|---|
| Context paragraphs on `PathFs.CanonicalExists` public API | `Core/Path/path.feature.md` -- S16, C28 | added this directive |
| BUG-0098 problem 1 resolution + fix scope | `memory/KNOWN-ISSUES.md` -> Resolved + `memory/BUG-INDEX.md` update | performed at close |
| BUG-0098 problem 2 spec (GUI CRUD + Verify + LastVerified) | new BUG entry OR directive slug `config-gui-editable-testable` | filed at close as follow-up (BUG-0098 stays Active for problem 2) |
| Follow-up: audit ~9 suspect `LocalExists(<possibly-canonical>)` sites | new BUG entry, directive slug `canonical-input-drift-audit` | filed at close |
