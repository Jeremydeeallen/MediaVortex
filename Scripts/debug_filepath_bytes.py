"""Inspect raw FilePath bytes to understand what separators are stored."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from Core.Database.DatabaseService import DatabaseService

Db = DatabaseService()
Rows = Db.ExecuteQuery("SELECT Id, FilePath, FileName FROM MediaFiles WHERE Id=%s", (622376,))
R = Rows[0]
fp = R['FilePath']
fn = R['FileName']
print(f"Id={R['Id']}")
print(f"FilePath repr:  {fp!r}")
print(f"FilePath len:   {len(fp)}")
print(f"FilePath bytes: {fp.encode('utf-8')}")
print(f"  count of '\\\\' in FilePath: {fp.count(chr(92))}")
print(f"  count of '/'  in FilePath: {fp.count('/')}")
print()
print(f"FileName repr:  {fn!r}")
print(f"FileName == FilePath? {fn == fp}")
print()

# Try the basename extraction
normalized = fp.replace(chr(92), '/')
print(f"normalized: {normalized!r}")
print(f"rsplit basename: {normalized.rsplit('/', 1)[-1]!r}")
