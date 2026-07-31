import sys
sys.path.insert(0, '.')

from Core.Database.DatabaseService import DatabaseService
from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService

Db = DatabaseService()

Sql = (
    "SELECT mf.Id "
    "FROM MediaFiles mf "
    "WHERE mf.WorkBucket = 'Transcode' "
    "AND mf.SizeMB > 0 "
    "AND mf.TranscodedByMediaVortex IS NOT TRUE "
    "AND (mf.HasExplicitEnglishAudio IS NULL OR mf.HasExplicitEnglishAudio = true) "
    "AND NOT EXISTS (SELECT 1 FROM TranscodeAttempts ta WHERE ta.MediaFileId = mf.Id) "
    "AND NOT EXISTS (SELECT 1 FROM TranscodeQueue tq WHERE tq.MediaFileId = mf.Id) "
    "ORDER BY mf.PriorityScore DESC NULLS LAST, mf.SizeMB DESC "
    "LIMIT 300"
)
Rows = Db.ExecuteQuery(Sql)
Ids = [int(r['id']) for r in Rows]
print(f"Selected {len(Ids)} candidate MediaFileIds")

Svc = QueueManagementBusinessService()
Result = Svc.AddSuggestionsToQueue(MediaFileIds=Ids, Mode='Transcode')
print(f"Result: {Result}")
