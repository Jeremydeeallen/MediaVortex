# directive: tv-video-rule-tier1 | # see video-encoding.C1
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


TV_LIBRARY_NAME = 'media_tv'
TV_DEFAULT_TIER = 1


# directive: tv-video-rule-tier1 | # see video-encoding.C1
def Run():
    Db = DatabaseService()
    Db.ExecuteNonQuery(
        "ALTER TABLE StorageRoots ADD COLUMN IF NOT EXISTS DefaultQualityTier INT NULL"
    )
    Db.ExecuteNonQuery(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'storageroots_defaultqualitytier_range') THEN "
        "ALTER TABLE StorageRoots ADD CONSTRAINT storageroots_defaultqualitytier_range "
        "CHECK (DefaultQualityTier IS NULL OR DefaultQualityTier BETWEEN 1 AND 5); "
        "END IF; END $$"
    )
    Db.ExecuteNonQuery(
        "UPDATE StorageRoots SET DefaultQualityTier = %s WHERE Name = %s AND DefaultQualityTier IS NULL",
        (TV_DEFAULT_TIER, TV_LIBRARY_NAME),
    )
    for R in Db.ExecuteQuery("SELECT Id, Name, DefaultQualityTier FROM StorageRoots ORDER BY Id"):
        print(f"  StorageRoot {R.get('Id')} {R.get('Name')}: DefaultQualityTier={R.get('DefaultQualityTier')}")
    return 0


if __name__ == '__main__':
    raise SystemExit(Run())
