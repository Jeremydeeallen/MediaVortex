# Backlog Directive: Transcode-Pipeline Comment Promotion

**Filed:** 2026-05-31 (by `nvenc-rate-anchored-remediation` close-out)
**Status:** Backlog -- not yet started
**Slug:** transcode-pipeline-comment-promotion
**Triggered by:** `nvenc-rate-anchored-remediation` directive scattered ~50 `# allow: R12 -- preexisting` overrides across `ProcessTranscodeQueueService.py`, `QualityTestingBusinessService.py`, `ProfileController.py`, `ProfileManagementViewModel.py`, `ProfileService.py`. Per `.claude/rules/ceo-mode.md#handling-preexisting-comment--doc-violations-encountered-mid-directive`, that's deferred tech debt; this directive collects it.

## Outcome

The five files listed above carry no preexisting multi-line docstrings or `#` comment blocks. Every multi-line block was classified per the policy and either deleted, moved to a permanent home, or collapsed to a single line. All `# allow: R12 -- preexisting` overrides are removed. The hook does not flag R12 violations in any of these files.

## Acceptance Criteria

1. `grep -n "# allow: R12" Features/TranscodeJob/ProcessTranscodeQueueService.py Features/QualityTesting/QualityTestingBusinessService.py Features/Profiles/ProfileController.py Features/Profiles/ProfileManagementViewModel.py Features/Profiles/ProfileService.py` returns zero matches.
2. Every multi-line comment / docstring that existed at the start of this directive has a documented disposition: `DELETED` | `COLLAPSED` | `MOVED <- <destination>`. Recorded in this directive's `## Status` block.
3. Permanent-invariant content (BUG references, hard-won constraints, the VMAF input-order BUG-0022 explanation, the disposition decision-table rationale) lives at its new permanent home; grep confirms.
4. Touching any of the five files no longer triggers R12 refusals on preexisting code.
5. No behavior change. `Tests/Contract/` suite green before and after.

## Out of Scope

- `Models/CommandBuilder.py` -- tracked by `commandbuilder-comment-promotion`.
- R6 path-shape migration -- tracked by `path-shape-migration`.

## Reference

Source policy: `.claude/rules/ceo-mode.md#handling-preexisting-comment--doc-violations-encountered-mid-directive`
Parent directive (closed): `.claude/directives/closed/2026-05-31-nvenc-rate-anchored-remediation.md`
