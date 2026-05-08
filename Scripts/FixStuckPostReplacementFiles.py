"""One-shot recovery for files where transcode + replacement succeeded but the
post-replacement re-probe failed (the bug fixed in FileReplacementBusinessService:
ntpath instead of os.path on Linux workers). For each MediaFiles row where
TranscodeAttempts.Success=true AND FileReplaced=true AND TranscodedByMediaVortex
is not true, locate the new file on disk via the same naming pattern the
replacement uses, FFprobe it, and write the missing metadata back.

Skips any file we cannot locate on disk -- those are real losses and must be
handled separately.
"""

import json
import ntpath
import os
import subprocess
import sys

import psycopg2
import psycopg2.extras

FFPROBE = r"C:\Code\MediaVortex\FFmpegMaster\bin\ffprobe.exe"


def Probe(LocalPath):
    Cmd = [FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", LocalPath]
    Result = subprocess.run(Cmd, capture_output=True, text=True, timeout=60)
    if Result.returncode != 0:
        return None
    return json.loads(Result.stdout)


def ExtractMetadata(Probe, FileSize):
    Format = Probe.get("format", {})
    Streams = Probe.get("streams", [])
    Video = next((S for S in Streams if S.get("codec_type") == "video"), None)
    Audio = next((S for S in Streams if S.get("codec_type") == "audio"), None)

    DurationSec = float(Format.get("duration", 0)) or 0.0
    Width = Video.get("width") if Video else None
    Height = Video.get("height") if Video else None
    Resolution = f"{Width}x{Height}" if Width and Height else None
    if Height and Height >= 2000:
        Category = "2160p"
    elif Height and Height >= 1000:
        Category = "1080p"
    elif Height and Height >= 700:
        Category = "720p"
    elif Height:
        Category = "480p"
    else:
        Category = None

    OverallBitrate = int(Format.get("bit_rate")) if Format.get("bit_rate") else None

    return {
        "SizeMB": FileSize / 1024 / 1024,
        "FileSize": FileSize,
        "Resolution": Resolution,
        "ResolutionCategory": Category,
        "Codec": Video.get("codec_name") if Video else None,
        "DurationMinutes": DurationSec / 60 if DurationSec else None,
        "FrameRate": eval(Video.get("r_frame_rate")) if Video and Video.get("r_frame_rate") else None,
        "AudioCodec": Audio.get("codec_name") if Audio else None,
        "AudioChannels": Audio.get("channels") if Audio else None,
        "ContainerFormat": Format.get("format_name"),
        "OverallBitrate": OverallBitrate,
    }


def Main():
    Conn = psycopg2.connect(
        host=os.environ.get("MEDIAVORTEX_DB_HOST", "localhost"),
        port=int(os.environ.get("MEDIAVORTEX_DB_PORT", 5432)),
        dbname="mediavortex",
        user="mediavortex",
        password="mediavortex",
    )
    Conn.autocommit = False

    with Conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as Cur:
        Cur.execute(
            """
            SELECT DISTINCT mf.Id, mf.FilePath, tf.FinalFilePath
            FROM MediaFiles mf
            JOIN TranscodeAttempts ta ON ta.MediaFileId = mf.Id
            LEFT JOIN TranscodeFiles tf ON tf.MediaFileId = mf.Id
            WHERE ta.Success = true AND ta.FileReplaced = true
              AND (mf.TranscodedByMediaVortex IS NULL OR mf.TranscodedByMediaVortex = false)
            ORDER BY mf.Id
            """
        )
        Stuck = Cur.fetchall()

    print(f"Found {len(Stuck)} stuck rows")
    Fixed = 0
    Lost = 0

    for Row in Stuck:
        MediaFileId = Row["id"]
        OriginalPath = Row["filepath"]
        StagingPath = Row["finalfilepath"] or ""
        Filename = os.path.basename(StagingPath) if StagingPath else None
        if not Filename:
            print(f"  [{MediaFileId}] SKIP: no FinalFilePath in TranscodeFiles")
            Lost += 1
            continue

        # Reconstruct final media-share path: same directory as original, new filename
        NewCanonical = ntpath.join(ntpath.dirname(OriginalPath), Filename)
        if not os.path.exists(NewCanonical):
            print(f"  [{MediaFileId}] LOST: not on disk at {NewCanonical}")
            Lost += 1
            continue

        FileSize = os.path.getsize(NewCanonical)
        ProbeData = Probe(NewCanonical)
        if not ProbeData:
            print(f"  [{MediaFileId}] FFprobe failed: {NewCanonical}")
            Lost += 1
            continue

        Meta = ExtractMetadata(ProbeData, FileSize)

        with Conn.cursor() as Cur:
            Cur.execute(
                """
                UPDATE MediaFiles
                SET FilePath = %s,
                    FileName = %s,
                    SizeMB = %s,
                    FileSize = %s,
                    Resolution = %s,
                    ResolutionCategory = %s,
                    Codec = %s,
                    DurationMinutes = %s,
                    FrameRate = %s,
                    AudioCodec = %s,
                    AudioChannels = %s,
                    ContainerFormat = %s,
                    OverallBitrate = %s,
                    TranscodedByMediaVortex = TRUE,
                    LastScannedDate = NOW()
                WHERE Id = %s
                """,
                (
                    NewCanonical,
                    os.path.basename(NewCanonical),
                    Meta["SizeMB"],
                    Meta["FileSize"],
                    Meta["Resolution"],
                    Meta["ResolutionCategory"],
                    Meta["Codec"],
                    Meta["DurationMinutes"],
                    Meta["FrameRate"],
                    Meta["AudioCodec"],
                    Meta["AudioChannels"],
                    Meta["ContainerFormat"],
                    Meta["OverallBitrate"],
                    MediaFileId,
                ),
            )

            # Point TranscodeFiles.FinalFilePath at the actual final location
            Cur.execute(
                "UPDATE TranscodeFiles SET FinalFilePath = %s WHERE MediaFileId = %s",
                (NewCanonical, MediaFileId),
            )

            # Also delete any pending queue items for this file (it's done)
            Cur.execute(
                "DELETE FROM TranscodeQueue WHERE MediaFileId = %s",
                (MediaFileId,),
            )

        print(f"  [{MediaFileId}] FIXED: {Filename} ({Meta['Codec']}, {Meta['ResolutionCategory']})")
        Fixed += 1

    Conn.commit()
    Conn.close()
    print(f"\nFixed: {Fixed}  Lost: {Lost}")


if __name__ == "__main__":
    Main()
