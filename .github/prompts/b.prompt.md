---
description: "Record a bug without investigating it. Use when a bug is found during feature work that is not blocking and not a small same-file fix."
agent: "agent"
argument-hint: "<bug-description>"
---
Record bug: {{input}}

Do NOT investigate, fix, or expand scope. Capture context only -- these steps preserve the bug at peak freshness so a dedicated session can fix it efficiently.

1. Read KNOWN-ISSUES.md. Deduplicate: if this bug is already recorded, add any new context to the existing entry and stop.

2. Identify which feature doc(s) this bug violates. A bug always violates at least one success criterion.

3. Check that a feature doc exists for each affected feature. Document this in the bug if it does not exist.

4. Add a [BUG] tagged criterion to the relevant feature doc(s). The criterion should be testable: describe what "fixed" looks like, not just what is broken.

5. Check whether a flow doc covers the affected pipeline. If none exists, flag the gap -- /t will create the flow doc before fixing.

6. Write an entry in the **Open** section of KNOWN-ISSUES.md using this format: `### [BUG] <description>` with date, what breaks, which feature criterion it violates, and what file/function to look at first.

7. If the **Resolved** section of KNOWN-ISSUES.md has more than 10 entries, move the oldest resolved entries to `memory/KNOWN-ISSUES-ARCHIVE.md` (create the archive file if it does not exist).

8. Report: use /t to investigate and fix in a dedicated session.

Report back to the user: done <action taken>
