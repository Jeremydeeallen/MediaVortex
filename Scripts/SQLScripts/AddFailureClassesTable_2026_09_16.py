# directive: bug-0095-failure-classification
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


# directive: bug-0095-failure-classification
_SEED_RULES = [
    ('source_unreadable', 10, r'moov atom not found|Invalid data found when processing input|Error opening input file', True, 'Regrab source (Sonarr/Radarr); source file is corrupt or truncated'),
    ('source_audio_corrupt_dts', 20, r'Error while decoding stream.*dca', True, 'Regrab source; audio stream corrupt'),
    ('source_video_corrupt_h264', 30, r'Error while decoding stream.*h264', True, 'Regrab source; video stream corrupt'),
    ('subtitle_sample_too_large', 40, r'mov_text.*Result too large', False, 'Auto-drop subtitle stream (BUG-0102 fix); or choose mkv container variant'),
    ('pix_fmt_unsupported', 50, r'Impossible to convert between the formats.*yuv4[24]2p16', False, 'Pipeline fix pending; VideoSlot pix_fmt normalization filter (BUG-0104)'),
    ('stereo_downmix_source_unreadable', 55, r'stereo downmix failed.*moov atom not found', True, 'Regrab source; pre-encode source-readability preflight (BUG-0103) will catch upstream once shipped'),
    ('demucs_daemon_down', 60, r'DemucsDaemonUnavailableError', False, 'Restart worker; retry auto-triggered via D13 partial-completion'),
    ('loudness_invalid_unrecoverable', 70, r'ComplianceGateFailed:\s*invalid_loudness_measurement', False, 'Under investigation per BUG-0100; may become Terminal or pipeline fix once validator rule identified'),
    ('ffmpeg_crash_midencode', 80, r'Segmentation fault|core dumped', False, 'Retry once; escalate if repeats within 24h'),
    ('codec_map_mismatch', 90, r'Requested output format.*does not accept', False, 'Pipeline fix pending; codec assignment audit'),
    ('orphan_output', 100, r'Refusing to overwrite existing', False, 'Delete .inprogress at path; then retry'),
    ('unclassified', 9999, r'.*', False, 'Investigate manually via /FailedJobs modal attempt history'),
]


# directive: bug-0095-failure-classification
def Main():
    Db = DatabaseService()
    Db.ExecuteNonQuery(
        "CREATE TABLE IF NOT EXISTS FailureClasses ("
        "  ClassName TEXT PRIMARY KEY,"
        "  Priority INTEGER NOT NULL,"
        "  ErrorPattern TEXT NOT NULL,"
        "  Terminal BOOLEAN NOT NULL DEFAULT FALSE,"
        "  Remediation TEXT NOT NULL,"
        "  CreatedAt TIMESTAMP NOT NULL DEFAULT NOW(),"
        "  UpdatedAt TIMESTAMP NOT NULL DEFAULT NOW()"
        ")"
    )
    Db.ExecuteNonQuery(
        "CREATE INDEX IF NOT EXISTS ix_failureclasses_priority ON FailureClasses (Priority)"
    )
    for Row in _SEED_RULES:
        Db.ExecuteNonQuery(
            "INSERT INTO FailureClasses (ClassName, Priority, ErrorPattern, Terminal, Remediation) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (ClassName) DO NOTHING",
            Row,
        )
    Rows = Db.ExecuteQuery("SELECT COUNT(*) AS n FROM FailureClasses")
    Count = int((Rows[0] or {}).get('n') or 0) if Rows else 0
    if Count < len(_SEED_RULES):
        raise RuntimeError(
            f"seed rule count {Count} below expected {len(_SEED_RULES)}"
        )
    print(f"Applied. FailureClasses table present. Seed rule count: {Count}.")


if __name__ == '__main__':
    Main()
