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