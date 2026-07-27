# directive: verify-signal-cleanup | # see DOMAIN.md 2026-07-26 Vmaf-truthful rule
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


# directive: verify-signal-cleanup
def Main():
    Db = DatabaseService()
    Before = Db.ExecuteQuery(
        "SELECT COUNT(*) AS n FROM TranscodeAttempts "
        "WHERE ProcessingMode IN ('Remux','AudioFix','SubtitleFix','Quick') AND Vmaf = 100.0"
    )
    N = int(Before[0].get('n')) if Before else 0
    print(f"Sentinel rows to nullify: {N}")
    Db.ExecuteNonQuery(
        "UPDATE TranscodeAttempts SET Vmaf = NULL "
        "WHERE ProcessingMode IN ('Remux','AudioFix','SubtitleFix','Quick') AND Vmaf = 100.0"
    )
    After = Db.ExecuteQuery(
        "SELECT COUNT(*) AS n FROM TranscodeAttempts "
        "WHERE ProcessingMode IN ('Remux','AudioFix','SubtitleFix','Quick') AND Vmaf = 100.0"
    )
    R = int(After[0].get('n')) if After else 0
    if R != 0:
        print(f"FAIL: {R} sentinel rows still present")
    else:
        print("Applied. Stream-copy Vmaf=100.0 sentinels nullified.")


if __name__ == '__main__':
    Main()
