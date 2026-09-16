# directive: bug-0095-failure-classification | # see failure-accounting.C10
from typing import Optional
from Core.Logging.LoggingService import LoggingService
from Features.FailureAccounting.Repositories.FailureClassesRepository import FailureClassesRepository


# directive: bug-0095-failure-classification | # see failure-accounting.C10
class FailureClassifier:
    """Classifies TranscodeAttempts failure ErrorMessage strings into a FailureClasses.ClassName. First-match-wins by Priority ASC. Reads DB fresh per call (db-is-authority)."""

    # directive: bug-0095-failure-classification | # see failure-accounting.C10
    def __init__(self, Repo: Optional[FailureClassesRepository] = None):
        self._Repo = Repo or FailureClassesRepository()

    # directive: bug-0095-failure-classification | # see failure-accounting.C10
    def Classify(self, ErrorMessage: Optional[str]) -> str:
        ClassName = self._Repo.ClassifyErrorMessage(ErrorMessage)
        LoggingService.LogInfo(
            f"classified failure as {ClassName}",
            "FailureClassifier", "Classify",
        )
        return ClassName
