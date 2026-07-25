# directive: audio-dialog-boost-real | # see audio-normalization.C14
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from Core.Path.LocalPath import LocalExists

RootDirectory = Path(__file__).resolve().parent
WorkerEntry = RootDirectory / "WorkerService" / "Main.py"
DefaultVenvPython = RootDirectory / "WorkerService" / "venv" / "Scripts" / "python.exe"


# directive: audio-dialog-boost-real | # see audio-normalization.C14
def _ResolvePython():
    if LocalExists(str(DefaultVenvPython)):
        return str(DefaultVenvPython)
    print(f"[WARN] venv not found at {DefaultVenvPython}; using {sys.executable}")
    return sys.executable


# directive: transcode-flow-canonical | # see claim-authority.md
def _LaunchOne(PythonExe, WorkerName):
    Env = os.environ.copy()
    Env["MEDIAVORTEX_WORKER_NAME"] = WorkerName
    return subprocess.Popen(
        [PythonExe, str(WorkerEntry)],
        cwd=str(RootDirectory),
        env=Env,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )


# directive: transcode-flow-canonical | # see claim-authority.md
def main():
    Parser = argparse.ArgumentParser(description="Launch N parallel MediaVortex workers.")
    Parser.add_argument("--count", type=int, default=3, help="Number of worker instances (default 3).")
    Parser.add_argument("--prefix", type=str, default="i9", help="Worker name prefix; each becomes {prefix}-worker-N (matches deploy-assigned naming).")
    Args = Parser.parse_args()

    if not WorkerEntry.exists():
        print(f"[FAIL] WorkerService entry not found at {WorkerEntry}")
        return 2

    PythonExe = _ResolvePython()
    print(f"Launching {Args.count} workers as '{Args.prefix}-worker-1..{Args.count}' using {PythonExe}")
    print("=" * 60)

    Children = []
    for Slot in range(Args.count):
        WorkerName = f"{Args.prefix}-worker-{Slot + 1}"
        Child = _LaunchOne(PythonExe, WorkerName)
        Children.append(Child)
        print(f"[OK] launched pid {Child.pid} as {WorkerName}")
        time.sleep(2)

    print()
    print(f"All {Args.count} workers running. Ctrl+C to stop all.")

    try:
        while True:
            time.sleep(5)
            Alive = [C for C in Children if C.poll() is None]
            Dead = [C for C in Children if C.poll() is not None]
            if Dead:
                print(f"[WARN] {len(Dead)} worker(s) exited; surviving={len(Alive)}")
                for D in Dead:
                    print(f"  pid {D.pid} exit={D.returncode}")
                Children = Alive
            if not Children:
                print("[FAIL] all workers exited")
                return 1
    except KeyboardInterrupt:
        print("\nShutting down workers...")
        for C in Children:
            try:
                C.terminate()
            except Exception as Ex:
                print(f"  terminate pid {C.pid} failed: {Ex}")
        for C in Children:
            try:
                C.wait(timeout=30)
            except subprocess.TimeoutExpired:
                C.kill()
        return 0


if __name__ == "__main__":
    sys.exit(main())
