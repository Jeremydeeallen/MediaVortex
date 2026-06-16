import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


DROP_VIEW_SQL = "DROP VIEW IF EXISTS v_audio_consistency_summary"

CREATE_VIEW_SQL = (
    "CREATE VIEW v_audio_consistency_summary AS "
    "WITH track_metrics AS ("
    "SELECT "
    "ta.Id AS AttemptId, "
    "mf.StorageRootId AS LibraryId, "
    "(track->>'AchievedIntegratedLufs')::REAL AS AchievedLufs, "
    "COALESCE("
    "(ta.AudioPolicyJson->>'TargetIntegratedLufs')::REAL, "
    "-23.0"
    ") AS TargetLufs "
    "FROM TranscodeAttempts ta "
    "LEFT JOIN MediaFiles mf ON mf.Id = ta.MediaFileId "
    "CROSS JOIN LATERAL jsonb_array_elements(COALESCE(ta.AudioTracksEmittedJson, '[]'::jsonb)) AS track "
    "WHERE ta.Success = TRUE "
    "AND ta.AudioTracksEmittedJson IS NOT NULL"
    "), "
    "banded AS ("
    "SELECT "
    "LibraryId, "
    "AttemptId, "
    "ABS(AchievedLufs - TargetLufs) AS DeltaLu "
    "FROM track_metrics "
    "WHERE AchievedLufs IS NOT NULL"
    ") "
    "SELECT "
    "LibraryId, "
    "SUM(CASE WHEN DeltaLu <= 2.0 THEN 1 ELSE 0 END) AS UniformCount, "
    "SUM(CASE WHEN DeltaLu > 2.0 AND DeltaLu <= 4.0 THEN 1 ELSE 0 END) AS AcceptableCount, "
    "SUM(CASE WHEN DeltaLu > 4.0 THEN 1 ELSE 0 END) AS DeviantCount, "
    "COUNT(*) AS TotalCount "
    "FROM banded "
    "GROUP BY LibraryId"
)


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C15
def Main():
    """Idempotent migration: drop and recreate v_audio_consistency_summary view."""
    Db = DatabaseService()
    Db.ExecuteNonQuery(DROP_VIEW_SQL)
    Db.ExecuteNonQuery(CREATE_VIEW_SQL)
    print("v_audio_consistency_summary view present.")
    print("Rollback: DROP VIEW IF EXISTS v_audio_consistency_summary;")
    return 0


if __name__ == "__main__":
    raise SystemExit(Main())
