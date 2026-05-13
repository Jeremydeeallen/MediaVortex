---
description: "Use when installing packages, managing dependencies, or configuring the Python environment. Covers venv conventions and requirements.txt workflow."
applyTo: "**/*.py"
---
# Python Environment

Uses a local venv and requirements.txt. No global installs.

## Verified conventions
- venv lives at `venv/` in the repo root
- `py -m venv venv` on Windows, `python3 -m venv venv` on Mac/Linux
- After activation, use `python` and `pip` (OS-agnostic)
- Every dependency goes in `requirements.txt` first, then `pip install -r requirements.txt`

## Common mistakes
- Installing packages with bare `pip install foo` without adding to requirements.txt
- Using `python3` on Windows (use `py`) or `py` on Mac/Linux (use `python3`)
- Committing `venv/` to git
