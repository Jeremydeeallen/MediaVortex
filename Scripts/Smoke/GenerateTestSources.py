# directive: db-monolith-decompose
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TARGET_DIR = Path(r"X:\MediaVortex-TestMedia")
FFMPEG = REPO_ROOT / "FFmpegMaster" / "bin" / "ffmpeg.exe"
FFMPEG_FALLBACK = Path(r"C:\Code\MediaVortex\FFmpegMaster\bin\ffmpeg.exe")

SOURCES = [
    {
        "name": "bars-1080p-h264-10s.mp4",
        "width": 1920, "height": 1080, "duration": 10,
        "vcodec": "libx264", "acodec": "aac", "crf": 23,
    },
    {
        "name": "bars-4k-h264-10s.mp4",
        "width": 3840, "height": 2160, "duration": 10,
        "vcodec": "libx264", "acodec": "aac", "crf": 23,
    },
    {
        "name": "bars-1080p-hevc-10s.mp4",
        "width": 1920, "height": 1080, "duration": 10,
        "vcodec": "libx265", "acodec": "aac", "crf": 28,
    },
]


# directive: db-monolith-decompose
def ResolveFFmpeg() -> Path:
    if FFMPEG.exists():
        return FFMPEG
    if FFMPEG_FALLBACK.exists():
        return FFMPEG_FALLBACK
    raise SystemExit(f"ffmpeg.exe not found at {FFMPEG} or {FFMPEG_FALLBACK}")


# directive: db-monolith-decompose
def GenerateSource(FFmpegExe: Path, OutputPath: Path, Spec: dict, Force: bool) -> bool:
    if OutputPath.exists() and not Force:
        return False
    Vf = f"testsrc2=size={Spec['width']}x{Spec['height']}:rate=30:duration={Spec['duration']}"
    Af = f"sine=frequency=440:duration={Spec['duration']}"
    Cmd = [
        str(FFmpegExe), "-y",
        "-f", "lavfi", "-i", Vf,
        "-f", "lavfi", "-i", Af,
        "-c:v", Spec["vcodec"], "-preset", "fast", "-crf", str(Spec["crf"]),
        "-pix_fmt", "yuv420p",
        "-c:a", Spec["acodec"], "-b:a", "128k",
        "-shortest",
        str(OutputPath),
    ]
    Result = subprocess.run(Cmd, capture_output=True, text=True)
    if Result.returncode != 0:
        print(f"FAIL  {OutputPath.name}: {Result.stderr[-300:]}", file=sys.stderr)
        return False
    return True


# directive: db-monolith-decompose
def Main() -> int:
    Parser = argparse.ArgumentParser(description="Generate small synthetic test sources on X:\\MediaVortex-TestMedia (idempotent; skip if file already exists).")
    Parser.add_argument("--force", action="store_true", help="regenerate even if file exists")
    Parser.add_argument("--target", default=str(TARGET_DIR), help=f"target directory (default {TARGET_DIR})")
    Args = Parser.parse_args()
    Target = Path(Args.target)
    if not Target.parent.exists():
        print(f"ERROR: parent of target does not exist: {Target.parent}", file=sys.stderr)
        return 2
    Target.mkdir(parents=True, exist_ok=True)
    FFmpegExe = ResolveFFmpeg()
    print(f"FFmpeg: {FFmpegExe}")
    print(f"Target: {Target}")
    Created = 0
    Skipped = 0
    for Spec in SOURCES:
        Out = Target / Spec["name"]
        if GenerateSource(FFmpegExe, Out, Spec, Args.force):
            Size = Out.stat().st_size // 1024
            print(f"  CREATED  {Out.name}  ({Size} KB)")
            Created += 1
        else:
            if Out.exists():
                print(f"  SKIP     {Out.name}  (already present)")
                Skipped += 1
            else:
                print(f"  FAILED   {Out.name}")
                return 1
    print(f"\n{Created} created, {Skipped} already present.")
    return 0


if __name__ == "__main__":
    sys.exit(Main())
