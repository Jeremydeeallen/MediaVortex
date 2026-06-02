---
description: "Set up or audit a project's documentation and enforcement structure. Checks orientation questions, identifies gaps, and scaffolds missing pieces."
agent: "agent"
---
# Project Setup

Audit the project's documentation and structure for orientation gaps.

## Step 1: Load existing state

Read: copilot-instructions.md (or CLAUDE.md), README.md, memory/KNOWN-ISSUES.md, and top-level directory listing.

## Step 2: Orientation audit

Answer five questions by reading content. Report PASS / WEAK / FAIL for each:

### Q1: Where am I?
- Is there a root-level entry point doc?
- Does it state what the project does?
- Does it list build and test commands?

### Q2: What's in flight?
- Is there a current feature indicator?
- Does it point at a real feature doc with a Status line?

### Q3: What's broken?
- Is there a known-issues tracker?
- Is it discoverable from the root?
- Does it have recent entries?

### Q4: What does "done" mean here?
- Are there feature docs with numbered success criteria?
- Do they have Status lines?

### Q5: How do pipelines work?
- Are there flow docs for complex pipelines?
- Does the complexity warrant them?

## Step 3: Report and propose

Present findings as PASS/WEAK/FAIL per question. Propose only changes that close a specific gap. Ask before creating anything.
