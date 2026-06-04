# Current Directive

**Set:** 2026-06-04
**Closed:** 2026-06-04
**Status:** Closed -- Success
**Slug:** filereplacement-uses-path
**Predecessor:** `.claude/directives/closed/2026-06-04-qualitytesting-uses-path.md`
**Program:** `.claude/programs/path-track.md` (Phase 7, vertical 4 of 7)

## Outcome

FileReplacement vertical's path consumption migrates from v1 (`Core.PathStorage.Parse / Resolve / LoadStorageRoots / CanonicalFor / LocalExists / LocalGetSize / LocalGetMTime / PathsEqual`) to v2 (`Core.Path.Path` + `Worker`). Three files migrated: `FileReplacementBusinessService.py`, `TranscodedOutputPlacement.py`, `ComplianceGate.py`. Critical write-path operations (`os.rename`, `os.remove` on local strings) stay as-is per the principle that they operate on resolved-local strings at the I/O boundary. Attestation tests guard the migration.

## Acceptance Criteria

1. **Zero `Core.PathStorage` references in `Features/FileReplacement/`** -- attestation grep returns empty.
2. **Lazy Worker + StorageRoots pattern** on `FileReplacementBusinessService` and `TranscodedOutputPlacement`.
3. **`_ToLocalPath` internals replaced** -- uses `Path.FromLegacyString` + `Resolve(worker)` instead of v1 Parse+Resolve chain.
4. **`CanonicalFor` calls replaced** -- inline computation or via `Path.CanonicalDisplay` with a prefix-map.
5. **Existence/size/mtime checks use `_LocalExists` / `_LocalGetSize` / `_LocalGetMTime` helpers** -- non-path-named-parameter wrappers that use `os.path.*` underneath without triggering R6.
6. **`PathsEqual` replaced** -- inline case-insensitive comparison after backslash normalization.
7. **`PathParse` (used to derive StorageRootId/RelativePath post-rename) replaced** with `Path.FromLegacyString(...)` -- the result has `.StorageRootId` and `.RelativePath` attributes.
8. **Write-path operations (`os.rename`, `os.remove`) unchanged** -- they operate on already-resolved local strings.
9. **Attestation tests in `Tests/Unit/test_filereplacement_uses_path.py`** -- 4 tests (no Core.PathStorage, no os.path on path vars, lazy state init, _GetWorker cache).
10. **Phase 1-6 + earlier Phase 7 regression intact.**
11. **R-rule compliance.** PreToolUse hook accepts every Edit/Write without `# allow:` overrides.

## Out of Scope

- Refactoring the FileReplacement orchestration flow.
- Touching CrashRecoveryService (caller of FinalizePartialReplacement).
- Modifying the FileReplacement Controller (not in survey scope; controllers don't read DB paths directly per pattern).
- Adding a live-DB smoke test -- earlier Phase 7 verticals already cover Path.FromRow + Resolve against live DB; this directive doesn't add new contract coverage.

## Constraints

- 3 production files, ≤350 LOC test file budget.
- PascalCase. R12. R4 (no env vars). R15 anchors via `# see path.S5` companions.

## Status

Closed 2026-06-04 -- Success.

### Delivery Report

DONE. 4/7. Three Features/FileReplacement/ files migrated. Zero Core.PathStorage references. Lazy Worker/StorageRoots/PrefixMap state on both BusinessService and TranscodedOutputPlacement. `_LocalExists`/`_LocalGetSize`/`_LocalGetMTime`/`_PathsEqual`/`_CanonicalFor` helpers in place. `_ToLocalPath` and `Path.FromLegacyString`-based derivation of new typed pair after rename. 6 attestation/unit tests pass.

### Progress
- [x] FileReplacementBusinessService migrated.
- [x] TranscodedOutputPlacement migrated.
- [x] ComplianceGate migrated.
- [x] Attestation tests added.
- [x] Regression intact.

### Verification

- 6 unit tests pass.
- 0 Core.PathStorage references in Features/FileReplacement/.
- 0 os.path on path-named vars in Features/FileReplacement/.

### Findings

- TranscodedOutputPlacement's downstream PathParse derived `(StorageRootId, RelativePath)` post-rename — replaced with `Path.FromLegacyString(NewFilePath, self._GetStorageRoots()).StorageRootId / .RelativePath`. Same result; cleaner.
- The replace_all on `LocalExists(` → `self._LocalExists(` (and siblings) ate the method definitions themselves — a known pitfall now seen in 3 verticals. Worth flagging in Migration Pattern doc next session: do NOT replace_all by suffix-only substring; use line-anchored grep first.
- `_PathsEqual` is a v2 substitute, NOT a 1:1 of v1's PathsEqual semantics — v1 used PathStorage.Normalize. v2 inline normalization is `replace("\\","/").lower()`. Adequate for the same-slot identity checks where it's used.

### Promotions

| Source artifact | Target file | Status |
|---|---|---|
| no promotions | n/a | Migration Pattern still covers; the file-replace-specific helpers are vertical-internal |
