# directive: profile-row-lookup
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService

CheckSql = (
    "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{Name}') THEN "
    "ALTER TABLE {Table} ADD CONSTRAINT {Name} CHECK ({Column} IN ('live_action', 'animation')); END IF; END $$;"
)


# directive: profile-row-lookup | # see profile-tier-ladder.C10 -- content class is operator data: per-genre class, else the library's default
def Run():
    Db = DatabaseService()
    Db.ExecuteNonQuery("ALTER TABLE StorageRoots ADD COLUMN IF NOT EXISTS DefaultContentClass TEXT NULL")
    Db.ExecuteNonQuery(CheckSql.format(Name='storageroots_defaultcontentclass_check', Table='StorageRoots', Column='DefaultContentClass'))
    Db.ExecuteNonQuery("ALTER TABLE GenreQualityTiers ADD COLUMN IF NOT EXISTS ContentClass TEXT NULL")
    Db.ExecuteNonQuery(CheckSql.format(Name='genrequalitytiers_contentclass_check', Table='GenreQualityTiers', Column='ContentClass'))
    Db.ExecuteNonQuery("UPDATE StorageRoots SET DefaultContentClass = 'live_action' WHERE DefaultContentClass IS NULL")
    Db.ExecuteNonQuery("UPDATE GenreQualityTiers SET ContentClass = 'animation' WHERE Genre = 'Animation' AND ContentClass IS NULL")
    for R in Db.ExecuteQuery("SELECT Id, Name, DefaultContentClass FROM StorageRoots ORDER BY Id"):
        print(f"  root {R.get('Id')} {R.get('Name')}: DefaultContentClass={R.get('DefaultContentClass')}")
    for R in Db.ExecuteQuery("SELECT Genre, ContentClass FROM GenreQualityTiers WHERE ContentClass IS NOT NULL ORDER BY Genre"):
        print(f"  genre {R.get('Genre')}: ContentClass={R.get('ContentClass')}")
    return 0


if __name__ == '__main__':
    raise SystemExit(Run())
