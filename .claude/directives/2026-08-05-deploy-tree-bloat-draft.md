# Directive: deploy-tree-bloat

**Status:** Active -- phase: NEEDS_STANDARDS_REVIEW
**Opened:** 2026-08-05
**Slug:** deploy-tree-bloat

## Outcome

Fleet deploy of a code-only change ships in seconds, not minutes. Runtime-generated dirs (`cache/`, `test_remux_sandbox/`, per-run artifacts) do not silently balloon the tar stream. Regression is caught by a check that fails loud, not by a slow deploy.

## Domain Decisions

Operator-set 2026-08-05.

**DD_A. `.deployignore` becomes an EXCLUDE-then-INCLUDE model, not a static blocklist.**
Reason: 2026-08-01 fix (commit `34180100`) recreated `.deployignore` with a static list of known-bad dirs (VCS, venvs, bytecode, IDE). Solved the crisis. But `.deployignore` still ships everything not on the list -- so `cache/vmaf-compare` (5.5 GB), `test_remux_sandbox/` (42 MB private videos), test-media files under `Scripts/Smoke/`, and any future runtime-generated dir all sneak through and bloat every deploy. Deploys silently regress; only symptom is minutes instead of seconds.
How to apply: `.deployignore` explicitly excludes runtime-generated + large-binary + private test-media dirs today (`cache`, `test_remux_sandbox`, and enumerate the large `Scripts/Smoke/*` binaries or exclude the smoke dir entirely if smoke stays local). Longer-term: consider inverting to a `.deployinclude` allowlist (code only), but that's OOS unless the blocklist can't reach parity.

**DD_B. Deploy fails loud when tar payload exceeds budget.**
Reason: silent slowdown is the exact failure pattern we just hit. A payload budget (e.g. **50 MB**) is the shape-agnostic invariant a code-only deploy respects. Anything above suggests unlisted bloat.
How to apply: `deploy/SyncSource.py` sums the tar payload as it streams; if > 50 MB, print a warning naming the top 5 largest files/dirs and abort with a non-zero exit code, forcing operator to either exclude the new bloat or explicitly raise the budget. Budget lives in `SystemSettings.DeployPayloadBudgetMb` per db-is-authority + gui-editable-knobs; operator can raise it (e.g. after adding new AI models that legitimately need to ship).

## Acceptance Criteria

C1. **Fleet deploy of an unchanged code tree completes in under 60s total wall time.** With sync-source step under 15s per host. Empirically observable in `sync:<host> END ... elapsed` line.

C2. **`.deployignore` excludes `cache`, `test_remux_sandbox`, and any large binary that's not runtime-required on workers.** Grep `.deployignore`: contains `cache` and `test_remux_sandbox` as literal glob entries.

C3. **`deploy/SyncSource.py` refuses to stream a payload > `SystemSettings.DeployPayloadBudgetMb` (default 50).** Contract: run SyncSource against a synthetic dir with a 100 MB file at budget=50; assert non-zero exit + stderr names the offending file.

C4. **`SystemSettings.DeployPayloadBudgetMb` row exists, default 50, whitelist-guarded to positive int.** Contract test.

C5. **Larry LXC 218 disk usage drops below 50% after next deploy + GC.** Old bloated `src-<sha>` dirs are pruned by GC-keep-5; combined with the fixed `.deployignore` the new versioned dirs are ~30 MB each. `pct exec 218 -- df -h /opt/mediavortex` shows <50% used post-fix.

## Call-Graph Audit

1. **Multiple flow docs for one operation.** `deploy/worker-deploy-baremetal.flow.md` is the primary. No competing flow doc for sync.
2. **Mode-branching at orchestration.** None. `.deployignore` applies to all hosts identically. Budget check applies to all hosts.
3. **Shared output columns.** `DeployHistory` records elapsed time; a payload-budget-refused deploy writes `Outcome=FAILED` + `ErrorMessage='payload_budget_exceeded: ...'`. Same schema, new outcome path.
4. **Config-driven graph shape.** `DeployPayloadBudgetMb` is DATA. Same code path runs regardless of value.
5. **OOS classification.** Every OOS item categorized (a) or (b) below.

## Out of Scope

- **Inverting to a `.deployinclude` allowlist.** (b) deferred. Blocklist can reach parity if maintained; only revisit if repeated regressions occur.
- **Incremental / hardlink-dedup deploy** (rsync `--link-dest` between `src-<sha_prior>` and `src-<sha_current>`). (b) deferred. Bigger refactor; current tar-over-ssh is simpler + works once payload is small.
- **CDN / registry-based deploy.** (b) deferred. Homelab-scale; not needed.
- **Auto-repair of the 89 AoT `KeepSource=TRUE` files.** (b) not this directive. Owner decides when to re-enable.

## Files (planned)

Frozen at NEEDS_PLAN.

### To edit
- `.deployignore` -- add `cache`, `test_remux_sandbox`, and any auditable bloat.
- `deploy/SyncSource.py` -- add payload-budget check; abort + name top-5 largest on breach.
- `Scripts/SQLScripts/AddDeployPayloadBudget_<date>.py` -- idempotent seed of `DeployPayloadBudgetMb=50`.
- `Features/SystemSettings/SystemSettingsController.py` -- whitelist positive-int values for the new key.

### To add
- `Tests/Contract/TestDeployPayloadBudget.py` -- C3 + C4.

### To promote at DELIVERING
- `deploy/worker-deploy-baremetal.flow.md` -- add payload-budget invariant.
- `.claude/rules/worker-deploy.md` -- add sentence: "Deploy payload budget: fresh `src-<sha>` is < 50 MB by default; SyncSource fails loud above budget."

## Progress

- [ ] NEEDS_STANDARDS_REVIEW: read every `.claude/rules/*.md` + `.claude/standards/index.md`; audit call-graph
- [ ] NEEDS_PLAN: freeze Files list
- [ ] NEEDS_DOC_PREREAD: read `deploy/worker-deploy-baremetal.flow.md` + related feature docs
- [ ] IMPLEMENTING: land the 4 file edits + migration + test
- [ ] VERIFYING: re-run fleet deploy; measure sync time; confirm all hosts complete under 15s host-sync
- [ ] DELIVERING: delivery report + Promotions

## Notes

- Where we went wrong: commit `34180100` (2026-08-01) recreated `.deployignore` after docker-purge deleted it. Static blocklist. `cache/vmaf-compare` didn't exist / was tiny at that moment; grew to 5.5 GB by 2026-08-05 via runtime VMAF comparison artifacts.
- Today's fleet deploy: fleet wall time 1376s (23 min). Larry sync failed at step 5 due to disk quota after larry LXC 218 accumulated three 7 GB `src-<sha>` versioned dirs. Manual cleanup + re-sync recovered.
- Fixing the root .deployignore prevents recurrence; payload-budget invariant makes future regressions fail loud instead of silent.
