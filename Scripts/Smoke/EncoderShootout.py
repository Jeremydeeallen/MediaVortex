"""Encoder shootout harness: SVT-AV1 vs av1_nvenc head-to-head.

Reads a matrix JSON declaring sources and variants, runs every (source, variant)
pair, scores each with libvmaf (production-equivalent chain + motion-filter
pooling), and emits a per-source table, cross-source rollup, and persisted
sidecar.

No source probing at run time. Every parameter that affects output is in the
matrix; the same matrix file produces the same numbers on every run.

Usage:
    py Scripts/Smoke/EncoderShootout.py --matrix Scripts/Smoke/NvencVsSvtAv1.matrix.json

Optional:
    --keep-encoded     Don't delete encoded mp4 outputs after VMAF
    --resume           Skip (source, variant) pairs that already have a passing
                       result in the sidecar (re-run only failures)
"""

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent.parent.parent
FFMPEG = str(ROOT / "FFmpegMaster" / "bin" / "ffmpeg.exe")
SMOKE_DIR = ROOT / "Scripts" / "Smoke"
OUTPUT_DIR = SMOKE_DIR / "shootout_output"


def Log(Msg):
    print(f"[{time.strftime('%H:%M:%S')}] {Msg}", flush=True)


def BuildEncodeCmd(Source, Variant, OutputPath, OutputScale):
    """Return the full ffmpeg arg list for one (source, variant) encode."""
    Common = [
        FFMPEG, "-hide_banner", "-loglevel", "warning", "-stats",
        "-i", Source,
        "-map", "0:v:0", "-map", "0:a:0?",
        "-vf", f"scale={OutputScale}:flags=lanczos",
    ]
    Enc = Variant["encoder"]
    if Enc == "libsvtav1":
        VideoArgs = [
            "-c:v", "libsvtav1",
            "-crf", str(Variant["crf"]),
            "-preset", str(Variant["preset"]),
            "-svtav1-params", f"film-grain={Variant.get('film_grain', 0)}",
            "-pix_fmt", Variant.get("pix_fmt", "yuv420p10le"),
        ]
    elif Enc == "av1_nvenc":
        VideoArgs = [
            "-c:v", "av1_nvenc",
            "-preset", str(Variant["preset"]),
            "-tune", str(Variant["tune"]),
            "-multipass", str(Variant["multipass"]),
            "-rc", str(Variant["rc"]),
            "-cq", str(Variant["cq"]),
            "-b:v", "0",
            "-spatial-aq", str(Variant.get("spatial_aq", 1)),
            "-temporal-aq", str(Variant.get("temporal_aq", 1)),
            "-aq-strength", str(Variant.get("aq_strength", 8)),
            "-rc-lookahead", str(Variant.get("rc_lookahead", 20)),
            "-bf", str(Variant.get("bf", 4)),
            "-b_ref_mode", str(Variant.get("b_ref_mode", "middle")),
            "-weighted_pred", str(Variant.get("weighted_pred", 0)),
            "-pix_fmt", Variant.get("pix_fmt", "p010le"),
        ]
    else:
        raise ValueError(f"Unknown encoder: {Enc}")

    AudioArgs = [
        "-c:a", "aac",
        "-b:a", "96k",
        "-ac", "2",
    ]
    Tail = [
        "-movflags", "+faststart",
        "-metadata", "comment=MediaVortex encoder shootout",
        "-f", "mp4",
        "-y", OutputPath,
    ]
    return Common + VideoArgs + AudioArgs + Tail


def Encode(Source, Variant, OutputPath, OutputScale):
    """Run one encode. Returns (success_bool, encode_seconds, size_bytes)."""
    Cmd = BuildEncodeCmd(Source, Variant, OutputPath, OutputScale)
    Log(f"  ENCODE {Variant['label']}")
    T0 = time.time()
    R = subprocess.run(Cmd, capture_output=True, text=True)
    Dt = time.time() - T0
    if R.returncode != 0:
        Log(f"    encode failed (rc={R.returncode}). stderr tail:")
        print((R.stderr or "")[-1500:])
        return False, Dt, 0
    Size = os.path.getsize(OutputPath) if os.path.exists(OutputPath) else 0
    Log(f"    done in {Dt/60:.1f} min, size={Size/(1024*1024):.1f} MB")
    return True, Dt, Size


def RunVmaf(EncodedPath, SourcePath, XmlBareName, CompareScale, NThreads):
    """Run libvmaf with the production-equivalent filter chain.

    Both inputs: setpts reset, scaled to compare resolution with lanczos and
    explicit limited-range output, 10-bit precision. libvmaf writes XML to a
    BARE filename in SMOKE_DIR (absolute Windows paths break the filtergraph
    parser); we run cwd=SMOKE_DIR so the bare filename resolves.

    Returns (success_bool, vmaf_seconds, abs_xml_path).
    """
    AbsXml = SMOKE_DIR / XmlBareName
    if AbsXml.exists():
        AbsXml.unlink()
    Filter = (
        f"[0:v]setpts=PTS-STARTPTS,scale={CompareScale}:flags=lanczos:in_range=auto:out_range=tv,format=yuv420p10le[dist];"
        f"[1:v]setpts=PTS-STARTPTS,scale={CompareScale}:flags=lanczos:in_range=auto:out_range=tv,format=yuv420p10le[ref];"
        f"[dist][ref]libvmaf=log_fmt=xml:log_path={XmlBareName}:n_threads={NThreads}"
    )
    Cmd = [
        FFMPEG, "-hide_banner", "-loglevel", "warning",
        "-i", EncodedPath,
        "-i", SourcePath,
        "-lavfi", Filter,
        "-f", "null", "-",
    ]
    Log(f"  VMAF   (compare at {CompareScale})")
    T0 = time.time()
    R = subprocess.run(Cmd, capture_output=True, text=True, cwd=str(SMOKE_DIR))
    Dt = time.time() - T0
    if R.returncode != 0:
        Log(f"    VMAF failed (rc={R.returncode}). stderr tail:")
        print((R.stderr or "")[-1500:])
        return False, Dt, str(AbsXml)
    Log(f"    done in {Dt:.0f}s")
    return True, Dt, str(AbsXml)


def ParseMetricsFromXml(XmlPath):
    """Parse pooled VMAF metrics with held-frame motion filtering.

    Ported verbatim from EncodeAndVmaf.ParseMetricsFromXml which mirrors
    Features/QualityTesting/QualityTestingBusinessService.ParseVMAFMetrics.
    When >15% of source frames have integer_motion < 0.5, Mean / StdDev /
    percentiles are pooled over only the motion>=0.5 frames so libvmaf's
    bimodal scoring on held-frame content doesn't poison the headline metric.
    """
    Result = {
        "Mean": 0.0, "Min": None, "Max": None, "HarmonicMean": None,
        "StdDev": None, "P1": None, "P5": None, "P10": None, "P25": None,
        "MotionZeroFraction": None, "MotionFilterApplied": False,
        "FrameCount": 0,
    }
    if not os.path.exists(XmlPath):
        return Result
    try:
        Root = ET.parse(XmlPath).getroot()
        Pooled = Root.find('.//pooled_metrics/metric[@name="vmaf"]')
        if Pooled is None:
            Pooled = Root.find('.//metric[@name="vmaf"]')
        if Pooled is not None:
            for K, A in (("Min", "min"), ("Max", "max")):
                Val = Pooled.get(A)
                if Val is not None:
                    try: Result[K] = float(Val)
                    except: pass
        PerFrame = []
        MZero = 0
        for F in Root.findall('.//frame'):
            Val = F.get("vmaf")
            if Val is None: continue
            try: V = float(Val)
            except: continue
            MStr = F.get("integer_motion")
            M = 0.0
            if MStr is not None:
                try: M = float(MStr)
                except: pass
            PerFrame.append((V, M))
            if M < 0.5:
                MZero += 1
        N = len(PerFrame)
        if N == 0:
            return Result
        Result["FrameCount"] = N
        MZF = MZero / N
        Result["MotionZeroFraction"] = MZF
        Filtered = [V for (V, M) in PerFrame if M >= 0.5]
        if MZF > 0.15 and len(Filtered) >= 50:
            Result["MotionFilterApplied"] = True
            Pool = Filtered
        else:
            Pool = [V for (V, _) in PerFrame]
        Sorted_ = sorted(Pool)
        PoolN = len(Sorted_)
        Mn = sum(Pool) / PoolN
        Result["Mean"] = Mn
        Result["StdDev"] = math.sqrt(sum((X - Mn) ** 2 for X in Pool) / PoolN)
        Result["HarmonicMean"] = PoolN / sum(1.0 / max(1.0, X) for X in Pool)
        for K, Pct in (("P1", 0.01), ("P5", 0.05), ("P10", 0.10), ("P25", 0.25)):
            Idx = max(0, min(PoolN - 1, int(Pct * PoolN)))
            Result[K] = Sorted_[Idx]
    except Exception as Ex:
        Log(f"    XML parse failed: {Ex}")
    return Result


def ComputeBitrateKbps(SizeBytes, DurationSeconds):
    if not DurationSeconds or DurationSeconds <= 0:
        return 0.0
    return round((SizeBytes * 8 / 1000.0) / DurationSeconds, 1)


def PrintSourceTable(SrcLabel, Results):
    """Per-source table: variant, encode time, size, bitrate, VMAF cluster."""
    print()
    print("=" * 130)
    print(f"  SOURCE: {SrcLabel}")
    print("=" * 130)
    Hdr = f"  {'Variant':<46} {'Encode':>9} {'Size MB':>9} {'kbps':>8} {'Mean':>7} {'HMean':>7} {'StdDev':>7} {'P5':>7} {'P10':>7} {'P25':>7} {'MotFilt':>8}"
    print(Hdr)
    print(f"  {'-'*46} {'-'*9} {'-'*9} {'-'*8} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*8}")
    for R in Results:
        if not R.get("encode_ok"):
            print(f"  {R['variant_label']:<46} ENCODE FAILED")
            continue
        if not R.get("vmaf_ok"):
            print(f"  {R['variant_label']:<46} {R['encode_seconds']/60:>7.1f}m  {R['size_mb']:>9.1f} {R['bitrate_kbps']:>8.0f}  VMAF FAILED")
            continue
        M = R["metrics"]
        print(f"  {R['variant_label']:<46} "
              f"{R['encode_seconds']/60:>7.1f}m  "
              f"{R['size_mb']:>9.1f} "
              f"{R['bitrate_kbps']:>8.0f} "
              f"{M['Mean']:>7.2f} "
              f"{(M['HarmonicMean'] or 0):>7.2f} "
              f"{(M['StdDev'] or 0):>7.2f} "
              f"{(M['P5'] or 0):>7.2f} "
              f"{(M['P10'] or 0):>7.2f} "
              f"{(M['P25'] or 0):>7.2f} "
              f"{'yes' if M['MotionFilterApplied'] else 'no':>8}")
    print("=" * 130)


def PrintRollup(VariantNames, VariantLabels, AllResults):
    """Cross-source rollup: per-variant median size / encode time / VMAF Mean / P5."""
    print()
    print("=" * 130)
    print("  CROSS-SOURCE ROLLUP (medians across all sources where encode + VMAF succeeded)")
    print("=" * 130)
    print(f"  {'Variant':<46} {'EncMin':>8} {'Size MB':>9} {'kbps':>8} {'Mean':>7} {'P5':>7} {'Sources':>8}")
    print(f"  {'-'*46} {'-'*8} {'-'*9} {'-'*8} {'-'*7} {'-'*7} {'-'*8}")
    for Name, Label in zip(VariantNames, VariantLabels):
        Rows = [
            R for SrcRows in AllResults.values() for R in SrcRows
            if R.get("variant_name") == Name and R.get("vmaf_ok")
        ]
        if not Rows:
            print(f"  {Label:<46} (no successful runs)")
            continue
        EncMins = [R["encode_seconds"] / 60 for R in Rows]
        Sizes = [R["size_mb"] for R in Rows]
        Bitrates = [R["bitrate_kbps"] for R in Rows]
        Means = [R["metrics"]["Mean"] for R in Rows]
        P5s = [R["metrics"]["P5"] or 0 for R in Rows]
        print(f"  {Label:<46} "
              f"{median(EncMins):>8.1f} "
              f"{median(Sizes):>9.1f} "
              f"{median(Bitrates):>8.0f} "
              f"{median(Means):>7.2f} "
              f"{median(P5s):>7.2f} "
              f"{len(Rows):>8}")
    print("=" * 130)


def Main():
    Parser = argparse.ArgumentParser(description="SVT-AV1 vs av1_nvenc shootout harness.")
    Parser.add_argument("--matrix", required=True, help="Path to matrix JSON.")
    Parser.add_argument("--keep-encoded", action="store_true", help="Don't delete encoded outputs after VMAF.")
    Parser.add_argument("--keep-xml", action="store_true", help="Don't delete VMAF XML files after parsing.")
    Args = Parser.parse_args()

    if not os.path.exists(Args.matrix):
        Log(f"Matrix not found: {Args.matrix}")
        sys.exit(1)

    with open(Args.matrix, "r", encoding="utf-8") as F:
        Matrix = json.load(F)

    TestName = Matrix["test_name"]
    OutputScale = Matrix["output_scale"]
    CompareScale = Matrix["comparison_scale"]
    NThreads = Matrix.get("vmaf_n_threads", 4)
    Sources = Matrix["sources"]
    Variants = Matrix["variants"]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    Log(f"Test: {TestName}")
    Log(f"Output: {OutputScale}  Compare: {CompareScale}  VMAF threads: {NThreads}")
    Log(f"Sources: {len(Sources)}  Variants: {len(Variants)}  Total encodes: {len(Sources) * len(Variants)}")

    # Pre-flight: every declared source must exist on disk now. Better to fail
    # before the first 30-min encode than after.
    MissingSources = [S for S in Sources if not os.path.exists(S["path"])]
    if MissingSources:
        Log("Missing sources -- aborting:")
        for S in MissingSources:
            Log(f"  - {S['path']}")
        sys.exit(2)

    AllResults = {}  # source_id -> list of result dicts
    SidecarPath = SMOKE_DIR / f"{TestName}.shootout.json"
    Sidecar = {
        "schema_version": 1,
        "test_name": TestName,
        "matrix_file": os.path.abspath(Args.matrix),
        "run_started": datetime.now().isoformat(timespec="seconds"),
        "matrix": Matrix,
        "results": {},
    }

    GrandT0 = time.time()
    for SrcIdx, Src in enumerate(Sources, 1):
        SrcId = Src["id"]
        SrcLabel = Src["label"]
        SrcPath = Src["path"]
        SrcSize = os.path.getsize(SrcPath)
        Log("")
        Log(f"[{SrcIdx}/{len(Sources)}] {SrcLabel}")
        Log(f"  source: {SrcPath}")
        Log(f"  source size: {SrcSize/(1024*1024):.1f} MB  fps: {Src['fps']}  height: {Src['source_height']}  codec: {Src['source_codec']}")

        SrcResults = []
        for V in Variants:
            VarName = V["name"]
            OutName = f"{SrcId}__{VarName}.mp4"
            OutPath = str(OUTPUT_DIR / OutName)
            XmlBare = f"shootout_{TestName}_{SrcId}__{VarName}.xml"

            Result = {
                "source_id": SrcId,
                "source_label": SrcLabel,
                "source_path": SrcPath,
                "source_size_bytes": SrcSize,
                "source_fps": Src["fps"],
                "variant_name": VarName,
                "variant_label": V["label"],
                "variant": V,
                "output_path": OutPath,
                "encode_ok": False,
                "encode_seconds": 0.0,
                "size_bytes": 0,
                "size_mb": 0.0,
                "bitrate_kbps": 0.0,
                "vmaf_ok": False,
                "vmaf_seconds": 0.0,
                "xml_path": "",
                "metrics": None,
            }

            EncodeOk, EncodeDt, SizeB = Encode(SrcPath, V, OutPath, OutputScale)
            Result["encode_ok"] = EncodeOk
            Result["encode_seconds"] = EncodeDt
            Result["size_bytes"] = SizeB
            Result["size_mb"] = round(SizeB / (1024 * 1024), 2)

            if EncodeOk and SizeB > 0:
                VmafOk, VmafDt, XmlPath = RunVmaf(OutPath, SrcPath, XmlBare, CompareScale, NThreads)
                Result["vmaf_ok"] = VmafOk
                Result["vmaf_seconds"] = VmafDt
                Result["xml_path"] = XmlPath
                if VmafOk:
                    Metrics = ParseMetricsFromXml(XmlPath)
                    Result["metrics"] = Metrics
                    if Metrics["FrameCount"] > 0:
                        DurationSec = Metrics["FrameCount"] / float(Src["fps"])
                        Result["bitrate_kbps"] = ComputeBitrateKbps(SizeB, DurationSec)
                if not Args.keep_xml:
                    try: os.remove(XmlPath)
                    except OSError: pass

            if not Args.keep_encoded:
                try: os.remove(OutPath)
                except OSError: pass

            SrcResults.append(Result)
            # Persist after every (source, variant) so a crash mid-run doesn't
            # lose results.
            Sidecar["results"][SrcId] = SrcResults
            Sidecar["run_last_update"] = datetime.now().isoformat(timespec="seconds")
            with open(SidecarPath, "w", encoding="utf-8") as F:
                json.dump(Sidecar, F, indent=2, default=str)

        AllResults[SrcId] = SrcResults
        PrintSourceTable(SrcLabel, SrcResults)

    GrandDt = time.time() - GrandT0
    Sidecar["run_completed"] = datetime.now().isoformat(timespec="seconds")
    Sidecar["wall_seconds"] = GrandDt
    with open(SidecarPath, "w", encoding="utf-8") as F:
        json.dump(Sidecar, F, indent=2, default=str)

    VariantNames = [V["name"] for V in Variants]
    VariantLabels = [V["label"] for V in Variants]
    PrintRollup(VariantNames, VariantLabels, AllResults)

    Log("")
    Log(f"Total wall time: {GrandDt/60:.1f} min")
    Log(f"Sidecar: {SidecarPath}")


if __name__ == "__main__":
    Main()
