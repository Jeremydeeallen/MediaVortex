#!/usr/bin/env python3
"""
BackfillAudioComplete.py
One-time backfill of MediaFiles.AudioComplete / AudioCorruptSuspect /
AudioCorruptReason / AudioCompletedAt.

Owns: audio-completion.feature.md criteria 16-17.

Four idempotent UPDATE statements, run in order:

  1. no_audio_stream         -- probed + AudioCodec IS NULL + Resolution
                                -> AudioCorruptSuspect=true,
                                   AudioCorruptReason='no_audio_stream'
  2. loudnorm-history        -- MediaFileId in TranscodeAttempts.FFpmpegCommand
                                ILIKE '%loudnorm%' (Success=true)
                                -> AudioComplete=true, AudioCompletedAt=NOW()
  3. below_bitrate_floor     -- MP4-compat audio codec AND AudioBitrateKbps
                                at or below channel-tier floor
                                -> AudioComplete=true,
                                   AudioCorruptReason='below_bitrate_floor',
                                   AudioCompletedAt=NOW()
  4. eligible-normalize      -- everything else that's probed
                                -> AudioComplete=false

Each UPDATE WHERE clause excludes rows already in their target state, so
re-running the script is a no-op (idempotency).

Expected counts (live DB sample 2026-05-16, 56,698 total):
  no_audio_stream:       ~2,097
  loudnorm-history:      ~9,198
  below_bitrate_floor:   ~9,385 (8,879 stereo + 87 mono + 419 surround)
  eligible-normalize:    ~24,000 (remainder of probed rows)
  unprobed (NULL):       ~11,782 (untouched)

Coordinate worker pause before running (memory/feedback_coordinate_live_worker_writes.md).
"""

import os
import psycopg2


def GetConnection():
    return psycopg2.connect(
        host=os.environ.get('MEDIAVORTEX_DB_HOST', 'localhost'),
        port=int(os.environ.get('MEDIAVORTEX_DB_PORT', '5432')),
        database=os.environ.get('MEDIAVORTEX_DB_NAME', 'mediavortex'),
        user=os.environ.get('MEDIAVORTEX_DB_USER', 'mediavortex'),
        password=os.environ.get('MEDIAVORTEX_DB_PASSWORD', 'mediavortex'),
    )


def Header(Msg):
    print()
    print('--- ' + Msg + ' ---')


def UpdateNoAudioStream(Cur):
    Header('Pass 1: no_audio_stream (probed + AudioCodec IS NULL + Resolution)')
    Cur.execute(
        """
        UPDATE MediaFiles
        SET AudioCorruptSuspect = TRUE,
            AudioCorruptReason  = 'no_audio_stream'
        WHERE HasExplicitEnglishAudio IS NOT NULL
          AND (AudioCodec IS NULL OR AudioCodec = '')
          AND Resolution IS NOT NULL
          AND AudioCorruptSuspect = FALSE
        """
    )
    print(f"  updated {Cur.rowcount} rows")


def UpdateLoudnormHistory(Cur):
    Header("Pass 2: loudnorm-history (MediaFileId in TranscodeAttempts with loudnorm)")
    Cur.execute(
        """
        UPDATE MediaFiles m
        SET AudioComplete = TRUE,
            AudioCompletedAt = NOW(),
            AudioCorruptReason = NULL
        WHERE m.AudioComplete IS NULL
          AND m.AudioCorruptSuspect = FALSE
          AND EXISTS (
              SELECT 1 FROM TranscodeAttempts ta
              WHERE ta.MediaFileId = m.Id
                AND ta.Success = TRUE
                AND ta.FFpmpegCommand ILIKE '%loudnorm%'
          )
        """
    )
    print(f"  updated {Cur.rowcount} rows")


def UpdateBelowBitrateFloor(Cur):
    Header('Pass 3: below_bitrate_floor (MP4-compat codec at or below channel floor)')
    # Pull floor values fresh from QueueAdmissionConfig.
    Cur.execute(
        """
        SELECT MinAudioBitrateKbpsMono, MinAudioBitrateKbpsStereo, MinAudioBitrateKbpsSurround
        FROM QueueAdmissionConfig WHERE Id = 1
        """
    )
    Row = Cur.fetchone()
    Mono, Stereo, Surround = Row[0], Row[1], Row[2]
    print(f"  floor config: mono={Mono}, stereo={Stereo}, surround={Surround}")

    Cur.execute(
        """
        UPDATE MediaFiles
        SET AudioComplete = TRUE,
            AudioCompletedAt = NOW(),
            AudioCorruptReason = 'below_bitrate_floor'
        WHERE AudioComplete IS NULL
          AND AudioCorruptSuspect = FALSE
          AND LOWER(COALESCE(AudioCodec, '')) IN ('aac', 'ac3', 'eac3', 'mp3')
          AND AudioBitrateKbps IS NOT NULL
          AND (
              (AudioChannels = 1 AND AudioBitrateKbps <= %s) OR
              (AudioChannels = 2 AND AudioBitrateKbps <= %s) OR
              (AudioChannels >= 3 AND AudioBitrateKbps <= %s)
          )
        """,
        (Mono, Stereo, Surround),
    )
    print(f"  updated {Cur.rowcount} rows")


def UpdateEligibleNormalize(Cur):
    Header('Pass 4: eligible-normalize (everything else probed)')
    Cur.execute(
        """
        UPDATE MediaFiles
        SET AudioComplete = FALSE
        WHERE AudioComplete IS NULL
          AND AudioCorruptSuspect = FALSE
          AND HasExplicitEnglishAudio IS NOT NULL
          AND AudioCodec IS NOT NULL
          AND AudioCodec <> ''
        """
    )
    print(f"  updated {Cur.rowcount} rows")


def Summary(Cur):
    Header('Summary')
    Cur.execute(
        """
        SELECT
          COUNT(*) AS total,
          SUM(CASE WHEN AudioComplete IS TRUE THEN 1 ELSE 0 END) AS complete_true,
          SUM(CASE WHEN AudioComplete IS FALSE THEN 1 ELSE 0 END) AS complete_false,
          SUM(CASE WHEN AudioComplete IS NULL THEN 1 ELSE 0 END) AS complete_null,
          SUM(CASE WHEN AudioCorruptSuspect IS TRUE THEN 1 ELSE 0 END) AS suspect_true
        FROM MediaFiles
        """
    )
    Total, CT, CF, CN, Suspect = Cur.fetchone()
    print(f"  total={Total}")
    print(f"  AudioComplete=true  : {CT}")
    print(f"  AudioComplete=false : {CF}")
    print(f"  AudioComplete=NULL  : {CN}")
    print(f"  AudioCorruptSuspect : {Suspect}")
    print()
    Cur.execute(
        """
        SELECT AudioCorruptReason, COUNT(*)
        FROM MediaFiles
        WHERE AudioCorruptReason IS NOT NULL
        GROUP BY AudioCorruptReason
        ORDER BY 2 DESC
        """
    )
    print('  by reason:')
    for Reason, Count in Cur.fetchall():
        print(f"    {Reason:<35} {Count}")


def RunBackfill():
    Conn = GetConnection()
    Cur = Conn.cursor()
    try:
        UpdateNoAudioStream(Cur)
        Conn.commit()
        UpdateLoudnormHistory(Cur)
        Conn.commit()
        UpdateBelowBitrateFloor(Cur)
        Conn.commit()
        UpdateEligibleNormalize(Cur)
        Conn.commit()
        Summary(Cur)
    finally:
        Cur.close()
        Conn.close()


if __name__ == '__main__':
    RunBackfill()
