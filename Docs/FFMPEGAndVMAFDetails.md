# FFmpeg + libvmaf Version Details
Usage Details: https://github.com/Netflix/vmaf/blob/master/resource/doc/ffmpeg.md
## FFmpeg Build Information
- **Version:** N-121164-gced4a6ebc9 (built 2025-09-22)
- **Compiler:** gcc 15.2.0 (crosstool-NG 1.28.0.1_403899e)
- **Architecture:** x86_64 (Windows, MinGW-w64)
- **libvmaf Support:** Enabled (`--enable-libvmaf`)
- **libav Versions:**
  - libavutil: 60.13.100
  - libavcodec: 62.15.100
  - libavformat: 62.6.100
  - libavfilter: 11.9.100
  - libswscale: 9.3.100
  - libswresample: 6.2.100

---

## libvmaf Filter Information
- **Filter Name:** `libvmaf`
- **Description:** Calculate the VMAF between two video streams.
- **Inputs:**
  - `#0`: main (distorted) video
  - `#1`: reference (original) video
- **Default Model:** `version=vmaf_v0.6.1`
- **Default Log Format:** `xml`
- **Supported Log Formats:** `csv`, `json`, `xml`, `sub`
- **Key Options:**
  - `log_path=<string>` — Path to VMAF log file  
  - `log_fmt=<string>` — Log output format  
  - `model=<string>` — Model selection (e.g. `vmaf_v0.6.1`)  
  - `n_threads=<int>` — Number of threads  
  - `n_subsample=<int>` — Frame subsampling interval  
  - `pool=<string>` — Pooling method (mean, harmonic_mean, etc.)
  - `n_subsample=10` — Analyze every 10th frame (90% CPU reduction, maintains accuracy)
  - Recommended settings for efficiency: `n_threads=2:n_subsample=10`

---

## libvmaf Version Details
- **Version Hash:** `2b2cf9c`
- **Approximate VMAF Release:** ≥ v2.3.0 (likely v2.3.1 or newer)
- **Default Model File:** `vmaf_v0.6.1.json`
- **JSON Log Key:** `"version": "2b2cf9c"`

Reference Commit:  
https://github.com/Netflix/vmaf/commit/2b2cf9c

---

## Example Command (Used in Test)
```bash
ffmpeg -f lavfi -i testsrc=size=1920x1080:rate=1 \
       -f lavfi -i testsrc=size=1920x1080:rate=1 \
       -lavfi libvmaf="log_path=vmaf.json:log_fmt=json" \
       -frames:v 1 -f null -
