---
description: "Bug success -- cleanup and commit after a bug fix is verified. Removes [BUG] tags, cleans up failed fix attempts, and commits."
agent: "agent"
---
Bug success -- close out the fix cleanly:

1. Remove the [BUG] tag from the feature doc criterion. Keep the criterion text as a normal passing criterion so the fix is permanently testable.

2. Remove the bug entry from KNOWN-ISSUES.md.

3. Dead code cleanup: remove any code from failed fix attempts made during this session.

4. Update flow docs if the fix changed the code path -- a fixed bug often reveals a gap in the flow doc's failure-modes section.

5. Commit with a descriptive message. Include the feature doc path and criterion number in the message body.
