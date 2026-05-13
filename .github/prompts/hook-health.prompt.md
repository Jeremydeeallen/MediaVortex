---
description: "Verify that Copilot customization files (instructions, prompts, agents) are correctly configured and discoverable."
agent: "agent"
---
# Hook Health (Customization Verification)

Verify that Copilot customization files are correctly configured in this workspace.

## Step 1: Check instructions files

List all `.github/instructions/*.instructions.md` files. For each:
- Verify YAML frontmatter has `description`
- Check `applyTo` patterns are valid globs
- Report any with missing or empty descriptions

## Step 2: Check prompts

List all `.github/prompts/*.prompt.md` files. For each:
- Verify YAML frontmatter is valid
- Check that descriptions are keyword-rich for discoverability

## Step 3: Check agents

List all `.github/agents/*.agent.md` files. For each:
- Verify `description` is present
- Check `tools` list uses valid aliases
- Verify the body defines a clear role

## Step 4: Check copilot-instructions.md

- Verify `.github/copilot-instructions.md` exists
- Check it is not duplicating content from instruction files
- Verify it covers: project overview, commands, architecture, conventions

## Step 5: Report

```
Instructions:  X files, Y valid, Z issues
Prompts:       X files, Y valid, Z issues
Agents:        X files, Y valid, Z issues
Instructions:  [OK/MISSING/ISSUES]

Issues:
  [path] description
```
