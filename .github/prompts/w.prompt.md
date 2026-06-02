---
description: "What's next -- reads the issues tracker, reports open bugs and tech debt, and flags anything needing immediate attention."
agent: "agent"
---
Report what is open and what needs attention:

1. Read memory/KNOWN-ISSUES.md.

2. Gather feature statuses efficiently:
   - Use grep to extract "Status" lines from all *.feature.md files in one call.
   - Only read individual feature docs if you need NEXT/handoff details for non-COMPLETE features.
   - Do NOT read every feature doc individually just to extract status fields.

3. Report all open items grouped by category: [BUG] criteria, tech debt, parked features (IN PROGRESS with no recent progress entry), NEXT handoff lines with no owner.

4. Flag anything that needs immediate attention: blocking bugs, features that are IN PROGRESS but stalled, or KNOWN-ISSUES entries with no feature doc tracking them.

5. Review the memory/KNOWN-ISSUES.md lifecycle:
   - Flag **Open** entries older than 30 days with no linked `[BUG]` criterion in any feature doc (orphaned issues).
   - Flag **Open** entries whose linked `[BUG]` criterion has been removed from the feature doc (silently resolved -- should be in Resolved).
   - If the **Resolved** section has more than 10 entries, recommend archiving the oldest to `memory/KNOWN-ISSUES-ARCHIVE.md`.
