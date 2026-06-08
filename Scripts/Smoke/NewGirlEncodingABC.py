"""Three-variant encode + VMAF test against a single bloated source.

For 'should we keep at 720p for sitcom content?' tuning. Runs three SVT-AV1
transcodes at different (resolution, CRF) combos all targeting roughly the
same bitrate budget, then VMAFs each against the source with the comparison
forced to 720p for apples-to-apples scoring across variants. Outputs a
results table.

Source files are never modified. Test outputs land alongside the source
with `-test-<res>` suffix so they don't collide with pipeline products.

Usage: py Scripts/Smoke/NewGirlEncodingABC.py
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

SOURCE = r"T:\New Girl\Season 7\New Girl - S07E01 - About Three Years Later WEBDL-1080p.mkv"
OUT_DIR = r"T:\New Girl\Season 7"
FFMPEG = r"C:\Code\MediaVortex\FFmpegMaster\bin\ffmpeg.exe"
FFPROBE = r"C:\Code\MediaVortex\FFmpegMaster\bin\ffprobe.exe"

VARIANTS = [
    {"name": "A", "label": "1080p CRF32", "scale": None,        "crf": 32, "outname": "S07E01-test-1080p.mp4"},
    {"name": "B", "label": "720p CRF25",  "scale": "1280:720",  "crf": 25, "outname": "S07E01-test-720p.mp4"},
    {"name": "C", "label": "480p CRF18",  "scale": "854:480",   "crf": 18, "outname": "S07E01-test-480p.mp4"},
]


def Log(Msg):
    Stamp = time.strftime("%H:%M:%S")
    print(f"[{Stamp}] {Msg}", flush=True)


def Encode(V):
    Out = os.path.join(OUT_DIR, V["outname"])
    Cmd = [
        FFMPEG, "-i", SOURCE,
        "-map", "0:v:0", "-map", "0:a:0",
        "-c:v", "libsvtav1",
        "-crf", str(V["crf"]),
        "-preset", "4",
        "-svtav1-params", "film-grain=0",
        "-pix_fmt", "yuv420p10le",
        "-c:a", "eac3", "-b:a", "128k",
        "-movflags", "+faststart",
        "-metadata", "comment=MediaVortex test encode",
        "-y",
    ]
    if V["scale"]:
        Cmd.extend(["-vf", f"scale={V['scale']}"])
    Cmd.append(Out)

    Log(f"ENCODE {V['label']} -> {V['outname']}")
    T0 = time.time()
    R = subprocess.run(Cmd, capture_output=True, text=True)
    if R.returncode != 0:
        Log(f"  FFMPEG failed (rc={R.returncode}). stderr tail:")
        print(R.stderr[-2000:])
        return None
    Dt = time.time() - T0
    Size = os.path.getsize(Out)
    V["size_bytes"] = Size
    V["encode_seconds"] = Dt
    V["out_path"] = Out
    Log(f"  done in {Dt:.0f}s, size={Size/(1024*1024):.1f} MB ({Dt/60:.1f} min)")
    return Out


def ProbeBitrate(V):
    R = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=bit_rate,duration",
         "-of", "default=noprint_wrappers=1", V["out_path"]],
        capture_output=True, text=True,
    )
    Bitrate = None
    Duration = None
    for Line in R.stdout.splitlines():
        if Line.startswith("bit_rate="):
            Bitrate = int(Line.split("=")[1])
        elif Line.startswith("duration="):
            Duration = float(Line.split("=")[1])
    V["bitrate_kbps"] = round((Bitrate or 0) / 1000, 1)
    V["duration_seconds"] = Duration


def Vmaf(V):
    XmlLog = f"vmaf_test_{V['name']}.xml"
    # Force comparison at 720p so the three variants score on equal footing.
    FilterStr = (
        "[0:v]scale=1280:720,format=yuv420p[dist];"
        "[1:v]scale=1280:720,format=yuv420p[ref];"
        f"[dist][ref]libvmaf=log_path={XmlLog}:n_subsample=10"
    )
    Cmd = [FFMPEG, "-i", SOURCE, "-i", V["out_path"], "-lavfi", FilterStr, "-f", "null", "-"]
    Log(f"VMAF   {V['label']} (comparison at 720p)")
    T0 = time.time()
    R = subprocess.run(Cmd, capture_output=True, text=True)
    Dt = time.time() - T0
    if R.returncode != 0:
        Log(f"  VMAF failed (rc={R.returncode}). stderr tail:")
        print((R.stderr or "")[-2000:])
        return
    Score = None
    for Line in (R.stderr or "").splitlines():
        if "VMAF score:" in Line:
            try:
                Score = float(Line.split("VMAF score:")[1].strip())
            except Exception:
                pass
            break
    V["vmaf"] = Score
    V["vmaf_seconds"] = Dt
    Log(f"  done in {Dt:.0f}s, VMAF={Score}")


def Main():
    if not os.path.exists(SOURCE):
        Log(f"SOURCE not found: {SOURCE}")
        sys.exit(1)

    SrcSize = os.path.getsize(SOURCE)
    Log(f"Source: {os.path.basename(SOURCE)}")
    Log(f"        {SrcSize/(1024*1024):.0f} MB")
    Log("Plan: encode 3 variants sequentially, then VMAF each (forced to 720p comparison).")

    # Step 1: encodes
    for V in VARIANTS:
        if Encode(V) is None:
            Log(f"Variant {V['name']} encode failed. Stopping.")
            sys.exit(2)

    # Step 2: probe each output
    for V in VARIANTS:
        ProbeBitrate(V)

    # Step 3: VMAFs
    for V in VARIANTS:
        Vmaf(V)

    # Step 4: results
    print()
    print("=" * 78)
    print(f"  RESULTS (source: {SrcSize/(1024*1024):.0f} MB, {VARIANTS[0].get('duration_seconds', 0)/60:.1f} min)")
    print("=" * 78)
    print(f"  {'Variant':<14} {'Bitrate':>10} {'Size':>10} {'Savings':>9} {'VMAF':>8} {'Encode':>9}")
    print(f"  {'-'*14} {'-'*10} {'-'*10} {'-'*9} {'-'*8} {'-'*9}")
    for V in VARIANTS:
        Bitrate = f"{V['bitrate_kbps']:.0f} kbps"
        Size = f"{V['size_bytes']/(1024*1024):.0f} MB"
        Savings = f"{(1 - V['size_bytes']/SrcSize) * 100:.0f}%"
        Vmaf_s = f"{V.get('vmaf', 0):.2f}" if V.get('vmaf') is not None else "FAIL"
        Encode_s = f"{V['encode_seconds']/60:.1f} min"
        print(f"  {V['label']:<14} {Bitrate:>10} {Size:>10} {Savings:>9} {Vmaf_s:>8} {Encode_s:>9}")
    print("=" * 78)

    # JSON sidecar for later reference
    Sidecar = os.path.join(os.path.dirname(__file__), "NewGirlEncodingABC.results.json")
    with open(Sidecar, "w") as F:
        json.dump({"source": SOURCE, "source_size_bytes": SrcSize, "variants": VARIANTS}, F, indent=2, default=str)
    Log(f"Results saved: {Sidecar}")


if __name__ == "__main__":
    Main()
