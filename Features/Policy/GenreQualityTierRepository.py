from typing import Dict, List, Optional

from Core.Database.DatabaseService import DatabaseService


# directive: movies-video-rule | # see transcode.ST4
class GenreQualityTierRepository:

    # directive: movies-video-rule
    def __init__(self, Db: Optional[DatabaseService] = None):
        self.Db = Db or DatabaseService()

    # directive: movies-video-rule | # see transcode.ST4
    def GetTiers(self, Genres: List[str]) -> Dict[str, Optional[int]]:
        if not Genres:
            return {}
        Rows = self.Db.ExecuteQuery(
            "SELECT Genre, QualityTier FROM GenreQualityTiers WHERE Genre = ANY(%s)",
            (list(Genres),),
        )
        return {R.get('Genre'): (int(R.get('QualityTier')) if R.get('QualityTier') is not None else None) for R in Rows}

    # directive: profile-row-lookup | # see profile-tier-ladder.S4
    def GetClasses(self, Genres: List[str]) -> Dict[str, Optional[str]]:
        if not Genres:
            return {}
        Rows = self.Db.ExecuteQuery(
            "SELECT Genre, ContentClass FROM GenreQualityTiers WHERE Genre = ANY(%s)",
            (list(Genres),),
        )
        return {R.get('Genre'): R.get('ContentClass') for R in Rows}

    # directive: movies-video-rule, profile-row-lookup | # see video-encoding.C4, profile-tier-ladder.S4
    def ListGenreTiers(self) -> List[dict]:
        Rows = self.Db.ExecuteQuery(
            "SELECT g.Genre, g.QualityTier, g.ContentClass, "
            "  (SELECT COUNT(*) FROM MediaFiles mf WHERE mf.Genres IS NOT NULL "
            "     AND g.Genre = ANY(string_to_array(mf.Genres, ','))) AS FileCount "
            "FROM GenreQualityTiers g ORDER BY g.Genre"
        )
        return [
            {
                'Genre': R.get('Genre'),
                'QualityTier': int(R.get('QualityTier')) if R.get('QualityTier') is not None else None,
                'ContentClass': R.get('ContentClass'),
                'FileCount': int(R.get('FileCount')),
            }
            for R in Rows
        ]

    # directive: profile-row-lookup | # see profile-tier-ladder.S4
    def SetContentClass(self, Genre: str, ContentClass: Optional[str]) -> int:
        if ContentClass is not None and ContentClass not in ('live_action', 'animation'):
            raise ValueError(f"ContentClass must be live_action, animation or None, got {ContentClass!r}")
        return int(self.Db.ExecuteNonQuery(
            "UPDATE GenreQualityTiers SET ContentClass = %s, LastUpdated = NOW() WHERE Genre = %s",
            (ContentClass, Genre),
        ) or 0)

    # directive: movies-video-rule | # see video-encoding.C4
    def SetTier(self, Genre: str, Tier: Optional[int]) -> int:
        if Tier is not None and not (1 <= int(Tier) <= 5):
            raise ValueError(f"QualityTier must be 1-5 or None, got {Tier!r}")
        return int(self.Db.ExecuteNonQuery(
            "UPDATE GenreQualityTiers SET QualityTier = %s, LastUpdated = NOW() WHERE Genre = %s",
            (int(Tier) if Tier is not None else None, Genre),
        ) or 0)

    # directive: movies-video-rule | # see ingest.ST3
    def RegisterGenres(self, Genres: List[str]) -> None:
        for Genre in Genres:
            self.Db.ExecuteNonQuery(
                "INSERT INTO GenreQualityTiers (Genre) VALUES (%s) ON CONFLICT (Genre) DO NOTHING",
                (Genre,),
            )
