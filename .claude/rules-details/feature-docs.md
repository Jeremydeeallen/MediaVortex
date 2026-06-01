# Feature Docs -- Details

> Invariant: `.claude/rules/feature-docs.md`.

## Why the Workflows table exists

The Workflows table is the contract -- a directive that retires a surface must edit the affected rows in the same commit that deletes the code, or regression review will catch the missing capability.

Workflow IDs (`W1, W2, ...`) are stable and never renumbered -- downstream test plans and directive references depend on them. The Workflows table replaces ad-hoc "capability preservation" checklists. When refactoring or replacing a surface, reading the table is the safety net: every row is a capability that must continue to exist somewhere.

## Why the Seams table exists

Seams hide silent compensations (type coercions, defensive defaults, workaround logic). Without an explicit seam table per feature, the next code change can re-introduce bugs the previous code was quietly masking. See `.claude/rules/seam-verification.md` for the discipline.

The feature-doc Seams section covers intra-feature boundaries: function-call seams to helpers, wire-format seams to the DB / JSON / queue, UI seams to operator forms, process seams to other workers or services. Cross-stage pipeline seams live in the corresponding `*.flow.md` -- the feature doc references the flow doc, never duplicates.

## Slug + IDs operational notes

- Slug is derived mechanically from the filename. `Features/TranscodeQueue/queue-priority.feature.md` -> slug `queue-priority`. Backfilled by `Scripts/Maintenance/AddSlugsToFeatureDocs.ps1`; required by R16 on edit.
- Slugs are repo-unique. If two feature docs would derive the same slug (different directories, same filename stem), one of them gets a prefix: `<directory>-<filename>` -- the backfill script enforces uniqueness.
- IDs (W/S/C) are stable per doc and never reused after deletion. If `W3` is retired, the next workflow added is `W4` -- not a renumbering.
- Cross-doc references use fully-qualified form: `<slug>.<ID>`. Within a single doc you can use bare `S3` etc.

## Code anchors and R1 partial-read

When code carries `# see <slug>.S3` (e.g. `# see transcode-queue.S2`), R1's doc-preread requirement is satisfied by a partial Read that covers S2's section -- not a full-file Read. This is the primary token-saving mechanism for code-edit sessions.

Anchor placement: immediately above the function/method/block that touches the seam. The anchor isn't a comment-block (R12 allows single lines). Multiple anchors on adjacent lines OK -- one per related seam.

## Common mistakes

- Feature doc has no `## Seams` section -- every wire-format boundary becomes tribal knowledge until something breaks.
- `## Seams` lists what the feature DOES instead of what crosses its boundaries (that's `## What It Does`, a separate section).
- Wire shape is described semantically ("the file's quality score") instead of structurally (`TranscodeAttempts.VMAF DOUBLE PRECISION, NULL when not yet measured`).
- Verification column is empty or says "tested manually" -- without a runnable reference, the contract drifts silently.
- Feature doc duplicates content from flow docs instead of referencing them (creates two sources of truth that drift).
- Feature doc has no `## Workflows` section, or the table is missing the Backing column -- every operator capability becomes invisible to code review.
- A directive deletes a handler but doesn't update the corresponding Workflows row -- the row now points at code that doesn't exist. Grep on the backing column catches this; CI can be made to enforce it.
- New criteria added as bare integers (1, 2, 3) instead of `C1, C2, C3` -- breaks cross-doc references.
- W/S/C IDs renumbered after a deletion -- breaks anchors in code and references in closed directives.
- Slug derived inconsistently (kebab-case vs snake-case mix) -- the backfill script normalizes to lowercase-hyphenated.
