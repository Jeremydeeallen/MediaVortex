from typing import Optional, List
from Core.Database.BaseRepository import BaseRepository
from Core.Logging.LoggingService import LoggingService
from Features.TranscodeQueue.Models.CrfBitrateEstimateModel import CrfBitrateEstimateModel


class CrfBitrateEstimateRepository(BaseRepository):
    """CRUD for CrfBitrateEstimates. No caching -- per-call DB read.

    Used by the marginal-savings gate to estimate output size for CRF-only
    profiles (VideoBitrateKbps=0). Editable from the /settings page.
    """

    def _MapRow(self, Row) -> CrfBitrateEstimateModel:
        return CrfBitrateEstimateModel(
            Id=Row['Id'],
            Codec=Row['Codec'],
            Resolution=Row['Resolution'],
            Crf=Row['Crf'],
            EstimatedKbps=Row['EstimatedKbps'],
            LastUpdated=Row.get('LastUpdated'),
            Source=Row.get('Source'),
        )

    def GetEstimatedKbps(self, Codec: str, Resolution: str, Crf: int) -> Optional[int]:
        """Look up the estimated total kbps for a (Codec, Resolution, CRF) triple.

        Returns None when no row matches -- caller decides fail-open vs fail-closed
        per QueueAdmissionConfig.MissingEstimatePolicy.
        """
        try:
            Rows = self.ExecuteQuery(
                """
                SELECT EstimatedKbps FROM CrfBitrateEstimates
                WHERE LOWER(Codec) = LOWER(%s) AND Resolution = %s AND Crf = %s
                """,
                (Codec, Resolution, Crf),
            )
            return Rows[0]['EstimatedKbps'] if Rows else None
        except Exception as Ex:
            LoggingService.LogException(
                f"GetEstimatedKbps failed for ({Codec}, {Resolution}, CRF={Crf})",
                Ex, "CrfBitrateEstimateRepository", "GetEstimatedKbps",
            )
            return None

    def GetAll(self) -> List[CrfBitrateEstimateModel]:
        try:
            Rows = self.ExecuteQuery(
                """
                SELECT Id, Codec, Resolution, Crf, EstimatedKbps, LastUpdated, Source
                FROM CrfBitrateEstimates
                ORDER BY Codec, Resolution, Crf
                """
            )
            return [self._MapRow(R) for R in Rows]
        except Exception as Ex:
            LoggingService.LogException(
                "GetAll failed", Ex, "CrfBitrateEstimateRepository", "GetAll",
            )
            return []

    def Upsert(self, Model: CrfBitrateEstimateModel) -> bool:
        """Insert-or-update on (Codec, Resolution, Crf). Stamps LastUpdated=NOW()."""
        try:
            self.ExecuteNonQuery(
                """
                INSERT INTO CrfBitrateEstimates
                    (Codec, Resolution, Crf, EstimatedKbps, Source, LastUpdated)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (Codec, Resolution, Crf)
                DO UPDATE SET
                    EstimatedKbps = EXCLUDED.EstimatedKbps,
                    Source = EXCLUDED.Source,
                    LastUpdated = NOW()
                """,
                (Model.Codec, Model.Resolution, Model.Crf,
                 Model.EstimatedKbps, Model.Source or 'OperatorOverride'),
            )
            return True
        except Exception as Ex:
            LoggingService.LogException(
                f"Upsert failed for ({Model.Codec}, {Model.Resolution}, CRF={Model.Crf})",
                Ex, "CrfBitrateEstimateRepository", "Upsert",
            )
            return False
