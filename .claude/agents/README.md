# Project Agents

This directory holds agents specific to this project. They coexist with global agents synced from `claude-config/agents/` into `~/.claude/agents/`.

## Resolution

If an agent in this directory shares a name with a global agent, the project version wins inside this repo. Same-name shadowing is an override -- use sparingly, not as a default pattern.

## Framework-level agents (already global, do not copy here)

- `ux-reviewer` -- invoked by `fs:` when a feature doc declares `## Surface`. Lives in `~/.claude/agents/`.
- `qa-tester` -- invoked by `fs:` step 2 to check success criteria. May live globally or per-project depending on setup.
