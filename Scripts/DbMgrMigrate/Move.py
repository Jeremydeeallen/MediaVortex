# directive: db-monolith-decompose
import argparse
import ast
import csv
import difflib
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE_FILE = REPO_ROOT / "Repositories" / "DatabaseManager.py"
INVENTORY_FILE = Path(__file__).resolve().parent / "inventory.csv"

SCAFFOLD_LINES = [
    "from typing import Any, Dict, List, Optional",
    "from datetime import datetime, timezone",
    "from Services.DatabaseService import DatabaseService",
    "from Services.LoggingService import LoggingService",
    "from Core.Database.DatabaseService import EscapeLikePattern",
    "",
    "",
    "class {ClassName}:",
    "    def __init__(self, DatabaseServiceInstance: Optional[DatabaseService] = None):",
    "        self.DatabaseService = DatabaseServiceInstance or DatabaseService()",
    "",
]


# directive: db-monolith-decompose
def BuildScaffold(ClassName: str) -> str:
    return "\n".join(L.format(ClassName=ClassName) for L in SCAFFOLD_LINES) + "\n"


# directive: db-monolith-decompose
def LoadInventoryRows(AggregateName: str) -> list[dict]:
    if not INVENTORY_FILE.exists():
        raise SystemExit(f"inventory.csv missing; run Inventory.py first: {INVENTORY_FILE}")
    AllRows = []
    with INVENTORY_FILE.open("r", encoding="utf-8", newline="") as Handle:
        for Row in csv.DictReader(Handle):
            if Row["target_aggregate"] == AggregateName:
                AllRows.append(Row)
    return AllRows


# directive: db-monolith-decompose
def ExtractMethodText(SourceLines: list[str], LineStart: int, LineEnd: int) -> str:
    Chunk = SourceLines[LineStart - 1:LineEnd]
    return "".join(Chunk).rstrip("\r\n") + "\n"


# directive: db-monolith-decompose
def BuildTargetContent(ExistingContent: Optional[str], ClassName: str, MethodChunks: list[str]) -> str:
    Body = "\n".join(MethodChunks).rstrip() + "\n"
    if ExistingContent is None:
        return BuildScaffold(ClassName) + "\n" + Body
    Trimmed = ExistingContent.rstrip("\r\n")
    if not MethodChunks:
        return Trimmed + "\n"
    return Trimmed + "\n\n" + Body


# directive: db-monolith-decompose
def AlreadyHasMethod(TargetContent: str, MethodName: str) -> bool:
    try:
        Tree = ast.parse(TargetContent)
    except SyntaxError:
        return False
    for Node in ast.walk(Tree):
        if isinstance(Node, ast.ClassDef):
            for Item in Node.body:
                if isinstance(Item, (ast.FunctionDef, ast.AsyncFunctionDef)) and Item.name == MethodName:
                    return True
    return False


# directive: db-monolith-decompose
def RemoveMethodRangesFromSource(SourceLines: list[str], Ranges: list[tuple[int, int]]) -> list[str]:
    Drop = set()
    for Start, End in Ranges:
        for I in range(Start - 1, End):
            Drop.add(I)
    return [Line for I, Line in enumerate(SourceLines) if I not in Drop]


# directive: db-monolith-decompose
def DeriveClassName(TargetFile: str) -> str:
    return Path(TargetFile.replace("\\", "/")).stem


# directive: db-monolith-decompose
def PrintDiff(LabelA: str, A: str, LabelB: str, B: str) -> None:
    Diff = difflib.unified_diff(
        A.splitlines(keepends=True),
        B.splitlines(keepends=True),
        fromfile=LabelA,
        tofile=LabelB,
    )
    sys.stdout.writelines(Diff)


# directive: db-monolith-decompose
def ResolveLiveMethodRanges(SourcePath: Path, MethodNames: list[str]) -> tuple[dict[str, list[tuple[int, int]]], dict[str, tuple[int, int]]]:
    Tree = ast.parse(SourcePath.read_text(encoding="utf-8"))
    AllRanges: dict[str, list[tuple[int, int]]] = {N: [] for N in MethodNames}
    for Node in ast.walk(Tree):
        if isinstance(Node, ast.ClassDef) and Node.name == "DatabaseManager":
            for Item in Node.body:
                if isinstance(Item, (ast.FunctionDef, ast.AsyncFunctionDef)) and Item.name in AllRanges:
                    End = Item.end_lineno or Item.lineno
                    AllRanges[Item.name].append((Item.lineno, End))
            break
    LastRanges: dict[str, tuple[int, int]] = {}
    for Name, RangeList in AllRanges.items():
        if RangeList:
            LastRanges[Name] = RangeList[-1]
    return AllRanges, LastRanges


# directive: db-monolith-decompose
def MoveAggregate(AggregateName: str, DryRun: bool) -> int:
    AllRows = LoadInventoryRows(AggregateName)
    if not AllRows:
        print(f"No rows for aggregate '{AggregateName}' in inventory.csv", file=sys.stderr)
        return 2
    CleanRows = [R for R in AllRows if R["classification"] == "clean"]
    SkippedRows = [R for R in AllRows if R["classification"] != "clean"]
    if not CleanRows:
        print(f"Aggregate '{AggregateName}' has no clean methods to move", file=sys.stderr)
        for R in SkippedRows:
            print(f"  SKIP {R['classification']}: {R['method_name']}", file=sys.stderr)
        return 2
    UniqueNames = sorted({R["method_name"] for R in CleanRows})
    AllRanges, LastRanges = ResolveLiveMethodRanges(SOURCE_FILE, UniqueNames)
    MissingNames = [N for N in UniqueNames if not AllRanges[N]]
    if MissingNames:
        print(f"  WARN methods in inventory not found in current DatabaseManager.py: {MissingNames}", file=sys.stderr)
    DiscardedTags: list[str] = []
    DiscardedRanges: list[tuple[int, int]] = []
    for Name in UniqueNames:
        Ranges = AllRanges[Name]
        for Older in Ranges[:-1]:
            DiscardedTags.append(f"{Name}@line{Older[0]}")
            DiscardedRanges.append(Older)
    for D in DiscardedTags:
        print(f"  WARN discarded older duplicate def: {D}", file=sys.stderr)
    for R in SkippedRows:
        print(f"  SKIP {R['classification']}: {R['method_name']}", file=sys.stderr)
    TargetFileRel = CleanRows[0]["target_file"]
    TargetFile = REPO_ROOT / TargetFileRel.replace("\\", "/")
    ClassName = DeriveClassName(TargetFileRel)
    SourceText = SOURCE_FILE.read_text(encoding="utf-8")
    SourceLines = SourceText.splitlines(keepends=True)
    Chunks: list[str] = []
    Ranges: list[tuple[int, int]] = []
    TargetExisting = TargetFile.read_text(encoding="utf-8") if TargetFile.exists() else None
    MovedNames: list[str] = []
    AlreadyPresent: list[str] = []
    for Name in UniqueNames:
        if Name not in LastRanges:
            continue
        Range = LastRanges[Name]
        if TargetExisting is not None and AlreadyHasMethod(TargetExisting, Name):
            AlreadyPresent.append(Name)
        else:
            Chunks.append(ExtractMethodText(SourceLines, *Range))
            MovedNames.append(Name)
        Ranges.append(Range)
    Ranges.extend(DiscardedRanges)
    NewSourceLines = RemoveMethodRangesFromSource(SourceLines, Ranges)
    NewSource = "".join(NewSourceLines)
    NewTarget = BuildTargetContent(TargetExisting, ClassName, Chunks)
    if DryRun:
        print(f"--- DRY RUN: aggregate '{AggregateName}' ---")
        print(f"Moved methods (new in target): {MovedNames}")
        print(f"Already present (skipped extraction; still removed from source): {AlreadyPresent}")
        print(f"Discarded older duplicate defs: {DiscardedTags}")
        print()
        PrintDiff(str(SOURCE_FILE.relative_to(REPO_ROOT)), SourceText, str(SOURCE_FILE.relative_to(REPO_ROOT)) + " (after)", NewSource)
        print()
        PrintDiff(
            (str(TargetFile.relative_to(REPO_ROOT)) + " (before)") if TargetExisting is not None else "(new file)",
            TargetExisting or "",
            str(TargetFile.relative_to(REPO_ROOT)) + " (after)",
            NewTarget,
        )
        return 0
    if NewSource == SourceText and TargetExisting is not None and NewTarget == TargetExisting:
        print(f"No-op: aggregate '{AggregateName}' already migrated")
        return 0
    TargetFile.parent.mkdir(parents=True, exist_ok=True)
    TargetFile.write_text(NewTarget, encoding="utf-8")
    SOURCE_FILE.write_text(NewSource, encoding="utf-8")
    print(f"Migrated {len(MovedNames)} new method(s) to {TargetFile.relative_to(REPO_ROOT)}: {MovedNames}")
    if AlreadyPresent:
        print(f"Removed {len(AlreadyPresent)} method(s) from source that were already in target: {AlreadyPresent}")
    if DiscardedTags:
        print(f"Removed {len(DiscardedTags)} older duplicate def(s): {DiscardedTags}")
    return 0


# directive: db-monolith-decompose
def Main() -> int:
    Parser = argparse.ArgumentParser(description="Move clean-classified methods for one aggregate from DatabaseManager.py to its per-aggregate repository file.")
    Parser.add_argument("--aggregate", required=True, help="target aggregate name (from inventory.csv target_aggregate column)")
    Parser.add_argument("--dry-run", action="store_true", help="print unified diff to stdout; do not write")
    Args = Parser.parse_args()
    return MoveAggregate(Args.aggregate, Args.dry_run)


if __name__ == "__main__":
    sys.exit(Main())
