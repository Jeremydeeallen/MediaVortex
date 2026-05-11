"""Quick per-frame VMAF inspector: prints histogram and the 20 worst frames
with timestamps so we can correlate low scores to scene type."""

import sys
import xml.etree.ElementTree as ET


def Main(XmlPath, Fps=23.976):
    Root = ET.parse(XmlPath).getroot()
    Frames = []
    for F in Root.findall('.//frame'):
        Val = F.get('vmaf')
        if Val is not None:
            try:
                Frames.append({'idx': int(F.get('frameNum') or len(Frames)), 'vmaf': float(Val)})
            except: pass
    if not Frames:
        print("No frames parsed."); return
    N = len(Frames)
    print(f"Frames: {N}")

    Buckets = [0]*11
    for FrameRow in Frames:
        B = min(10, max(0, int(FrameRow['vmaf'] / 10)))
        Buckets[B] += 1
    print("\nHistogram (10-pt bins):")
    for I in range(11):
        Lo, Hi = I*10, (I+1)*10
        Pct = 100 * Buckets[I] / N
        Bar = '#' * int(Pct / 2)
        print(f"  [{Lo:3}-{Hi:3}) n={Buckets[I]:5} {Pct:5.1f}% {Bar}")

    Sorted_ = sorted(Frames, key=lambda F: F['vmaf'])
    print(f"\n20 worst frames:")
    print(f"  {'frame#':>8} {'timestamp':>10} {'vmaf':>7}")
    for F in Sorted_[:20]:
        Ts = F['idx'] / Fps
        Mins, Secs = divmod(Ts, 60)
        print(f"  {F['idx']:>8} {int(Mins):>4}:{Secs:05.2f} {F['vmaf']:>7.2f}")

    print(f"\n20 best frames:")
    for F in Sorted_[-20:][::-1]:
        Ts = F['idx'] / Fps
        Mins, Secs = divmod(Ts, 60)
        print(f"  {F['idx']:>8} {int(Mins):>4}:{Secs:05.2f} {F['vmaf']:>7.2f}")


if __name__ == "__main__":
    XmlPath = sys.argv[1] if len(sys.argv) > 1 else "Scripts/Smoke/vmaf_MinnieBowToons-S04E07-Animation8Mbps_A.xml"
    Fps = float(sys.argv[2]) if len(sys.argv) > 2 else 23.976
    Main(XmlPath, Fps)
