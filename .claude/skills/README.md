# Project Skills

This directory holds skills specific to this project. They coexist with global skills synced from `claude-config/skills/` into `~/.claude/skills/`.

## Resolution

If a skill in this directory shares a name with a global skill, the project version wins inside this repo. Same-name shadowing is an override -- use sparingly, not as a default pattern.

## Naming

Prefix project skills with the project slug (e.g. `mediavortex-db-query`) to avoid accidental shadowing. Prefix-less names are reserved for framework-level skills in the global pool.
