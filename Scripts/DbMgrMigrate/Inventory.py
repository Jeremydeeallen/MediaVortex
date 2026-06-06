# directive: db-monolith-decompose
import ast
import csv
import json
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE_FILE = REPO_ROOT / "Repositories" / "DatabaseManager.py"
AGGREGATES_FILE = REPO_ROOT / ".claude" / "standards" / "database-manager-aggregates.json"
OUTPUT_FILE = Path(__file__).resolve().parent / "inventory.csv"

EXCLUDE_DIRS = {"venv", ".git", "__pycache__", "node_modules", ".claude", ".github", "Scripts"}


# directive: db-monolith-decompose
def LoadAggregateMap() -> list[dict]:
    Data = json.loads(AGGREGATES_FILE.read_text(encoding="utf-8"))
    Prefixes = [P for P in Data.get("prefixes", []) if "match" in P and "target" in P]
    return sorted(Prefixes, key=lambda P: -len(P["match"]))


# directive: db-monolith-decompose
def DeriveAggregate(TargetPath: str) -> str:
    Stem = Path(TargetPath.replace("\\", "/")).stem
    if Stem.endswith("Repository"):
        return Stem[: -len("Repository")]
    return Stem


# directive: db-monolith-decompose
def MatchPrefix(MethodName: str, SortedPrefixes: list[dict]) -> Optional[dict]:
    for Entry in SortedPrefixes:
        if MethodName.startswith(Entry["match"]):
            return Entry
    return None


# directive: db-monolith-decompose
def ExtractDatabaseManagerMethods(SourcePath: Path) -> list[ast.FunctionDef]:
    Tree = ast.parse(SourcePath.read_text(encoding="utf-8"))
    Methods: list[ast.FunctionDef] = []
    for Node in ast.walk(Tree):
        if isinstance(Node, ast.ClassDef) and Node.name == "DatabaseManager":
            for Item in Node.body:
                if isinstance(Item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    Methods.append(Item)
            break
    return Methods


# directive: db-monolith-decompose
def FindSelfCallNames(Method: ast.FunctionDef) -> set[str]:
    Names: set[str] = set()
    for Node in ast.walk(Method):
        if isinstance(Node, ast.Call) and isinstance(Node.func, ast.Attribute):
            Value = Node.func.value
            if isinstance(Value, ast.Name) and Value.id == "self":
                Names.add(Node.func.attr)
    return Names


# directive: db-monolith-decompose
def ClassifyMethod(Method: ast.FunctionDef, SortedPrefixes: list[dict]) -> tuple[str, str, str]:
    Match = MatchPrefix(Method.name, SortedPrefixes)
    if Match is None:
        return ("", "", "unmapped")
    OwnAggregate = DeriveAggregate(Match["target"])
    for CalleeName in FindSelfCallNames(Method):
        if CalleeName == Method.name:
            continue
        CalleeMatch = MatchPrefix(CalleeName, SortedPrefixes)
        if CalleeMatch is None:
            continue
        CalleeAggregate = DeriveAggregate(CalleeMatch["target"])
        if CalleeAggregate != OwnAggregate:
            return (OwnAggregate, Match["target"], "cross-aggregate")
    return (OwnAggregate, Match["target"], "clean")


# directive: db-monolith-decompose
def IterProductionPythonFiles(Root: Path):
    for Candidate in Root.rglob("*.py"):
        Skip = False
        for Part in Candidate.relative_to(Root).parts[:-1]:
            if Part in EXCLUDE_DIRS:
                Skip = True
                break
        if not Skip:
            yield Candidate


# directive: db-monolith-decompose
def CountCallers(MethodNames: list[str], Root: Path) -> dict[str, int]:
    Counts: dict[str, int] = {Name: 0 for Name in MethodNames}
    Needles = {Name: f"self.DatabaseManager.{Name}(" for Name in MethodNames}
    for File in IterProductionPythonFiles(Root):
        if File.resolve() == SOURCE_FILE.resolve():
            continue
        try:
            Text = File.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for Name, Needle in Needles.items():
            if Needle in Text:
                Counts[Name] += Text.count(Needle)
    return Counts


# directive: db-monolith-decompose
def BuildInventoryRows() -> list[dict]:
    SortedPrefixes = LoadAggregateMap()
    Methods = ExtractDatabaseManagerMethods(SOURCE_FILE)
    MethodNames = [M.name for M in Methods]
    CallerCounts = CountCallers(MethodNames, REPO_ROOT)
    Rows: list[dict] = []
    for Method in Methods:
        Aggregate, TargetFile, Classification = ClassifyMethod(Method, SortedPrefixes)
        EndLine = Method.end_lineno or Method.lineno
        Rows.append({
            "method_name": Method.name,
            "target_aggregate": Aggregate,
            "target_file": TargetFile,
            "line_start": Method.lineno,
            "line_end": EndLine,
            "body_lines": EndLine - Method.lineno + 1,
            "caller_count": CallerCounts.get(Method.name, 0),
            "classification": Classification,
        })
    Rows.sort(key=lambda R: (R["target_aggregate"], R["method_name"]))
    return Rows


# directive: db-monolith-decompose
def WriteCsv(Rows: list[dict], OutputPath: Path) -> None:
    Columns = ["method_name", "target_aggregate", "target_file", "line_start",
               "line_end", "body_lines", "caller_count", "classification"]
    with OutputPath.open("w", encoding="utf-8", newline="") as Handle:
        Writer = csv.DictWriter(Handle, fieldnames=Columns)
        Writer.writeheader()
        for Row in Rows:
            Writer.writerow(Row)


# directive: db-monolith-decompose
def PrintSummary(Rows: list[dict]) -> None:
    ByAggregate: dict[str, dict[str, int]] = {}
    for Row in Rows:
        Agg = Row["target_aggregate"] or "<unmapped>"
        Entry = ByAggregate.setdefault(Agg, {"clean": 0, "cross-aggregate": 0, "unmapped": 0, "total": 0})
        Entry[Row["classification"]] += 1
        Entry["total"] += 1
    print(f"{'Aggregate':<35}{'Clean':>8}{'Cross':>8}{'Unmap':>8}{'Total':>8}")
    print("-" * 67)
    for Agg in sorted(ByAggregate.keys()):
        E = ByAggregate[Agg]
        print(f"{Agg:<35}{E['clean']:>8}{E['cross-aggregate']:>8}{E['unmapped']:>8}{E['total']:>8}")
    Totals = {K: sum(E[K] for E in ByAggregate.values()) for K in ("clean", "cross-aggregate", "unmapped", "total")}
    print("-" * 67)
    print(f"{'TOTAL':<35}{Totals['clean']:>8}{Totals['cross-aggregate']:>8}{Totals['unmapped']:>8}{Totals['total']:>8}")


# directive: db-monolith-decompose
def Main() -> int:
    if not SOURCE_FILE.exists():
        print(f"ERROR: source not found: {SOURCE_FILE}", file=sys.stderr)
        return 2
    if not AGGREGATES_FILE.exists():
        print(f"ERROR: aggregates map not found: {AGGREGATES_FILE}", file=sys.stderr)
        return 2
    Rows = BuildInventoryRows()
    WriteCsv(Rows, OUTPUT_FILE)
    print(f"Wrote {len(Rows)} rows to {OUTPUT_FILE}")
    PrintSummary(Rows)
    return 0


if __name__ == "__main__":
    sys.exit(Main())
