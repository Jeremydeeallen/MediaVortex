"""
One-time data fix script: Backfill ResolutionCategory and fix stale profile assignments.
Run with: py Scripts/SQLScripts/BackfillDataFixes.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService

DB = DatabaseService()

def BackfillResolutionCategory():
    """Derive ResolutionCategory from Resolution for files that have it NULL."""
    Query = """
        UPDATE MediaFiles
        SET ResolutionCategory = CASE
            WHEN CAST(SPLIT_PART(Resolution, 'x', 2) AS INTEGER) >= 2160 THEN '2160p'
            WHEN CAST(SPLIT_PART(Resolution, 'x', 2) AS INTEGER) >= 1080 THEN '1080p'
            WHEN CAST(SPLIT_PART(Resolution, 'x', 2) AS INTEGER) >= 720  THEN '720p'
            ELSE '480p'
        END
        WHERE Resolution IS NOT NULL
          AND Resolution LIKE '%x%'
          AND ResolutionCategory IS NULL
    """
    RowCount = DB.ExecuteNonQuery(Query)
    print(f"[ResolutionCategory] Backfilled {RowCount} files")
    return RowCount

def ClearStaleProfiles():
    """Set profiles to NULL where the assigned profile no longer exists in the Profiles table.
    User manually assigns profiles per series, so we don't auto-remap."""
    Query = """
        UPDATE MediaFiles
        SET AssignedProfile = NULL
        WHERE AssignedProfile IS NOT NULL
          AND AssignedProfile != 'None'
          AND AssignedProfile NOT IN (SELECT ProfileName FROM Profiles)
    """
    RowCount = DB.ExecuteNonQuery(Query)
    print(f"[StaleProfiles] Cleared {RowCount} files with non-existent profiles to NULL")
    return RowCount

def FixNoneStringToNull():
    """Convert the string 'None' to actual NULL in AssignedProfile."""
    Query = "UPDATE MediaFiles SET AssignedProfile = NULL WHERE AssignedProfile = 'None'"
    RowCount = DB.ExecuteNonQuery(Query)
    print(f"[NoneToNull] Set {RowCount} files from 'None' string to NULL")
    return RowCount

if __name__ == "__main__":
    print("=== MediaVortex Data Fix Script ===\n")

    print("1. Backfilling ResolutionCategory...")
    BackfillResolutionCategory()

    print("\n2. Clearing stale profile assignments...")
    ClearStaleProfiles()

    print("\n3. Converting 'None' string to NULL...")
    FixNoneStringToNull()

    print("\n=== Done ===")
