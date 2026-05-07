# MediaVortex TranscodeService Worker
# Multi-stage build: FFmpeg static + Python app

# --- Stage 1: FFmpeg static build (BtbN, latest SVT-AV1 2.x) ---
FROM debian:bookworm-slim AS ffmpeg
RUN apt-get update -qq && apt-get install -y -qq curl xz-utils > /dev/null
RUN curl -sL https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz \
    | tar xJ --strip-components=1 -C /usr/local

# --- Stage 2: Application ---
FROM python:3.12-slim

# Copy FFmpeg/FFprobe from build stage
COPY --from=ffmpeg /usr/local/bin/ffmpeg /usr/local/bin/ffmpeg
COPY --from=ffmpeg /usr/local/bin/ffprobe /usr/local/bin/ffprobe

# Locale (media paths may contain non-ASCII characters)
RUN apt-get update -qq && apt-get install -y -qq locales > /dev/null \
    && sed -i 's/# en_US.UTF-8/en_US.UTF-8/' /etc/locale.gen \
    && locale-gen en_US.UTF-8 > /dev/null \
    && rm -rf /var/lib/apt/lists/*
ENV LANG=en_US.UTF-8

# Python dependencies (TranscodeService only)
RUN pip install --no-cache-dir \
    psycopg2-binary \
    psutil \
    setproctitle

# Copy application code
WORKDIR /opt/mediavortex
COPY . .

# Create staging directory mount point
RUN mkdir -p /mnt/media_tv/MediaVortex/Staging

ENTRYPOINT ["python3", "TranscodeService/Main.py"]
