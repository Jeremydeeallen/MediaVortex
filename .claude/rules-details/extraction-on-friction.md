# Extraction on Friction

When hook refusals cluster on the same file, the file is over-scoped. Decompose by SRP before landing the original edit.

## Trigger

This rule applies when an active directive's edit hits **two or more** of:

- R1 preread refusals naming **distinct** colocated `*.feature.md` / `*.flow.md` files on one source file
- R6 path-shape refusals at lines **outside** the directive's edited region
- R12 anchor refusals on functions outside the directive's SRP focus
- A single file with `>= 3` colocated feature docs

These signals mean the file is carrying multiple concerns. The hooks scale linearly with file size; further edits pay the same tax indefinitely until decomposition lands.

## Sequence

1. **Stop the current directive.** Close as `Abandoned` (architecture pivot) or `Paused -- preempted by <decompose-slug>`. Populate `### Promotions` with one row: `no promotions | n/a | superseded by <decompose-slug>`.

2. **Open `<filename-stem>-decompose` directive.** Slug example: `FileReplacementBusinessService.py` -> `filereplacement-decompose`. Outcome paragraph names: each SRP cluster lands in its own file with its own colocated feature doc; original file's name finally matches its remaining content; R1 preread cost on the original file drops to 1; R6 fires zero times on a clean edit inside any extracted slice.

3. **Inventory before extracting.** Read-only Explore agent produces:
   - Method roster grouped by SRP cluster (one cluster per colocated doc usually).
   - Caller graph (`grep -rn "from <module> import <symbol>"`) per cluster.
   - Path-shape violation sites per cluster (line + variable + producer).
   - Cross-cluster dependencies (which extracted file imports which).
   The inventory becomes the directive's `## Engineering Calls Already Made` and `### Files` blocks.

4. **One commit per extraction.** Each commit moves one SRP cluster + creates its colocated feature doc + adds Seams table + cleans R6 sins inside the moved code. Imports in original file get updated. Tests stay green.

5. **Seams table is the upstream/downstream contract.** For each extraction:
   - Producer column: the caller(s) that invoke the extracted methods.
   - Wire shape: argument types + return shape + any DB/file side effect.
   - Consumer expects: invariants the extracted code relies on from its inputs.
   - Verification: contract test or runnable command that exercises the boundary.

   If a seam can't be expressed concretely, the cluster isn't well enough understood to extract yet — read producers and consumers first.

6. **Flow doc when pipeline-shaped.** If the extracted slice participates in a multi-stage pipeline, the colocated `*.flow.md` gets `ST<N>` stage IDs + cross-stage Seams. Code carries `# see <slug>.ST<N>` anchors so R1 accepts partial reads.

7. **Resume the original directive** once decomposition closes. The original ask is now the smallest natural slice on a clean file; the previous hook friction is gone.

## Compliance check (end of each extraction)

- One `.py` <-> one `*.feature.md` (plus optional `*.flow.md`).
- Slug matches filename matches feature-doc title.
- Seams table enumerates every cross-file caller + every external write (DB row, on-disk file, HTTP call).
- R1 preread cost on next edit to the extracted file = 1 doc.
- R6 firing on the extracted file = 0 (path-shape sins inside the slice got fixed in the same commit).
- The original file's line count dropped by approximately the size of the extracted cluster.

## Anti-patterns

- **`# allow:` per-line silencing.** Defers the architectural fix forever; grows debt linearly with edits.
- **Hook rule relaxation as the fix.** Edited-region-only gates are reasonable for R1/R15 (already done) but treating R6 the same way hides the path-shape debt that R6 is correctly surfacing.
- **Extracting without docs.** Moving methods to a new file without a colocated feature doc + Seams table just re-distributes the mega-file problem.
- **Parallel extractions on the same source file.** Each extraction edits the source file's imports; serialize them.

## When NOT to extract

- Trigger condition not met (one hook refusal on legacy code is `# allow:` territory if the legacy code has a documented reason; reference the doc).
- File is < ~300 lines and has one colocated doc — friction is not architectural, it's localized debt.
- The "cluster" turns out to be a single method with no natural sibling — move the method into an existing well-scoped file rather than creating a new one for one symbol.

## Related rules

- `.claude/rules/doc-layering.md` -- three-tier model; extracted files get a feature doc as a durable contract.
- `.claude/rules/feature-docs.md` -- shape of the colocated feature doc the extraction produces.
- `.claude/rules/flow-docs.md` -- shape of the flow doc when the extraction is pipeline-shaped.
- `.claude/rules/seam-verification.md` -- discipline for enumerating + round-tripping seams at the extraction boundary.
- `.claude/rules-details/ceo-mode.md` -- handling preexisting violations; this rule supersedes the `# allow:` override path when refusals cluster.
