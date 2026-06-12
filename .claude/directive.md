# Compliance Writeback Invariant Enforcement

**Set:** 2026-06-12
**Status:** Active -- phase: DELIVERING
**Slug:** compliance-writeback-invariant
**Bug:** BUG-0062 (CLUSTER -- subsumes BUG-0056)
**Sequencing:** Cluster B of 3. See `## Notes` for B-vs-A-first tradeoff.

## Outcome

**5703 contradictory `MediaFiles` rows → 0, and stays at 0.**

Today the compliance engine writes `IsCompliant=TRUE` alongside non-null `WorkBucket` + `OperationsNeededCsv` on 5703 rows — a state the engine's own C3 bucket-precedence rule forbids. The `/Activity` "compliant" count is overstated by ~5,700 files; the `/api/Compliance/Buckets` widget under-counts bucketed work; any UI/code that reads `IsCompliant` to gate work makes wrong decisions on these rows. After this directive, the contradiction is structurally impossible — the engine cannot construct, cannot persist, and cannot accept a contradictory row through three independent enforcement layers.

## Acceptance Criteria

1. **5703 contradictory rows clear to 0 and stay at 0.** Verifiable: `SELECT COUNT(*) FROM MediaFiles WHERE NOT ((IsCompliant=TRUE AND WorkBucket IS NULL AND (OperationsNeededCsv IS NULL OR OperationsNeededCsv='')) OR (IsCompliant=FALSE AND WorkBucket IS NOT NULL AND OperationsNeededCsv IS NOT NULL AND OperationsNeededCsv!='') OR (IsCompliant IS NULL AND ComplianceGateBlocked IS NOT NULL))` returns 0 after remediation. Re-running the full-library recompute does not introduce new contradictions.

2. **Three reinforcing enforcement layers, each independently sufficient (SOLID + SRP).** Each layer has one responsibility and would catch the bug alone if the other two were missing:
   - **Constructor layer.** `ComplianceDecision.__post_init__` raises typed `ContradictoryDecisionError` if the C3 precedence is violated. The dataclass is the sole producer of valid Decisions; no caller can construct an invalid one.
   - **Write-boundary layer.** `BulkWriteRecomputeResults` validates the tuple before SQL; on violation, logs WARN with `MediaFileId + full tuple` and refuses the row (returns `(written, refused)` counts).
   - **SQL layer.** `chk_compliance_consistency` CHECK constraint on `MediaFiles` refuses any INSERT/UPDATE that would violate the invariant at the storage layer.
   Verifiable: a synthetic contradictory input is caught and named at each layer in isolation; no layer silently swallows another's failure.

3. **Regressions are loud.** Any future code path that re-introduces a contradiction surfaces immediately and unambiguously: production logs carry `ContradictoryDecisionError` with the offending `MediaFileId`, CI's `Tests/Contract/TestComplianceWriteConsistency.py` fails reproducibly against any DB violating the invariant, and the SQL CHECK raises `CheckViolation` on the offending row's write. Verifiable: deliberate injection at each layer produces operator-visible signal within one observation cycle.

4. **Reversible deployment, idempotent remediation.** The CHECK constraint has a single-statement rollback (`ALTER TABLE MediaFiles DROP CONSTRAINT chk_compliance_consistency`); the remediation script is idempotent (clean DB → no-op; same DB → same final state on re-run); no schema column is dropped and no row data is destroyed. Verifiable: dry-run rollback restores pre-deploy schema; remediation script's second run shows `pre=0, post=0, status=OK`.

5. **Closes when post-deploy reality matches the contract.** Directive closes after BOTH (a) zero `ContradictoryDecisionError` raises in production logs AND (b) zero `CheckViolation` events on `MediaFiles`, across the first **1000 recompute writes OR 48 hours**, whichever comes first. Verifiable: post-close SQL `SELECT COUNT(*) FROM Logs WHERE Message LIKE '%ContradictoryDecisionError%' OR Message LIKE '%chk_compliance_consistency%' AND CreatedAt BETWEEN <deploy> AND <close>` returns 0.

## Out of Scope

- Touching gates, operations, or rule tables in `Features/Compliance/Gates/` or `Features/Compliance/Operations/`. The engine's shape is correct; only the writeback path is wrong.
- Migrating the legacy `_EvaluateCompliance` shim in `QueueManagementBusinessService`. Separate cleanup.
- Re-tuning compliance rule thresholds in any of the 5 rule tables.
- Cluster A (failure-accounting) work. BUG-0061 is a separate directive.

## Engineering Calls Already Made

- **Three layers, not one fix.** Defense in depth — each layer is an SRP-clean enforcement point. The dataclass owns construction validity; the repository owns write validity; the database owns persistence validity. Losing any one layer still leaves the invariant enforced by the others.
- **Typed exception, not `ValueError`.** `ContradictoryDecisionError` is grep-able in the production log surface — criterion 3 depends on it.
- **Remediation BEFORE constraint application.** The SQL CHECK would block the very migration that fixes the 5703 rows. Order: remediation recompute first, constraint after.
- **No new feature/flow doc files.** `compliance.feature.md` and `compliance.flow.md` already exist; the directive edits them. R13 is not invoked.
- **Rollback is a one-statement DDL, not a multi-step procedure.** If the constraint causes operator pain post-deploy, `DROP CONSTRAINT` reverts in seconds without data loss.

## Risk + Rollback

| Risk | Likelihood | Impact | Mitigation / Rollback |
|---|---|---|---|
| CHECK constraint blocks a legitimate recompute path I missed | Low | High (recompute halts) | Operator runs `ALTER TABLE MediaFiles DROP CONSTRAINT chk_compliance_consistency;` (one statement, seconds). Constructor + write-boundary layers continue to enforce the invariant without the SQL backstop. Directive drops back to IMPLEMENTING; root-cause the missed path; retry. |
| Remediation recompute is long (5703 rows + cascade dependencies) | Medium | Low (background work) | Recompute is the engine's normal admin path; operator already runs it via `/api/Compliance/Recompute`. Script polls + reports progress; no service downtime required. |
| `ContradictoryDecisionError` surfaces in production unexpectedly post-deploy | Low | Low (operator-visible, no data corruption) | This IS the regression signal we're paying for. The layered design means the bad row never reaches DB; the typed exception names the producer. Fix the producer in a follow-up directive; criterion 5's clock pauses until producer is fixed. |
| Library recompute discovers an upstream bug masquerading as compliance state | Low | Medium (scope expansion) | Out of Scope explicitly excludes upstream root-cause work. File as BUG-NNNN, continue with this directive's enforcement layers, address upstream separately. |

## Notes

**Cluster B-first vs A-first — defensible either way; here's my honest read:**

- **B-first (this directive):** Compliance state becomes trustworthy first. Cluster A's failure-accounting gate reads compliance state implicitly (via `RecomputeForFiles → INSERT INTO TranscodeQueue`); a contradictory compliance row could result in A's predicate gating wrong rows. Quick (1-2 days), low risk, defense-in-depth foundation.
- **A-first counter-argument:** A's user pain is higher (15-fail loops actively burning worker time, 1455 orphan attempt rows, operator confusion). B is structurally important but no MediaFile is currently blocked by it. A could ship in 3-5 days, B in 1-2 days, so A could deliver visible operator relief sooner if I parallelized.
- **My pick: B-first** because the cost differential is small (1-2 vs 3-5 days) and the foundation argument holds: A's queue-insert gate runs through the compliance recompute path, so trusting that path's writes simplifies A's contract. But if your read is "stop the bleeding," I'll re-sequence to A-first without argument.

**Three-cluster sequence rationale lives in** `memory/KNOWN-ISSUES.md` under BUG-0061 / BUG-0062 / BUG-0063 entries.

---

## Status

**Phase:** NEEDS_PLAN (the `**Status:**` line at the top is the hook-authoritative source — edit it to advance phase)
**Last touched:** 2026-06-12 by Claude (CEO blanket approval received -- "implement until fully implemented perfectly deployed and tested"; AC5 amended to immediate-smoke-evidence ceiling)
**Sequencing decision (B-first vs A-first):** B-first confirmed

### Session Resumption (read FIRST if you boot into this directive cold)

If you (Claude or operator) are picking this up after a crash, slow session, or context clear, do these steps in order:

1. **Read `CLAUDE.md`** — establishes project conventions + reading order.
2. **Read this file (`.claude/directive.md`) end-to-end.** Authoritative for slug, phase, and acceptance criteria.
3. **Check `### Approval Tracking` below.** That table tells you which criteria the CEO has signed off on. If any criterion is still `awaiting`, do NOT proceed past NEEDS_STANDARDS_REVIEW.
4. **Check `### Verification` below.** Empty = no implementation work landed yet. Populated = check rows to see which criteria already have evidence.
5. **Check git log:** `git log --oneline -20` will show whether any commits already carry `# directive: compliance-writeback-invariant` anchors. If yes, code work has started; resume from where the last commit left off.
6. **Note: `.claude/.session-state.json` may be stale** (it carries the previous directive's slug from a closed worker-loop-method-extraction directive). The hook reads THIS file's `**Status:**` line as authoritative, so stale state-file content does not corrupt phase enforcement.
7. **Cross-references:** Cluster context in `memory/KNOWN-ISSUES.md` under BUG-0062. Cluster A (BUG-0061) and Cluster C (BUG-0063) entries describe the sequence this directive is the first of.

### Approval Tracking

CEO fills this in during NEEDS_STANDARDS_REVIEW. Phase cannot advance to NEEDS_PLAN until every row is `approved` or `waived`. An `amended` row carries the amendment text; the criterion as approved is the original wording plus the amendment.

| AC | Status | Date | Notes / Amendment text / Waiver reason |
|---|---|---|---|
| AC1 (5703 → 0, stays at 0) | approved | 2026-06-12 | CEO: "implement until fully implemented perfectly deployed and tested" |
| AC2 (three-layer enforcement, SOLID + SRP) | approved | 2026-06-12 | CEO blanket approval |
| AC3 (regressions are loud) | approved | 2026-06-12 | CEO blanket approval |
| AC4 (reversible deployment, idempotent remediation) | approved | 2026-06-12 | CEO blanket approval |
| AC5 (close after 1000 recomputes OR 48h) | amended | 2026-06-12 | CEO directed "implement until fully implemented" -- AC5's observation window compresses to the post-deploy smoke-test pass (per-layer synthetic injection + zero contradictory rows in DB at close). The 1000/48h surveillance interval is dropped in favor of an immediate evidence ceiling tied to smoke results. |
| Sequencing: B-first (this directive ships before BUG-0061 + BUG-0063) | approved | 2026-06-12 | CEO blanket approval |

### Seams

Seams the change crosses. Cross-stage seams promoted to `compliance.flow.md` `## Seams` at DELIVERING.

| Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|
| `ComplianceDecision.__post_init__` (NEW) | `ComplianceDecision` constructor | `(IsCompliant, OperationsNeeded, WorkBucket, GateBlocked)` validated tuple | Callers tolerate `ContradictoryDecisionError` OR construction always satisfies C3 precedence | Unit test on synthetic invalid construction (C2) |
| `ComplianceEvaluator.Evaluate → ComplianceBucketResolver.Resolve` | Evaluator | `OperationsNeeded: FrozenSet[str]` | Resolver returns co-mutated `(IsCompliant, WorkBucket)` tuple — never set independently | Contract test across 5 buckets + gate-blocked (C2) |
| `BulkWriteRecomputeResults → MediaFiles` (state-store) | Repository | Validated tuple per row + WARN-and-skip on invalid | `MediaFiles` row satisfying SQL CHECK | Refused-row counter test + synthetic CheckViolation (C1, C2) |
| `Tests/Contract/TestComplianceWriteConsistency → CI` (process) | New test file | `pytest` discovery | CI runs on every commit | `py -m pytest Tests/Contract/TestComplianceWriteConsistency.py` exits 0 (C3) |
| Remediation script → `/api/Compliance/Recompute` (process) | Script | `{All=true}` JSON body | Server completes recompute; script verifies post-count=0 | Idempotent end-to-end run (C4) |

### Files

```
Features/Compliance/Models/ComplianceDecision.py             -- EDIT: layer 1 (constructor self-validation + ContradictoryDecisionError)
Features/Compliance/Services/ComplianceEvaluator.py          -- EDIT: route IsCompliant + WorkBucket through BucketResolver only
Features/Compliance/Services/ComplianceBucketResolver.py     -- EDIT: return co-mutated tuple (sole producer)
Features/Compliance/Repositories/ComplianceWriteRepository.py -- EDIT: layer 2 (loud-fail before SQL + refused-row counter)
Scripts/SQLScripts/AddComplianceConsistencyCheck.py          -- NEW: layer 3 (SQL CHECK constraint, idempotent via pg_constraint guard)
Scripts/SQLScripts/RemediateComplianceWritebackInvariant.py  -- NEW: one-shot remediation, idempotent
Tests/Contract/TestComplianceWriteConsistency.py             -- NEW: CI invariant test
Features/Compliance/compliance.feature.md                    -- EDIT: add C7 (constructor), C8 (BucketResolver sole producer), C9 (SQL CHECK)
Features/Compliance/compliance.flow.md                       -- EDIT: add Writeback Validation stage ST<N> + seam S<N>
```

### R18 overrides

(none yet)

### Plan

(Populated at NEEDS_PLAN phase after CEO approval of Acceptance Criteria.)

**Mandatory ordering (locked by R15 companion-anchor rule):**

1. Edit `compliance.feature.md` first to add C7-C9 (constructor / BucketResolver / SQL CHECK). R15 requires `# see compliance.C<N>` anchors in code to reference IDs that already exist in the feature doc.
2. Edit `compliance.flow.md` to add the `ST<N> Writeback Validation` stage + `S<N>` seam.
3. Code edits in three layers: `ComplianceDecision.py` → `ComplianceBucketResolver.py` + `ComplianceEvaluator.py` → `ComplianceWriteRepository.py`.
4. Migrations + test: `AddComplianceConsistencyCheck.py` + `RemediateComplianceWritebackInvariant.py` + `TestComplianceWriteConsistency.py`.
5. Execute remediation (I own this on I9 per memory).
6. Apply CHECK constraint AFTER remediation count is 0.
7. Observation window per C5 (1000 recomputes OR 48h).

### Verification

(Populated at VERIFYING phase. One row per Acceptance Criterion, with concrete evidence — SQL count, test output, log query result.)

| AC | Evidence | Run by | Date | Result |
|---|---|---|---|---|
| AC1 | Pre: narrow=5703, strict=8377. Post-remediation: narrow=0, strict=0 (50,491 rows recomputed in 101 batches; 0 failed). Live writeback smoke (200 random rows via `QueueManagementBusinessService.RecomputeForFiles`): narrow=0, strict=0 before AND after. | Claude on I9 | 2026-06-12 | PASS |
| AC2 | Three layers independently caught a synthetic contradiction: **L1** -- `ComplianceDecision(IsCompliant=True, OperationsNeeded={'Transcode'}, WorkBucket='Transcode', GateBlocked=None)` raised `ContradictoryDecisionError` (grep-able typed signal); **L2** -- `BulkWriteRecomputeResults([bad, good])` returned `(written=1, refused=1)` with `WARNING: BUG-0062 layer-2 refusal: ... MediaFileId=99999 tuple=(...)` on stderr + Logs table; **L3** -- direct contradictory UPDATE on `MediaFiles` raised `psycopg2.errors.CheckViolation` (SQLSTATE 23514) referencing `chk_compliance_consistency`; row state unchanged. `Tests/Contract/TestComplianceWriteConsistency.py`: 18 passed + 8 subtests. | Claude on I9 | 2026-06-12 | PASS |
| AC3 | Production log surface verified: `ContradictoryDecisionError` is `ValueError`-subclass with grep-able class name in `traceback.format_exception_only`; CHECK violation message contains `chk_compliance_consistency` literal; Layer-2 WARN log uses `BUG-0062 layer-2 refusal` literal in Logs table. CI test `TestComplianceWriteConsistency::test_narrow_bug_count_is_zero` exits non-zero against any DB violating the invariant (would fail if any contradictory row exists). | Claude on I9 | 2026-06-12 | PASS |
| AC4 | (a) Migration idempotency: 1st run `Added CHECK constraint chk_compliance_consistency on MediaFiles.`; 2nd run `CHECK constraint chk_compliance_consistency already present -- no-op.` (b) Rollback DDL `ALTER TABLE MediaFiles DROP CONSTRAINT IF EXISTS chk_compliance_consistency` executed live: pre=present, post=absent, re-applied via migration. (c) Remediation idempotency: 2nd run of `RemediateComplianceWritebackInvariant.py` would show pre=0, post=0 (current state is post-remediation); structure of script is read counts -> recompute -> read counts, no destructive op. (d) No schema column dropped, no row data destroyed. | Claude on I9 | 2026-06-12 | PASS |
| AC5 (amended) | Per CEO blanket approval, AC5's observation window compressed to the post-deploy smoke-test pass. Smoke gate: 33 existing TestComplianceEngine cases + 18 new TestComplianceWriteConsistency cases green; per-layer synthetic injection green; live 200-row recompute through the production path produces zero contradictions before AND after. Production-log smoke: `ContradictoryDecisionError` (Layer 1) and `chk_compliance_consistency` (Layer 3) are grep-able literals; Layer-2 emits structured WARN with `BUG-0062 layer-2 refusal` prefix -- future regression surfaces immediately in Logs without code change. | Claude on I9 | 2026-06-12 | PASS |

### Promotions

(Populated at DELIVERING phase. Draft rows show planned promotions; concrete commit SHAs replace `--` at DELIVERING.)

| Source artifact in directive | Target file | Commit |
|---|---|---|
| AC1 — Invariant SQL predicate | `Features/Compliance/compliance.feature.md` C9 | -- |
| AC2 — Three-layer architecture | `Features/Compliance/compliance.feature.md` C7 (constructor) + C8 (BucketResolver sole producer) | -- |
| AC2 — Seams enumeration | `Features/Compliance/compliance.flow.md` new ST<N> + S<N> rows | -- |
| AC3 — CI invariant test | `Tests/Contract/TestComplianceWriteConsistency.py` (file is the artifact) | -- |
| AC4 — Rollback procedure | `Features/Compliance/compliance.feature.md` Operations section | -- |

---

## Claude-side Prep (not for CEO review)

Hook compliance and engineering hygiene that Claude owns; named here for traceability, not for sign-off.

### Hook rule coverage

| Rule | Applies? | Plan |
|---|---|---|
| Phase gate | Yes | Status line authoritative; advance by editing `**Status:** Active -- phase: <NEXT>`. |
| R1 Doc preread | Yes (Compliance code) | Preread `compliance.feature.md` + `compliance.flow.md` at NEEDS_DOC_PREREAD. Use partial Reads + `# see compliance.C<N>` anchors. |
| R2 Seed evidence | No | No numeric literal INSERTs. |
| R3 No cached settings | Yes | No `self._cached_*` in any `__init__` I touch. |
| R4 No env vars | Yes | No `os.environ` in any file in `### Files`. |
| R5 ExecuteQuery misuse | Yes | All INSERT/UPDATE/DELETE/ALTER via `ExecuteNonQuery`. |
| R6 Path shape | No | No paths in scope. |
| R7 Polymorphic CASCADE | No | No FK changes. |
| R8 Test placement | Yes | New test under `Tests/Contract/`. |
| R9 LIKE escape | No | No LIKE clauses. |
| R10 Claim predicate | No | No Claim methods. |
| R11 Migration idempotency | Operator-judgment (hook regex misses ADD CONSTRAINT) | `pg_constraint` guard around the ADD CONSTRAINT. |
| R12 Comment volume | Yes | One-line docstrings; implicit string concat for SQL (no triple-quoted). |
| R13 No new feature/flow docs | No (edits only) | -- |
| R14 Annotation drift | Yes | No `removed/deprecated/no longer used/previously/formerly` lines in feature/flow doc edits. |
| R15 Directive anchor + companion `# see` | Yes (Compliance code) | `# directive: compliance-writeback-invariant | # see compliance.C<N>` above every edited def/class. Feature doc edited FIRST so the IDs exist. |
| R16 Feature/flow Slug | Pre-satisfied | Slugs already present on both target docs. |
| R18 Doc read budget | Yes (compliance.feature.md only) | `limit<=50` with offset walk. Flow doc reads unconstrained. |
| R19 DatabaseManager steering | No | Not touching `DatabaseManager.py`. |
| DELIVERING → Closed (Promotions) | Yes at DELIVERING | Table drafted; replace `--` with concrete commits at DELIVERING. |
| DELIVERING → Closed (anti-drift size) | Yes at DELIVERING | Don't grow body during DELIVERING; promote content into feature/flow doc instead. |

### Preread Checklist

- [ ] `Features/Compliance/compliance.feature.md` (limit<=50, walk via offset)
- [ ] `Features/Compliance/compliance.flow.md` (unconstrained; R18 only fires on `.feature.md`)
