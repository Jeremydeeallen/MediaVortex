import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from Core.Database.DatabaseService import DatabaseService


def Run() -> int:
    Db = DatabaseService()
    for Stmt in [
        "DELETE FROM ContentClassificationRules WHERE RuleName = 'AnimeBySignal'",
        "ALTER TABLE ContentClassificationRules DROP COLUMN IF EXISTS MotionFractionMin",
        "ALTER TABLE ContentClassificationRules DROP COLUMN IF EXISTS MotionFractionMax",
        "ALTER TABLE ContentClassificationRules DROP COLUMN IF EXISTS SceneChangeRateMin",
        "ALTER TABLE ContentClassificationRules DROP COLUMN IF EXISTS SceneChangeRateMax",
        "ALTER TABLE ContentClassificationRules DROP COLUMN IF EXISTS LumaVarianceMin",
        "ALTER TABLE ContentClassificationRules DROP COLUMN IF EXISTS LumaVarianceMax",
        "ALTER TABLE MediaFiles DROP COLUMN IF EXISTS MotionFraction",
        "ALTER TABLE MediaFiles DROP COLUMN IF EXISTS SceneChangeRatePerMin",
        "ALTER TABLE MediaFiles DROP COLUMN IF EXISTS LumaVariance",
    ]:
        Db.ExecuteNonQuery(Stmt, ())
    RulesRemaining = Db.ExecuteQuery(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='contentclassificationrules' "
        "AND column_name IN ('motionfractionmin','motionfractionmax','scenechangeratemin','scenechangeratemax','lumavariancemin','lumavariancemax') "
        "ORDER BY column_name",
        (),
    )
    MediaRemaining = Db.ExecuteQuery(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='mediafiles' "
        "AND column_name IN ('motionfraction','scenechangeratepermin','lumavariance') "
        "ORDER BY column_name",
        (),
    )
    Rule = Db.ExecuteQuery(
        "SELECT COUNT(*) AS N FROM ContentClassificationRules WHERE RuleName = 'AnimeBySignal'",
        (),
    )
    print(f"Signal cols on ContentClassificationRules remaining: {[R.get('column_name') for R in RulesRemaining]} (want [])")
    print(f"Signal cols on MediaFiles remaining: {[R.get('column_name') for R in MediaRemaining]} (want [])")
    print(f"AnimeBySignal rows remaining: {Rule[0].get('N') if Rule else '?'} (want 0)")
    return 0


if __name__ == "__main__":
    sys.exit(Run())
