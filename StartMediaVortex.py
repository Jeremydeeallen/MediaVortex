"""
StartMediaVortex - Service orchestrator
Opens each service in its own Windows Terminal tab using their own venv Python.

Network drives use NFS via the Windows NFS client. Porky exports the TV share;
Synology exports Movies + XXX. None of the mounts require credentials.
Mapped with /persistent:yes so they survive reboots.
"""

import os
import sys
import subprocess

RootDirectory = os.path.dirname(os.path.abspath(__file__))

NetworkDrives = [
    {"Letter": "T", "UncPath": r"\\10.0.0.43\srv\nfs-media-_tv", "Required": True},
    {"Letter": "M", "UncPath": r"\\10.0.0.61\volume1\_video\Adults\Movies", "Required": True},
    {"Letter": "Z", "UncPath": r"\\10.0.0.61\volume2\XXX", "Required": False},
]

Services = [
    {
        "Name": "WebService",
        "Directory": os.path.join(RootDirectory, "WebService"),
        "MainFile": "Main.py",
    },
    {
        "Name": "WorkerService",
        "Directory": os.path.join(RootDirectory, "WorkerService"),
        "MainFile": "Main.py",
    },
]


def GetPythonExe(ServiceDirectory):
    return os.path.join(ServiceDirectory, "venv", "Scripts", "python.exe")


def _MountNfsDrives(Drives):
    """Mount NFS drives via mount.exe with mtype=hard. Hard mounts retry RPCs forever instead
    of returning EINVAL when the server is briefly slow -- net use without explicit options
    defaults to mtype=soft + timeout=0.8s + retry=1, which caused intermittent FFmpeg
    'Error opening output file: Invalid argument' failures on worker output writes."""
    for Drive in Drives:
        Letter = Drive["Letter"]
        UncPath = Drive["UncPath"]
        Cmd = ["mount.exe",
               "-o", "mtype=hard",
               "-o", "timeout=30",
               "-o", "rsize=1024",
               "-o", "wsize=1024",
               "-o", "anon",
               UncPath, f"{Letter}:"]
        Result = subprocess.run(Cmd, capture_output=True, text=True)
        if Result.returncode == 0:
            print(f"  [OK]   {Letter}:\\ mounted")
        else:
            Tag = "[FAIL]" if Drive.get("Required", True) else "[WARN]"
            ErrorMsg = (Result.stdout + Result.stderr).strip().split("\n")[0]
            print(f"  {Tag} {Letter}:\\: {ErrorMsg}")


def main():
    print("================================")
    print("Starting MediaVortex services...")
    print("================================")

    # Check which drives need mounting
    DrivesNeeded = []
    for Drive in NetworkDrives:
        DrivePath = f"{Drive['Letter']}:\\"
        if os.path.exists(DrivePath):
            print(f"  [OK]   {DrivePath} already mounted")
        else:
            DrivesNeeded.append(Drive)

    if DrivesNeeded:
        _MountNfsDrives(DrivesNeeded)
        time.sleep(2)

    # Verify required drives are accessible
    for Drive in NetworkDrives:
        DrivePath = f"{Drive['Letter']}:\\"
        if Drive.get("Required", True) and not os.path.exists(DrivePath):
            print(f"  [FAIL] Required drive {DrivePath} is not accessible")
            sys.exit(1)
        elif not os.path.exists(DrivePath):
            print(f"  [WARN] Optional drive {DrivePath} is not accessible")

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

    # Launch all services as tabs in a single Windows Terminal window.
    # Each tab runs RunService.cmd which loops on Ctrl+C so you can restart.
    RunServiceScript = os.path.join(RootDirectory, "RunService.cmd")
    TabCommands = []
    for Service in Services:
        PythonExe = GetPythonExe(Service["Directory"])
        Tab = f'--title "{Service["Name"]}" -d "{Service["Directory"]}" "{RunServiceScript}" "{Service["Name"]}" "{PythonExe}" "{Service["MainFile"]}"'
        TabCommands.append(Tab)

    WtCmd = "wt.exe " + TabCommands[0]
    for Tab in TabCommands[1:]:
        WtCmd += f" ; new-tab {Tab}"

    subprocess.Popen(WtCmd)
    for Service in Services:
        print(f"  Launched {Service['Name']}")

    print("================================")
    print("All services launched.")


if __name__ == "__main__":
    main()