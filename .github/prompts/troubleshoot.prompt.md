---
description: "Expert error troubleshooting skill. Always moves forward. Never repeats failed attempts. Use for deep debugging with retry tracking."
agent: "agent"
argument-hint: "<error-description>"
---
# Troubleshoot

Expert error troubleshooting. Always moves forward. Never repeats failed attempts.

## If no description provided -- show bug list:
1. Read memory/KNOWN-ISSUES.md
2. Present bugs grouped by severity (HIGH, MEDIUM, LOW)
3. User picks one to investigate
4. Proceed below

## Troubleshoot: {{input}}

### Step 1: Document the Problem
- Error message: exact text, error codes, stack traces
- Context: what operation, what state
- Reproduction: what steps led here
- Which feature doc criterion is violated

### Step 2: Check Docs First
1. Feature doc (*.feature.md near the code)
2. memory/KNOWN-ISSUES.md for known gotchas
3. Flow docs (*.flow.md near entry points)
4. Previous failure patterns
- If a fix was already tried and failed, DO NOT try it again

### Step 3: Research Root Cause
- Look up exact error in official docs (max 2 web searches)
- Read source at the exact function where error occurs
- Trace data flow: what values, what state
- Add diagnostic logging if cause not obvious

### Step 4: Identify the SINGLE Root Cause
> **Root cause:** [exact technical reason]
> **Evidence:** [log line or code that proves it]
> **Fix:** [exact change needed]

### Step 5: Apply the Fix
- Minimum change to fix root cause
- Do NOT refactor surrounding code
- Build and verify zero errors

### Step 6: Document
- Update feature doc criterion
- Record failure pattern so it is never repeated

## Retry Tracking
```
RETRY LOG:
Attempt 1: [tried] -> [result]
```
At attempt 3: STOP. Research from official docs.
At attempt 4: Ask user how to proceed.

## Rules
- NEVER guess. Add logging first.
- NEVER try the same fix twice.
- NEVER make multiple speculative changes.
- Trace from error backward to cause.
