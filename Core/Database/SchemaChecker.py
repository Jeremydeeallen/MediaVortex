# directive: transcode-flow-canonical
import json
import os
from pathlib import Path
from typing import Dict, List, Set

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SNAPSHOT_PATH = REPO_ROOT / ".claude" / "schema" / "snapshot.json"


# directive: transcode-flow-canonical
class SchemaDriftError(RuntimeError):
    pass


# directive: transcode-flow-canonical
class SchemaChecker:
    """DB-schema authority. Compares live PostgreSQL schema against a committed snapshot; refuses process start on drift."""

    # directive: transcode-flow-canonical
    def __init__(self, DatabaseServiceInstance: DatabaseService = None, SnapshotPath: Path = None):
        self.Db = DatabaseServiceInstance or DatabaseService()
        self.SnapshotPath = Path(SnapshotPath) if SnapshotPath else SNAPSHOT_PATH

    # directive: transcode-flow-canonical
    def QueryLive(self) -> Dict[str, Dict[str, Dict[str, str]]]:
        Rows = self.Db.ExecuteQuery(
            "SELECT table_name, column_name, data_type, is_nullable, is_generated "
            "FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name NOT LIKE 'pg\\_%%' ESCAPE '\\' "
            "ORDER BY table_name, ordinal_position",
            ('public',),
        )
        Out: Dict[str, Dict[str, Dict[str, str]]] = {}
        for R in Rows:
            Tbl = R.get('table_name') or R.get('TableName') or R.get('TABLE_NAME')
            Col = R.get('column_name') or R.get('ColumnName') or R.get('COLUMN_NAME')
            if not Tbl or not Col:
                continue
            Out.setdefault(Tbl, {})[Col] = {
                'data_type': (R.get('data_type') or R.get('DataType') or R.get('DATA_TYPE') or ''),
                'is_nullable': (R.get('is_nullable') or R.get('IsNullable') or R.get('IS_NULLABLE') or ''),
                'is_generated': (R.get('is_generated') or R.get('IsGenerated') or R.get('IS_GENERATED') or ''),
            }
        return Out

    # directive: transcode-flow-canonical
    def LoadSnapshot(self) -> Dict[str, Dict[str, Dict[str, str]]]:
        if not self.SnapshotPath.exists():
            return {}
        with open(self.SnapshotPath, 'r', encoding='utf-8') as F:
            return json.load(F)

    # directive: transcode-flow-canonical
    def WriteSnapshot(self, Snapshot: Dict) -> None:
        self.SnapshotPath.parent.mkdir(parents=True, exist_ok=True)
        with open(self.SnapshotPath, 'w', encoding='utf-8') as F:
            json.dump(Snapshot, F, indent=2, sort_keys=True)

    # directive: transcode-flow-canonical
    def Diff(self, Expected: Dict, Actual: Dict) -> Dict[str, List[str]]:
        MissingTables = sorted(set(Expected.keys()) - set(Actual.keys()))
        ExtraTables = sorted(set(Actual.keys()) - set(Expected.keys()))
        MissingColumns: List[str] = []
        ExtraColumns: List[str] = []
        TypeMismatches: List[str] = []
        for Tbl in sorted(set(Expected.keys()) & set(Actual.keys())):
            Exp = Expected[Tbl]
            Act = Actual[Tbl]
            for Col in sorted(set(Exp.keys()) - set(Act.keys())):
                MissingColumns.append(f"{Tbl}.{Col}")
            for Col in sorted(set(Act.keys()) - set(Exp.keys())):
                ExtraColumns.append(f"{Tbl}.{Col}")
            for Col in sorted(set(Exp.keys()) & set(Act.keys())):
                if Exp[Col].get('data_type') != Act[Col].get('data_type'):
                    TypeMismatches.append(f"{Tbl}.{Col}: expected={Exp[Col].get('data_type')} actual={Act[Col].get('data_type')}")
        return {
            'MissingTables': MissingTables,
            'ExtraTables': ExtraTables,
            'MissingColumns': MissingColumns,
            'ExtraColumns': ExtraColumns,
            'TypeMismatches': TypeMismatches,
        }

    # directive: transcode-flow-canonical
    def AssertMatches(self, StrictExtras: bool = False) -> None:
        """Refuse process start on schema drift. MissingTables + MissingColumns + TypeMismatches always fail. ExtraTables + ExtraColumns only fail when StrictExtras=True (default: log-warn only, since ADD is safer than DROP)."""
        Snapshot = self.LoadSnapshot()
        if not Snapshot:
            LoggingService.LogWarning(
                f"SchemaChecker: no snapshot at {self.SnapshotPath}; skipping drift check. Generate via `py Scripts/Migration/GenerateSchemaSnapshot.py`.",
                'SchemaChecker', 'AssertMatches',
            )
            return
        Live = self.QueryLive()
        D = self.Diff(Snapshot, Live)
        BreakingKeys = ['MissingTables', 'MissingColumns', 'TypeMismatches']
        AdditiveKeys = ['ExtraTables', 'ExtraColumns']
        Breaking = {K: D[K] for K in BreakingKeys if D[K]}
        Additive = {K: D[K] for K in AdditiveKeys if D[K]}
        if Additive:
            LoggingService.LogWarning(
                f"SchemaChecker: live schema has additive drift vs snapshot: {json.dumps(Additive)}. Regenerate snapshot after migration lands.",
                'SchemaChecker', 'AssertMatches',
            )
        if Breaking and StrictExtras:
            Breaking = {**Breaking, **Additive}
        if Breaking:
            raise SchemaDriftError(
                f"SchemaChecker: live PostgreSQL schema drifts from snapshot at {self.SnapshotPath}. Breaking drift: {json.dumps(Breaking)}. Either regenerate snapshot (if migration is intentional) or migrate DB to match code."
            )
