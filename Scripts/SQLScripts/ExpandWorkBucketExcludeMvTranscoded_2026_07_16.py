import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from Core.Database.DatabaseService import DatabaseService


# directive: transcode-flow-canonical -- WorkBucket must NULL out MediaVortex-transcoded files so UI counts reflect real re-transcode candidates, not self-encoded outputs the operator can't act on
NEW_EXPRESSION = (
    "CASE "
    "WHEN TranscodedByMediaVortex = TRUE THEN NULL::text "
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
    if 'transcodedbymediavortex = true' in Current:
        print("WorkBucket generation already excludes TranscodedByMediaVortex -- skipping")
        return
    print("Dropping stale WorkBucket generated column...")
    Db.ExecuteNonQuery("ALTER TABLE MediaFiles DROP COLUMN WorkBucket", ())
    print("Re-adding WorkBucket with TranscodedByMediaVortex exclusion...")
    Db.ExecuteNonQuery(
        f"ALTER TABLE MediaFiles ADD COLUMN WorkBucket TEXT GENERATED ALWAYS AS ({NEW_EXPRESSION}) STORED",
        (),
    )
    print("Done.")


if __name__ == '__main__':
    RunMigration()
