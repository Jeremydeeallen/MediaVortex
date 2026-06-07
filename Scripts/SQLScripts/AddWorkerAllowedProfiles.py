import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


# directive: worker-routing | # see worker-routing.C1
def Run():
    DB = DatabaseService()
    DB.ExecuteNonQuery("ALTER TABLE Workers ADD COLUMN IF NOT EXISTS AllowedProfiles TEXT NULL")
    print("Added AllowedProfiles column to Workers (NULL = accept every profile; CSV = explicit allowlist; '' = accept none)")


if __name__ == '__main__':
    Run()
