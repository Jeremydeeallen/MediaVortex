"""One-shot status of active scans + SizeSurvey drain. Re-runnable.

Usage: py Scripts/CheckScanDrain.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from Core.Database.DatabaseService import DatabaseService

ROWS = DatabaseService().ExecuteQuery("""
    SELECT WorkerName, RootFolderPath AS Drive, Phase,
           COALESCE(jsonb_array_length(TopFiles), -1) AS Remaining,
           COALESCE(ProbedFiles, 0) AS Probed,
           COALESCE(FilesNeedingProbe, 0) AS Total,
           EXTRACT(EPOCH FROM (NOW() - StartTime))::int  AS ElapsedS,
           EXTRACT(EPOCH FROM (NOW() - LastUpdated))::int AS StaleS,
           TopFiles->0->>'fileName' AS LargestLeft
    FROM ScanJobs
    WHERE Status = 'Running'
    ORDER BY WorkerName
""")

if not ROWS:
    print("No running scans.")
else:
    print(f"{'Worker':<16} {'Drive':<6} {'Phase':<11} {'Probed':>8} {'Left':>6} {'Elapsed':>8} {'Stale':>6}  Largest remaining")
    for R in ROWS:
        Left = R['Remaining'] if R['Remaining'] >= 0 else '-'
        Probed = f"{R['Probed']}/{R['Total']}"
        Stale = R['StaleS']
        StaleStr = f"{Stale}s" + ("!" if Stale > 30 else "")
        Largest = (R['LargestLeft'] or '')[:50]
        print(f"{R['WorkerName']:<16} {R['Drive']:<6} {R['Phase'] or '?':<11} {Probed:>8} {str(Left):>6} {R['ElapsedS']:>7}s {StaleStr:>6}  {Largest}")
