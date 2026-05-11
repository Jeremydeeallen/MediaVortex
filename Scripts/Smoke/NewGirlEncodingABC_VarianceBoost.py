"""Re-run the 3-variant New Girl S07E01 test WITH variance boost enabled.

Same recipe as NewGirlEncodingABC.py (1080p CRF32 / 720p CRF25 / 480p CRF18,
preset 4, FG 0, lanczos scaling, EBU R128 loudnorm, EAC3 128k stereo) but
with SVT-AV1 variance boost added to the encoder params:

  enable-variance-boost=1:variance-boost-strength=2

Expected: +1-3 VMAF on flat-region frames (which is where banding lives in
sitcom content), +5-10% file size. Variance boost spends more bits on
low-variance regions where the human eye is most sensitive to artifacts.

Output filenames use a `-vb` infix to keep them separate from the original
NewGirlEncodingABC.py outputs:

  S07E01-vb-test-1080p.mp4
  S07E01-vb-test-720p.mp4
  S07E01-vb-test-480p.mp4

VMAF logs go to vmaf_vb_test_{A,B,C}.xml so the previous run's XMLs aren't
overwritten (and the new distribution metrics will be persisted in
QualityTestResults if those rows exist).

Comparison after run: parse both old and new XMLs, print side-by-side
mean / P5 / P10 / P25 / HarmonicMean per variant.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

SOURCE = r"T:\New Girl\Season 7\New Girl - S07E01 - About Three Years Later WEBDL-1080p.mkv"
OUT_DIR = r"T:\New Girl\Season 7"
FFMPEG = r"C:\Code\MediaVortex\FFmpegMaster\bin\ffmpeg.exe"
FFPROBE = r"C:\Code\MediaVortex\FFmpegMaster\bin\ffprobe.exe"

SVT_PARAMS = "film-grain=0:enable-variance-boost=1:variance-boost-strength=2"

VARIANTS = [
    {"name": "A", "label": "1080p CRF32 +VB", "scale": None,       "crf": 32, "outname": "S07E01-vb-test-1080p.mp4", "xml": "vmaf_vb_test_A.xml"},
    {"name": "B", "label": "720p  CRF25 +VB", "scale": "1280:720", "crf": 25, "outname": "S07E01-vb-test-720p.mp4",  "xml": "vmaf_vb_test_B.xml"},
    {"name": "C", "label": "480p  CRF18 +VB", "scale": "854:480",  "crf": 18, "outname": "S07E01-vb-test-480p.mp4",  "xml": "vmaf_vb_test_C.xml"},
]


def Log(Msg):
    print(f"[{time.strftime('%H:%M:%S')}] {Msg}", flush=True)


def Encode(V):
    Out = os.path.join(OUT_DIR, V["outname"])
    Cmd = [
        FFMPEG, "-i", SOURCE,
        "-map", "0:v:0", "-map", "0:a:0",
        "-c:v", "libsvtav1",
        "-crf", str(V["crf"]),
        "-preset", "4",
        "-svtav1-params", SVT_PARAMS,
        "-pix_fmt", "yuv420p10le",
        "-c:a", "eac3", "-b:a", "128k",
        "-af", "loudnorm=I=-23:LRA=7:TP=-2",
        "-movflags", "+faststart",
        "-metadata", "comment=MediaVortex VB test",
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
    XmlLog = V["xml"]
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


def ParseMetricsFromXml(XmlPath):
    """Reduced version of QualityTestingBusinessService.ParseVMAFMetrics --
    inlined here so the script is self-contained and runs in background."""
    import xml.etree.ElementTree as ET
    Result = {'Mean': 0.0, 'Min': None, 'Max': None, 'HarmonicMean': None,
              'StdDev': None, 'P1': None, 'P5': None, 'P10': None, 'P25': None}
    if not os.path.exists(XmlPath):
        return Result
    try:
        Root = ET.parse(XmlPath).getroot()
        Pooled = Root.find('.//pooled_metrics/metric[@name="vmaf"]')
        if Pooled is None:
            Pooled = Root.find('.//metric[@name="vmaf"]')
        if Pooled is not None:
            for K, A in (('Mean','mean'), ('Min','min'), ('Max','max'), ('HarmonicMean','harmonic_mean')):
                V = Pooled.get(A)
                if V is not None:
                    try: Result[K] = float(V)
                    except: pass
        PerFrame = []
        for F in Root.findall('.//frame'):
            V = F.get('vmaf')
            if V is not None:
                try: PerFrame.append(float(V))
                except: pass
        if PerFrame:
            Sorted_ = sorted(PerFrame)
            N = len(Sorted_)
            M = sum(PerFrame) / N
            Result['StdDev'] = (sum((X-M)**2 for X in PerFrame) / N) ** 0.5
            for K, Pct in (('P1', 0.01), ('P5', 0.05), ('P10', 0.10), ('P25', 0.25)):
                Idx = max(0, min(N-1, int(Pct * N)))
                Result[K] = Sorted_[Idx]
    except Exception as Ex:
        Log(f"  XML parse failed for {XmlPath}: {Ex}")
    return Result


def Main():
    if not os.path.exists(SOURCE):
        Log(f"SOURCE not found: {SOURCE}")
        sys.exit(1)

    SrcSize = os.path.getsize(SOURCE)
    Log(f"Source: {os.path.basename(SOURCE)}, {SrcSize/(1024*1024):.0f} MB")
    Log(f"Variance boost: {SVT_PARAMS}")

    for V in VARIANTS:
        if Encode(V) is None:
            Log(f"Variant {V['name']} encode failed. Stopping.")
            sys.exit(2)

    for V in VARIANTS:
        ProbeBitrate(V)

    for V in VARIANTS:
        Vmaf(V)

    # Pull distribution from XMLs (fresh + previous run for comparison)
    print()
    print("=" * 100)
    print(f"  VARIANCE BOOST vs ORIGINAL  (source {SrcSize/(1024*1024):.0f} MB, {VARIANTS[0].get('duration_seconds', 0)/60:.1f} min)")
    print("=" * 100)
    print(f"  {'Variant':<22} {'Bitrate':>11} {'Size':>9} {'Save':>6} {'Mean':>7} {'HMean':>7} {'StdDev':>7} {'P5':>7} {'P10':>7} {'P25':>7}")
    print(f"  {'-'*22} {'-'*11} {'-'*9} {'-'*6} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*7}")

    # Old runs (NewGirlEncodingABC.py results)
    OldPairs = [
        ("1080p CRF32 (orig)",  "vmaf_test_A.xml"),
        ("720p  CRF25 (orig)",  "vmaf_test_B.xml"),
        ("480p  CRF18 (orig)",  "vmaf_test_C.xml"),
    ]
    for Lbl, XmlPath in OldPairs:
        if not os.path.exists(XmlPath):
            print(f"  {Lbl:<22} {'(no XML)':>11}")
            continue
        M = ParseMetricsFromXml(XmlPath)
        print(f"  {Lbl:<22} {'-':>11} {'-':>9} {'-':>6} {M['Mean']:>7.2f} {M['HarmonicMean']:>7.2f} {M['StdDev']:>7.2f} {M['P5']:>7.2f} {M['P10']:>7.2f} {M['P25']:>7.2f}")

    print(f"  {'-'*22} {'-'*11} {'-'*9} {'-'*6} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*7}")

    # New (variance boost) runs
    for V in VARIANTS:
        M = ParseMetricsFromXml(V["xml"])
        Bitrate = f"{V['bitrate_kbps']:.0f} kbps"
        Size = f"{V['size_bytes']/(1024*1024):.0f} MB"
        Save = f"{(1 - V['size_bytes']/SrcSize)*100:.0f}%"
        print(f"  {V['label']:<22} {Bitrate:>11} {Size:>9} {Save:>6} {M['Mean']:>7.2f} {M['HarmonicMean']:>7.2f} {M['StdDev']:>7.2f} {M['P5']:>7.2f} {M['P10']:>7.2f} {M['P25']:>7.2f}")

    print("=" * 100)

    Sidecar = os.path.join(os.path.dirname(__file__), "NewGirlEncodingABC_VB.results.json")
    with open(Sidecar, "w") as F:
        json.dump({"source": SOURCE, "source_size_bytes": SrcSize, "svt_params": SVT_PARAMS, "variants": VARIANTS}, F, indent=2, default=str)
    Log(f"Results saved: {Sidecar}")


if __name__ == "__main__":
    Main()
