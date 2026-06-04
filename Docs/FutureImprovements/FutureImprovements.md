During file scanning can we capture number of frames? (Or the quick check before the transcoding starts? So that we don't have to hope that we capture the output from ffmpeg transcode.)


Change hardcoded FFmpeg path to configurable in the services.
Profile service has a bunch of snake case. It needs to be fixed to PascalCase

Compression potential algorhythm.

Stop transcode from web isn't workign I have to close the website to get the transcode to cancel.

Transcode attempts are logging a quality and a bitrate they shouldn't be able to do that.


Add more options in the profiles selection (Av1 with grain get's better results and a smaller file than hevc with grain.)
-c:v hevc: H.265/x265 video codec (added) uses an ffmpeg library that isn't here.
-b:v 1300k: Video bitrate 1300 kbps (from ProfileThresholds)
-c:a aac: AAC audio codec (should be changed to -c:a libopus -b:a 70k opus is better at lower bitrates.)
-b:a 70k: Audio bitrate 70 kbps (from ProfileThresholds) 
-preset medium: x265 encoding speed/quality balance
-crf 27: Constant Rate Factor (quality target)
-movflags +faststart: Optimize for web streaming
-vf scale=...: Scale to 720p with aspect ratio preservation and padding

Add smart profile assignment during file scanning

File replacement is currently event driven - We could make it more scaleable by changing it to a queue system and we could add files to it without checking their VMAF score.

Thread suspension: Use thread suspension to pause transcode jobs

## Quality Testing Service Improvements

Service startup recovery: Check for orphaned processes on service start, reattach to running processes if they exist, reset status of jobs that were running.

## Smart Crash Recovery with Process Resume

Implement intelligent crash recovery that can resume orphaned FFmpeg processes instead of killing and restarting them. This would preserve work already completed and provide better user experience.

**Key Components:**
- **FFmpeg Log File Integration**: Start FFmpeg with log file redirection (`ffmpeg ... 2> /tmp/mediavortex_job_{QueueId}.log`)
- **Process Resume Detection**: On service startup, detect orphaned FFmpeg processes and read their log files to determine current progress
- **Progress Recovery**: Parse log files to extract current frame count, processing speed, and ETA
- **Database Sync**: Update TranscodeProgress/QualityTestProgress tables with recovered progress information
- **Monitoring Thread**: Spawn background thread to monitor log file and update progress in real-time
- **Cleanup on Completion**: Remove log files when FFmpeg processes complete naturally

**Benefits:**
- No wasted work from crashes (could save hours of transcoding)
- Better user experience with preserved progress
- More efficient resource utilization
- Maintains PID tracking purpose for intelligent recovery

**Implementation Considerations:**
- Log file location strategy (temp directory vs project directory)
- Log file parsing for different FFmpeg output formats
- Cross-platform log file handling
- Cleanup of old log files
- Error handling for corrupted log files

Advanced error handling: Implement retry logic for failed quality tests, timeout handling for hung processes, and advanced error recovery patterns.

Performance optimizations: Job prioritization, resource monitoring, and advanced queue management.

Manual quality test controls: GUI for manually triggering quality tests, batch operations for skipping multiple tests, and manual override capabilities.

Database transaction management: Implement proper transaction handling for cross-service data updates and rollback mechanisms for partial failures.

Hard Coded FileManagerService

## Profile Architecture Refactoring

Refactor profile system to be more semantic and easier to manage. Currently profiles are tied to specific CRF values (e.g., "720p CRF 42 12grain", "720p CRF 36 HD 8 grain"). 

**Proposed Structure:**

### Profile Categories:
1. **Resolution Strategy**
   - "Downscale to 720p" - Target resolution of 720p
   - "Downscale to 1080p" - Target resolution of 1080p  
   - "Compress without downscaling" - Keep same resolution, reduce file size
   - "No downscaling" - Maintain original resolution

2. **Media Type Options**
   - "With Film Grain" - Film grain settings enabled (for grainy content)
   - "Clean/No Grain" - No film grain settings (for clean content)
   - "Animation" - Optimized settings for animated content
   - "Live Action" - Default settings for live-action content

3. **Quality Tier (Dynamic CRF range)**
   - "Aggressive" - CRF 40-45 (maximum compression, lower quality)
   - "Balanced" - CRF 30-35 (good balance of size and quality)
   - "High Quality" - CRF 25-30 (prioritize quality)
   - "Maximum" - CRF 20-25 (highest quality, largest files)

**Benefits:**
- More user-friendly profile selection (select resolution + grain type, not CRF numbers)
- CRF becomes a calculated value based on quality tier and adaptive adjustment
- Easier to understand what each profile does
- Better separation of concerns (resolution strategy vs media characteristics vs quality)

**Implementation Notes:**
- Would require database schema changes to Profiles and ProfileThresholds tables
- CRF would be calculated dynamically based on quality tier + adaptive adjustments
- Migration script needed to convert existing profiles to new structure
- UI changes required for new profile selection interface

## Replace Directory Walk with `zfs diff` on Porky (2026-06-04)

Today MediaVortex walks directories on Porky (R740xd, 65.5 T `tank`, ZFS) to detect new / moved / renamed media. Walking a multi-TB tree to find a handful of changes is the wrong shape — the filesystem already knows what changed. Switch the scanner to consume `zfs diff` between periodic snapshots and ffprobe only the delta.

**How it works:**
- Take periodic snapshots of `tank` (or the specific media datasets) via `sanoid` — e.g. 12 × 5-min, 24 × hourly, 7 × daily.
- Run `zfs diff <prev-snap> <curr-snap>` against the last-processed snapshot. Output is metadata-only and scales with churn, not pool size — single-digit seconds on a 65 T pool with normal ingest churn.
- Parse the four prefixes:
  - `+ F <path>` — new file → enqueue for ffprobe + DB insert
  - `- F <path>` — deleted → soft-delete in DB
  - `R F <old> -> <new>` — rename (single correlated line) → row update, no re-probe
  - `M F <path>` — modified → re-probe (rare for finished media; common during write-in-progress)
- Persist `last_processed_snapshot` so the next run resumes from there.

**Wins:**
- Walk cost goes from O(tree size) to O(changes).
- Renames stop being a costly "find by inode" or "match by hash" — `zfs diff` emits the pair directly.
- ffprobe load drops to just the files that actually changed.

**Gotchas to design for:**
- **Catch-up after downtime**: if `last_processed_snapshot` got pruned by sanoid retention, fall back to an older retained snapshot or a one-time full walk. Retention policy and "last seen" state must align.
- **Where ffprobe runs**: `zfs diff` happens on Porky, but MediaVortex lives elsewhere. Either reuse the existing NFS/SMB mount path or run a tiny probe-agent on Porky that returns ffprobe JSON over HTTP/SSH.
- **Write-in-progress files**: a `+ F` event can fire before the file is fully written. Either wait for `M F` to stop firing for N seconds (quiescence), or check size-stability before probing.
- **Datasets vs filesystem-root paths**: `zfs diff` paths are dataset-relative; need a small mapping layer to translate to MediaVortex's logical paths.

**Status:** Parked — MediaVortex is mid-database-overhaul. Revisit once the DB layer stabilizes. Infrastructure side (sanoid retention on `tank`) can be set up independently and is value-positive even without MediaVortex consuming it. 