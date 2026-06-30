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


# directive: audio-dialog-boost-real | # see audio-normalization.C14
def _LaunchOne(PythonExe, Prefix, Slot):
    Env = os.environ.copy()
    Env["MEDIAVORTEX_WORKER_PREFIX"] = Prefix
    return subprocess.Popen(
        [PythonExe, str(WorkerEntry)],
        cwd=str(RootDirectory),
        env=Env,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )


# directive: audio-dialog-boost-real | # see audio-normalization.C14
def main():
    Parser = argparse.ArgumentParser(description="Launch N parallel MediaVortex workers.")
    Parser.add_argument("--count", type=int, default=3, help="Number of worker instances (default 3).")
    Parser.add_argument("--prefix", type=str, default="i9", help="Worker name prefix (default 'i9'); each becomes {prefix}-N.")
    Args = Parser.parse_args()

    if not WorkerEntry.exists():
        print(f"[FAIL] WorkerService entry not found at {WorkerEntry}")
        return 2

    PythonExe = _ResolvePython()
    print(f"Launching {Args.count} workers with prefix '{Args.prefix}' using {PythonExe}")
    print("=" * 60)

    Children = []
    for Slot in range(Args.count):
        Child = _LaunchOne(PythonExe, Args.prefix, Slot + 1)
        Children.append(Child)
        print(f"[OK] launched pid {Child.pid} (slot {Slot + 1})")
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
