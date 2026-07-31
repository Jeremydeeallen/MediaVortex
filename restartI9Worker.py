"""Kill the local WorkerService process and start a fresh one."""
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent
VENV_PY = REPO / "WorkerService" / "venv" / "Scripts" / "python.exe"
MAIN = REPO / "WorkerService" / "Main.py"


def _kill_existing():
    out = subprocess.run(
        ["wmic", "process", "where",
         "name='python.exe' and commandline like '%WorkerService\\\\Main.py%'",
         "get", "ProcessId", "/format:value"],
        capture_output=True, text=True,
    ).stdout
    pids = [line.split("=", 1)[1] for line in out.splitlines() if line.startswith("ProcessId=") and line.split("=", 1)[1]]
    for pid in pids:
        print(f"kill {pid}")
        subprocess.run(["taskkill", "/PID", pid, "/F", "/T"], capture_output=True)
    return len(pids)


def main():
    n = _kill_existing()
    print(f"killed {n} worker process(es)")
    time.sleep(1)
    print(f"start {MAIN}")
    subprocess.Popen(
        [str(VENV_PY), str(MAIN)],
        cwd=str(REPO / "WorkerService"),
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
    print("worker restarted")


if __name__ == "__main__":
    sys.exit(main())
