---
description: Analyze a transcode for a given media file. Pulls source (MediaFilesArchive) vs current (MediaFiles) metadata, the matching TranscodeAttempts row, and any QualityTestResults / VMAF data, and presents it as comparison tables.
argument-hint: <filename-substring-or-mediafileid>
---

Analyze the transcode history of a media file. The goal is a clear before/after picture: what the source looked like, what FFmpeg actually did to video and audio, and whether VMAF was performed.

## Steps

1. Resolve the MediaFiles row from `$ARGUMENTS`:
   - If numeric, treat as `MediaFiles.Id`.
   - Otherwise, search `MediaFiles.FileName ILIKE '%<arg>%'`. If multiple matches, list them with id + filename and stop.

2. Pull the four related records in parallel (use `py Scripts/SQLScripts/QueryDatabase.py sql "..."`):
   - `SELECT * FROM mediafilesarchive WHERE id = <id> ORDER BY archivedate DESC` -- the original metadata snapshot (one or more rows; pick the latest unless asked otherwise).
   - `SELECT * FROM mediafiles WHERE id = <id>` -- the current post-transcode state.
   - `SELECT * FROM transcodeattempts WHERE mediafileid = <id> ORDER BY attemptdate DESC` -- attempts.
   - `SELECT * FROM qualitytestresults WHERE transcodeattemptid IN (<attempt ids>)` -- VMAF, if any.

3. If `transcodeattempts.ffpmpegcommand` is truncated by the query script, fetch it without truncation via:
   ```
   py -c "import sys; sys.path.insert(0, '.'); from Core.Database.DatabaseService import DatabaseService; db = DatabaseService(); r = db.ExecuteQuery('SELECT ffpmpegcommand FROM transcodeattempts WHERE id = <attempt_id>'); print(r[0]['FfpmpegCommand'])"
   ```
   Note the column is intentionally `ffpmpegcommand` (double `p`) -- this is a known DB typo per CLAUDE.md.

4. Present three tables:

   **Source vs Current** -- container, size, duration, resolution, video codec/profile/pixfmt/bitrate, audio codec/channels/samplerate/bitrate, total frames. Show a third "Delta" column for size (MB and %).

   **Transcode attempt** -- attempt id, profile name, worker, start/complete time, wall duration, success, old/new bytes, reduction %, disposition + reason, file replaced (yes/no, type), preferred attempt flag, test variant if set.

   **Video / audio operations from the FFmpeg command** -- parse the command and show: input map (`-map`), video codec arg (`-c:v ...` -- highlight `copy` vs an encoder), video tag, audio codec/bitrate, audio filter chain (one row per filter, e.g. `acompressor`, `loudnorm`), container flags (`-movflags`). This is the most useful table for explaining "what actually happened."

   **VMAF** -- if any rows exist in `qualitytestresults`: status, vmafscore, min/max/harmonic mean/stddev, percentiles (p1/p5/p10/p25), passesthreshold, testduration. If none: state explicitly that no VMAF was performed, and cite the reason from `transcodeattempts.disposition` + `dispositionreason` (e.g. `Replace / QualityTestNotRequired` = StreamCopy strategy verified inline via checksum; VMAF not applicable).

5. Close with a one-line summary: "Source was X, FFmpeg did Y to video and Z to audio, VMAF result was W."

## Interpretation notes

- `disposition = Replace`, `dispositionreason = QualityTestNotRequired` -- typical for StreamCopy profiles (Remux / AudioFix / SubtitleFix / Quick) where `-c:v copy` is used. Verify was checksum, not VMAF. Size savings come from audio re-encode and/or container change.
- `qualitytestrequired = false` AND `qualitytestcompleted = false` AND no `qualitytestresults` row -- VMAF was deliberately skipped, not failed.
- `loudnorm` in the audio filter chain often upsamples the audio internally (e.g. source 48 kHz can come out 96 kHz). That is expected, not a bug.
- If the current `videobitratekbps` differs from source but `-c:v copy` is set, the difference is the container remeasuring -- the video stream itself is byte-identical.
- A few frames lost between source and current totals (e.g. 82441 -> 82438) is normal container metadata trim on remux, not data loss.

## Output

No file output. Just the tables and the one-line summary. The user reads them in the terminal.
