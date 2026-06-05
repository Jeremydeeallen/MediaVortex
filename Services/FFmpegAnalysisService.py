import os
import json
import re
import uuid
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from pathlib import Path
from Models.FFmpegAnalysisModel import FFmpegAnalysisModel
from Services.FFmpegService import FFmpegService
from Services.LoggingService import LoggingService
# directive: path-schema-migration | # see path.S8
from Core.Path.LocalPath import LocalBasename


# directive: path-schema-migration | # see path.S8
def _LocalExists(Value): return bool(Value) and os.path.exists(Value)


# directive: path-schema-migration | # see path.S8
def _LocalGetSize(Value): return os.path.getsize(Value)


class FFmpegAnalysisService:
    """Business service for FFmpeg media analysis operations."""
    
    def __init__(self, FFmpegServiceInstance: FFmpegService = None, DatabaseService = None, FFprobePath: str = None):
        self.FFmpegService = FFmpegServiceInstance or FFmpegService(FFprobePath=FFprobePath)
        self.DatabaseService = DatabaseService
    
    # directive: path-schema-migration | # see path.S8
    def AnalyzeMediaFile(self, FilePath: str) -> FFmpegAnalysisModel:
        """Analyze a media file and return comprehensive metadata."""
        try:
            LoggingService.LogFunctionEntry("AnalyzeMediaFile", 'FFmpegAnalysisService', FilePath)

            # Create analysis model
            AnalysisModel = FFmpegAnalysisModel()
            AnalysisModel.FilePath = FilePath
            AnalysisModel.FileName = LocalBasename(FilePath)
            AnalysisModel.FileExtension = Path(FilePath).suffix.lower()

            # Get file size
            if _LocalExists(FilePath):
                AnalysisModel.FileSizeMB = _LocalGetSize(FilePath) / (1024 * 1024)
            
            # Execute FFprobe analysis. ExecuteFFprobe is responsible for logging the
            # subprocess failure (with stderr/stdout/command) -- don't double-log here,
            # just propagate the error onto the analysis model so the caller has the cause.
            FFprobeResult = self.FFmpegService.ExecuteFFprobe(FilePath)

            if not FFprobeResult['Success']:
                Command = FFprobeResult.get('Command', 'Unknown command')
                ErrorMessage = FFprobeResult.get('ErrorMessage', 'FFprobe analysis failed')
                AnalysisModel.ErrorMessage = f"{ErrorMessage} - Command: {Command}"
                return AnalysisModel

            # Parse FFprobe JSON output
            try:
                MediaInfo = json.loads(FFprobeResult['Output'])
                self.ParseFFprobeOutput(AnalysisModel, MediaInfo)
                AnalysisModel.Success = True

            except json.JSONDecodeError as e:
                Command = FFprobeResult.get('Command', 'Unknown command')
                OutputSnippet = (FFprobeResult.get('Output') or '')[:500]
                AnalysisModel.ErrorMessage = f"Failed to parse FFprobe JSON output: {str(e)} - Command: {Command}"
                LoggingService.LogException(
                    f"FFprobe JSON parsing failed for {FilePath}. Output snippet: {OutputSnippet!r}. Command: {Command}",
                    e, 'AnalyzeMediaFile', 'FFmpegAnalysisService'
                )
                return AnalysisModel
            
            # Extract metadata from filename if not found in embedded tags
            if not AnalysisModel.Title and not AnalysisModel.ShowTitle:
                FilenameMetadata = self.ExtractMetadataFromFilename(AnalysisModel.FileName)
                self.ApplyFilenameMetadata(AnalysisModel, FilenameMetadata)
            
            LoggingService.LogDebug(f"Successfully analyzed file: {FilePath}", 'AnalyzeMediaFile', 'FFmpegAnalysisService')
            return AnalysisModel
            
        except Exception as e:
            LoggingService.LogException("Error analyzing media file", e, 'AnalyzeMediaFile', 'FFmpegAnalysisService')
            AnalysisModel = FFmpegAnalysisModel()
            AnalysisModel.FilePath = FilePath
            AnalysisModel.ErrorMessage = f"Analysis error: {str(e)}"
            return AnalysisModel
    
    def ExtractTotalFrames(self, VideoStream: Dict[str, Any], Format: Dict[str, Any]) -> Optional[int]:
        """Extract total frames with codec-specific fallback strategies."""
        try:
            codec = VideoStream.get('codec_name', '').lower()
            
            # Strategy 1: Direct nb_frames (MPEG4, some others)
            totalFrames = VideoStream.get('nb_frames')
            if totalFrames:
                try:
                    return int(totalFrames)
                except (ValueError, TypeError):
                    pass
            
            # Strategy 2: AV1 - Extract from tags
            if codec == 'av1':
                tags = VideoStream.get('tags', {})
                numberFrames = tags.get('NUMBER_OF_FRAMES')
                if numberFrames:
                    try:
                        return int(numberFrames)
                    except (ValueError, TypeError):
                        pass
            
            # Strategy 3: Calculate from duration × frame rate (H264, HEVC, others)
            duration = Format.get('duration')
            frameRate = VideoStream.get('r_frame_rate')
            if duration and frameRate and '/' in frameRate:
                try:
                    numerator, denominator = frameRate.split('/')
                    fps = float(numerator) / float(denominator)
                    calculatedFrames = int(float(duration) * fps)
                    LoggingService.LogInfo(f"Calculated frames from duration×fps: {calculatedFrames} (duration: {duration}s, fps: {fps})", 'ExtractTotalFrames', 'FFmpegAnalysisService')
                    return calculatedFrames
                except (ValueError, TypeError, ZeroDivisionError) as e:
                    LoggingService.LogWarning(f"Failed to calculate frames from duration×fps: {e}", 'ExtractTotalFrames', 'FFmpegAnalysisService')
            
            # Strategy 4: Try avg_frame_rate as fallback
            avgFrameRate = VideoStream.get('avg_frame_rate')
            if duration and avgFrameRate and '/' in avgFrameRate:
                try:
                    numerator, denominator = avgFrameRate.split('/')
                    fps = float(numerator) / float(denominator)
                    calculatedFrames = int(float(duration) * fps)
                    LoggingService.LogInfo(f"Calculated frames from duration×avg_fps: {calculatedFrames} (duration: {duration}s, avg_fps: {fps})", 'ExtractTotalFrames', 'FFmpegAnalysisService')
                    return calculatedFrames
                except (ValueError, TypeError, ZeroDivisionError) as e:
                    LoggingService.LogWarning(f"Failed to calculate frames from duration×avg_fps: {e}", 'ExtractTotalFrames', 'FFmpegAnalysisService')
            
            LoggingService.LogWarning(f"Could not extract total frames for codec: {codec}", 'ExtractTotalFrames', 'FFmpegAnalysisService')
            return None
            
        except Exception as e:
            LoggingService.LogException("Error extracting total frames", e, 'ExtractTotalFrames', 'FFmpegAnalysisService')
            return None
    
    def ParseFFprobeOutput(self, AnalysisModel: FFmpegAnalysisModel, MediaInfo: Dict[str, Any]):
        """Parse FFprobe JSON output and populate analysis model."""
        try:
            # Extract format information
            Format = MediaInfo.get('format', {})

            # Duration -- prefer format.duration, fall back to the longest stream
            # duration (some MKV/AVI containers don't populate format.duration).
            # Mutate Format so downstream consumers (e.g. ExtractTotalFrames
            # Strategy 3) see the resolved value too.
            DurationSeconds = Format.get('duration')
            if not DurationSeconds:
                StreamDurations = []
                for Stream in MediaInfo.get('streams', []):
                    StreamDur = Stream.get('duration')
                    if StreamDur:
                        try:
                            StreamDurations.append(float(StreamDur))
                        except (ValueError, TypeError):
                            pass
                if StreamDurations:
                    DurationSeconds = max(StreamDurations)
                    Format['duration'] = DurationSeconds
            if DurationSeconds:
                try:
                    AnalysisModel.DurationMinutes = float(DurationSeconds) / 60.0
                except (ValueError, TypeError):
                    pass
            
            # Container format
            AnalysisModel.ContainerFormat = Format.get('format_name', '')
            
            # Overall bitrate from format level
            FormatBitrate = Format.get('bit_rate')
            if FormatBitrate:
                try:
                    AnalysisModel.OverallBitrate = int(FormatBitrate)
                    FormatBitrateKbps = AnalysisModel.OverallBitrate // 1000
                    LoggingService.LogInfo(f"Found format bitrate: {FormatBitrateKbps} kbps for {AnalysisModel.FilePath}", 'ParseFFprobeOutput', 'FFmpegAnalysisService')
                    # If we don't have video bitrate, use format bitrate as video bitrate
                    if not AnalysisModel.VideoBitrateKbps:
                        AnalysisModel.VideoBitrateKbps = FormatBitrateKbps
                        LoggingService.LogInfo(f"Set video bitrate from format: {FormatBitrateKbps} kbps", 'ParseFFprobeOutput', 'FFmpegAnalysisService')
                    # If we don't have audio bitrate, estimate it (typically 10-20% of total)
                    if not AnalysisModel.AudioBitrateKbps:
                        AnalysisModel.AudioBitrateKbps = FormatBitrateKbps // 10  # Rough estimate
                        LoggingService.LogInfo(f"Set audio bitrate from format: {FormatBitrateKbps // 10} kbps", 'ParseFFprobeOutput', 'FFmpegAnalysisService')
                except (ValueError, TypeError):
                    pass
            
            # Creation and modification dates
            CreationTime = Format.get('creation_time')
            if CreationTime:
                try:
                    from datetime import datetime
                    AnalysisModel.CreationDate = datetime.fromisoformat(CreationTime.replace('Z', '+00:00'))
                except (ValueError, TypeError):
                    pass
            
            # Extract stream information
            Streams = MediaInfo.get('streams', [])
            VideoStream = None
            AudioStreams = []
            SubtitleStreams = []

            for Stream in Streams:
                CodecType = Stream.get('codec_type', '')
                if CodecType == 'video' and VideoStream is None:
                    VideoStream = Stream
                elif CodecType == 'audio':
                    AudioStreams.append(Stream)
                elif CodecType == 'subtitle':
                    SubtitleStreams.append(Stream)

            # Select preferred audio stream (English preferred, most channels as tiebreaker)
            AudioStream, AudioStreamIndex, AllAudioLanguages, HasExplicitEnglish = self.SelectPreferredAudioStream(AudioStreams)
            AnalysisModel.AudioStreamIndex = AudioStreamIndex
            AnalysisModel.AudioLanguages = ','.join(AllAudioLanguages) if AllAudioLanguages else None
            AnalysisModel.HasExplicitEnglishAudio = HasExplicitEnglish
            
            # Process video stream
            if VideoStream:
                AnalysisModel.VideoCodec = VideoStream.get('codec_name', '')
                
                # Resolution
                Width = VideoStream.get('width')
                Height = VideoStream.get('height')
                if Width and Height:
                    AnalysisModel.Resolution = f"{Width}x{Height}"
                
                # Frame rate
                FrameRate = VideoStream.get('r_frame_rate', '')
                if FrameRate and '/' in FrameRate:
                    try:
                        Numerator, Denominator = FrameRate.split('/')
                        AnalysisModel.FrameRate = float(Numerator) / float(Denominator)
                    except (ValueError, ZeroDivisionError):
                        pass
                
                # Video bitrate
                VideoBitrate = VideoStream.get('bit_rate')
                if VideoBitrate:
                    try:
                        AnalysisModel.VideoBitrateKbps = int(VideoBitrate) // 1000
                        LoggingService.LogInfo(f"Set video bitrate from stream: {AnalysisModel.VideoBitrateKbps} kbps", 'ParseFFprobeOutput', 'FFmpegAnalysisService')
                    except (ValueError, TypeError):
                        pass
                else:
                    LoggingService.LogInfo(f"No bitrate in video stream, keeping existing: {AnalysisModel.VideoBitrateKbps} kbps", 'FFmpegAnalysisService', 'ParseFFprobeOutput')
                
                # Extract new metadata fields from video stream
                AnalysisModel.TotalFrames = self.ExtractTotalFrames(VideoStream, Format)
                AnalysisModel.CodecProfile = VideoStream.get('profile', '')
                AnalysisModel.ColorRange = VideoStream.get('color_range', '')
                AnalysisModel.FieldOrder = VideoStream.get('field_order', '')
                AnalysisModel.HasBFrames = VideoStream.get('has_b_frames', 0)
                AnalysisModel.RefFrames = VideoStream.get('refs', 0)
                AnalysisModel.PixelFormat = VideoStream.get('pix_fmt', '')
                AnalysisModel.Level = VideoStream.get('level', 0)
            
            # Process audio stream
            if AudioStream:
                AnalysisModel.AudioCodec = AudioStream.get('codec_name', '')
                
                # Audio bitrate
                AudioBitrate = AudioStream.get('bit_rate')
                if AudioBitrate:
                    try:
                        AnalysisModel.AudioBitrateKbps = int(AudioBitrate) // 1000
                    except (ValueError, TypeError):
                        pass
                
                # Audio channels
                Channels = AudioStream.get('channels')
                if Channels:
                    AnalysisModel.AudioChannels = f"{Channels} channels"
                
                # Language
                Language = AudioStream.get('tags', {}).get('language')
                if Language:
                    AnalysisModel.Language = Language
                
                # Extract new audio metadata fields
                AnalysisModel.AudioChannels = AudioStream.get('channels', 0)
                AnalysisModel.AudioSampleRate = AudioStream.get('sample_rate', 0)
                AnalysisModel.AudioSampleFormat = AudioStream.get('sample_fmt', '')
                AnalysisModel.AudioChannelLayout = AudioStream.get('channel_layout', '')
            
            # Process subtitle streams
            if SubtitleStreams:
                SubtitleLanguages = []
                SubtitleCodecs = []
                for SubStream in SubtitleStreams:
                    Language = SubStream.get('tags', {}).get('language')
                    if Language:
                        SubtitleLanguages.append(Language)
                    CodecName = SubStream.get('codec_name', '')
                    if CodecName and CodecName not in SubtitleCodecs:
                        SubtitleCodecs.append(CodecName)
                if SubtitleLanguages:
                    AnalysisModel.Subtitles = ', '.join(SubtitleLanguages)
                if SubtitleCodecs:
                    AnalysisModel.SubtitleFormats = ','.join(SubtitleCodecs)

                # Select preferred subtitle stream for potential SubtitleFix
                SelectedSubStream, SubStreamIndex, _ = self.SelectPreferredSubtitleStream(SubtitleStreams)
                if SelectedSubStream:
                    AnalysisModel.SubtitleStreamIndex = SubStreamIndex
                    AnalysisModel.SubtitleCodec = SelectedSubStream.get('codec_name', '')
            
            # Calculate bitrate from file size and duration if still missing
            if not AnalysisModel.VideoBitrateKbps and AnalysisModel.DurationMinutes and AnalysisModel.FileSizeMB:
                try:
                    # Calculate total bitrate from file size and duration
                    DurationSeconds = AnalysisModel.DurationMinutes * 60
                    TotalBitrateKbps = (AnalysisModel.FileSizeMB * 8 * 1024) / DurationSeconds
                    if TotalBitrateKbps > 0:
                        # Estimate video bitrate (typically 80-90% of total)
                        AnalysisModel.VideoBitrateKbps = int(TotalBitrateKbps * 0.85)
                        # Estimate audio bitrate (typically 10-20% of total)
                        if not AnalysisModel.AudioBitrateKbps:
                            AnalysisModel.AudioBitrateKbps = int(TotalBitrateKbps * 0.15)
                except (ValueError, TypeError, ZeroDivisionError):
                    pass
            
            # Extract metadata tags
            Tags = Format.get('tags', {})
            if Tags:
                AnalysisModel.Title = Tags.get('title')
                AnalysisModel.ShowTitle = Tags.get('show') or Tags.get('series')
                AnalysisModel.Season = Tags.get('season_number')
                AnalysisModel.Episode = Tags.get('episode_number')
                AnalysisModel.EpisodeTitle = Tags.get('episode')
                AnalysisModel.Year = Tags.get('year')
                AnalysisModel.Genre = Tags.get('genre')
                AnalysisModel.Language = Tags.get('language') or AnalysisModel.Language
                AnalysisModel.ReleaseGroup = Tags.get('release_group')
            
        except Exception as e:
            LoggingService.LogException("Error parsing FFprobe output", e, 'ParseFFprobeOutput', 'FFmpegAnalysisService')
    
    def SelectPreferredAudioStream(self, AudioStreams: list) -> tuple:
        """Select the preferred audio stream, preferring English with most channels.

        Returns:
            Tuple of (SelectedStream dict or None, 0-based audio stream index,
                      AllLanguages list, HasExplicitEnglish bool)
        """
        if not AudioStreams:
            return None, 0, [], False

        # Collect all audio stream languages
        AllLanguages = []
        for Stream in AudioStreams:
            Language = Stream.get('tags', {}).get('language', '')
            if Language:
                AllLanguages.append(Language.lower())
            else:
                AllLanguages.append('und')  # undetermined

        # Find English streams
        EnglishStreams = []
        for Index, Stream in enumerate(AudioStreams):
            Language = Stream.get('tags', {}).get('language', '')
            if Language.lower() in ('eng', 'en'):
                EnglishStreams.append((Index, Stream))

        HasExplicitEnglish = len(EnglishStreams) > 0

        if EnglishStreams:
            # Pick English stream with most channels (surround > stereo)
            BestIndex, BestStream = max(EnglishStreams, key=lambda x: x[1].get('channels', 0))
            LoggingService.LogInfo(
                f"Selected English audio stream index {BestIndex} ({BestStream.get('channels', '?')}ch) "
                f"from {len(AudioStreams)} audio stream(s)",
                'SelectPreferredAudioStream', 'FFmpegAnalysisService'
            )
            return BestStream, BestIndex, AllLanguages, HasExplicitEnglish

        # No English streams found — fall back to first stream
        LoggingService.LogWarning(
            f"No English audio stream found among {len(AudioStreams)} stream(s) (languages: {AllLanguages}), using first stream",
            'SelectPreferredAudioStream', 'FFmpegAnalysisService'
        )
        return AudioStreams[0], 0, AllLanguages, HasExplicitEnglish

    # Subtitle codecs that are text-based and can be converted to SRT/mov_text
    TEXT_SUBTITLE_CODECS = {'ass', 'ssa', 'srt', 'subrip', 'webvtt', 'mov_text'}
    # Subtitle codecs that are image-based and require OCR (skipped for now)
    IMAGE_SUBTITLE_CODECS = {'hdmv_pgs_subtitle', 'pgssub', 'dvdsub', 'dvd_subtitle', 'dvbsub', 'dvb_subtitle'}

    def SelectPreferredSubtitleStream(self, SubtitleStreams: list) -> tuple:
        """Select the preferred subtitle stream for subtitle fix.
        Prefers English text-based subtitles. Skips image-based (PGS/VOBSUB).

        Returns:
            Tuple of (SelectedStream dict or None, 0-based subtitle stream index, skip_reason or None)
        """
        if not SubtitleStreams:
            return None, 0, "no_subtitles"

        # Filter to text-based subtitle streams only
        TextStreams = []
        for Index, Stream in enumerate(SubtitleStreams):
            CodecName = Stream.get('codec_name', '').lower()
            if CodecName in self.TEXT_SUBTITLE_CODECS:
                TextStreams.append((Index, Stream))

        if not TextStreams:
            return None, 0, "pgs_only"

        # Find English text streams
        EnglishTextStreams = []
        for Index, Stream in TextStreams:
            Language = Stream.get('tags', {}).get('language', '').lower()
            if Language in ('eng', 'en', 'english'):
                EnglishTextStreams.append((Index, Stream))

        if EnglishTextStreams:
            # Prefer ASS/SSA (the ones causing burn-in) so we convert them
            for Index, Stream in EnglishTextStreams:
                if Stream.get('codec_name', '').lower() in ('ass', 'ssa'):
                    LoggingService.LogInfo(
                        f"Selected English ASS subtitle stream index {Index} from {len(SubtitleStreams)} subtitle stream(s)",
                        'SelectPreferredSubtitleStream', 'FFmpegAnalysisService'
                    )
                    return Stream, Index, None
            # Fall back to first English text stream
            LoggingService.LogInfo(
                f"Selected English subtitle stream index {EnglishTextStreams[0][0]} from {len(SubtitleStreams)} subtitle stream(s)",
                'SelectPreferredSubtitleStream', 'FFmpegAnalysisService'
            )
            return EnglishTextStreams[0][1], EnglishTextStreams[0][0], None

        # No English subtitles — use first text stream
        LoggingService.LogInfo(
            f"No English subtitle found among {len(SubtitleStreams)} stream(s), using first text stream (index {TextStreams[0][0]})",
            'SelectPreferredSubtitleStream', 'FFmpegAnalysisService'
        )
        return TextStreams[0][1], TextStreams[0][0], None

    def ExtractMetadataFromFilename(self, FileName: str) -> Dict[str, Any]:
        """Extract metadata from filename using pattern matching."""
        try:
            Result = {
                'Title': None,
                'ShowTitle': None,
                'Season': None,
                'Episode': None,
                'EpisodeTitle': None,
                'Year': None,
                'Quality': None,
                'Source': None,
                'ReleaseGroup': None
            }
            
            # Remove file extension
            NameWithoutExt = Path(FileName).stem
            
            # Extract year (4 digits)
            YearMatch = re.search(r'\b(19|20)\d{2}\b', NameWithoutExt)
            if YearMatch:
                Result['Year'] = int(YearMatch.group())
            
            # Extract season/episode patterns
            SeasonEpisodePatterns = [
                r'[Ss](\d+)[Ee](\d+)',  # S01E01, S1E1
                r'(\d+)x(\d+)',         # 1x01, 01x01
                r'Season\s*(\d+).*Episode\s*(\d+)',  # Season 1 Episode 1
                r'(\d+)\.(\d+)',        # 1.01, 01.01
            ]
            
            for Pattern in SeasonEpisodePatterns:
                Match = re.search(Pattern, NameWithoutExt, re.IGNORECASE)
                if Match:
                    Result['Season'] = f"S{Match.group(1).zfill(2)}"
                    Result['Episode'] = f"E{Match.group(2).zfill(2)}"
                    break
            
            # Extract show title (everything before season/episode)
            if Result['Season'] and Result['Episode']:
                # Find the position of season/episode pattern
                SeasonEpisodePattern = r'[Ss]\d+[Ee]\d+|\d+x\d+|Season\s*\d+.*Episode\s*\d+|\d+\.\d+'
                Match = re.search(SeasonEpisodePattern, NameWithoutExt, re.IGNORECASE)
                if Match:
                    ShowTitle = NameWithoutExt[:Match.start()].strip()
                    # Clean up the show title
                    ShowTitle = re.sub(r'[-._]', ' ', ShowTitle).strip()
                    Result['ShowTitle'] = ShowTitle
                    Result['Title'] = ShowTitle  # Use show title as main title
            
            # Extract quality indicators
            QualityPatterns = ['2160p', '4K', '1080p', '720p', '480p', '360p', 'HD', 'SD']
            for Pattern in QualityPatterns:
                if Pattern.lower() in NameWithoutExt.lower():
                    Result['Quality'] = Pattern
                    break
            
            # Extract source indicators
            SourcePatterns = ['BluRay', 'Blu-ray', 'BDRip', 'BRRip', 'HDTV', 'WEBRip', 'WEB-DL', 'DVDRip', 'TVRip', 'CAM', 'TS', 'TC']
            for Pattern in SourcePatterns:
                if Pattern.lower() in NameWithoutExt.lower():
                    Result['Source'] = Pattern
                    break
            
            # Extract release group (usually in brackets or parentheses at the end)
            ReleaseGroupPatterns = [
                r'\[([^\]]+)\]',  # [GroupName]
                r'\(([^)]+)\)',   # (GroupName)
                r'-([A-Z0-9]+)$'  # -GROUPNAME at end
            ]
            
            for Pattern in ReleaseGroupPatterns:
                Match = re.search(Pattern, NameWithoutExt)
                if Match:
                    ReleaseGroup = Match.group(1).strip()
                    # Filter out common non-release-group patterns
                    if not any(word in ReleaseGroup.lower() for word in ['1080p', '720p', '480p', 'x264', 'x265', 'h264', 'h265']):
                        Result['ReleaseGroup'] = ReleaseGroup
                        break
            
            # If no show title found, use the cleaned filename as title
            if not Result['Title'] and not Result['ShowTitle']:
                CleanTitle = re.sub(r'[-._]', ' ', NameWithoutExt).strip()
                # Remove quality, source, and release group info
                CleanTitle = re.sub(r'\b(2160p|4K|1080p|720p|480p|360p|HD|SD|BluRay|Blu-ray|BDRip|BRRip|HDTV|WEBRip|WEB-DL|DVDRip|TVRip|CAM|TS|TC)\b', '', CleanTitle, flags=re.IGNORECASE)
                CleanTitle = re.sub(r'\[([^\]]+)\]|\(([^)]+)\)', '', CleanTitle)  # Remove brackets/parentheses
                CleanTitle = re.sub(r'\s+', ' ', CleanTitle).strip()  # Clean up spaces
                if CleanTitle:
                    Result['Title'] = CleanTitle
            
            return Result
            
        except Exception as e:
            LoggingService.LogException("Error extracting metadata from filename", e, 'ExtractMetadataFromFilename', 'FFmpegAnalysisService')
            return {}
    
    def ApplyFilenameMetadata(self, AnalysisModel: FFmpegAnalysisModel, FilenameMetadata: Dict[str, Any]):
        """Apply filename-extracted metadata to analysis model."""
        try:
            if FilenameMetadata.get('Title'):
                AnalysisModel.Title = FilenameMetadata['Title']
            if FilenameMetadata.get('ShowTitle'):
                AnalysisModel.ShowTitle = FilenameMetadata['ShowTitle']
            if FilenameMetadata.get('Season'):
                AnalysisModel.Season = FilenameMetadata['Season']
            if FilenameMetadata.get('Episode'):
                AnalysisModel.Episode = FilenameMetadata['Episode']
            if FilenameMetadata.get('Year'):
                AnalysisModel.Year = FilenameMetadata['Year']
            if FilenameMetadata.get('Quality'):
                AnalysisModel.Quality = FilenameMetadata['Quality']
            if FilenameMetadata.get('Source'):
                AnalysisModel.Source = FilenameMetadata['Source']
            if FilenameMetadata.get('ReleaseGroup'):
                AnalysisModel.ReleaseGroup = FilenameMetadata['ReleaseGroup']
                
        except Exception as e:
            LoggingService.LogException("Error applying filename metadata", e, 'ApplyFilenameMetadata', 'FFmpegAnalysisService')
    
    def IsAvailable(self) -> bool:
        """Check if FFprobe is available for analysis."""
        return self.FFmpegService.IsFFprobeAvailable()
    
    def CreateFFprobeScanJob(self, JobId: str, RootFolderPath: str, Recursive: bool):
        """Create a new FFprobe scan job record in the database."""
        try:
            LoggingService.LogInfo(f"Creating FFprobe scan job {JobId} for {RootFolderPath}, Recursive: {Recursive}", 'FFmpegAnalysisService', 'CreateFFprobeScanJob')
            
            Query = """
            INSERT INTO ScanJobs (JobId, RootFolderPath, Recursive, Status, StartTime, LastUpdated, ScanType)
            VALUES (%s, %s, %s, 'Pending', %s, %s, 'FFprobe')
            """
            Now = datetime.now(timezone.utc)
            LoggingService.LogInfo(f"Executing FFprobe query with params: JobId={JobId}, RootFolderPath={RootFolderPath}, Recursive={Recursive}, Now={Now}")
            
            if self.DatabaseService:
                self.DatabaseService.ExecuteNonQuery(Query, (JobId, RootFolderPath, Recursive, Now, Now))
            else:
                LoggingService.LogWarning("DatabaseService not available", 'CreateFFprobeScanJob', 'FFmpegAnalysisService')
                return
            
            LoggingService.LogInfo(f"Successfully created FFprobe scan job {JobId} for {RootFolderPath}")
            
        except Exception as e:
            LoggingService.LogException(f"Error creating FFprobe scan job {JobId}", e, 'CreateFFprobeScanJob', 'FFmpegAnalysisService')
            raise
    
    def StartFFprobeScanning(self, RootFolderPath: str, Recursive: bool = True) -> Dict[str, Any]:
        """Start FFprobe metadata extraction for all media files in the specified directory."""
        try:
            LoggingService.LogFunctionEntry("StartFFprobeScanning", 'FFmpegAnalysisService', f"RootFolder: {RootFolderPath}, Recursive: {Recursive}")
            
            # Generate unique job ID
            JobId = f"FFprobe_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
            
            # Create FFprobe scan job
            self.CreateFFprobeScanJob(JobId, RootFolderPath, Recursive)
            
            # Update job status to running
            Query = "UPDATE ScanJobs SET Status = 'Running', ProcessId = %s, LastUpdated = %s WHERE JobId = %s"
            Now = datetime.now(timezone.utc)
            
            if self.DatabaseService:
                self.DatabaseService.ExecuteNonQuery(Query, (os.getpid(), Now, JobId))
            else:
                LoggingService.LogWarning("DatabaseService not available", 'StartFFprobeScanning', 'FFmpegAnalysisService')
                return {
                    'Success': False,
                    'Message': 'DatabaseService not available',
                    'Error': 'DatabaseServiceError'
                }
            
            LoggingService.LogInfo(f"Started FFprobe scanning job {JobId} for {RootFolderPath}")
            
            return {
                'Success': True,
                'Message': f'FFprobe scanning started successfully for {RootFolderPath}',
                'JobId': JobId
            }
            
        except Exception as e:
            LoggingService.LogException("Error starting FFprobe scan", e, 'StartFFprobeScanning', 'FFmpegAnalysisService')
            return {
                'Success': False,
                'Message': f'Error starting FFprobe scan: {str(e)}',
                'Error': 'FFprobeScanError'
            }
