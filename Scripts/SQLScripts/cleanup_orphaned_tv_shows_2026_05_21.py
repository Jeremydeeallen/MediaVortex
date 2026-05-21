"""One-shot DB cleanup for TV shows removed during the brain -> porky migration.

Context: in May 2026 the TV source was migrated from brain's CIFS share to
porky's NFS export. Sixty-odd shows were intentionally dropped from the new
source (verified empty on brain too). MediaFiles still has ~4972 rows pointing
at the dropped paths; this script removes those rows and all dependent
history.

Usage:
    py Scripts/SQLScripts/cleanup_orphaned_tv_shows_2026_05_21.py            # dry-run (default)
    py Scripts/SQLScripts/cleanup_orphaned_tv_shows_2026_05_21.py --execute  # actually delete

Dry-run is a read-only audit: COUNT(*) for every delete candidate, no DML.
Execute runs the deletes inside a single transaction; failure rolls back.
"""

import argparse
import sys
from typing import Dict, List, Tuple

sys.path.insert(0, '.')
from Core.Database.DatabaseService import DatabaseService

# Shows confirmed empty on /mnt/media_tv (verified 2026-05-21) and absent
# from brain's _tv and _tv-d-2026-05-28 snapshot. Source: diff between
# MediaFiles distinct show prefixes and porky filesystem listing.
ORPHANED_SHOWS: List[str] = [
    "Fugget About It",
    "Fullmetal Alchemist - Brotherhood",
    "GATE",
    "Girl Meets World",
    "High School of the Dead",
    "House of Lies",
    "How to Get Away with Murder",
    "Human Resources (2022)",
    "Infinity Train",
    "Jackass",
    "Jacob Two-Two",
    "Justice League",
    "Killjoys",
    "Lilo & Stitch - The Series",
    "Loner Life in Another World",
    "Looney Tunes",
    "Manifest",
    "Married. with Children",
    "Merlin",
    "Monsters vs. Aliens",
    "NewsRadio",
    "OK K.O.! Let's Be Heroes",
    "Over the Garden Wall",
    "Paradise PD",
    "Red Dwarf",
    "Rules of Engagement",
    "Sabrina, The Teenage Witch",
    "Scandal (2012)",
    "Shangri-La Frontier",
    "Silicon Valley",
    "Star Trek - Discovery",
    "Star Wars - The Bad Batch",
    "Storage Wars - Northern Treasures",
    "Suits",
    "Switched at Birth",
    "That Mitchell and Webb Look",
    "The Ancient Magus' Bride",
    "The Daily Life of a Middle-Aged Online Shopper in Another World",
    "The Last Kids on Earth",
    "The Mighty Boosh",
    "The Misfit of Demon King Academy",
    "The Muppet Show",
    "The Naked Truth",
    "The Nanny",
    "The Originals",
    "The Practice",
    "The Promised Neverland",
    "The Scooby-Doo Show",
    "The Seven Deadly Sins",
    "Trinity Seven",
    "Veep",
    "Vinland Saga",
    "We Baby Bears",
    "We Bare Bears",
    "Where on Earth is Carmen Sandiego!",
    "White Lines",
    "World of Winx",
    "Younger",
    "Yu Yu Hakusho",
]

# Stray file at T:\ root (no show folder).
ORPHANED_STRAY_FILES: List[str] = [
    "T:\\8 Minute Ab workout.mkv",
]

BS = chr(92)
LIKE_ESCAPE = "|"  # picked to avoid collision with `!`, `\`, and the show names


def ShowPathPrefix(Show: str) -> str:
    return f"T:{BS}{Show}{BS}"


def ShowLikePattern(Show: str) -> str:
    Escaped = Show.replace(LIKE_ESCAPE, LIKE_ESCAPE + LIKE_ESCAPE) \
                  .replace("%", LIKE_ESCAPE + "%") \
                  .replace("_", LIKE_ESCAPE + "_")
    return f"T:{BS}{Escaped}{BS}%"


def ShowRootFolderPath(Show: str) -> str:
    return f"T:{BS}{Show}"


def CountForShow(Db: DatabaseService, Show: str) -> Dict[str, int]:
    LikePattern = ShowLikePattern(Show)
    RootFolderPath = ShowRootFolderPath(Show)
    Esc = LIKE_ESCAPE
    Counts: Dict[str, int] = {}

    Counts["mediafiles"] = Db.ExecuteQuery(
        f"SELECT COUNT(*) AS n FROM mediafiles WHERE filepath LIKE %s ESCAPE '{Esc}'",
        (LikePattern,))[0]["n"]
    Counts["transcodequeue"] = Db.ExecuteQuery(
        f"SELECT COUNT(*) AS n FROM transcodequeue WHERE filepath LIKE %s ESCAPE '{Esc}'",
        (LikePattern,))[0]["n"]
    Counts["transcodeattempts"] = Db.ExecuteQuery(
        f"SELECT COUNT(*) AS n FROM transcodeattempts WHERE filepath LIKE %s ESCAPE '{Esc}'",
        (LikePattern,))[0]["n"]
    Counts["transcodefiles"] = Db.ExecuteQuery(
        f"SELECT COUNT(*) AS n FROM transcodefiles "
        f"WHERE filepath LIKE %s ESCAPE '{Esc}' "
        f"   OR finalfilepath LIKE %s ESCAPE '{Esc}' "
        f"   OR originalfilepath LIKE %s ESCAPE '{Esc}'",
        (LikePattern, LikePattern, LikePattern))[0]["n"]
    Counts["mediafilesarchive"] = Db.ExecuteQuery(
        f"SELECT COUNT(*) AS n FROM mediafilesarchive WHERE filepath LIKE %s ESCAPE '{Esc}'",
        (LikePattern,))[0]["n"]
    Counts["problemfiles"] = Db.ExecuteQuery(
        f"SELECT COUNT(*) AS n FROM problemfiles WHERE filepath LIKE %s ESCAPE '{Esc}'",
        (LikePattern,))[0]["n"]
    Counts["clipbuilderpresets"] = Db.ExecuteQuery(
        f"SELECT COUNT(*) AS n FROM clipbuilderpresets WHERE filepath LIKE %s ESCAPE '{Esc}'",
        (LikePattern,))[0]["n"]
    Counts["compressionlearningsamples"] = Db.ExecuteQuery(
        f"SELECT COUNT(*) AS n FROM compressionlearningsamples WHERE filepath LIKE %s ESCAPE '{Esc}'",
        (LikePattern,))[0]["n"]
    Counts["jellyfinoperations"] = Db.ExecuteQuery(
        f"SELECT COUNT(*) AS n FROM jellyfinoperations WHERE filepath LIKE %s ESCAPE '{Esc}'",
        (LikePattern,))[0]["n"]
    Counts["qualitytestingqueue"] = Db.ExecuteQuery(
        f"SELECT COUNT(*) AS n FROM qualitytestingqueue WHERE originalfilepath LIKE %s ESCAPE '{Esc}'",
        (LikePattern,))[0]["n"]
    Counts["qualitytestingqueuebackup"] = Db.ExecuteQuery(
        f"SELECT COUNT(*) AS n FROM qualitytestingqueuebackup WHERE originalfilepath LIKE %s ESCAPE '{Esc}'",
        (LikePattern,))[0]["n"]
    Counts["qualitytestingqueuetest"] = Db.ExecuteQuery(
        f"SELECT COUNT(*) AS n FROM qualitytestingqueuetest WHERE originalfilepath LIKE %s ESCAPE '{Esc}'",
        (LikePattern,))[0]["n"]

    # Transitive via transcodeattempts.id
    AttemptIdRows = Db.ExecuteQuery(
        f"SELECT id FROM transcodeattempts WHERE filepath LIKE %s ESCAPE '{Esc}'",
        (LikePattern,))
    AttemptIds = [r["id"] for r in AttemptIdRows]
    if AttemptIds:
        Tuple_ = tuple(AttemptIds)
        Counts["qualitytestprogress"] = Db.ExecuteQuery(
            "SELECT COUNT(*) AS n FROM qualitytestprogress WHERE transcodeattemptid IN %s",
            (Tuple_,))[0]["n"]
        Counts["qualitytestresults"] = Db.ExecuteQuery(
            "SELECT COUNT(*) AS n FROM qualitytestresults WHERE transcodeattemptid IN %s",
            (Tuple_,))[0]["n"]
        Counts["temporaryfilepaths"] = Db.ExecuteQuery(
            "SELECT COUNT(*) AS n FROM temporaryfilepaths WHERE transcodeattemptid IN %s",
            (Tuple_,))[0]["n"]
        Counts["transcodeprogress"] = Db.ExecuteQuery(
            "SELECT COUNT(*) AS n FROM transcodeprogress WHERE transcodeattemptid IN %s",
            (Tuple_,))[0]["n"]
    else:
        Counts["qualitytestprogress"] = 0
        Counts["qualitytestresults"] = 0
        Counts["temporaryfilepaths"] = 0
        Counts["transcodeprogress"] = 0

    # activejobs is polymorphic — count rows whose queueid points at one of
    # our transcodequeue or qualitytestingqueue rows for this show.
    TqRows = Db.ExecuteQuery(
        f"SELECT id FROM transcodequeue WHERE filepath LIKE %s ESCAPE '{Esc}'",
        (LikePattern,))
    QtqRows = Db.ExecuteQuery(
        f"SELECT id FROM qualitytestingqueue WHERE originalfilepath LIKE %s ESCAPE '{Esc}'",
        (LikePattern,))
    TqIds = [r["id"] for r in TqRows]
    QtqIds = [r["id"] for r in QtqRows]
    AjN = 0
    if TqIds:
        AjN += Db.ExecuteQuery(
            "SELECT COUNT(*) AS n FROM activejobs WHERE jobtype IN ('Transcode','Remux','AudioFix','Quick') AND queueid IN %s",
            (tuple(TqIds),))[0]["n"]
    if QtqIds:
        AjN += Db.ExecuteQuery(
            "SELECT COUNT(*) AS n FROM activejobs WHERE jobtype='QualityTest' AND queueid IN %s",
            (tuple(QtqIds),))[0]["n"]
    Counts["activejobs"] = AjN

    # Show-keyed metadata
    Counts["rootfolders"] = Db.ExecuteQuery(
        "SELECT COUNT(*) AS n FROM rootfolders WHERE rootfolder = %s",
        (RootFolderPath,))[0]["n"]
    RfRows = Db.ExecuteQuery(
        "SELECT id FROM rootfolders WHERE rootfolder = %s",
        (RootFolderPath,))
    RfIds = [r["id"] for r in RfRows]
    if RfIds:
        Counts["seasons"] = Db.ExecuteQuery(
            "SELECT COUNT(*) AS n FROM seasons WHERE rootfolderid IN %s",
            (tuple(RfIds),))[0]["n"]
    else:
        Counts["seasons"] = 0
    Counts["showsettings"] = Db.ExecuteQuery(
        "SELECT COUNT(*) AS n FROM showsettings WHERE showfolder = %s OR showfolder = %s",
        (RootFolderPath, Show))[0]["n"]

    return Counts


def DeleteForShow(Cursor, Show: str) -> Dict[str, int]:
    """Execute deletes in FK-safe order for one show. Returns rows-deleted per table.

    Cursor is a live psycopg2 cursor inside a transaction; caller commits or rolls back.
    """
    LikePattern = ShowLikePattern(Show)
    RootFolderPath = ShowRootFolderPath(Show)
    Esc = LIKE_ESCAPE
    Deleted: Dict[str, int] = {}

    # Pre-fetch IDs we'll need across multiple steps
    Cursor.execute(
        f"SELECT id FROM transcodeattempts WHERE filepath LIKE %s ESCAPE '{Esc}'",
        (LikePattern,))
    AttemptIds = [r[0] for r in Cursor.fetchall()]

    Cursor.execute(
        f"SELECT id FROM transcodequeue WHERE filepath LIKE %s ESCAPE '{Esc}'",
        (LikePattern,))
    TqIds = [r[0] for r in Cursor.fetchall()]

    Cursor.execute(
        f"SELECT id FROM qualitytestingqueue WHERE originalfilepath LIKE %s ESCAPE '{Esc}'",
        (LikePattern,))
    QtqIds = [r[0] for r in Cursor.fetchall()]

    Cursor.execute("SELECT id FROM rootfolders WHERE rootfolder = %s", (RootFolderPath,))
    RfIds = [r[0] for r in Cursor.fetchall()]

    # Phase 1: polymorphic activejobs (no FK; do first)
    AjDeleted = 0
    if TqIds:
        Cursor.execute(
            "DELETE FROM activejobs WHERE jobtype IN ('Transcode','Remux','AudioFix','Quick') AND queueid IN %s",
            (tuple(TqIds),))
        AjDeleted += Cursor.rowcount
    if QtqIds:
        Cursor.execute(
            "DELETE FROM activejobs WHERE jobtype='QualityTest' AND queueid IN %s",
            (tuple(QtqIds),))
        AjDeleted += Cursor.rowcount
    Deleted["activejobs"] = AjDeleted

    # Phase 2: transcodeattempt-keyed children (no FK CASCADE here)
    if AttemptIds:
        Cursor.execute(
            "DELETE FROM qualitytestprogress WHERE transcodeattemptid IN %s",
            (tuple(AttemptIds),))
        Deleted["qualitytestprogress"] = Cursor.rowcount
        Cursor.execute(
            "DELETE FROM qualitytestresults WHERE transcodeattemptid IN %s",
            (tuple(AttemptIds),))
        Deleted["qualitytestresults"] = Cursor.rowcount
        Cursor.execute(
            "DELETE FROM temporaryfilepaths WHERE transcodeattemptid IN %s",
            (tuple(AttemptIds),))
        Deleted["temporaryfilepaths"] = Cursor.rowcount
        Cursor.execute(
            "DELETE FROM transcodeprogress WHERE transcodeattemptid IN %s",
            (tuple(AttemptIds),))
        Deleted["transcodeprogress"] = Cursor.rowcount
    else:
        Deleted["qualitytestprogress"] = 0
        Deleted["qualitytestresults"] = 0
        Deleted["temporaryfilepaths"] = 0
        Deleted["transcodeprogress"] = 0

    # Phase 3: path-keyed history tables (no FK to mediafiles)
    Cursor.execute(
        f"DELETE FROM qualitytestingqueue WHERE originalfilepath LIKE %s ESCAPE '{Esc}'",
        (LikePattern,))
    Deleted["qualitytestingqueue"] = Cursor.rowcount
    Cursor.execute(
        f"DELETE FROM qualitytestingqueuebackup WHERE originalfilepath LIKE %s ESCAPE '{Esc}'",
        (LikePattern,))
    Deleted["qualitytestingqueuebackup"] = Cursor.rowcount
    Cursor.execute(
        f"DELETE FROM qualitytestingqueuetest WHERE originalfilepath LIKE %s ESCAPE '{Esc}'",
        (LikePattern,))
    Deleted["qualitytestingqueuetest"] = Cursor.rowcount
    Cursor.execute(
        f"DELETE FROM mediafilesarchive WHERE filepath LIKE %s ESCAPE '{Esc}'",
        (LikePattern,))
    Deleted["mediafilesarchive"] = Cursor.rowcount
    Cursor.execute(
        f"DELETE FROM clipbuilderpresets WHERE filepath LIKE %s ESCAPE '{Esc}'",
        (LikePattern,))
    Deleted["clipbuilderpresets"] = Cursor.rowcount
    Cursor.execute(
        f"DELETE FROM compressionlearningsamples WHERE filepath LIKE %s ESCAPE '{Esc}'",
        (LikePattern,))
    Deleted["compressionlearningsamples"] = Cursor.rowcount
    Cursor.execute(
        f"DELETE FROM jellyfinoperations WHERE filepath LIKE %s ESCAPE '{Esc}'",
        (LikePattern,))
    Deleted["jellyfinoperations"] = Cursor.rowcount

    # Phase 4: transcode history (transcodeattempts and transcodefiles SET NULL
    # on mediafileid, so deleting mediafiles last would leave orphans. Delete
    # them explicitly first.)
    Cursor.execute(
        f"DELETE FROM transcodeattempts WHERE filepath LIKE %s ESCAPE '{Esc}'",
        (LikePattern,))
    Deleted["transcodeattempts"] = Cursor.rowcount
    Cursor.execute(
        f"DELETE FROM transcodefiles WHERE filepath LIKE %s ESCAPE '{Esc}' "
        f"   OR finalfilepath LIKE %s ESCAPE '{Esc}' "
        f"   OR originalfilepath LIKE %s ESCAPE '{Esc}'",
        (LikePattern, LikePattern, LikePattern))
    Deleted["transcodefiles"] = Cursor.rowcount

    # Phase 5: transcodequeue + problemfiles (CASCADE from mediafiles, but
    # delete by path-key explicitly so a stray row with NULL mediafileid still
    # goes)
    Cursor.execute(
        f"DELETE FROM transcodequeue WHERE filepath LIKE %s ESCAPE '{Esc}'",
        (LikePattern,))
    Deleted["transcodequeue"] = Cursor.rowcount
    Cursor.execute(
        f"DELETE FROM problemfiles WHERE filepath LIKE %s ESCAPE '{Esc}'",
        (LikePattern,))
    Deleted["problemfiles"] = Cursor.rowcount

    # Phase 6: the main table
    Cursor.execute(
        f"DELETE FROM mediafiles WHERE filepath LIKE %s ESCAPE '{Esc}'",
        (LikePattern,))
    Deleted["mediafiles"] = Cursor.rowcount

    # Phase 7: show-keyed metadata
    if RfIds:
        Cursor.execute("DELETE FROM seasons WHERE rootfolderid IN %s", (tuple(RfIds),))
        Deleted["seasons"] = Cursor.rowcount
    else:
        Deleted["seasons"] = 0
    Cursor.execute("DELETE FROM rootfolders WHERE rootfolder = %s", (RootFolderPath,))
    Deleted["rootfolders"] = Cursor.rowcount
    Cursor.execute(
        "DELETE FROM showsettings WHERE showfolder = %s OR showfolder = %s",
        (RootFolderPath, Show))
    Deleted["showsettings"] = Cursor.rowcount

    return Deleted


def DeleteStrayFile(Cursor, FilePath: str) -> Dict[str, int]:
    """Same FK-safe ordering as DeleteForShow but for a single file path
    (no show folder, so no RootFolders / Seasons / ShowSettings work).
    """
    Deleted: Dict[str, int] = {}

    Cursor.execute(
        "SELECT id FROM transcodeattempts WHERE filepath = %s", (FilePath,))
    AttemptIds = [r[0] for r in Cursor.fetchall()]
    Cursor.execute(
        "SELECT id FROM transcodequeue WHERE filepath = %s", (FilePath,))
    TqIds = [r[0] for r in Cursor.fetchall()]
    Cursor.execute(
        "SELECT id FROM qualitytestingqueue WHERE originalfilepath = %s", (FilePath,))
    QtqIds = [r[0] for r in Cursor.fetchall()]

    AjDeleted = 0
    if TqIds:
        Cursor.execute(
            "DELETE FROM activejobs WHERE jobtype IN ('Transcode','Remux','AudioFix','Quick') AND queueid IN %s",
            (tuple(TqIds),))
        AjDeleted += Cursor.rowcount
    if QtqIds:
        Cursor.execute(
            "DELETE FROM activejobs WHERE jobtype='QualityTest' AND queueid IN %s",
            (tuple(QtqIds),))
        AjDeleted += Cursor.rowcount
    Deleted["activejobs"] = AjDeleted

    if AttemptIds:
        for Tbl in ("qualitytestprogress", "qualitytestresults", "temporaryfilepaths", "transcodeprogress"):
            Cursor.execute(f"DELETE FROM {Tbl} WHERE transcodeattemptid IN %s", (tuple(AttemptIds),))
            Deleted[Tbl] = Cursor.rowcount
    else:
        for Tbl in ("qualitytestprogress", "qualitytestresults", "temporaryfilepaths", "transcodeprogress"):
            Deleted[Tbl] = 0

    for Tbl, Col in (
        ("qualitytestingqueue", "originalfilepath"),
        ("qualitytestingqueuebackup", "originalfilepath"),
        ("qualitytestingqueuetest", "originalfilepath"),
        ("mediafilesarchive", "filepath"),
        ("clipbuilderpresets", "filepath"),
        ("compressionlearningsamples", "filepath"),
        ("jellyfinoperations", "filepath"),
        ("transcodeattempts", "filepath"),
        ("transcodequeue", "filepath"),
        ("problemfiles", "filepath"),
        ("mediafiles", "filepath"),
    ):
        Cursor.execute(f"DELETE FROM {Tbl} WHERE {Col} = %s", (FilePath,))
        Deleted[Tbl] = Cursor.rowcount

    Cursor.execute(
        "DELETE FROM transcodefiles WHERE filepath = %s OR finalfilepath = %s OR originalfilepath = %s",
        (FilePath, FilePath, FilePath))
    Deleted["transcodefiles"] = Cursor.rowcount

    return Deleted


TABLE_ORDER = [
    "activejobs",
    "qualitytestprogress",
    "qualitytestresults",
    "temporaryfilepaths",
    "transcodeprogress",
    "qualitytestingqueue",
    "qualitytestingqueuebackup",
    "qualitytestingqueuetest",
    "mediafilesarchive",
    "clipbuilderpresets",
    "compressionlearningsamples",
    "jellyfinoperations",
    "transcodeattempts",
    "transcodefiles",
    "transcodequeue",
    "problemfiles",
    "mediafiles",
    "seasons",
    "rootfolders",
    "showsettings",
]


def RenderRow(Label: str, Counts: Dict[str, int]) -> str:
    Parts = [f"{Label:<60}"]
    Parts.append(f"mf={Counts.get('mediafiles', 0):>4}")
    Parts.append(f"ta={Counts.get('transcodeattempts', 0):>4}")
    Parts.append(f"tq={Counts.get('transcodequeue', 0):>3}")
    Parts.append(f"tf={Counts.get('transcodefiles', 0):>4}")
    Parts.append(f"arch={Counts.get('mediafilesarchive', 0):>4}")
    Parts.append(f"qtq={Counts.get('qualitytestingqueue', 0):>3}")
    Parts.append(f"qtr={Counts.get('qualitytestresults', 0):>3}")
    Parts.append(f"aj={Counts.get('activejobs', 0):>2}")
    Parts.append(f"rf={Counts.get('rootfolders', 0):>2}")
    Parts.append(f"se={Counts.get('seasons', 0):>3}")
    Parts.append(f"ss={Counts.get('showsettings', 0):>2}")
    return "  ".join(Parts)


def Main():
    Parser = argparse.ArgumentParser(description=__doc__)
    Parser.add_argument("--execute", action="store_true",
                        help="Actually delete. Default is dry-run (read-only).")
    Args = Parser.parse_args()
    Mode = "EXECUTE" if Args.execute else "DRY-RUN"

    Db = DatabaseService()
    print(f"\n=== Orphaned-TV cleanup ({Mode}) ===")
    print(f"shows={len(ORPHANED_SHOWS)}  stray_files={len(ORPHANED_STRAY_FILES)}\n")

    if not Args.execute:
        Totals: Dict[str, int] = {t: 0 for t in TABLE_ORDER}
        for Show in ORPHANED_SHOWS:
            Counts = CountForShow(Db, Show)
            for t, n in Counts.items():
                Totals[t] = Totals.get(t, 0) + n
            print(RenderRow(Show, Counts))
        print()
        for Stray in ORPHANED_STRAY_FILES:
            print(f"STRAY: {Stray} (counted under mediafiles directly)")
        print()
        print(f"--- Totals across {len(ORPHANED_SHOWS)} shows ---")
        for t in TABLE_ORDER:
            print(f"  {t:<30}  {Totals.get(t, 0)}")
        print("\nDry-run complete. Re-run with --execute to apply.")
        return 0

    # EXECUTE: one transaction, rollback on any error.
    Conn = Db.GetConnection()
    Cur = Conn.cursor()
    Totals: Dict[str, int] = {t: 0 for t in TABLE_ORDER}
    try:
        for Show in ORPHANED_SHOWS:
            Deleted = DeleteForShow(Cur, Show)
            for t, n in Deleted.items():
                Totals[t] = Totals.get(t, 0) + n
            print(RenderRow(Show, Deleted))
        for Stray in ORPHANED_STRAY_FILES:
            Deleted = DeleteStrayFile(Cur, Stray)
            for t, n in Deleted.items():
                Totals[t] = Totals.get(t, 0) + n
            print(RenderRow(f"STRAY: {Stray}", Deleted))
        Conn.commit()
        print()
        print(f"--- Committed. Totals across {len(ORPHANED_SHOWS)} shows + {len(ORPHANED_STRAY_FILES)} strays ---")
        for t in TABLE_ORDER:
            print(f"  {t:<30}  {Totals.get(t, 0)}")
        return 0
    except Exception as Exc:
        Conn.rollback()
        print(f"\nERROR -- rolled back. {type(Exc).__name__}: {Exc}", file=sys.stderr)
        return 1
    finally:
        Cur.close()
        Db.CloseConnection(Conn)


if __name__ == "__main__":
    sys.exit(Main())
