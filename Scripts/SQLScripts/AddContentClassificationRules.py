"""Create ContentClassificationRules table + AssignedProfileSource column +
seed baseline rules.

See Features/ContentClassifier/content-classifier.feature.md criteria 1-3, 14.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from Core.Database.DatabaseService import DatabaseService


CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS ContentClassificationRules (
    Id BIGSERIAL PRIMARY KEY,
    RuleName TEXT NOT NULL,
    Priority INTEGER NOT NULL,
    IsActive BOOLEAN NOT NULL DEFAULT TRUE,
    BitrateKbpsMin INTEGER,
    BitrateKbpsMax INTEGER,
    ResolutionCategory TEXT,
    CodecIn TEXT,
    MotionFractionMin DOUBLE PRECISION,
    MotionFractionMax DOUBLE PRECISION,
    SceneChangeRateMin DOUBLE PRECISION,
    SceneChangeRateMax DOUBLE PRECISION,
    LumaVarianceMin DOUBLE PRECISION,
    LumaVarianceMax DOUBLE PRECISION,
    FolderPathPattern TEXT,
    AssignProfileName TEXT NOT NULL,
    Description TEXT,
    LastUpdated TIMESTAMP DEFAULT NOW(),
    Source TEXT
)
"""

CREATE_PRIORITY_UNIQUE = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_contentclassrules_priority_unique "
    "ON ContentClassificationRules (Priority)"
)

ADD_PROFILE_SOURCE_COL = (
    "ALTER TABLE MediaFiles ADD COLUMN IF NOT EXISTS AssignedProfileSource TEXT"
)

# Baseline seeded rules. Profile names that may not yet exist at migration
# time are inserted IsActive=FALSE with a Description noting the dependency.
# Operator flips IsActive=TRUE once the corresponding profile lands.
SEED_RULES = [
    {
        "Priority": 10,
        "RuleName": "AlreadyAv1Skip",
        "CodecIn": "av1",
        "AssignProfileName": "__skip__",
        "Description": "Source is already AV1; classifier marks AssignedProfileSource=classifier_skip_av1 and leaves AssignedProfile NULL.",
        "IsActive": True,
    },
    {
        "Priority": 30,
        "RuleName": "AnimeByFolder",
        "FolderPathPattern": "%Anime%",
        "AssignProfileName": "NVENC AV1 P7 HQ CQ29 G480 ANIME -720p",
        "Description": "Folder-pattern detection for animation. Depends on anime profile from nvenc-rate-anchored.feature.md.",
        "IsActive": False,
    },
    {
        "Priority": 40,
        "RuleName": "AnimeBySignal",
        "MotionFractionMax": 0.30,
        "SceneChangeRateMax": 2.0,
        "LumaVarianceMax": 400.0,
        "AssignProfileName": "NVENC AV1 P7 HQ CQ29 G480 ANIME -720p",
        "Description": "Signal-based animation detection. Requires ContentSignals columns populated. Depends on anime profile.",
        "IsActive": False,
    },
    {
        "Priority": 50,
        "RuleName": "LowBitrateLiveAction",
        "BitrateKbpsMax": 1500,
        "CodecIn": "h264,hevc",
        "AssignProfileName": "NVENC AV1 P7 VBR 30pct -720p",
        "Description": "Already-compressed live action -- rate-anchored profile prevents CQ-mode ballooning. Depends on VBR profile from nvenc-rate-anchored.feature.md.",
        "IsActive": False,
    },
    {
        "Priority": 70,
        "RuleName": "Default1080pLiveAction",
        "ResolutionCategory": "1080p",
        "AssignProfileName": "NVENC AV1 P7 UHQ CQ32 -720p",
        "Description": "Default for 1080p live action. References the existing production CQ profile.",
        "IsActive": True,
    },
    {
        "Priority": 80,
        "RuleName": "Default720pLiveAction",
        "ResolutionCategory": "720p",
        "AssignProfileName": "NVENC AV1 P7 UHQ CQ32 -480p",
        "Description": "Default for 720p live action.",
        "IsActive": True,
    },
]


def Run() -> int:
    Db = DatabaseService()
    Db.ExecuteNonQuery(CREATE_TABLE, ())
    Db.ExecuteNonQuery(CREATE_PRIORITY_UNIQUE, ())
    Db.ExecuteNonQuery(ADD_PROFILE_SOURCE_COL, ())

    SeedSql = """
        INSERT INTO ContentClassificationRules
            (Priority, RuleName, IsActive, BitrateKbpsMin, BitrateKbpsMax,
             ResolutionCategory, CodecIn, MotionFractionMin, MotionFractionMax,
             SceneChangeRateMin, SceneChangeRateMax, LumaVarianceMin, LumaVarianceMax,
             FolderPathPattern, AssignProfileName, Description, Source)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'InitialSeed')
        ON CONFLICT (Priority) DO NOTHING
    """

    InsertedCount = 0
    for R in SEED_RULES:
        N = Db.ExecuteNonQuery(SeedSql, (
            R["Priority"],
            R["RuleName"],
            R.get("IsActive", True),
            R.get("BitrateKbpsMin"),
            R.get("BitrateKbpsMax"),
            R.get("ResolutionCategory"),
            R.get("CodecIn"),
            R.get("MotionFractionMin"),
            R.get("MotionFractionMax"),
            R.get("SceneChangeRateMin"),
            R.get("SceneChangeRateMax"),
            R.get("LumaVarianceMin"),
            R.get("LumaVarianceMax"),
            R.get("FolderPathPattern"),
            R["AssignProfileName"],
            R.get("Description"),
        ))
        InsertedCount += N or 0

    print(f"Seeded {InsertedCount} new rule(s). Current rule set:")
    Rows = Db.ExecuteQuery(
        "SELECT Priority, RuleName, IsActive, AssignProfileName "
        "FROM ContentClassificationRules ORDER BY Priority",
        (),
    )
    for R in Rows:
        Active = "ON " if R.get("IsActive") else "off"
        print(f"  [{Active}] {R.get('Priority'):>3} {R.get('RuleName'):<28} -> {R.get('AssignProfileName')}")

    return 0


if __name__ == "__main__":
    sys.exit(Run())
