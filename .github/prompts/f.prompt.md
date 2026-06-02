---
description: "Finalize current work. Turns off debug logging, updates the feature doc progress checklist, marks the feature COMPLETE, and reports git status."
agent: "agent"
---
Finalize the current feature. Work through these steps in order:

1. Turn off any debug logging, verbose flags, or temporary instrumentation added during development.

2. Update the feature doc ### Progress checklist: mark completed items with their commit hashes. Every decision point that happened during implementation should have a progress entry.

3. Mark the feature doc ## Status as COMPLETE.

4. Move resolved bugs from **Open** to **Resolved** in memory/KNOWN-ISSUES.md. Annotate each with `[BUG - FIXED <today's date>]`. Only move entries that are verifiably fixed by this work. Do NOT delete entries.

5. If the **Resolved** section has more than 10 entries, move the oldest resolved entries to `memory/KNOWN-ISSUES-ARCHIVE.md` (create the archive file if it does not exist).

6. Quick tracker hygiene (while memory/KNOWN-ISSUES.md is open): scan **Open** entries. Flag any that are older than 30 days or whose linked `[BUG]` criterion no longer exists in the feature doc. Report findings inline -- do not block finalization.

7. Run git status and report the current state of the working tree.
