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