"""Generic 3-variant SVT-AV1 + VMAF harness.

Usage:
    py Scripts/Smoke/EncodeAndVmaf.py --source "T:\\Show\\file.mkv"
    py Scripts/Smoke/EncodeAndVmaf.py --source "..." --name MyTest --variants C:\\path\\to\\variants.json
    py Scripts/Smoke/EncodeAndVmaf.py --source "..." --vmaf-only

Writes a standardized *.results.json sidecar to Scripts/Smoke/ which the
/VmafCompare Test bench picks up automatically.

Variants JSON shape (array of objects, optional override):
    [{"name":"A","label":"...","scale":"1920:1080","crf":32}, ...]

Default variants: 1080p CRF32, 720p CRF25, 480p CRF18 -- but variants whose
output resolution exceeds the source resolution are skipped (no upscaling).
"""

import argparse
import json
import math
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

FFMPEG = str(ROOT / "FFmpegMaster" / "bin" / "ffmpeg.exe")
FFPROBE = str(ROOT / "FFmpegMaster" / "bin" / "ffprobe.exe")

DEFAULT_FILM_GRAIN = 0

DEFAULT_VARIANTS = [
    {"name": "A", "label": "1080p CRF32 FG0", "scale": "1920:1080", "crf": 32, "film_grain": 0, "height": 1080},
    {"name": "B", "label": "720p  CRF25 FG0", "scale": "1280:720",  "crf": 25, "film_grain": 0, "height": 720},
    {"name": "C", "label": "480p  CRF18 FG0", "scale": "854:480",   "crf": 18, "film_grain": 0, "height": 480},
]


def Log(Msg):
    print(f"[{time.strftime('%H:%M:%S')}] {Msg}", flush=True)


def ProbeSource(Path_):
    R = subprocess.run(
        [FFPROBE, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate",
         "-show_entries", "format=bit_rate,duration",
         "-of", "default=noprint_wrappers=1", Path_],
        capture_output=True, text=True,
    )
    Out = {'Width': 0, 'Height': 0, 'BitrateKbps': 0, 'DurationSeconds': 0.0, 'Fps': 0.0}
    for Line in R.stdout.splitlines():
        if Line.startswith("width="):
            Out['Width'] = int(Line.split("=")[1])
        elif Line.startswith("height="):
            Out['Height'] = int(Line.split("=")[1])
        elif Line.startswith("bit_rate="):
            try: Out['BitrateKbps'] = round(int(Line.split("=")[1]) / 1000, 1)
            except: pass
        elif Line.startswith("duration="):
            try: Out['DurationSeconds'] = float(Line.split("=")[1])
            except: pass
        elif Line.startswith("r_frame_rate="):
            try:
                Num, Den = Line.split("=")[1].split("/")
                Out['Fps'] = round(float(Num) / float(Den), 3) if float(Den) else 0
            except: pass
    return Out


def BuildSvtAv1Params(V):
    """Build SVT-AV1 -svtav1-params string from per-variant fields. Lets each
    variant override film-grain, aq-mode, tune, lookahead independently, and
    accept a raw svtav1_extra string for anything else."""
    Fg = V.get('film_grain', V.get('FilmGrain', DEFAULT_FILM_GRAIN))
    Parts = [f"film-grain={Fg}"]
    if V.get('aq_mode') is not None:
        Parts.append(f"aq-mode={V['aq_mode']}")
    if V.get('tune') is not None:
        Parts.append(f"tune={V['tune']}")
    if V.get('lookahead') is not None:
        Parts.append(f"lookahead={V['lookahead']}")
    if V.get('variance_boost') is not None:
        Parts.append(f"variance-boost-strength={V['variance_boost']}")
    Extra = V.get('svtav1_extra')
    if Extra:
        Parts.append(Extra)
    return ':'.join(Parts)


def Encode(Source, OutDir, V):
    Out = os.path.join(OutDir, V["outname"])
    SvtParams = BuildSvtAv1Params(V)
    Cmd = [
        FFMPEG, "-i", Source,
        "-map", "0:v:0", "-map", "0:a:0?",
        "-c:v", "libsvtav1",
        "-crf", str(V["crf"]),
        "-preset", "4",
        "-svtav1-params", SvtParams,
        "-pix_fmt", "yuv420p10le",
        "-c:a", "eac3", "-b:a", "128k",
        "-af", "loudnorm=I=-23:LRA=7:TP=-2",
        "-vf", f"scale={V['scale']}:flags=lanczos",
        "-movflags", "+faststart",
        "-metadata", "comment=MediaVortex test harness",
        "-y", Out,
    ]
    Log(f"ENCODE {V['label']} -> {os.path.basename(Out)}")
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
            try: Bitrate = int(Line.split("=")[1])
            except: pass
        elif Line.startswith("duration="):
            try: Duration = float(Line.split("=")[1])
            except: pass
    V["bitrate_kbps"] = round((Bitrate or 0) / 1000, 1)
    V["duration_seconds"] = Duration


def Vmaf(Source, V, CompareScale="1280:720"):
    """Run libvmaf against (Source, V['out_path']). Writes per-frame XML to
    Scripts/Smoke/ using a BARE filename -- backslashes and colons in absolute
    Windows paths confuse libavfilter's filter-graph parser. Run cwd=Scripts/Smoke
    so the bare filename resolves correctly."""
    SmokeDir = str(ROOT / "Scripts" / "Smoke")
    XmlBare = os.path.basename(V["xml"]) if V.get("xml") else f"vmaf_{V['name']}.xml"
    V["xml"] = os.path.join(SmokeDir, XmlBare)
    Filter = (
        f"[0:v]scale={CompareScale},format=yuv420p[dist];"
        f"[1:v]scale={CompareScale},format=yuv420p[ref];"
        f"[dist][ref]libvmaf=log_path={XmlBare}"
    )
    Cmd = [FFMPEG, "-i", Source, "-i", V["out_path"], "-lavfi", Filter, "-f", "null", "-"]
    Log(f"VMAF   {V['label']} (compare at {CompareScale})")
    T0 = time.time()
    R = subprocess.run(Cmd, capture_output=True, text=True, cwd=SmokeDir)
    Dt = time.time() - T0
    if R.returncode != 0:
        Log(f"  VMAF failed (rc={R.returncode}). stderr tail:")
        print((R.stderr or "")[-2000:])
        return
    Score = None
    for Line in (R.stderr or "").splitlines():
        if "VMAF score:" in Line:
            try: Score = float(Line.split("VMAF score:")[1].strip())
            except: pass
            break
    V["vmaf"] = Score
    V["vmaf_seconds"] = Dt
    Log(f"  done in {Dt:.0f}s, VMAF={Score}")


def ParseMetricsFromXml(XmlPath):
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
                Val = Pooled.get(A)
                if Val is not None:
                    try: Result[K] = float(Val)
                    except: pass
        PerFrame = []
        for F in Root.findall('.//frame'):
            Val = F.get('vmaf')
            if Val is not None:
                try: PerFrame.append(float(Val))
                except: pass
        if PerFrame:
            Sorted_ = sorted(PerFrame)
            N = len(Sorted_)
            M = sum(PerFrame) / N
            Result['StdDev'] = math.sqrt(sum((X-M)**2 for X in PerFrame) / N)
            for K, Pct in (('P1', 0.01), ('P5', 0.05), ('P10', 0.10), ('P25', 0.25)):
                Idx = max(0, min(N-1, int(Pct * N)))
                Result[K] = Sorted_[Idx]
    except Exception as Ex:
        Log(f"  XML parse failed for {XmlPath}: {Ex}")
    return Result


def DeriveTestName(SourcePath, Override=None):
    if Override:
        return Override
    Base = os.path.splitext(os.path.basename(SourcePath))[0]
    Tag = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{Base[:40]}-{Tag}"


def VmafOnlyFromSidecar(SidecarPath, CompareScale="1280:720", KeepXml=False):
    """Re-run VMAF against the variants recorded in an existing sidecar.
    Use when prior encode succeeded but VMAF failed (or to recompute with a
    different comparison resolution). Overwrites the sidecar in place."""
    with open(SidecarPath, 'r', encoding='utf-8') as F:
        Sidecar = json.load(F)
    Source = Sidecar['source']
    TestName = Sidecar.get('test_name') or os.path.basename(SidecarPath).replace('.results.json', '')
    Variants = Sidecar['variants']
    SrcSize = Sidecar.get('source_size_bytes') or os.path.getsize(Source)
    SrcInfo = Sidecar.get('source_info') or ProbeSource(Source)
    if not os.path.exists(Source):
        Log(f"SOURCE not found: {Source}"); sys.exit(1)
    for V in Variants:
        V['xml'] = str(ROOT / "Scripts" / "Smoke" / f"vmaf_{TestName}_{V['name']}.xml")
        if not os.path.exists(V['out_path']):
            Log(f"SKIP {V['label']}: out_path missing: {V['out_path']}"); continue
        Vmaf(Source, V, CompareScale)

    print()
    print("=" * 110)
    print(f"  {TestName}  (source {SrcInfo.get('Width','?')}x{SrcInfo.get('Height','?')} @ {SrcInfo.get('BitrateKbps',0):.0f} kbps)")
    print("=" * 110)
    print(f"  {'Variant':<22} {'Bitrate':>11} {'Size':>9} {'Save':>6} {'Mean':>7} {'HMean':>7} {'StdDev':>7} {'P5':>7} {'P10':>7} {'P25':>7}")
    print(f"  {'-'*22} {'-'*11} {'-'*9} {'-'*6} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*7}")
    for V in Variants:
        M = ParseMetricsFromXml(V['xml'])
        V['Vmaf_Metrics'] = M
        Bitrate = f"{V.get('bitrate_kbps', 0):.0f} kbps"
        Size = f"{V.get('size_bytes', 0)/(1024*1024):.0f} MB"
        Save = f"{(1 - V.get('size_bytes', 0)/SrcSize)*100:.0f}%" if SrcSize else '-'
        print(f"  {V['label']:<22} {Bitrate:>11} {Size:>9} {Save:>6} "
              f"{M['Mean']:>7.2f} {(M['HarmonicMean'] or 0):>7.2f} {(M['StdDev'] or 0):>7.2f} "
              f"{(M['P5'] or 0):>7.2f} {(M['P10'] or 0):>7.2f} {(M['P25'] or 0):>7.2f}")
    print("=" * 110)

    Sidecar['variants'] = Variants
    Sidecar['comparison_resolution'] = CompareScale
    Sidecar['rerun_at'] = datetime.now().isoformat(timespec='seconds')
    with open(SidecarPath, 'w', encoding='utf-8') as F:
        json.dump(Sidecar, F, indent=2, default=str)
    Log(f"Sidecar updated: {SidecarPath}")

    if not KeepXml:
        for V in Variants:
            try: os.remove(V['xml'])
            except OSError: pass


def Main():
    Parser = argparse.ArgumentParser(description="Generic SVT-AV1 + VMAF test harness.")
    Parser.add_argument("--source", default=None, help="Path to the source media file.")
    Parser.add_argument("--name", default=None, help="Test name (default: source basename + timestamp).")
    Parser.add_argument("--variants", default=None, help="Path to JSON file describing variants. Default: 3-variant 1080p/720p/480p set.")
    Parser.add_argument("--compare-scale", default="1280:720", help="VMAF comparison resolution (default 1280:720).")
    Parser.add_argument("--out-dir", default=None, help="Where to write encoded variants (default: alongside source).")
    Parser.add_argument("--keep-xml", action="store_true", help="Keep per-variant VMAF XML files after parsing.")
    Parser.add_argument("--vmaf-only", default=None, help="Path to an existing *.results.json sidecar. Skips encoding; re-runs VMAF against the recorded variants.")
    Args = Parser.parse_args()

    if Args.vmaf_only:
        return VmafOnlyFromSidecar(Args.vmaf_only, Args.compare_scale, Args.keep_xml)
    if not Args.source:
        Parser.error("--source is required unless --vmaf-only is used")

    Source = Args.source
    if not os.path.exists(Source):
        Log(f"SOURCE not found: {Source}")
        sys.exit(1)

    SrcInfo = ProbeSource(Source)
    SrcSize = os.path.getsize(Source)
    Log(f"Source: {os.path.basename(Source)}")
    Log(f"  {SrcInfo['Width']}x{SrcInfo['Height']} @ {SrcInfo['Fps']} fps, "
        f"{SrcInfo['BitrateKbps']:.0f} kbps, {SrcInfo['DurationSeconds']/60:.1f} min, "
        f"{SrcSize/(1024*1024):.0f} MB")

    if Args.variants:
        with open(Args.variants, 'r', encoding='utf-8') as F:
            VariantsRaw = json.load(F)
    else:
        VariantsRaw = DEFAULT_VARIANTS

    TestName = DeriveTestName(Source, Args.name)
    OutDir = Args.out_dir or os.path.dirname(Source)
    Stem = os.path.splitext(os.path.basename(Source))[0]
    SidecarPath = ROOT / "Scripts" / "Smoke" / f"{TestName}.results.json"

    Variants = []
    for V in VariantsRaw:
        Height = V.get('height') or 0
        if not Height and 'scale' in V:
            try: Height = int(V['scale'].split(':')[1])
            except: Height = 0
        if Height and SrcInfo['Height'] and Height > SrcInfo['Height']:
            Log(f"SKIP {V.get('label', V.get('name'))}: variant height {Height} > source height {SrcInfo['Height']} (no upscale)")
            continue
        VCopy = dict(V)
        VCopy.setdefault('outname', f"{Stem}-{TestName}-{V['name']}.mp4")
        VCopy.setdefault('xml', str(ROOT / "Scripts" / "Smoke" / f"vmaf_{TestName}_{V['name']}.xml"))
        Variants.append(VCopy)

    if not Variants:
        Log("No variants left after upscale filter. Nothing to do.")
        sys.exit(0)

    for V in Variants:
        if Encode(Source, OutDir, V) is None:
            Log(f"Variant {V['name']} encode failed. Stopping.")
            sys.exit(2)
    for V in Variants:
        ProbeBitrate(V)
    for V in Variants:
        Vmaf(Source, V, Args.compare_scale)

    print()
    print("=" * 110)
    print(f"  {TestName}  (source {SrcInfo['Width']}x{SrcInfo['Height']} @ {SrcInfo['BitrateKbps']:.0f} kbps, "
          f"{SrcSize/(1024*1024):.0f} MB, {SrcInfo['DurationSeconds']/60:.1f} min)")
    print("=" * 110)
    print(f"  {'Variant':<22} {'Bitrate':>11} {'Size':>9} {'Save':>6} {'Mean':>7} {'HMean':>7} {'StdDev':>7} {'P5':>7} {'P10':>7} {'P25':>7}")
    print(f"  {'-'*22} {'-'*11} {'-'*9} {'-'*6} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*7}")
    for V in Variants:
        M = ParseMetricsFromXml(V["xml"])
        V['Vmaf_Metrics'] = M
        Bitrate = f"{V['bitrate_kbps']:.0f} kbps"
        Size = f"{V['size_bytes']/(1024*1024):.0f} MB"
        Save = f"{(1 - V['size_bytes']/SrcSize)*100:.0f}%"
        print(f"  {V['label']:<22} {Bitrate:>11} {Size:>9} {Save:>6} "
              f"{M['Mean']:>7.2f} {(M['HarmonicMean'] or 0):>7.2f} {(M['StdDev'] or 0):>7.2f} "
              f"{(M['P5'] or 0):>7.2f} {(M['P10'] or 0):>7.2f} {(M['P25'] or 0):>7.2f}")
    print("=" * 110)

    Sidecar = {
        "schema_version": 1,
        "test_name": TestName,
        "run_date": datetime.now().isoformat(timespec='seconds'),
        "source": Source,
        "source_size_bytes": SrcSize,
        "source_info": SrcInfo,
        "comparison_resolution": Args.compare_scale,
        "vmaf_model": "vmaf_v0.6.1",
        "encoder": {"name": "libsvtav1", "preset": 4, "svtav1_params": SVT_PARAMS},
        "variants": Variants,
    }
    with open(SidecarPath, 'w', encoding='utf-8') as F:
        json.dump(Sidecar, F, indent=2, default=str)
    Log(f"Results saved: {SidecarPath}")
    Log(f"View at: http://localhost:5000/VmafCompare (Test bench card)")

    if not Args.keep_xml:
        for V in Variants:
            try: os.remove(V["xml"])
            except OSError: pass


if __name__ == "__main__":
    Main()
