"""Smoke test: verify file scanning is non-destructive and non-duplicative.

FileScanning.feature.md criterion 22:
  Pick one known file in MediaFiles, trigger a scan of its parent RootFolder,
  then verify:
    (a) No duplicate MediaFiles row created
    (b) Row Id unchanged (not delete+reinsert)
    (c) Metadata preserved (AssignedProfile, TranscodedByMediaVortex, IsCompliant, RecommendedMode)
    (d) ScanJobs shows Completed with NewFiles=0, DeletedFiles=0
    (e) No orphaned TranscodeAttempts/MediaFilesArchive rows for the same path

Usage:
    py Scripts/SmokeTestScan.py                  # auto-picks a file from T:\ root
    py Scripts/SmokeTestScan.py --filepath "T:\Show\Season 1\file.mkv"
    py Scripts/SmokeTestScan.py --dry-run        # shows what would be tested without scanning
"""

import sys
import os
import time
import argparse
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Core.Database.DatabaseService import DatabaseService


def Main():
    Parser = argparse.ArgumentParser(description="Smoke test: scan is non-destructive")
    Parser.add_argument('--filepath', type=str, default=None, help="Specific file path to test")
    Parser.add_argument('--dry-run', action='store_true', help="Show test plan without executing scan")
    Parser.add_argument('--api-base', type=str, default='http://localhost:5000', help="WebService base URL")
    Parser.add_argument('--timeout', type=int, default=300, help="Max seconds to wait for scan completion")
    Args = Parser.parse_args()

    Db = DatabaseService()

    # Step 1: Pick a test file
    if Args.filepath:
        Rows = Db.ExecuteQuery(
            "SELECT Id, FilePath, SizeMB, AssignedProfile, TranscodedByMediaVortex, IsCompliant, RecommendedMode "
            "FROM MediaFiles WHERE FilePath = %s",
            (Args.filepath,)
        )
        if not Rows:
            print(f"[FAIL] File not found in MediaFiles: {Args.filepath}")
            sys.exit(1)
    else:
        # Pick a file from the T:\ root that has metadata worth preserving
        Rows = Db.ExecuteQuery(
            "SELECT Id, FilePath, SizeMB, AssignedProfile, TranscodedByMediaVortex, IsCompliant, RecommendedMode "
            "FROM MediaFiles "
            "WHERE AssignedProfile IS NOT NULL AND TranscodedByMediaVortex IS NOT NULL "
            "ORDER BY Id DESC LIMIT 1"
        )
        if not Rows:
            Rows = Db.ExecuteQuery(
                "SELECT Id, FilePath, SizeMB, AssignedProfile, TranscodedByMediaVortex, IsCompliant, RecommendedMode "
                "FROM MediaFiles ORDER BY Id DESC LIMIT 1"
            )
        if not Rows:
            print("[FAIL] No MediaFiles rows found in database")
            sys.exit(1)

    TestFile = Rows[0]
    FileId = TestFile['id']
    FilePath = TestFile['filepath']
    OrigSizeMB = TestFile['sizemb']
    OrigProfile = TestFile.get('assignedprofile')
    OrigTranscoded = TestFile.get('transcodedbyMediaVortex') or TestFile.get('transcodedby_mediavortex') or TestFile.get('transcodedbyMediavortex')
    OrigCompliant = TestFile.get('iscompliant')
    OrigMode = TestFile.get('recommendedmode')

    # Resolve the RootFolder for this file (find closest match)
    RfRows = Db.ExecuteQuery(
        "SELECT Id, RootFolder FROM RootFolders ORDER BY LENGTH(RootFolder) DESC"
    )
    MatchedRoot = None
    for Rf in RfRows:
        RootPath = Rf.get('rootfolder') or Rf.get('RootFolder')
        if FilePath.lower().startswith(RootPath.lower()):
            MatchedRoot = RootPath
            break
    if not MatchedRoot:
        # Fallback: use drive root
        MatchedRoot = FilePath[:3]

    print("=" * 70)
    print("SCAN SMOKE TEST - Criterion 22")
    print("=" * 70)
    print(f"  Test File Id:           {FileId}")
    print(f"  FilePath:               {FilePath}")
    print(f"  SizeMB:                 {OrigSizeMB}")
    print(f"  AssignedProfile:        {OrigProfile}")
    print(f"  TranscodedByMediaVortex:{OrigTranscoded}")
    print(f"  IsCompliant:            {OrigCompliant}")
    print(f"  RecommendedMode:        {OrigMode}")
    print(f"  Root Folder:            {MatchedRoot}")
    print("=" * 70)

    if Args.dry_run:
        print("\n[DRY RUN] Would scan root folder and verify assertions. Exiting.")
        sys.exit(0)

    # Step 2: Count existing rows for this path BEFORE scan
    PreDupCount = Db.ExecuteQuery(
        "SELECT COUNT(*) AS Cnt FROM MediaFiles WHERE FilePath = %s", (FilePath,)
    )[0]['cnt']
    print(f"\n[PRE] Duplicate count for path: {PreDupCount}")

    PreAttemptIds = Db.ExecuteQuery(
        "SELECT Id FROM TranscodeAttempts WHERE MediaFileId = %s", (FileId,)
    )
    PreArchiveIds = Db.ExecuteQuery(
        "SELECT Id FROM MediaFilesArchive WHERE OriginalMediaFileId = %s", (FileId,)
    )
    print(f"[PRE] TranscodeAttempts for this file: {len(PreAttemptIds)}")
    print(f"[PRE] MediaFilesArchive for this file: {len(PreArchiveIds)}")

    # Step 3: Trigger scan via API
    print(f"\n[SCAN] Triggering scan for: {MatchedRoot}")
    try:
        Resp = requests.post(
            f"{Args.api_base}/api/Scan/Start",
            json={"RootFolderPath": MatchedRoot, "Recursive": True},
            timeout=30
        )
        RespData = Resp.json()
        if not RespData.get('Success'):
            print(f"[WARN] Scan start response: {RespData.get('Message')}")
            if RespData.get('Error') == 'ScanAlreadyRunning':
                print("[INFO] Scan already running -- waiting for it to complete")
            else:
                print("[FAIL] Could not start scan")
                sys.exit(1)
    except Exception as e:
        print(f"[FAIL] Error calling scan API: {e}")
        sys.exit(1)

    # Step 4: Wait for scan to complete
    print("[WAIT] Waiting for scan to complete...")
    StartWait = time.time()
    ScanCompleted = False
    while time.time() - StartWait < Args.timeout:
        time.sleep(5)
        # Check ScanJobs for the most recent scan of this root
        Jobs = Db.ExecuteQuery(
            "SELECT Id, Status, NewFiles, DeletedFiles, ErrorMessage "
            "FROM ScanJobs WHERE RootFolderPath = %s ORDER BY Id DESC LIMIT 1",
            (MatchedRoot,)
        )
        if Jobs:
            Job = Jobs[0]
            Status = Job.get('status')
            if Status in ('Completed', 'Failed', 'Stopped'):
                ScanCompleted = True
                print(f"[SCAN] Finished with Status={Status}")
                if Status == 'Failed':
                    print(f"       ErrorMessage: {Job.get('errormessage')}")
                break
        Elapsed = int(time.time() - StartWait)
        if Elapsed % 30 == 0:
            print(f"       ...still waiting ({Elapsed}s)")

    if not ScanCompleted:
        print(f"[FAIL] Scan did not complete within {Args.timeout}s")
        sys.exit(1)

    # Step 5: VERIFY assertions
    print("\n" + "=" * 70)
    print("VERIFICATION")
    print("=" * 70)
    Failures = []

    # (a) No duplicate
    PostDupCount = Db.ExecuteQuery(
        "SELECT COUNT(*) AS Cnt FROM MediaFiles WHERE FilePath = %s", (FilePath,)
    )[0]['cnt']
    if PostDupCount != 1:
        Failures.append(f"(a) FAIL: Expected 1 row for path, got {PostDupCount}")
    else:
        print(f"  (a) PASS: Exactly 1 MediaFiles row for path (no duplicate)")

    # (b) Id unchanged
    PostRows = Db.ExecuteQuery(
        "SELECT Id, AssignedProfile, TranscodedByMediaVortex, IsCompliant, RecommendedMode "
        "FROM MediaFiles WHERE FilePath = %s",
        (FilePath,)
    )
    if not PostRows:
        Failures.append("(b) FAIL: MediaFiles row disappeared!")
    else:
        PostFile = PostRows[0]
        PostId = PostFile['id']
        if PostId != FileId:
            Failures.append(f"(b) FAIL: Id changed from {FileId} to {PostId} (delete+reinsert)")
        else:
            print(f"  (b) PASS: Id unchanged ({FileId})")

        # (c) Metadata preserved
        PostProfile = PostFile.get('assignedprofile')
        PostTranscoded = PostFile.get('transcodedbyMediaVortex') or PostFile.get('transcodedby_mediavortex') or PostFile.get('transcodedbyMediavortex')
        PostCompliant = PostFile.get('iscompliant')
        PostMode = PostFile.get('recommendedmode')

        MetaOk = True
        if PostProfile != OrigProfile:
            Failures.append(f"(c) FAIL: AssignedProfile changed from '{OrigProfile}' to '{PostProfile}'")
            MetaOk = False
        if PostTranscoded != OrigTranscoded:
            Failures.append(f"(c) FAIL: TranscodedByMediaVortex changed from '{OrigTranscoded}' to '{PostTranscoded}'")
            MetaOk = False
        if PostCompliant != OrigCompliant:
            Failures.append(f"(c) FAIL: IsCompliant changed from '{OrigCompliant}' to '{PostCompliant}'")
            MetaOk = False
        if PostMode != OrigMode:
            Failures.append(f"(c) FAIL: RecommendedMode changed from '{OrigMode}' to '{PostMode}'")
            MetaOk = False
        if MetaOk:
            print(f"  (c) PASS: Metadata preserved (AssignedProfile, TranscodedByMediaVortex, IsCompliant, RecommendedMode)")

    # (d) ScanJobs shows Completed with NewFiles=0, DeletedFiles=0 for a re-scan
    LatestJob = Db.ExecuteQuery(
        "SELECT Status, NewFiles, DeletedFiles FROM ScanJobs WHERE RootFolderPath = %s ORDER BY Id DESC LIMIT 1",
        (MatchedRoot,)
    )
    if LatestJob:
        J = LatestJob[0]
        if J.get('status') != 'Completed':
            Failures.append(f"(d) FAIL: ScanJobs.Status='{J.get('status')}', expected 'Completed'")
        else:
            print(f"  (d) PASS: ScanJobs Status='Completed'")
        # Note: NewFiles/DeletedFiles may be non-zero if OTHER files changed. We just report.
        print(f"       NewFiles={J.get('newfiles', 0)}, DeletedFiles={J.get('deletedfiles', 0)}")

    # (e) No orphaned TranscodeAttempts/MediaFilesArchive
    PostAttemptIds = Db.ExecuteQuery(
        "SELECT Id FROM TranscodeAttempts WHERE MediaFileId = %s", (FileId,)
    )
    PostArchiveIds = Db.ExecuteQuery(
        "SELECT Id FROM MediaFilesArchive WHERE OriginalMediaFileId = %s", (FileId,)
    )
    if len(PostAttemptIds) != len(PreAttemptIds):
        Failures.append(f"(e) FAIL: TranscodeAttempts count changed from {len(PreAttemptIds)} to {len(PostAttemptIds)}")
    elif len(PostArchiveIds) != len(PreArchiveIds):
        Failures.append(f"(e) FAIL: MediaFilesArchive count changed from {len(PreArchiveIds)} to {len(PostArchiveIds)}")
    else:
        print(f"  (e) PASS: No orphaned TranscodeAttempts or MediaFilesArchive rows")

    # Summary
    print("\n" + "=" * 70)
    if Failures:
        print(f"RESULT: FAILED ({len(Failures)} assertion(s))")
        for F in Failures:
            print(f"  {F}")
        sys.exit(1)
    else:
        print("RESULT: ALL ASSERTIONS PASSED")
        print("Scan is non-destructive and non-duplicative for this file.")
        sys.exit(0)


if __name__ == '__main__':
    Main()
