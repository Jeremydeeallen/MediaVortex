---
description: "Troubleshoot and fix a bug. Doc-first: ensures feature and flow docs exist before touching code so the fix is verifiable."
agent: "agent"
argument-hint: "<bug-description>"
---
Troubleshoot: {{input}}

Follow doc-first order. Do not read source code until step 5.

1. Read KNOWN-ISSUES.md. Match to an existing entry. If no entry exists, record it first (what breaks, which feature, what file to look at), then resume here.

2. Read the feature doc for the affected feature. If no criterion matches this bug, add a [BUG] criterion before proceeding -- the fix is not verifiable without one.

3. Read the flow doc for the affected pipeline. If no flow doc exists, create it before proceeding. The flow doc traces entry points, data steps, and failure modes so the next session does not start from zero.

4. Read relevant docs (KNOWN-ISSUES.md, architecture docs) for prior known state.

5. Source code LAST -- only after docs exist and have been read.

6. Report root cause and evidence before writing any fix: name the layer, file, function, and the proof that this is the root cause rather than a symptom.

7. Fix the original issue. Verify the fix against the [BUG] criterion from step 2 -- the criterion is the definition of "fixed".

8. Update the flow doc if the fix changed the pipeline.

## Retry Tracking
Maintain a visible retry count:
```
RETRY LOG:
Attempt 1: [what was tried] -> [result]
```
At attempt 3 with no progress: STOP. Research from official docs.
At attempt 4: Ask user how to proceed. Do not continue guessing.

## Rules
- NEVER guess. If you don't know the cause, add logging first.
- NEVER try the same fix twice.
- NEVER make multiple speculative changes. One change, one build, one test.
- Always trace from the error backward to the cause.
