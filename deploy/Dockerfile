# MediaVortex WorkerService
# Multi-stage build: FFmpeg static + Python app

# --- Stage 1: FFmpeg static build (BtbN, pinned tag + asset) ---
# directive: worker-runtime-state
FROM debian:bookworm-slim AS ffmpeg
ARG FFMPEG_TAG
ARG FFMPEG_ASSET
RUN test -n "$FFMPEG_TAG" && test -n "$FFMPEG_ASSET" || (echo "FFMPEG_TAG and FFMPEG_ASSET must be passed; see deploy/ffmpeg-release.txt" >&2; exit 1)
RUN apt-get update -qq && apt-get install -y -qq curl xz-utils > /dev/null
RUN curl -fsSL "https://github.com/BtbN/FFmpeg-Builds/releases/download/${FFMPEG_TAG}/${FFMPEG_ASSET}" \
    | tar xJ --strip-components=1 -C /usr/local

# --- Stage 2: Application ---
# Ubuntu noble base required by libmfx-gen1.2 baseline used by Docker-on-Linux hosts.
FROM ubuntu:24.04

# Copy FFmpeg/FFprobe from build stage
COPY --from=ffmpeg /usr/local/bin/ffmpeg /usr/local/bin/ffmpeg
COPY --from=ffmpeg /usr/local/bin/ffprobe /usr/local/bin/ffprobe

# Locale + Python runtime + Intel media stack. Single apt layer to keep image small.
# Intel kobuk PPA carries the noble-targeted libmfx-gen1.2 / iHD driver.
RUN apt-get update -qq \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
        software-properties-common \
        locales \
        ca-certificates \
        gnupg \
        curl \
        python3.12 \
        python3-pip > /dev/null \
    && add-apt-repository -y ppa:kobuk-team/intel-graphics > /dev/null \
    && apt-get update -qq \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
        intel-media-va-driver-non-free \
        libva-drm2 \
        libva2 \
        libvpl2 \
        libmfx-gen1.2 > /dev/null \
    && sed -i 's/# en_US.UTF-8/en_US.UTF-8/' /etc/locale.gen \
    && locale-gen en_US.UTF-8 > /dev/null \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.12 /usr/local/bin/python3 \
    && ln -sf /usr/bin/python3.12 /usr/local/bin/python
ENV LANG=en_US.UTF-8
ENV LIBVA_DRIVER_NAME=iHD

# Python dependencies (WorkerService). PEP 668 on Ubuntu noble needs --break-system-packages
# for global pip install in a single-purpose container.
# directive: audio-dialog-boost-real | # see audio-normalization.C14
# TORCH_VARIANT picks the wheel: cpu, cu124 (CUDA 12.4). Intel Arc / Xe hosts run bare-metal via deploy-baremetal-worker.py, not Docker.
ARG TORCH_VARIANT=cpu
RUN pip install --no-cache-dir --break-system-packages \
        psycopg2-binary \
        psutil \
        setproctitle \
        soundfile \
 && pip install --no-cache-dir --break-system-packages \
        --index-url https://download.pytorch.org/whl/${TORCH_VARIANT} \
        torch==2.6.0 torchaudio==2.6.0 \
 && pip install --no-cache-dir --break-system-packages demucs==4.0.1

# Copy application code
WORKDIR /opt/mediavortex
COPY . .

# BUG-0085: purge stale __pycache__ that build-cache may leak into cached layer.
RUN find /opt/mediavortex -type d -name __pycache__ -exec rm -rf {} + || true

# Create staging directory mount point
RUN mkdir -p /mnt/media_tv/MediaVortex/Staging

# Build-time version stamp (worker-versioning.feature.md criteria 1, 2).
# COMMIT_SHA is passed in via --build-arg from the deploy script (the source
# tree on the build host is an scp'd snapshot, not a git checkout, so the SHA
# can't be derived inside the image).
ARG COMMIT_SHA=unknown
RUN echo "$COMMIT_SHA" > /opt/mediavortex/VERSION \
 && printf "commit=%s\nbuilt_at=%s\nbuilt_by=%s\n" "$COMMIT_SHA" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(hostname)" > /opt/mediavortex/BUILD_INFO

ENTRYPOINT ["python3", "WorkerService/Main.py"]
