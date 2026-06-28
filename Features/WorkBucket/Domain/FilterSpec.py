from dataclasses import dataclass, field
from typing import Tuple


@dataclass(frozen=True)
# directive: work-transcode-unified
class FilterSpec:
    # see work-bucket.C6
    StorageRootIds: Tuple[int, ...] = field(default_factory=tuple)
    SearchTerm: str = ''

    # directive: work-transcode-unified
    def ToSqlFragments(self) -> Tuple[str, Tuple]:
        # see work-bucket.C6
        from Core.Database.DatabaseService import EscapeLikePattern
        Clauses = []
        Params = []
        if self.StorageRootIds:
            Placeholders = ','.join(['%s'] * len(self.StorageRootIds))
            Clauses.append(f"mf.StorageRootId IN ({Placeholders})")
            Params.extend(self.StorageRootIds)
        if self.SearchTerm.strip():
            Clauses.append("split_part(mf.RelativePath, '/', 1) ILIKE %s ESCAPE '!'")
            Params.append('%' + EscapeLikePattern(self.SearchTerm.strip()) + '%')
        if not Clauses:
            return ('', ())
        return ('AND ' + ' AND '.join(Clauses), tuple(Params))
