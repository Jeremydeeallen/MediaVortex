---
description: "Verifies the discovery cost of the current repo by answering four orient questions (what is this, what's done, what's broken, what's next) from docs alone."
agent: "agent"
---
# Discovery Check

Run a discovery-cost verification against this repo. Answer four orient questions cold -- reading only from files in the workspace, not from prior knowledge.

## Answer these four questions in order:

### 1. What is this repo?

One paragraph. Purpose, not a feature list. Read copilot-instructions.md or README.md.

### 2. What is done?

Bulleted. Features or capabilities currently working. Source: feature docs marked COMPLETE, progress checklists with closed entries.

**Caveat:** This reflects what is documented as done. Repos with undocumented working code should note that explicitly.

### 3. What is broken?

Bulleted. Real known issues. Check memory/KNOWN-ISSUES.md and feature docs for [BUG] criteria.

If no tracker exists, report: "No broken-items tracker discovered; absence is a finding."

### 4. What is next?

One sentence. The most load-bearing unfinished work. Check feature docs for IN PROGRESS status or unchecked progress items.

## Budget Report

Estimate total tokens read. Report whether discovery was achievable under 15k tokens. If over, identify exactly one specific missing doc that would have reduced the cost.
