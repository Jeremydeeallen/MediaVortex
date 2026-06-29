# Encoder shootout harness: SVT-AV1 / av1_nvenc / av1_qsv on a fixed corpus, libvmaf-scored. See EncoderShootout.feature.md.
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

# Harness file paths are LOCAL (ffmpeg binary, shootout output mp4s, matrix JSON on disk, libvmaf XML log).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from Core.Path.LocalPath import LocalExists, LocalGetSize

ROOT = Path(__file__).resolve().parent.parent.parent
FFMPEG = str(ROOT / "FFmpegMaster" / "bin" / "ffmpeg.exe")
SMOKE_DIR = ROOT / "Scripts" / "Smoke"
OUTPUT_DIR = SMOKE_DIR / "shootout_output"


def Log(Msg):
    print(f"[{time.strftime('%H:%M:%S')}] {Msg}", flush=True)


def BuildEncodeCmd(Source, Variant, OutputPath, OutputScale):
    """Return ffmpeg arg list for one (source, variant) encode."""
    SourcePath = Source["path"]
    Common = [
        FFMPEG, "-hide_banner", "-loglevel", "warning", "-stats",
        "-i", SourcePath,
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
        RcMode = Variant.get("rc_mode", "cq")
        if RcMode == "vbr":
            SrcKbps = Source.get("source_video_bitrate_kbps")
            if not SrcKbps or SrcKbps <= 0:
                raise ValueError(f"VBR variant {Variant['name']} requires source_video_bitrate_kbps on source {Source['id']}")
            TargetKbps = int(round(SrcKbps * Variant["rate_pct"] / 100))
            MaxKbps = TargetKbps * 2
            BufKbps = MaxKbps
            RateArgs = [
                "-rc", "vbr",
                "-b:v", f"{TargetKbps}k",
                "-maxrate:v", f"{MaxKbps}k",
                "-bufsize:v", f"{BufKbps}k",
            ]
        else:
            RateArgs = [
                "-rc", str(Variant.get("rc", "vbr")),
                "-cq", str(Variant["cq"]),
                "-b:v", "0",
            ]
        VideoArgs = [
            "-c:v", "av1_nvenc",
            "-preset", str(Variant["preset"]),
            "-tune", str(Variant["tune"]),
            "-multipass", str(Variant["multipass"]),
        ] + RateArgs + [
            "-spatial-aq", str(Variant.get("spatial_aq", 1)),
            "-temporal-aq", str(Variant.get("temporal_aq", 1)),
            "-aq-strength", str(Variant.get("aq_strength", 8)),
            "-rc-lookahead", str(Variant.get("rc_lookahead", 20)),
            "-bf", str(Variant.get("bf", 4)),
            "-b_ref_mode", str(Variant.get("b_ref_mode", "middle")),
            "-weighted_pred", str(Variant.get("weighted_pred", 0)),
            "-pix_fmt", Variant.get("pix_fmt", "p010le"),
        ]
        if Variant.get("gop"):
            VideoArgs += ["-g", str(Variant["gop"])]
    elif Enc == "av1_qsv":
        # QSV needs LIBVA_DRIVER_NAME=iHD env + libmfx-gen1.2 (oneVPL 2.x) at runtime. Container or host with Intel kobuk PPA.
        RcMode = Variant.get("rc_mode", "vbr")
        if RcMode == "vbr":
            SrcKbps = Source.get("source_video_bitrate_kbps")
            if not SrcKbps or SrcKbps <= 0:
                raise ValueError(f"VBR variant {Variant['name']} requires source_video_bitrate_kbps on source {Source['id']}")
            TargetKbps = int(round(SrcKbps * Variant["rate_pct"] / 100))
            MaxKbps = TargetKbps * int(Variant.get("max_multiplier", 2))
            BufKbps = MaxKbps
            RateArgs = [
                "-b:v", f"{TargetKbps}k",
                "-maxrate:v", f"{MaxKbps}k",
                "-bufsize:v", f"{BufKbps}k",
            ]
        elif RcMode == "icq":
            RateArgs = [
                "-rc", "icq",
                "-global_quality", str(Variant["global_quality"]),
            ]
        else:
            raise ValueError(f"av1_qsv rc_mode={RcMode} not implemented")
        VideoArgs = [
            "-c:v", "av1_qsv",
            "-preset", str(Variant.get("preset", "veryslow")),
        ] + RateArgs
        # BUG-0071: extbrc/look_ahead/b_strategy crash on Arc B580 libmfx-gen 2.16. Only emit when variant explicitly opts in.
        for ArgName, VKey in [("-extbrc", "extbrc"), ("-look_ahead", "look_ahead"),
                              ("-look_ahead_depth", "look_ahead_depth"), ("-b_strategy", "b_strategy"),
                              ("-adaptive_i", "adaptive_i"), ("-adaptive_b", "adaptive_b"),
                              ("-bf", "bf"), ("-async_depth", "async_depth"),
                              ("-low_power", "low_power")]:
            if VKey in Variant and Variant[VKey] is not None:
                VideoArgs += [ArgName, str(Variant[VKey])]
        VideoArgs += ["-pix_fmt", Variant.get("pix_fmt", "p010le")]
        if Variant.get("gop"):
            VideoArgs += ["-g", str(Variant["gop"])]
        if Variant.get("tile_cols"):
            VideoArgs += ["-tile_cols", str(Variant["tile_cols"]), "-tile_rows", str(Variant.get("tile_rows", 1))]
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


def Encode(SourceDict, Variant, OutputPath, OutputScale):
    """Run one encode. Returns (success_bool, encode_seconds, size_bytes)."""
    Cmd = BuildEncodeCmd(SourceDict, Variant, OutputPath, OutputScale)
    Log(f"  ENCODE {Variant['label']}")
    T0 = time.time()
    R = subprocess.run(Cmd, capture_output=True, text=True)
    Dt = time.time() - T0
    if R.returncode != 0:
        Log(f"    encode failed (rc={R.returncode}). stderr tail:")
        print((R.stderr or "")[-1500:])
        return False, Dt, 0
    Size = LocalGetSize(OutputPath) if LocalExists(OutputPath) else 0
    Log(f"    done in {Dt/60:.1f} min, size={Size/(1024*1024):.1f} MB")
    return True, Dt, Size


def RunVmaf(EncodedPath, SourcePath, XmlBareName, CompareScale, NThreads, SourceFps=None):
    """Score (encoded vs source) with libvmaf; production-equivalent chain. XML written bare-name in SMOKE_DIR (absolute Windows paths break filtergraph parser)."""
    AbsXml = SMOKE_DIR / XmlBareName
    if AbsXml.exists():
        AbsXml.unlink()
    # fps=<source.fps> lock prevents mkv 1/24000 vs mp4 1/1000 timebase walk-off in libvmaf frame pairing.
    FpsLock = f"fps={SourceFps}," if SourceFps else ""
    Filter = (
        f"[0:v]{FpsLock}setpts=PTS-STARTPTS,scale={CompareScale}:flags=lanczos:in_range=auto:out_range=tv,format=yuv420p10le[dist];"
        f"[1:v]{FpsLock}setpts=PTS-STARTPTS,scale={CompareScale}:flags=lanczos:in_range=auto:out_range=tv,format=yuv420p10le[ref];"
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
    """Parse pooled VMAF metrics with held-frame motion filtering (see feature md criterion 6)."""
    Result = {
        "Mean": 0.0, "Min": None, "Max": None, "HarmonicMean": None,
        "StdDev": None, "P1": None, "P5": None, "P10": None, "P25": None,
        "MotionZeroFraction": None, "MotionFilterApplied": False,
        "FrameCount": 0,
    }
    if not LocalExists(XmlPath):
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
    """Cross-source rollup: per-variant medians of size, encode time, VMAF Mean / P5."""
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
    global FFMPEG, SMOKE_DIR, OUTPUT_DIR
    Parser = argparse.ArgumentParser(description="SVT-AV1 / av1_nvenc / av1_qsv shootout harness.")
    Parser.add_argument("--matrix", required=True, help="Path to matrix JSON.")
    Parser.add_argument("--ffmpeg", default=FFMPEG, help="ffmpeg binary path (Linux: /usr/local/bin/ffmpeg).")
    Parser.add_argument("--smoke-dir", default=str(SMOKE_DIR), help="Directory for VMAF XML logs + sidecar.")
    Parser.add_argument("--output-dir", default=str(OUTPUT_DIR), help="Directory for encoded mp4 outputs.")
    Parser.add_argument("--keep-encoded", action="store_true", help="Don't delete encoded outputs after VMAF.")
    Parser.add_argument("--keep-xml", action="store_true", help="Don't delete VMAF XML files after parsing.")
    Args = Parser.parse_args()
    FFMPEG = Args.ffmpeg
    SMOKE_DIR = Path(Args.smoke_dir)
    OUTPUT_DIR = Path(Args.output_dir)

    if not LocalExists(Args.matrix):
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

    MissingSources = [S for S in Sources if not LocalExists(S["path"])]
    if MissingSources:
        Log("Missing sources -- aborting:")
        for S in MissingSources:
            Log(f"  - {S['path']}")
        sys.exit(2)

    AllResults = {}
    SidecarPath = SMOKE_DIR / f"{TestName}.shootout.json"
    Sidecar = {
        "schema_version": 1,
        "test_name": TestName,
        "matrix_file": str(Path(Args.matrix).resolve()),
        "run_started": datetime.now().isoformat(timespec="seconds"),
        "matrix": Matrix,
        "results": {},
    }

    GrandT0 = time.time()
    for SrcIdx, Src in enumerate(Sources, 1):
        SrcId = Src["id"]
        SrcLabel = Src["label"]
        SrcPath = Src["path"]
        SrcSize = LocalGetSize(SrcPath)
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

            EncodeOk, EncodeDt, SizeB = Encode(Src, V, OutPath, OutputScale)
            Result["encode_ok"] = EncodeOk
            Result["encode_seconds"] = EncodeDt
            Result["size_bytes"] = SizeB
            Result["size_mb"] = round(SizeB / (1024 * 1024), 2)

            if EncodeOk and SizeB > 0:
                VmafOk, VmafDt, XmlPath = RunVmaf(OutPath, SrcPath, XmlBare, CompareScale, NThreads, Src.get("fps"))
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
