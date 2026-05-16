"""Hard evidence: dump untruncated error messages + queue/worker context
for the failed remux test. No interpretation -- just facts."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from Core.Database.DatabaseService import DatabaseService

Db = DatabaseService()

print('=== FULL Message column for failed remux jobs ===')
for R in Db.ExecuteQuery(
    "SELECT Timestamp, FunctionName, Message FROM Logs "
    "WHERE Timestamp > NOW() - INTERVAL %s "
    "AND Message ILIKE %s "
    "ORDER BY Timestamp ASC",
    ('15 minutes', '%Exception processing remux%')
):
    print(f"[{R['Timestamp']}] {R['FunctionName']}")
    print(f"  {R['Message']}")
    print()

print('=== FULL Message column for "Insert attempt parameters" ===')
for R in Db.ExecuteQuery(
    "SELECT Timestamp, Message FROM Logs "
    "WHERE Timestamp > NOW() - INTERVAL %s "
    "AND Message LIKE %s "
    "ORDER BY Timestamp ASC LIMIT 2",
    ('15 minutes', 'Insert attempt parameters%')
):
    print(f"[{R['Timestamp']}]")
    print(f"  {R['Message'][:600]}")
    print()

print('=== FULL Message column for "Active job ... failed: Exception during remux:" ===')
for R in Db.ExecuteQuery(
    "SELECT Message FROM Logs "
    "WHERE Timestamp > NOW() - INTERVAL %s "
    "AND Message LIKE %s "
    "ORDER BY Timestamp DESC LIMIT 2",
    ('15 minutes', 'Active job%failed:%')
):
    print(f"  {R['Message']}")
    print()

print('=== StorageRootResolutions for the 4 test workers ===')
for W in ['larry-worker-1', 'wakko-worker-1', 'dot-worker-1', 'I9-2024']:
    rows = Db.ExecuteQuery(
        "SELECT StorageRootId, Platform, AbsolutePath, IsActive "
        "FROM StorageRootResolutions WHERE WorkerName = %s ORDER BY StorageRootId",
        (W,)
    )
    print(f"  {W}: {len(rows)} rows")
    for R in rows:
        print(f"    StorageRootId={R['StorageRootId']} Platform={R['Platform']!r} AbsolutePath={R['AbsolutePath']!r} IsActive={R['IsActive']}")
    print()
