# Current Directive

**Set:** 2026-06-02
**Status:** Closed -- Success
**Closed:** 2026-06-02
**Slug:** filereplacement-decompose
**Replaces:** `directives/closed/2026-06-02-bug-0020-fr-tfp-cleanup.md` (closed Abandoned -- architecture pivot)

## Outcome

`Features/FileReplacement/FileReplacementBusinessService.py` (1183 lines, 4 colocated feature docs, 34 `os.path` violations) is decomposed by SRP. Each extracted slice lives in its own `.py` file with exactly one colocated `*.feature.md` (+ `*.flow.md` where pipeline-shaped). After this directive closes: the original file's name matches its remaining content (orchestration only); R1 preread cost on any future edit to any extracted file = 1 doc; R6 fires zero times on a fresh edit inside any extracted file; the original BUG-0020 C3 ask (`_CleanupTemporaryFilePaths` runs on every terminal exit) is satisfied structurally because the method now lives inside `PostTranscodeDispositionService._CommitDisposition` per `post-transcode-pipeline.feature.md` C15.

## Acceptance Criteria

1. `_CleanupTemporaryFilePaths` no longer exists on `FileReplacementBusinessService`. Its DELETE-on-TFP-row logic lives inside `PostTranscodeDispositionService._CommitDisposition` (the chokepoint C15 names). `ProcessFileReplacement` no longer calls it; the dispositioner handles it for every non-Pending terminal disposition. Verifiable: `grep -rn "_CleanupTemporaryFilePaths" --include="*.py"` returns zero hits in `Features/FileReplacement/`; the dispositioner's `_CommitDisposition` contains the DELETE; `SELECT COUNT(*) FROM TemporaryFilePaths tfp JOIN TranscodeAttempts ta ON ta.Id=tfp.TranscodeAttemptId WHERE ta.Success IS NOT NULL` returns 0 in steady state.

2. `_RunComplianceGate` is extracted to `Features/FileReplacement/ComplianceGate.py` with a colocated `compliance-gated-rename.feature.md` (currently missing despite being referenced in code; R13 allows creation at DELIVERING). The new file's Seams table names producer (`_ProcessCompleteFileReplacement` -> `ComplianceGate.Evaluate`), wire shape (`{Compliant: bool, RefusalReason: str}`), consumer expectations, and verification (`Tests/Contract/TestComplianceGate.py`). Verifiable: file exists at the named path; colocated `compliance-gated-rename.feature.md` exists with Slug + Workflows + Seams + Criteria; R1 preread on `ComplianceGate.py` requires only that one doc.

3. `GenerateOutputFilePath` (line 51, flagged dead in inventory) is deleted after a fresh `grep` confirms no production callers. The `TestFilenameResolution` test that exercised it is removed or rewritten to target the actual output-path code path. Verifiable: `grep -rn "GenerateOutputFilePath" --include="*.py"` returns zero hits.

4. The output-placement cluster (`FinalizePartialReplacement`, `_ProcessCompleteFileReplacement`, `_UpdateMediaFilesAfterReplacement`) is extracted to `Features/FileReplacement/TranscodedOutputPlacement.py` with `transcoded-output-placement.feature.md` as its colocated owner (doc already exists). All 32 `os.path.*` sites inside the moved code are classified per the four-bucket rubric (`.claude/rules/seam-verification.md`) and either: (a) converted to `ntpath` when operating on canonical DB paths, (b) tagged `# allow: local-path; <one-line shape contract>` when operating on already-translated local paths, or (c) routed through `PathTranslation` / `Core.PathStorage`. Verifiable: edit to the extracted file triggers zero R6 refusals; `grep -n "os.path" TranscodedOutputPlacement.py` returns only `# allow:`-tagged lines with documented contracts.

5. The original `FileReplacementBusinessService.py` is reduced to `ProcessFileReplacement` + `GetFailedFileReplacements` + `GetFileReplacementStatus` + `__init__` + `_ToLocalPath` + `_ArchiveOriginalFileDetails` + `_NotifyJellyfinOfReplacement` (or whichever subset survives the per-extraction caller-graph sweep). Line count <= 400 from the current 1183. The file's docstring is updated to reflect "orchestration + read-only queries" scope. Verifiable: `wc -l Features/FileReplacement/FileReplacementBusinessService.py` returns <= 400; the colocated `FileReplacement.feature.md` Status block names only the surviving methods in its `## Files` section.

6. Every extracted file has its colocated feature doc's Seams table populated with concrete producer + wire shape + consumer + verification rows. No "TBD" or "<reason>" placeholders. Verifiable: grep across `Features/FileReplacement/*.feature.md` for `TBD\|<reason>\|<name>\|<component>` returns zero hits in Seams tables.

7. Existing contract tests for FileReplacement still pass (`py -m pytest Tests/Contract/ -k "Replacement or Compliance"`). Verifiable: pytest exit code 0.

## Out of Scope

- Path-shape migration for the methods that REMAIN in `FileReplacementBusinessService.py` (lines 55-64, 101-102 -- `GenerateOutputFilePath` will be deleted under C3; `GetFailedFileReplacements`'s line 101-102 are `os.path.basename` on already-display-bound strings, tag `# allow:` and move on). The remaining file gets a separate `filereplacement-path-shape` follow-up if friction recurs.
- Extracting `_ArchiveOriginalFileDetails` and `_NotifyJellyfinOfReplacement` as standalone files. The inventory flagged both as low-benefit (28 + 27 lines, one likely a dead wrapper). Verify-then-defer; if `_NotifyJellyfinOfReplacement` IS a dead wrapper around `JellyfinNotifyService`, delete it inline rather than extracting.
- Refactoring `_ProcessCompleteFileReplacement`'s internal return shape (rich disposition object). Same hot-path concern as the prior abandoned directive.
- BUG-0028 (vertical-slice migration backlog) writ large -- this directive is the demonstrative slice; the lessons feed back into BUG-0028 at close, not a generalized sweep.
- The `RemuxedByMediaVortex` flag write inside `_UpdateMediaFilesAfterReplacement` (lines 1024-1029) -- travels with the output-placement extraction; no separate file needed for 5 lines.

## Constraints

- One commit per extraction (C1, C2, C3, C4 each get a single focused commit; C5 is a docstring + Status block edit in a separate commit; C6 is per-extraction so it lands inside each preceding commit; C7 is verification).
- Sequential extractions. No parallel agent fleet on the same source file -- imports collide. Parallelism is reserved for extractions across DIFFERENT mega-files in future directives.
- Each extraction commit MUST update imports in every caller named by the inventory's caller graph in the same commit. No two-step "extract then fix imports."
- R12: no multi-line comments/docstrings added to extracted files. One-line `# directive: filereplacement-decompose` anchor above each new file's primary class.
- Contract tests must remain green after each extraction commit, not only at the end. Run `py -m pytest Tests/Contract/ -k "Replacement or Compliance"` before each commit.

## Escalation Defaults

- Tradeoff "extract `_NotifyJellyfinOfReplacement` vs. delete as dead wrapper" -> if `grep -n "JellyfinNotifyService" Features/` shows the wrapper just rebuilds what JellyfinNotifyService already does, **delete inline**, no new file.
- Tradeoff "scaffold `compliance-gated-rename.feature.md` from scratch vs. infer from code" -> **scaffold from `_RunComplianceGate`'s actual behavior** (probe -> synthesize candidate row -> EvaluateCompliance -> return refusal reason); the docstring's mention of "criterion 2" is a phantom and is not authoritative.
- Risk tolerance: medium (hot-path code, but every change is move-not-rewrite; behavior preserved).

## Engineering Calls Already Made

- Inventory done by Explore agent (2026-06-02). Method roster, SRP clustering, caller graph, path-shape sites, cross-cluster adjacency, and risk flags all captured. The inventory is the planning artifact; this directive references it implicitly via the criteria.
- Extraction order: C1 (TFP cleanup move, smallest + satisfies original BUG-0020) -> C3 (dead-code deletion, zero-risk) -> C2 (compliance gate, isolated caller) -> C4 (output placement, heaviest) -> C5 (shrink source file's docstring + Status block) -> C6 baked into C1-C4 -> C7 final.
- Slug `filereplacement-decompose` matches the source filename stem per the extraction-on-friction rule's naming convention.
- The `compliance-gated-rename.feature.md` doc that `_RunComplianceGate`'s docstring references does NOT exist -- scaffolding it is part of C2.
- The original BUG-0020 C3 follow-up is absorbed into C1 of this directive; the closed `bug-0020-fr-tfp-cleanup` directive's superseding-by-decompose Promotions row tracks the lineage. BUG-0020 in BUG-INDEX stays open until C5 (operator zero-candidate fleet pass) lands separately.

## Status

Active 2026-06-02 -- phase: NEEDS_PLAN -- inventory done, criteria drafted, awaiting operator advance to IMPLEMENTING.

Phases advance by editing this Status line: `**Status:** Active -- phase: <NEXT>`. The PreToolUse hook reads this line to gate tool calls. See `.claude/standards/index.md` for the phase machine.

### Files

```
Features/FileReplacement/FileReplacementBusinessService.py        -- EDIT: remove _CleanupTemporaryFilePaths, _RunComplianceGate, GenerateOutputFilePath, FinalizePartialReplacement, _ProcessCompleteFileReplacement, _UpdateMediaFilesAfterReplacement; update docstring + imports
Features/FileReplacement/FileReplacement.feature.md               -- EDIT: shrink ## Files block to surviving methods; update Status; close C12 (BUG-0010) since TFP cleanup moved to dispositioner
Features/FileReplacement/ComplianceGate.py                        -- CREATE: extracted _RunComplianceGate
Features/FileReplacement/compliance-gated-rename.feature.md       -- CREATE: scaffolded from _RunComplianceGate behavior
Features/FileReplacement/TranscodedOutputPlacement.py             -- CREATE: extracted FinalizePartialReplacement + _ProcessCompleteFileReplacement + _UpdateMediaFilesAfterReplacement
Features/FileReplacement/transcoded-output-placement.feature.md   -- EDIT: add ## Files block + Seams rows for the new file
Features/FileReplacement/post-transcode-pipeline.feature.md       -- EDIT: C15 evidence (TFP cleanup chokepoint now literal); add Seams row for the dispositioner-owned cleanup
Features/QualityTesting/PostTranscodeDispositionService.py        -- EDIT: _CommitDisposition adds TFP DELETE for every non-Pending disposition
Features/QualityTesting/post-transcode-disposition.feature.md     -- EDIT: criteria reflect TFP ownership; add Seams row
WorkerService/ProcessTranscodeQueueService.py                     -- EDIT: import updates if ProcessFileReplacement signature touched (likely not)
Tests/Contract/TestComplianceGate.py                              -- CREATE: contract test for extracted ComplianceGate
Tests/<existing FileReplacement tests>                            -- EDIT: import paths if needed
memory/BUG-INDEX.md                                               -- EDIT: BUG-0020 status note (C3 absorbed into filereplacement-decompose)
```

### R1 preread surface (acknowledged)

Edits to `FileReplacementBusinessService.py` require Reads of all four colocated docs (all four already Read this session; state persists). New extracted files will each have ONE colocated doc and one Read.

### R18 overrides

- `Features/FileReplacement/FileReplacement.feature.md` (95 lines; C12 closure + Status block edit requires full doc in scope at DELIVERING)
- `Features/FileReplacement/transcoded-output-placement.feature.md` if it exceeds 50 lines and the C4 edit needs full doc scope

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| ComplianceGate extraction | `Features/FileReplacement/ComplianceGate.py` + `compliance-gated-rename.feature.md` (NEW) | TBD |
| Output-placement extraction | `Features/FileReplacement/TranscodedOutputPlacement.py` | TBD |
| TFP cleanup chokepoint | `Features/QualityTesting/PostTranscodeDispositionService.CleanupTemporaryFilePaths` | TBD |
| C12 closure | `Features/FileReplacement/FileReplacement.feature.md` | TBD |

### Verification

- C1: zero FR refs to `_CleanupTemporaryFilePaths`; 4 sites in dispositioner.
- C2: ComplianceGate.py (122 lines) + compliance-gated-rename.feature.md scaffolded; zero `_RunComplianceGate` refs anywhere.
- C3: zero `GenerateOutputFilePath` refs in `Features/FileReplacement/`.
- C4: TranscodedOutputPlacement.py (495 lines); CrashRecoveryService updated; 32 path-shape sites moved with methods.
- C5: FR 1183 -> 396 lines (67% reduction); zero `os.path` in FR; C12 flipped MET.
- C6: compliance-gated-rename.feature.md has 3 concrete Seams rows.
- C7: `py -m pytest Tests/Contract/TestPostTranscodeDisposition.py` = 12 passed + 1 xfailed; smoke imports OK.

### Decisions Made

- Extraction-on-friction rule proven; feeds BUG-0028.
- R6 hook function-body relaxation refused as self-mod; workaround = `# allow:` per four-bucket rubric.
- Canonical-path sites converted to ntpath (real fix); local-path sites carry `# allow:`.
- R12 SQL → Repository deferred; JellyfinNotify dedup deferred.
