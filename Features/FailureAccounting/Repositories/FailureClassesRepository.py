# directive: bug-0095-failure-classification | # see failure-accounting.C10
import re
from typing import List, Optional
from Core.Database.BaseRepository import BaseRepository


# directive: bug-0095-failure-classification | # see failure-accounting.C10
class FailureClassRow:

    def __init__(self, ClassName: str, Priority: int, ErrorPattern: str, Terminal: bool, Remediation: str):
        self.ClassName = ClassName
        self.Priority = Priority
        self.ErrorPattern = ErrorPattern
        self.Terminal = Terminal
        self.Remediation = Remediation


# directive: bug-0095-failure-classification | # see failure-accounting.C10
class FailureClassesRepository(BaseRepository):
    """Reads FailureClasses fresh on every call -- db-is-authority; no cache. Operator changes via /settings observed by next classify."""

    # directive: bug-0095-failure-classification | # see failure-accounting.C10
    def ListOrderedByPriority(self) -> List[FailureClassRow]:
        Rows = self.ExecuteQuery(
            "SELECT ClassName, Priority, ErrorPattern, Terminal, Remediation "
            "FROM FailureClasses ORDER BY Priority ASC"
        )
        return [
            FailureClassRow(
                ClassName=R['ClassName'],
                Priority=int(R['Priority']),
                ErrorPattern=R['ErrorPattern'],
                Terminal=bool(R['Terminal']),
                Remediation=R['Remediation'],
            )
            for R in (Rows or [])
        ]

    # directive: bug-0095-failure-classification | # see failure-accounting.C10
    def Get(self, ClassName: str) -> Optional[FailureClassRow]:
        Rows = self.ExecuteQuery(
            "SELECT ClassName, Priority, ErrorPattern, Terminal, Remediation "
            "FROM FailureClasses WHERE ClassName = %s LIMIT 1",
            (ClassName,),
        )
        if not Rows:
            return None
        R = Rows[0]
        return FailureClassRow(
            ClassName=R['ClassName'],
            Priority=int(R['Priority']),
            ErrorPattern=R['ErrorPattern'],
            Terminal=bool(R['Terminal']),
            Remediation=R['Remediation'],
        )

    # directive: bug-0095-failure-classification | # see failure-accounting.C10
    def Upsert(self, ClassName: str, Priority: int, ErrorPattern: str, Terminal: bool, Remediation: str) -> None:
        re.compile(ErrorPattern)
        self.ExecuteNonQuery(
            "INSERT INTO FailureClasses (ClassName, Priority, ErrorPattern, Terminal, Remediation, UpdatedAt) "
            "VALUES (%s, %s, %s, %s, %s, NOW()) "
            "ON CONFLICT (ClassName) DO UPDATE SET "
            "  Priority = EXCLUDED.Priority, "
            "  ErrorPattern = EXCLUDED.ErrorPattern, "
            "  Terminal = EXCLUDED.Terminal, "
            "  Remediation = EXCLUDED.Remediation, "
            "  UpdatedAt = NOW()",
            (ClassName, int(Priority), ErrorPattern, bool(Terminal), Remediation),
        )

    # directive: bug-0095-failure-classification | # see failure-accounting.C10
    def Delete(self, ClassName: str) -> None:
        if ClassName == 'unclassified':
            raise ValueError("cannot delete the 'unclassified' catch-all rule")
        self.ExecuteNonQuery(
            "DELETE FROM FailureClasses WHERE ClassName = %s",
            (ClassName,),
        )

    # directive: bug-0095-failure-classification | # see failure-accounting.C10
    def ClassifyErrorMessage(self, ErrorMessage: Optional[str]) -> str:
        """First-match-wins by Priority ASC via SQL regex (POSIX). Returns 'unclassified' catch-all on no match."""
        if not ErrorMessage:
            return 'unclassified'
        Rows = self.ExecuteQuery(
            "SELECT ClassName FROM FailureClasses "
            "WHERE %s ~* ErrorPattern "
            "ORDER BY Priority ASC LIMIT 1",
            (ErrorMessage,),
        )
        if not Rows:
            return 'unclassified'
        return Rows[0]['ClassName']
