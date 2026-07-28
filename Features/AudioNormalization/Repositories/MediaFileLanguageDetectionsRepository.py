from typing import Dict, Optional

from Core.Database.DatabaseService import DatabaseService


# directive: audio-language-detection
class MediaFileLanguageDetectionsRepository:

    def __init__(self, Db: Optional[DatabaseService] = None):
        self._Db = Db or DatabaseService()

    def Insert(self, MediaFileId: int, StreamIndex: int, Language: str, Confidence: float, BackendName: str) -> None:
        self._Db.ExecuteNonQuery(
            "INSERT INTO MediaFileLanguageDetections "
            "(MediaFileId, StreamIndex, Language, Confidence, BackendName) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (MediaFileId, StreamIndex) DO UPDATE SET "
            "Language = EXCLUDED.Language, Confidence = EXCLUDED.Confidence, "
            "BackendName = EXCLUDED.BackendName, DetectedAt = NOW()",
            (int(MediaFileId), int(StreamIndex), str(Language).lower().strip(), float(Confidence), str(BackendName)),
        )

    def ExistsForMediaFile(self, MediaFileId: int) -> bool:
        Rows = self._Db.ExecuteQuery(
            "SELECT 1 FROM MediaFileLanguageDetections WHERE MediaFileId = %s LIMIT 1",
            (int(MediaFileId),),
        )
        return bool(Rows)

    def GetDetectionsMap(self, MediaFileId: int) -> Dict[str, dict]:
        Rows = self._Db.ExecuteQuery(
            "SELECT StreamIndex, Language, Confidence FROM MediaFileLanguageDetections "
            "WHERE MediaFileId = %s ORDER BY StreamIndex",
            (int(MediaFileId),),
        )
        Out = {}
        for R in (Rows or []):
            Idx = int(R.get('StreamIndex') if 'StreamIndex' in R else R.get('streamindex'))
            Lang = R.get('Language') or R.get('language')
            Conf = R.get('Confidence') if 'Confidence' in R else R.get('confidence')
            Out[str(Idx)] = {'Language': str(Lang).lower(), 'Confidence': float(Conf)}
        return Out

    def ClearForMediaFile(self, MediaFileId: int) -> int:
        self._Db.ExecuteNonQuery(
            "DELETE FROM MediaFileLanguageDetections WHERE MediaFileId = %s",
            (int(MediaFileId),),
        )
        return 0
