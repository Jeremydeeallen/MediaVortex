"""Dump full ErrorMessage + key columns for the failed remux attempts."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from Core.Database.DatabaseService import DatabaseService

Db = DatabaseService()
Rows = Db.ExecuteQuery(
    "SELECT Id, WorkerName, MediaFileId, ProfileName, FilePath, Success, FileReplaced, Disposition, DispositionReason, ErrorMessage "
    "FROM TranscodeAttempts WHERE Id IN (16240, 16241, 16242, 16243) ORDER BY Id",
    ()
) if False else Db.ExecuteQuery(
    "SELECT Id, WorkerName, MediaFileId, ProfileName, FilePath, Success, FileReplaced, Disposition, DispositionReason, ErrorMessage "
    "FROM TranscodeAttempts WHERE Id = ANY(%s) ORDER BY Id",
    ([16240, 16241, 16242, 16243],)
)
for R in Rows:
    print(f"Attempt {R['Id']}:")
    print(f"  Worker:           {R['WorkerName']}")
    print(f"  MediaFileId:      {R['MediaFileId']}")
    print(f"  ProfileName:      {R['ProfileName']!r}")
    print(f"  FilePath:         {R['FilePath']!r}")
    print(f"  Success:          {R['Success']}")
    print(f"  FileReplaced:     {R['FileReplaced']}")
    print(f"  Disposition:      {R['Disposition']!r}")
    print(f"  DispositionReason:{R['DispositionReason']!r}")
    print(f"  ErrorMessage:     {R['ErrorMessage']!r}")
    print()
