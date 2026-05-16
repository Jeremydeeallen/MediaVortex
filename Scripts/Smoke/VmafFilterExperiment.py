"""VMAF filter-chain experiment harness for the MKV-bimodal bug.

Re-runs libvmaf against the existing encoded variants in a sidecar (no
re-encode -- ~90s per variant) with a chosen filter recipe. Prints
Mean/HMean/StdDev/P5 so you can compare against the known-bimodal
baseline (Minnie's: Mean ~74.6, P5 0.00) and the known-clean reference
(FourK MP4: Mean ~95.8, P5 ~94.3).

Usage:
    py Scripts/Smoke/VmafFilterExperiment.py <sidecar.results.json> <recipe-name>

Recipes:
    baseline      -- current production filter (control)
    bit10         -- compare both streams at 10-bit (no downcast)
    setparams     -- force range=tv:colorspace=bt709 metadata on both
    scale_range   -- scale with explicit in_range=auto:out_range=tv
    zscale        -- zscale with explicit limited range + bt709
    setparams_10  -- setparams + compare at 10-bit (combo)
"""

import argparse
import math
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
FFMPEG = str(ROOT / "FFmpegMaster" / "bin" / "ffmpeg.exe")


RECIPES = {
    "baseline": (
        "[0:v]scale={cs},format=yuv420p[dist];"
        "[1:v]scale={cs},format=yuv420p[ref];"
        "[dist][ref]libvmaf=log_path={xml}"
    ),
    "bit10": (
        "[0:v]scale={cs},format=yuv420p10le[dist];"
        "[1:v]scale={cs},format=yuv420p10le[ref];"
        "[dist][ref]libvmaf=log_path={xml}"
    ),
    "setparams": (
        "[0:v]scale={cs},format=yuv420p,setparams=range=tv:colorspace=bt709:color_primaries=bt709:color_trc=bt709[dist];"
        "[1:v]scale={cs},format=yuv420p,setparams=range=tv:colorspace=bt709:color_primaries=bt709:color_trc=bt709[ref];"
        "[dist][ref]libvmaf=log_path={xml}"
    ),
    "scale_range": (
        "[0:v]scale={cs}:in_range=auto:out_range=tv,format=yuv420p[dist];"
        "[1:v]scale={cs}:in_range=auto:out_range=tv,format=yuv420p[ref];"
        "[dist][ref]libvmaf=log_path={xml}"
    ),
    "zscale": (
        "[0:v]zscale=w={zw}:h={zh}:range=limited:transfer=bt709:matrix=bt709:primaries=bt709,format=yuv420p[dist];"
        "[1:v]zscale=w={zw}:h={zh}:range=limited:transfer=bt709:matrix=bt709:primaries=bt709,format=yuv420p[ref];"
        "[dist][ref]libvmaf=log_path={xml}"
    ),
    "setparams_10": (
        "[0:v]scale={cs},format=yuv420p10le,setparams=range=tv:colorspace=bt709:color_primaries=bt709:color_trc=bt709[dist];"
        "[1:v]scale={cs},format=yuv420p10le,setparams=range=tv:colorspace=bt709:color_primaries=bt709:color_trc=bt709[ref];"
        "[dist][ref]libvmaf=log_path={xml}"
    ),
    "neg_model": (
        "[0:v]scale={cs},format=yuv420p[dist];"
        "[1:v]scale={cs},format=yuv420p[ref];"
        "[dist][ref]libvmaf=log_path={xml}:model=version=vmaf_v0.6.1neg"
    ),
    "ts_nearest": (
        "[0:v]scale={cs},format=yuv420p[dist];"
        "[1:v]scale={cs},format=yuv420p[ref];"
        "[dist][ref]libvmaf=log_path={xml}:ts_sync_mode=nearest"
    ),
    "mpdecimate": (
        "[0:v]mpdecimate,scale={cs},format=yuv420p[dist];"
        "[1:v]mpdecimate,scale={cs},format=yuv420p[ref];"
        "[dist][ref]libvmaf=log_path={xml}"
    ),
}


def Log(M):
    print(f"[{time.strftime('%H:%M:%S')}] {M}", flush=True)


def ParseMetrics(XmlPath):
    R = {"Mean": 0.0, "HMean": 0.0, "StdDev": 0.0, "P5": 0.0, "P10": 0.0, "P25": 0.0, "Frames": 0}
    if not os.path.exists(XmlPath):
        return R
    Root = ET.parse(XmlPath).getroot()
    Pooled = Root.find('.//pooled_metrics/metric[@name="vmaf"]') or Root.find('.//metric[@name="vmaf"]')
    if Pooled is not None:
        for K, A in (("Mean", "mean"), ("HMean", "harmonic_mean")):
            V = Pooled.get(A)
            if V is not None:
                try: R[K] = float(V)
                except: pass
    Per = [float(F.get("vmaf")) for F in Root.findall(".//frame") if F.get("vmaf")]
    if Per:
        R["Frames"] = len(Per)
        S = sorted(Per)
        N = len(S)
        M_ = sum(Per) / N
        R["StdDev"] = math.sqrt(sum((X - M_) ** 2 for X in Per) / N)
        for K, P in (("P5", 0.05), ("P10", 0.10), ("P25", 0.25)):
            R[K] = S[max(0, min(N - 1, int(P * N)))]
    return R


def RunVmaf(Source, OutPath, Recipe, CompareScale, XmlName):
    SmokeDir = str(ROOT / "Scripts" / "Smoke")
    XmlPath = os.path.join(SmokeDir, XmlName)
    if os.path.exists(XmlPath):
        os.remove(XmlPath)
    Cs = CompareScale  # e.g. "1280:720"
    Zw, Zh = Cs.split(":")
    Filter = RECIPES[Recipe].format(cs=Cs, zw=Zw, zh=Zh, xml=XmlName)
    Cmd = [FFMPEG, "-i", Source, "-i", OutPath, "-lavfi", Filter, "-f", "null", "-"]
    Log(f"  recipe={Recipe} | {Cs}")
    T0 = time.time()
    R = subprocess.run(Cmd, capture_output=True, text=True, cwd=SmokeDir)
    Dt = time.time() - T0
    if R.returncode != 0:
        Log(f"  FAIL rc={R.returncode}")
        print((R.stderr or "")[-1500:])
        return None
    M = ParseMetrics(XmlPath)
    M["Seconds"] = round(Dt, 1)
    return M


def Main():
    Parser = argparse.ArgumentParser()
    Parser.add_argument("sidecar", help="Path to *.results.json sidecar")
    Parser.add_argument("recipe", choices=list(RECIPES.keys()))
    Parser.add_argument("--compare-scale", default="1280:720")
    Args = Parser.parse_args()

    if Args.recipe not in RECIPES:
        Log(f"Unknown recipe '{Args.recipe}'. Choices: {list(RECIPES)}")
        sys.exit(2)

    with open(Args.sidecar, "r", encoding="utf-8") as F:
        Sidecar = json.load(F)
    Source = Sidecar["source"]
    if not os.path.exists(Source):
        Log(f"Source not found: {Source}")
        sys.exit(1)
    TestName = Sidecar.get("test_name", "unknown")

    Log(f"Source: {os.path.basename(Source)}")
    Log(f"Recipe: {Args.recipe}")
    Log(f"Compare-scale: {Args.compare_scale}")

    Results = []
    for V in Sidecar["variants"]:
        if not os.path.exists(V.get("out_path", "")):
            Log(f"SKIP {V['label']}: missing {V.get('out_path')}")
            continue
        XmlName = f"vmaf_exp_{TestName}_{Args.recipe}_{V['name']}.xml"
        Log(f"VMAF {V['label']}")
        M = RunVmaf(Source, V["out_path"], Args.recipe, Args.compare_scale, XmlName)
        if M is None:
            continue
        Log(f"  done in {M['Seconds']}s | Mean={M['Mean']:.2f} HMean={M['HMean']:.2f} StdDev={M['StdDev']:.2f} P5={M['P5']:.2f}")
        Results.append((V["label"], M))

    print()
    print("=" * 96)
    print(f"  {TestName}  recipe={Args.recipe}  compare={Args.compare_scale}")
    print("=" * 96)
    print(f"  {'Variant':<22} {'Mean':>7} {'HMean':>7} {'StdDev':>7} {'P5':>7} {'P10':>7} {'P25':>7} {'Frames':>7}")
    print(f"  {'-'*22} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*7}")
    for Label, M in Results:
        print(f"  {Label:<22} {M['Mean']:>7.2f} {M['HMean']:>7.2f} {M['StdDev']:>7.2f} {M['P5']:>7.2f} {M['P10']:>7.2f} {M['P25']:>7.2f} {M['Frames']:>7}")
    print("=" * 96)


if __name__ == "__main__":
    Main()
