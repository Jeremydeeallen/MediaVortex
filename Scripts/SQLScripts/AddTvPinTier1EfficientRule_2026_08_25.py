# directive: tv-tier1-classifier-pin
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


RULE_NAME = 'TvPinTier1Efficient'
PRIORITY = 20
TARGET_PROFILE = 'AV1 Tier 1 Efficient'
FOLDER_PATTERN = 'T:\\%'
DESCRIPTION = 'TV storage root pin: every T:\\ file assigns to Tier 1 (downscale 1080p+ to 720p @ 900 kbps).'


# directive: tv-tier1-classifier-pin
def Run():
    Db = DatabaseService()
    Existing = Db.ExecuteQuery(
        "SELECT Id FROM ContentClassificationRules WHERE RuleName = %s",
        (RULE_NAME,),
    )
    if Existing:
        RuleId = Existing[0].get('Id')
        Db.ExecuteNonQuery(
            "UPDATE ContentClassificationRules "
            "   SET Priority=%s, IsActive=TRUE, AssignProfileName=%s, "
            "       FolderPathPattern=%s, BitrateKbpsMin=NULL, BitrateKbpsMax=NULL, "
            "       ResolutionCategory=NULL, CodecIn=NULL, Description=%s "
            " WHERE Id=%s",
            (PRIORITY, TARGET_PROFILE, FOLDER_PATTERN, DESCRIPTION, RuleId),
        )
        print(f"Updated existing rule '{RULE_NAME}' (Id={RuleId}) to Priority={PRIORITY}, Profile={TARGET_PROFILE!r}, Pattern={FOLDER_PATTERN!r}.")
        return 0
    Db.ExecuteNonQuery(
        "INSERT INTO ContentClassificationRules "
        "  (Priority, RuleName, IsActive, AssignProfileName, FolderPathPattern, Description) "
        "VALUES (%s, %s, TRUE, %s, %s, %s) "
        "ON CONFLICT (Priority) DO UPDATE SET "
        "  RuleName=EXCLUDED.RuleName, IsActive=EXCLUDED.IsActive, "
        "  AssignProfileName=EXCLUDED.AssignProfileName, "
        "  FolderPathPattern=EXCLUDED.FolderPathPattern, Description=EXCLUDED.Description",
        (PRIORITY, RULE_NAME, TARGET_PROFILE, FOLDER_PATTERN, DESCRIPTION),
    )
    print(f"Inserted rule '{RULE_NAME}' at Priority={PRIORITY} -> {TARGET_PROFILE!r}, Pattern={FOLDER_PATTERN!r}.")
    return 0


if __name__ == '__main__':
    raise SystemExit(Run())
