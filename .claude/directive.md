# Scan New Subtrees First

**Slug:** scan-new-subtrees-first
**Set:** 2026-07-28 (pivot; parent: deploy-worker-identity-invariants)
**Status:** Active -- phase: DELIVERING

## Interrupts: deploy-worker-identity-invariants

## Outcome

Recursive scan orders walk output so files under level-1 subdirectories with zero MediaFiles rows in the DB reach `ProcessSingleMediaFile` before files under known subdirectories. Operator drops a new folder into `T:\Shows`; next scan probes it before re-walking the existing library.

DB is source of truth: `NewSubtrees = <disk level-1 subdirs via os.scandir> - <SELECT DISTINCT split_part(RelativePath, '/', 1) FROM MediaFiles WHERE StorageRootId=?>`.

## Domain Decisions (locked; operator-owned)

- **D1.** Level-1 only. New shows / movies caught. New season inside known show NOT caught (deferred).
- **D2.** Empty new subtree -> walk it, find nothing, move on. No pre-check.
- **D3.** INFO log line names new subtrees. No /Activity phase change, no new UI, no ScanJobs column.
- **D4.** Known subtrees keep native `os.walk` order among themselves. No sort by LastScannedDate.

## Non-Goals (from Domain Decisions)

- Level-2+ ordering (D1).
- Empty-subtree short-circuit (D2).
- ScanJobs.Phase='WalkingNew' or /Activity surface (D3).
- Cross-RootFolder ordering.
- Auto-discovery of new RootFolders.
- Tunable knob.

## Acceptance Criteria

C1. **Order (D1).** In one scan of `<root>`, every file under a level-1 subtree in `NewSubtrees` reaches `ProcessSingleMediaFile` before any file under a level-1 subtree NOT in `NewSubtrees`. Contract test seeds fixture (1 new dir + 1 known dir, 5 files each) + asserts call order.

C2. **Reconcile unchanged.** `ScanJobs.NewFiles / UpdatedFiles / DeletedFiles / SkippedFiles` match the pre-feature values for the same RootFolder state. Order-only change. Contract test compares counters against a control run with the sort disabled via test seam.

C3. **Log line (D3).** INFO log before walk begins:
- N>0: `Scan for <canonical-root>: <N> new subtree(s) prioritized: [<names>]`
- N==0: `Scan for <canonical-root>: no new subtrees`

## Call-Graph Audit

- Flow docs touching walk: `FileScanning.flow.md` only. No sibling.
- Orchestration mode-branch: none added. `sorted()` on data.
- Shared output columns: no schema change (D3).
- OOS categorization: all Non-Goals = (b) acknowledged debt.
- Config-driven graph shape: N/A -- unconditional.

## Files

| File | Change |
|------|--------|
| `Features/FileScanning/FileScanningRepository.py` | Add `GetKnownLevel1SubdirNames(StorageRootId: int) -> Set[str]` |
| `Features/FileScanning/FileScanningBusinessService.py` | `PerformScan`: enumerate level-1 disk dirs via `os.scandir`, diff against repo call, `sorted()` `MediaFiles` list new-first, INFO log |
| `Features/FileScanning/FileScanning.flow.md` | ST3 prose: one line noting new-first sort; new seam row for classify DB read |
| `Tests/Contract/TestScanNewSubtreesFirst.py` | New; asserts C1 + C2 |

## Promotions

| Source (directive) | Target |
|---|---|
| Outcome + C1-C3 + D1-D4 rationale | `Features/FileScanning/FileScanning.feature.md` C30 (appended) |
| ST3 walk-order behavior | `Features/FileScanning/FileScanning.flow.md` ST3 prose update |
| Classify DB read seam | `Features/FileScanning/FileScanning.flow.md` S6 |
| Contract test | `Tests/Contract/TestScanNewSubtreesFirst.py` (9 tests, green) |

## Progress

- [x] NEEDS_STANDARDS_REVIEW: operator approved criteria
- [x] IMPLEMENTING: repo method + PerformScan sort + log
- [x] IMPLEMENTING: flow-doc ST3 + seam row
- [x] VERIFYING: contract test green (9/9)
- [x] VERIFYING: live smoke -- repo returns correct level-1 sets for real RootFolders (mount-root + subfolder cases)
- [x] DELIVERING: promoted content into FileScanning.feature.md C30, flow.md ST3 + S6
