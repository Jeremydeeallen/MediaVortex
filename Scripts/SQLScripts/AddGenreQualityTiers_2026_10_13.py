# directive: movies-video-rule | # see video-encoding.C1
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


HIGH_TIER = 3
LOW_TIER = 1
HIGH_TIER_GENRES = ('Action', 'Adventure', 'Science Fiction', 'Fantasy', 'War')
LOW_TIER_GENRES = ('Romance', 'Comedy', 'Drama', 'Documentary', 'Music', 'History', 'TV Movie')
LIBRARY_DEFAULT_GENRES = ('Thriller', 'Crime', 'Horror', 'Mystery', 'Family', 'Animation', 'Western')


# directive: movies-video-rule | # see video-encoding.C1
def Run():
    Db = DatabaseService()
    Db.ExecuteNonQuery(
        "CREATE TABLE IF NOT EXISTS GenreQualityTiers ("
        "Genre TEXT PRIMARY KEY, "
        "QualityTier INT NULL CHECK (QualityTier IS NULL OR QualityTier BETWEEN 1 AND 5), "
        "LastUpdated TIMESTAMP NOT NULL DEFAULT NOW())"
    )
    Db.ExecuteNonQuery("ALTER TABLE MediaFiles ADD COLUMN IF NOT EXISTS Genres TEXT NULL")
    Db.ExecuteNonQuery("ALTER TABLE StorageRoots ADD COLUMN IF NOT EXISTS GenreSource TEXT NULL")
    Seed = [(G, HIGH_TIER) for G in HIGH_TIER_GENRES]
    Seed += [(G, LOW_TIER) for G in LOW_TIER_GENRES]
    Seed += [(G, None) for G in LIBRARY_DEFAULT_GENRES]
    for Genre, Tier in Seed:
        Db.ExecuteNonQuery(
            "INSERT INTO GenreQualityTiers (Genre, QualityTier) VALUES (%s, %s) ON CONFLICT (Genre) DO NOTHING",
            (Genre, Tier),
        )
    for R in Db.ExecuteQuery("SELECT Genre, QualityTier FROM GenreQualityTiers ORDER BY QualityTier DESC NULLS LAST, Genre"):
        print(f"  {R.get('Genre')}: QualityTier={R.get('QualityTier')}")
    return 0


if __name__ == '__main__':
    raise SystemExit(Run())
