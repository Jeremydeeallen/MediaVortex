# directive: tv-video-rule-tier1 | # see classifier.C9
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService
from Features.ContentClassifier.ContentClassifierService import ContentClassifierService


RULE_NAME = 'TvPinTier1Efficient'


# directive: tv-video-rule-tier1 | # see classifier.C9
def Run():
    Db = DatabaseService()
    Deleted = Db.ExecuteNonQuery(
        "DELETE FROM ContentClassificationRules WHERE RuleName = %s",
        (RULE_NAME,),
    )
    print(f"Deleted {Deleted} '{RULE_NAME}' rule row(s).")

    Rows = Db.ExecuteQuery(
        "SELECT mf.Id FROM MediaFiles mf JOIN StorageRoots sr ON sr.Id = mf.StorageRootId "
        "WHERE sr.DefaultQualityTier IS NOT NULL AND mf.AssignedProfile IS NULL ORDER BY mf.Id"
    )
    Ids = [int(R.get('Id')) for R in Rows]
    print(f"Assigning library-tier profile to {len(Ids)} unprofiled file(s) in tiered libraries...")
    Classifier = ContentClassifierService()
    for I in range(0, len(Ids), 200):
        Result = Classifier.ClassifyAndAssignBatch(Ids[I:I + 200])
        print(f"  {min(I + 200, len(Ids))}/{len(Ids)} {Result.get('HitCounts')}")
    return 0


if __name__ == '__main__':
    raise SystemExit(Run())
