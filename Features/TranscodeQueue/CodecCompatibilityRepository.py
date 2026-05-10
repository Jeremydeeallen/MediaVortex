from typing import List, Set
from Core.Database.BaseRepository import BaseRepository
from Core.Logging.LoggingService import LoggingService
from Features.TranscodeQueue.Models.CodecCompatibilityModel import CodecCompatibilityModel


class CodecCompatibilityRepository(BaseRepository):
    """CRUD for CodecCompatibility. No caching -- per-call DB read.

    Replaces hardcoded class constants (`COMPATIBLE_CONTAINERS`,
    `ACCEPTABLE_VIDEO_CODECS`, `MP4_COMPATIBLE_AUDIO_CODECS`). Editable from
    the /settings page.
    """

    VALID_KINDS = frozenset({'Container', 'VideoCodec', 'AudioCodecMp4'})

    def _MapRow(self, Row) -> CodecCompatibilityModel:
        return CodecCompatibilityModel(
            Id=Row['Id'],
            Kind=Row['Kind'],
            Name=Row['Name'],
            IsAcceptable=bool(Row['IsAcceptable']),
            Description=Row.get('Description'),
            LastUpdated=Row.get('LastUpdated'),
            Source=Row.get('Source'),
        )

    def GetAcceptableSet(self, Kind: str) -> Set[str]:
        """Return the set of Names where IsAcceptable=true for the given Kind.

        Empty set when the Kind has no rows or on DB error -- callers should
        treat empty as "no compatibility data, fail safe" depending on their
        rule. Names are returned lowercased for case-insensitive matching.
        """
        if Kind not in self.VALID_KINDS:
            LoggingService.LogWarning(
                f"GetAcceptableSet called with unknown Kind={Kind!r}; valid: {self.VALID_KINDS}",
                "CodecCompatibilityRepository", "GetAcceptableSet",
            )
            return set()
        try:
            Rows = self.ExecuteQuery(
                """
                SELECT LOWER(Name) AS name FROM CodecCompatibility
                WHERE Kind = %s AND IsAcceptable = true
                """,
                (Kind,),
            )
            return {R['name'] for R in Rows}
        except Exception as Ex:
            LoggingService.LogException(
                f"GetAcceptableSet failed for Kind={Kind}",
                Ex, "CodecCompatibilityRepository", "GetAcceptableSet",
            )
            return set()

    def GetAll(self) -> List[CodecCompatibilityModel]:
        try:
            Rows = self.ExecuteQuery(
                """
                SELECT Id, Kind, Name, IsAcceptable, Description, LastUpdated, Source
                FROM CodecCompatibility
                ORDER BY Kind, Name
                """
            )
            return [self._MapRow(R) for R in Rows]
        except Exception as Ex:
            LoggingService.LogException(
                "GetAll failed", Ex, "CodecCompatibilityRepository", "GetAll",
            )
            return []

    def Upsert(self, Model: CodecCompatibilityModel) -> bool:
        """Insert-or-update on (Kind, Name). Stamps LastUpdated=NOW()."""
        if Model.Kind not in self.VALID_KINDS:
            LoggingService.LogError(
                f"Upsert rejected: Kind={Model.Kind!r} not in {self.VALID_KINDS}",
                "CodecCompatibilityRepository", "Upsert",
            )
            return False
        try:
            self.ExecuteNonQuery(
                """
                INSERT INTO CodecCompatibility
                    (Kind, Name, IsAcceptable, Description, Source, LastUpdated)
                VALUES (%s, LOWER(%s), %s, %s, %s, NOW())
                ON CONFLICT (Kind, Name)
                DO UPDATE SET
                    IsAcceptable = EXCLUDED.IsAcceptable,
                    Description = EXCLUDED.Description,
                    Source = EXCLUDED.Source,
                    LastUpdated = NOW()
                """,
                (Model.Kind, Model.Name, Model.IsAcceptable,
                 Model.Description, Model.Source or 'OperatorOverride'),
            )
            return True
        except Exception as Ex:
            LoggingService.LogException(
                f"Upsert failed for ({Model.Kind}, {Model.Name})",
                Ex, "CodecCompatibilityRepository", "Upsert",
            )
            return False
