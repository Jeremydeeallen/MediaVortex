"""
StartMediaVortex - Service orchestrator
Opens each service in its own Windows Terminal tab using their own venv Python.
"""

import os
import sys
import subprocess
import time

RootDirectory = os.path.dirname(os.path.abspath(__file__))

NetworkDrives = [
    {"Letter": "T", "UncPath": r"\\10.0.0.40\mnt\pve\Media\_tv"},
]

Services = [
    {
        "Name": "WebService",
        "Directory": os.path.join(RootDirectory, "WebService"),
        "MainFile": "Main.py",
    },
    {
        "Name": "TranscodeService",
        "Directory": os.path.join(RootDirectory, "TranscodeService"),
        "MainFile": "Main.py",
    },
]


def GetPythonExe(ServiceDirectory):
    return os.path.join(ServiceDirectory, "venv", "Scripts", "python.exe")


def main():
    print("================================")
    print("Starting MediaVortex services...")
    print("================================")

    # Ensure required network drives are mounted
    for Drive in NetworkDrives:
        DrivePath = f"{Drive['Letter']}:\\"
        if os.path.exists(DrivePath):
            print(f"  [OK]   {DrivePath} already mounted")
        else:
            print(f"  [MAP]  Mounting {DrivePath} -> {Drive['UncPath']}")
            result = subprocess.run(
                ["powershell", "-Command",
                 f"New-PSDrive -Name {Drive['Letter']} -PSProvider FileSystem -Root \"{Drive['UncPath']}\" -Persist"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                print(f"  [OK]   {DrivePath} mounted successfully")
            else:
                print(f"  [WARN] Failed to mount {DrivePath}: {result.stderr.strip()}")

    # Validate all services before launching
    for Service in Services:
        PythonExe = GetPythonExe(Service["Directory"])
        MainFile = os.path.join(Service["Directory"], Service["MainFile"])
        if not os.path.exists(PythonExe):
            print(f"  [FAIL] {Service['Name']}: venv python not found at {PythonExe}")
            sys.exit(1)
        if not os.path.exists(MainFile):
            print(f"  [FAIL] {Service['Name']}: Main.py not found at {MainFile}")
            sys.exit(1)

    # Launch each service as a separate wt tab with a delay between them
    for i, Service in enumerate(Services):
        PythonExe = GetPythonExe(Service["Directory"])
        MainFile = os.path.join(Service["Directory"], Service["MainFile"])
        TabCmd = ["wt.exe", "--title", Service["Name"], "-d", Service["Directory"], PythonExe, MainFile]
        subprocess.Popen(TabCmd)
        print(f"  Launched {Service['Name']}")
        if i < len(Services) - 1:
            time.sleep(3)

    print("================================")
    print("All services launched.")


if __name__ == "__main__":
    main()