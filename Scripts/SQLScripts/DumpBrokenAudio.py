"""Dump loudness-broken transcoded files to CSV for triage."""

import csv
import sys
from pathlib import Path

RepoRoot = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RepoRoot))

from Core.Database.DatabaseService import DatabaseService

Query = """
SELECT
    id,
    filename,
    filepath,
    sourceintegratedlufs AS lufs,
    sourceloudnessrangelu AS lra,
    sourcetruepeakdbtp AS true_peak_dbtp,
    transcodedbymediavortex AS archive_replaced,
    CASE
        WHEN filename ~ '-mv-mv\\.' THEN 2
        WHEN filename ~ '-mv\\.' THEN 1
        ELSE 0
    END AS pass_count,
    CASE
        WHEN sourcetruepeakdbtp > 1 THEN 'severe_clipping'
        WHEN sourcetruepeakdbtp > 0 THEN 'clipping'
        WHEN sourceintegratedlufs < -30 THEN 'inaudibly_quiet'
        WHEN sourceintegratedlufs > -18 THEN 'very_loud'
        WHEN sourceintegratedlufs < -27 THEN 'very_quiet'
    END AS category,
    audiocodec,
    audiobitratekbps,
    audiochannellayout,
    loudnessmeasuredat
FROM mediafiles
WHERE loudnessmeasuredat IS NOT NULL
  AND filename ~ '-mv(-mv)*\\.mp4$'
  AND (
      sourcetruepeakdbtp > 0
      OR sourceintegratedlufs < -27
      OR sourceintegratedlufs > -18
  )
ORDER BY
    (sourcetruepeakdbtp > 0)::int DESC,
    sourcetruepeakdbtp DESC NULLS LAST,
    sourceintegratedlufs ASC
"""

Rows = DatabaseService.ExecuteQuery(Query)
OutputPath = RepoRoot / "broken_audio_files.csv"

if not Rows:
    print("No rows.")
    sys.exit(0)

Fieldnames = list(Rows[0].keys())

with open(OutputPath, "w", newline="", encoding="utf-8") as Fh:
    Writer = csv.DictWriter(Fh, fieldnames=Fieldnames)
    Writer.writeheader()
    for Row in Rows:
        Writer.writerow(dict(Row))

print(f"Wrote {len(Rows)} rows -> {OutputPath}")
