# directive: legacy-audio-damage-accounting | # see legacy-audio-damage-accounting.C1

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Core.Database.DatabaseService import DatabaseService


REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Reports")
REPORT_PATH = os.path.join(REPORT_DIR, "LegacyAudioDamagedMovies.csv")

BUG_REFERENCE_HEADER = (
    "# Legacy-audio-damage-accounting: the movies in this report were normalized "
    "under the deprecated acompressor+dynamic-loudnorm chain (active 2025-10-03 -> 2026-05-30). "
    "Damage is irreversible from encoded output. Operator-driven external re-acquisition is the "
    "only path to recovery. See memory/KNOWN-ISSUES.md."
)


def Main():
    """Write Reports/LegacyAudioDamagedMovies.csv with the legacy-dynamic-mode movie set."""
    Db = DatabaseService()

    Sql = (
        "SELECT mf.id AS mediafileid, mf.filename, mf.relativepath AS canonicalpath, "
        "sr.name AS storageroot, "
        "ta.attemptdate AS legacyattemptdate, ta.profilename AS legacyprofile, "
        "mf.sourceintegratedlufs, mf.audiocodec, mf.audiobitratekbps, mf.audiochannels, "
        "mf.durationminutes "
        "FROM mediafiles mf "
        "LEFT JOIN storageroots sr ON sr.id = mf.storagerootid "
        "JOIN LATERAL (SELECT attemptdate, profilename FROM transcodeattempts "
        "  WHERE mediafileid = mf.id AND success = TRUE AND ffpmpegcommand ILIKE %s "
        "    AND ffpmpegcommand NOT ILIKE %s "
        "  ORDER BY attemptdate DESC LIMIT 1) ta ON TRUE "
        "WHERE mf.audiocomplete = TRUE "
        "  AND mf.audiocorruptreason IS NULL "
        "  AND mf.audiocompletedat IS NOT NULL "
        "  AND mf.filename !~ %s "
        "  AND mf.seasonid IS NULL "
        "  AND NOT EXISTS (SELECT 1 FROM transcodeattempts ta2 "
        "    WHERE ta2.mediafileid = mf.id AND ta2.success = TRUE "
        "      AND ta2.ffpmpegcommand ILIKE %s) "
        "ORDER BY sr.name, mf.audiobitratekbps DESC NULLS LAST, mf.filename ASC"
    )
    Rows = Db.ExecuteQuery(Sql, ("%loudnorm%", "%linear=true%", "S[0-9]+E[0-9]+", "%linear=true%"))

    if not os.path.exists(REPORT_DIR):
        os.makedirs(REPORT_DIR)

    Columns = [
        "MediaFileId", "Filename", "StorageRoot", "CanonicalPath", "AudioDamageNotMaterial",
        "LegacyAttemptDate", "LegacyProfile", "SourceIntegratedLufs",
        "AudioCodec", "AudioBitrateKbps", "AudioChannels", "DurationMinutes",
    ]

    with open(REPORT_PATH, "w", newline="", encoding="utf-8") as Fh:
        Fh.write(BUG_REFERENCE_HEADER + "\n")
        Writer = csv.writer(Fh)
        Writer.writerow(Columns)
        for Row in Rows:
            StorageRootName = Row.get("StorageRoot")
            NotMaterial = (StorageRootName or "").lower() == "xxx"
            Writer.writerow([
                Row.get("MediaFileId"),
                Row.get("FileName"),
                StorageRootName,
                Row.get("CanonicalPath"),
                "TRUE" if NotMaterial else "FALSE",
                Row.get("LegacyAttemptDate"),
                Row.get("LegacyProfile"),
                Row.get("SourceIntegratedLufs"),
                Row.get("AudioCodec"),
                Row.get("AudioBitrateKbps"),
                Row.get("AudioChannels"),
                Row.get("DurationMinutes"),
            ])

    print(f"Wrote {len(Rows)} rows to {REPORT_PATH}")
    return len(Rows)


if __name__ == "__main__":
    Main()
