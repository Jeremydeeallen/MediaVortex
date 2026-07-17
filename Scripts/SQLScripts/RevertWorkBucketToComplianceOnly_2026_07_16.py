import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from Core.Database.DatabaseService import DatabaseService


# directive: transcode-flow-canonical -- WorkBucket is a pure derivation of the 3 compliance flags. TranscodedByMediaVortex is METADATA (which files we produced), not a suppression signal. A -mv file with audiocompliant=FALSE belongs in AudioFix, not hidden.
NEW_EXPRESSION = (
    "CASE "
    "WHEN videocompliant IS NULL OR containercompliant IS NULL OR audiocompliant IS NULL THEN NULL::text "
    "WHEN videocompliant = false THEN 'Transcode'::text "
    "WHEN containercompliant = false THEN 'Remux'::text "
    "WHEN audiocompliant = false THEN 'AudioFix'::text "
    "ELSE NULL::text "
    "END"
)


def RunMigration():
    Db = DatabaseService()
    Rows = Db.ExecuteQuery(
        "SELECT generation_expression FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s",
        ('mediafiles', 'workbucket'),
    )
    Current = (Rows[0]['generation_expression'] or '').lower() if Rows else ''
    if 'transcodedbymediavortex' not in Current:
        print("WorkBucket generation already compliance-only -- skipping")
        return
    print("Dropping WorkBucket generated column (has stale TranscodedByMediaVortex clause)...")
    Db.ExecuteNonQuery("ALTER TABLE MediaFiles DROP COLUMN WorkBucket", ())
    print("Re-adding WorkBucket derived from compliance flags only...")
    Db.ExecuteNonQuery(
        f"ALTER TABLE MediaFiles ADD COLUMN WorkBucket TEXT GENERATED ALWAYS AS ({NEW_EXPRESSION}) STORED",
        (),
    )
    print("Done.")


if __name__ == '__main__':
    RunMigration()
