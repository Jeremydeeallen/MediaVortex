import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


# directive: compliance-symmetry
def Run():
    DB = DatabaseService()

    DB.ExecuteNonQuery("ALTER TABLE Profiles ADD COLUMN IF NOT EXISTS Draft BOOLEAN NOT NULL DEFAULT TRUE")
    DB.ExecuteNonQuery("ALTER TABLE Profiles ADD COLUMN IF NOT EXISTS Active BOOLEAN NOT NULL DEFAULT TRUE")
    DB.ExecuteNonQuery("ALTER TABLE Profiles ADD COLUMN IF NOT EXISTS StreamCodecName VARCHAR(16) NULL")
    DB.ExecuteNonQuery("ALTER TABLE Profiles ADD COLUMN IF NOT EXISTS TargetResolutionCategory VARCHAR(8) NULL")
    DB.ExecuteNonQuery("ALTER TABLE Profiles ADD COLUMN IF NOT EXISTS TargetVideoKbps INT NULL")
    DB.ExecuteNonQuery("ALTER TABLE Profiles ADD COLUMN IF NOT EXISTS AllowUpscale BOOLEAN NOT NULL DEFAULT FALSE")
    DB.ExecuteNonQuery("ALTER TABLE Profiles ADD COLUMN IF NOT EXISTS AudioCodec VARCHAR(16) NULL")
    DB.ExecuteNonQuery("ALTER TABLE Profiles ADD COLUMN IF NOT EXISTS TargetAudioKbps INT NULL")
    DB.ExecuteNonQuery("ALTER TABLE Profiles ADD COLUMN IF NOT EXISTS Container VARCHAR(8) NULL")

    Rows = DB.ExecuteQuery(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'profiles' "
        "AND column_name IN ('draft', 'active', 'streamcodecname', 'targetresolutioncategory', "
        "'targetvideokbps', 'allowupscale', 'audiocodec', 'targetaudiokbps', 'container') "
        "ORDER BY column_name"
    )
    print(f"Profiles compliance columns present ({len(Rows)}/9):")
    for Row in Rows:
        print("  " + Row['column_name'])


if __name__ == '__main__':
    Run()
