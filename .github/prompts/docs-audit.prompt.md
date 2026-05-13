---
description: "Audit all project documentation for staleness, duplication, orphaned files, broken references, and sprawl. Recommends delete/merge/move/update actions."
agent: "agent"
---
# Documentation Audit

Systematic audit of all documentation in the current project. Finds sprawl, staleness, duplication, and broken references.

## Step 1: Discover All Docs

Find all markdown files in the workspace. List documentation directories and key files (CLAUDE.md, README.md, etc).

## Step 2: Check for Broken References

For every markdown file, extract file path references and verify they exist. Report every broken link with source file and target.

## Step 3: Check for Stale Code References

Find references to specific code artifacts (function names, file:line patterns) and verify they still exist. Flag mismatches.

## Step 4: Check for Duplication

Look for the same information in multiple places:
- copilot-instructions.md vs instruction files
- Feature docs vs other docs
- Multiple files covering the same topic

## Step 5: Check for Orphaned Files

- Memory files not indexed anywhere
- Feature docs referencing code that no longer exists
- Flow docs where the flow has been removed

## Step 6: Doc Health Metrics

- Files over size thresholds
- Feature docs missing required sections (Success Criteria, Status)
- Standalone docs that should be in docs/ or a feature directory

## Step 7: Generate Report

Compile findings into: Broken Links, Stale References, Duplicates, Orphans, Health Warnings, with recommended actions (delete/merge/move/update).
