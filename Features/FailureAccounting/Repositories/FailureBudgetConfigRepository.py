from typing import Optional
from Core.Database.BaseRepository import BaseRepository
from Features.FailureAccounting.Models.FailureBudgetConfigModel import FailureBudgetConfigModel


# directive: failure-accounting | # see failure-accounting.C2
class FailureBudgetConfigRepository(BaseRepository):
    """Reads FailureBudgetConfig single-row table fresh on every call -- db-is-authority; no cache."""

    # directive: failure-accounting | # see failure-accounting.C2
    def Get(self) -> FailureBudgetConfigModel:
        """Return the current FailureBudgetConfig row, or defaults if no row exists yet."""
        Rows = self.ExecuteQuery("SELECT MaxEncodeFailures, ResetWindowDays FROM FailureBudgetConfig WHERE Id = 1 LIMIT 1")
        if not Rows:
            return FailureBudgetConfigModel()
        R = Rows[0]
        return FailureBudgetConfigModel(
            MaxEncodeFailures=int(R['MaxEncodeFailures']),
            ResetWindowDays=R['ResetWindowDays'] if R.get('ResetWindowDays') is not None else None,
        )

    # directive: failure-accounting | # see failure-accounting.C2
    def Update(self, MaxEncodeFailures: Optional[int] = None, ResetWindowDays: Optional[int] = None) -> None:
        """Operator-facing setter; partial update of non-None fields."""
        if MaxEncodeFailures is None and ResetWindowDays is None:
            return
        Sets = []
        Params = []
        if MaxEncodeFailures is not None:
            Sets.append("MaxEncodeFailures = %s")
            Params.append(int(MaxEncodeFailures))
        if ResetWindowDays is not None:
            Sets.append("ResetWindowDays = %s")
            Params.append(int(ResetWindowDays))
        Sets.append("LastUpdated = NOW()")
        self.ExecuteNonQuery(
            "UPDATE FailureBudgetConfig SET " + ", ".join(Sets) + " WHERE Id = 1",
            tuple(Params),
        )
