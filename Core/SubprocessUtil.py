# directive: probe-worker-decoupled -- shared helper: return CREATE_NO_WINDOW under Windows so subprocess spawns from a windowless parent (pythonw) don't allocate a visible console; returns 0 on non-Windows.
import os
import subprocess


def NoWindowFlags() -> int:
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
