# directive: path-migration-rehearsal | # see path.C11
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path as PyPath

sys.path.append(str(PyPath(__file__).parent.parent))

from Core.Database.DatabaseService import DatabaseService
from Core.Path.Path import Path, PathError


_AUDIT_TABLES = [
    ("MediaFiles", "Id", "FilePath", "StorageRootId", "RelativePath"),
    ("MediaFilesArchive", "Id", "FilePath", "StorageRootId", "RelativePath"),
    ("TranscodeQueue", "Id", "FilePath", "StorageRootId", "RelativePath"),
    ("TranscodeAttempts", "Id", "FilePath", "StorageRootId", "RelativePath"),
    ("ShowSettings", "Id", "ShowFolder", "StorageRootId", "RelativePath"),
]


_TFP_COLUMNS = [
    ("OriginalPath", None, None),
    ("LocalSourcePath", "SourceStorageRootId", "SourceRelativePath"),
    ("LocalOutputPath", "OutputStorageRootId", "OutputRelativePath"),
]


# directive: path-migration-rehearsal | # see path.S6
def _LoadStorageRoots(Db) -> list:
    """Return [(Id, CanonicalPrefix), ...] sorted by len(CanonicalPrefix) DESC for longest-prefix-wins matching."""
    Rows = Db.ExecuteQuery(
        "SELECT Id, CanonicalPrefix FROM StorageRoots ORDER BY length(CanonicalPrefix) DESC"
    )
    return [{"Id": R["id"], "CanonicalPrefix": R["canonicalprefix"]} for R in Rows]


# directive: path-migration-rehearsal | # see path.C4
def _CategorizeAttempt(LegacyValue: str, StorageRoots: list):
    """Attempt FromLegacyString; return (category, path_or_none, error_message_or_none)."""
    if LegacyValue is None:
        return ("null", None, None)
    if LegacyValue == "":
        return ("validation_rejected", None, "empty string")
    try:
        Parsed = Path.FromLegacyString(LegacyValue, StorageRoots)
        return ("parsed", Parsed, None)
    except PathError as Exc:
        Msg = str(Exc)
        if "no matching prefix" in Msg:
            return ("no_prefix_match", None, Msg)
        return ("validation_rejected", None, Msg)
    except Exception as Exc:
        return ("unexpected_error", None, f"{type(Exc).__name__}: {Exc}")


# directive: path-migration-rehearsal | # see path.C7
def _AuditTable(Db, Table: str, IdCol: str, LegacyCol: str, SidCol: str, RelCol: str, StorageRoots: list) -> dict:
    """Walk one table's legacy column; categorize each row; cross-check against stored typed pair."""
    Sql = f"SELECT {IdCol} AS rowid, {LegacyCol} AS legacy, {SidCol} AS storagerootid, {RelCol} AS relativepath FROM {Table}"
    Rows = Db.ExecuteQuery(Sql)
    Counts = Counter()
    Samples = {"no_prefix_match": [], "validation_rejected": [], "unexpected_error": [], "cross_check_drift": []}
    for Row in Rows:
        RowId = Row.get("rowid")
        Legacy = Row.get("legacy")
        StoredSid = Row.get("storagerootid")
        StoredRel = Row.get("relativepath")
        Category, Parsed, ErrMsg = _CategorizeAttempt(Legacy, StorageRoots)
        Counts[Category] += 1
        if Category in ("no_prefix_match", "validation_rejected", "unexpected_error") and len(Samples[Category]) < 10:
            Samples[Category].append({"id": RowId, "legacy": Legacy, "error": ErrMsg})
        if Category == "parsed" and StoredSid is not None and StoredRel is not None:
            if Parsed.StorageRootId != StoredSid or Parsed.RelativePath != StoredRel:
                CaseOnly = (
                    Parsed.StorageRootId == StoredSid
                    and Parsed.RelativePath.lower() == StoredRel.lower()
                )
                DriftKey = "cross_check_drift_case_only" if CaseOnly else "cross_check_drift_content"
                Counts[DriftKey] += 1
                if DriftKey not in Samples:
                    Samples[DriftKey] = []
                if len(Samples[DriftKey]) < 10:
                    Samples[DriftKey].append({
                        "id": RowId,
                        "legacy": Legacy,
                        "reparsed": f"({Parsed.StorageRootId}, {Parsed.RelativePath!r})",
                        "stored": f"({StoredSid}, {StoredRel!r})",
                    })
    return {"counts": dict(Counts), "samples": Samples, "total": len(Rows)}


# directive: path-migration-rehearsal | # see path.C3
def _AuditTemporaryFilePaths(Db, StorageRoots: list) -> dict:
    """Walk each TemporaryFilePaths legacy column independently."""
    Rows = Db.ExecuteQuery(
        "SELECT Id, OriginalPath, LocalSourcePath, LocalOutputPath, "
        "SourceStorageRootId, SourceRelativePath, OutputStorageRootId, OutputRelativePath "
        "FROM TemporaryFilePaths"
    )
    Result = {}
    for LegacyCol, SidCol, RelCol in _TFP_COLUMNS:
        Counts = Counter()
        Samples = {"no_prefix_match": [], "validation_rejected": [], "unexpected_error": [], "cross_check_drift": []}
        for Row in Rows:
            RowId = Row.get("id")
            Legacy = Row.get(LegacyCol.lower())
            Category, Parsed, ErrMsg = _CategorizeAttempt(Legacy, StorageRoots)
            Counts[Category] += 1
            if Category in ("no_prefix_match", "validation_rejected", "unexpected_error") and len(Samples[Category]) < 10:
                Samples[Category].append({"id": RowId, "legacy": Legacy, "error": ErrMsg})
            if SidCol and Category == "parsed":
                StoredSid = Row.get(SidCol.lower())
                StoredRel = Row.get(RelCol.lower())
                if StoredSid is not None and StoredRel is not None:
                    if Parsed.StorageRootId != StoredSid or Parsed.RelativePath != StoredRel:
                        CaseOnly = (
                            Parsed.StorageRootId == StoredSid
                            and Parsed.RelativePath.lower() == StoredRel.lower()
                        )
                        DriftKey = "cross_check_drift_case_only" if CaseOnly else "cross_check_drift_content"
                        Counts[DriftKey] += 1
                        if DriftKey not in Samples:
                            Samples[DriftKey] = []
                        if len(Samples[DriftKey]) < 10:
                            Samples[DriftKey].append({
                                "id": RowId,
                                "legacy": Legacy,
                                "reparsed": f"({Parsed.StorageRootId}, {Parsed.RelativePath!r})",
                                "stored": f"({StoredSid}, {StoredRel!r})",
                            })
        Result[f"TemporaryFilePaths.{LegacyCol}"] = {"counts": dict(Counts), "samples": Samples, "total": len(Rows)}
    return Result


# directive: path-migration-rehearsal | # see path.C5
def _RenderReport(Results: dict, StorageRoots: list, ElapsedSec: float) -> str:
    """Format the audit results as a markdown report."""
    Now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    Lines = []
    Lines.append(f"# Path Migration Rehearsal Report")
    Lines.append(f"")
    Lines.append(f"**Generated:** {Now}")
    Lines.append(f"**Runtime:** {ElapsedSec:.2f}s")
    Lines.append(f"**StorageRoots loaded:** {len(StorageRoots)}")
    Lines.append(f"")
    Lines.append(f"## Per-(table, column) summary")
    Lines.append(f"")
    Lines.append(f"| Source | Total | NULL | Parsed | NoPrefix | ValidationReject | Unexpected | CaseDrift | ContentDrift | FailureRate |")
    Lines.append(f"|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    TotalRows = 0
    TotalNonNull = 0
    TotalFailures = 0
    TotalCaseDrift = 0
    TotalContentDrift = 0
    for Source, R in Results.items():
        C = R["counts"]
        Total = R["total"]
        Null = C.get("null", 0)
        Parsed = C.get("parsed", 0)
        NoPrefix = C.get("no_prefix_match", 0)
        Validation = C.get("validation_rejected", 0)
        Unexpected = C.get("unexpected_error", 0)
        CaseDrift = C.get("cross_check_drift_case_only", 0)
        ContentDrift = C.get("cross_check_drift_content", 0)
        NonNull = Total - Null
        Failures = NoPrefix + Validation + Unexpected
        Rate = (Failures / NonNull * 100) if NonNull > 0 else 0.0
        Lines.append(f"| {Source} | {Total} | {Null} | {Parsed} | {NoPrefix} | {Validation} | {Unexpected} | {CaseDrift} | {ContentDrift} | {Rate:.4f}% |")
        TotalRows += Total
        TotalNonNull += NonNull
        TotalFailures += Failures
        TotalCaseDrift += CaseDrift
        TotalContentDrift += ContentDrift
    OverallRate = (TotalFailures / TotalNonNull * 100) if TotalNonNull > 0 else 0.0
    Lines.append(f"| **TOTAL** | **{TotalRows}** | -- | -- | -- | -- | -- | **{TotalCaseDrift}** | **{TotalContentDrift}** | **{OverallRate:.4f}%** |")
    Lines.append(f"")
    Lines.append(f"## Verdict")
    Lines.append(f"")
    Lines.append(f"- Overall parse-failure rate: **{OverallRate:.4f}%** (target < 0.1%)")
    Lines.append(f"- Content drift: **{TotalContentDrift}** (target 0 -- legacy and typed pair represent different files)")
    Lines.append(f"- Case-only drift: **{TotalCaseDrift}** (informational -- expected per D2/D10; scanner canonicalizes case at ingest, FromLegacyString preserves legacy case)")
    Verdict = "PASS" if OverallRate < 0.1 and TotalContentDrift == 0 else "INVESTIGATE"
    Lines.append(f"- Verdict: **{Verdict}**")
    Lines.append(f"")
    Lines.append(f"## Failure samples")
    Lines.append(f"")
    for Source, R in Results.items():
        Samples = R["samples"]
        Any = any(len(S) > 0 for S in Samples.values())
        if not Any:
            continue
        Lines.append(f"### {Source}")
        Lines.append(f"")
        for Cat in ("no_prefix_match", "validation_rejected", "unexpected_error", "cross_check_drift_content", "cross_check_drift_case_only"):
            S = Samples.get(Cat, [])
            if not S:
                continue
            Lines.append(f"**{Cat}** ({len(S)} sample{'s' if len(S) != 1 else ''}):")
            Lines.append(f"")
            for Item in S:
                Lines.append(f"- id={Item['id']}: `{Item.get('legacy')!r}`")
                if "error" in Item and Item["error"]:
                    Lines.append(f"  - error: {Item['error']}")
                if "reparsed" in Item:
                    Lines.append(f"  - reparsed: {Item['reparsed']}")
                    Lines.append(f"  - stored:   {Item['stored']}")
            Lines.append(f"")
    Lines.append(f"## StorageRoots used")
    Lines.append(f"")
    for Sr in StorageRoots:
        Lines.append(f"- Id={Sr['Id']}  Prefix=`{Sr['CanonicalPrefix']}`")
    Lines.append(f"")
    return "\n".join(Lines)


# directive: path-migration-rehearsal | # see path.C1
def Main():
    """Read-only audit entry point: walks all path-bearing legacy columns, writes markdown report."""
    import time
    Db = DatabaseService()
    T0 = time.perf_counter()
    StorageRoots = _LoadStorageRoots(Db)
    Results = {}
    for Table, IdCol, LegacyCol, SidCol, RelCol in _AUDIT_TABLES:
        Source = f"{Table}.{LegacyCol}"
        print(f"Auditing {Source} ...")
        Results[Source] = _AuditTable(Db, Table, IdCol, LegacyCol, SidCol, RelCol, StorageRoots)
    print(f"Auditing TemporaryFilePaths (3 legacy columns) ...")
    Results.update(_AuditTemporaryFilePaths(Db, StorageRoots))
    T1 = time.perf_counter()
    Elapsed = T1 - T0
    Report = _RenderReport(Results, StorageRoots, Elapsed)
    Today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ReportPath = PyPath(__file__).parent.parent / f"path-migration-rehearsal-report-{Today}.md"
    ReportPath.write_text(Report, encoding="utf-8")
    print(f"\nReport written to {ReportPath}")
    print(f"Runtime: {Elapsed:.2f}s")


if __name__ == "__main__":
    Main()
