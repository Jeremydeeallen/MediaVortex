import os
import json
import re
import uuid
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path
from Models.FFmpegAnalysisModel import FFmpegAnalysisModel
from Services.FFmpegService import FFmpegService
from Services.LoggingService import LoggingService


class FFmpegAnalysisService:
    """Business service for FFmpeg media analysis operations."""
    
    def __init__(self, FFmpegServiceInstance: FFmpegService = None, DatabaseService = None):
        self.FFmpegService = FFmpegServiceInstance or FFmpegService()
        self.DatabaseService = DatabaseService
    
    def AnalyzeMediaFile(self, FilePath: str) -> FFmpegAnalysisModel:
        """Analyze a media file and return comprehensive metadata."""
        try:
            LoggingService.LogFunctionEntry("AnalyzeMediaFile", 'FFmpegAnalysisService', FilePath)
            
            # Create analysis model
            AnalysisModel = FFmpegAnalysisModel()
            AnalysisModel.FilePath = FilePath
            AnalysisModel.FileName = os.path.basename(FilePath)
            AnalysisModel.FileExtension = Path(FilePath).suffix.lower()
            
            # Get file size
            if os.path.exists(FilePath):
                AnalysisModel.FileSizeMB = os.path.getsize(FilePath) / (1024 * 1024)
            
            # Execute FFprobe analysis
            FFprobeResult = self.FFmpegService.ExecuteFFprobe(FilePath)
            
            if not FFprobeResult['Success']:
                Command = FFprobeResult.get('Command', 'Unknown command')
                ErrorMessage = FFprobeResult.get('ErrorMessage', 'FFprobe analysis failed')
                AnalysisModel.ErrorMessage = f"{ErrorMessage} - Command: {Command}"
                LoggingService.LogError(f"FFprobe failed for {FilePath}: {ErrorMessage} - Command: {Command}", 'FFmpegAnalysisService', 'AnalyzeMediaFile')
                return AnalysisModel
            
            # Parse FFprobe JSON output
            try:
                MediaInfo = json.loads(FFprobeResult['Output'])
                self.ParseFFprobeOutput(AnalysisModel, MediaInfo)
                AnalysisModel.Success = True
                
            except json.JSONDecodeError as e:
                Command = FFprobeResult.get('Command', 'Unknown command')
                AnalysisModel.ErrorMessage = f"Failed to parse FFprobe JSON output: {str(e)} - Command: {Command}"
                LoggingService.LogError(f"FFprobe JSON parsing failed for {FilePath}: {str(e)} - Command: {Command}", 'FFmpegAnalysisService', 'AnalyzeMediaFile')
                return AnalysisModel
            
            # Extract metadata from filename if not found in embedded tags
            if not AnalysisModel.Title and not AnalysisModel.ShowTitle:
                FilenameMetadata = self.ExtractMetadataFromFilename(AnalysisModel.FileName)
                self.ApplyFilenameMetadata(AnalysisModel, FilenameMetadata)
            
            LoggingService.LogDebug(f"Successfully analyzed file: {FilePath}", 'FFmpegAnalysisService', 'AnalyzeMediaFile')
            return AnalysisModel
            
        except Exception as e:
            LoggingService.LogException("Error analyzing media file", e, 'FFmpegAnalysisService', 'AnalyzeMediaFile')
            AnalysisModel = FFmpegAnalysisModel()
            AnalysisModel.FilePath = FilePath
            AnalysisModel.ErrorMessage = f"Analysis error: {str(e)}"
            return AnalysisModel
    
    def ParseFFprobeOutput(self, AnalysisModel: FFmpegAnalysisModel, MediaInfo: Dict[str, Any]):
        """Parse FFprobe JSON output and populate analysis model."""
        try:
            # Extract format information
            Format = MediaInfo.get('format', {})
            
            # Duration
            DurationSeconds = Format.get('duration')
            if DurationSeconds:
                try:
                    AnalysisModel.DurationMinutes = float(DurationSeconds) / 60.0
                except (ValueError, TypeError):
                    pass
            
            # Container format
            AnalysisModel.ContainerFormat = Format.get('format_name', '')
            
            # Try to get overall bitrate from format level as fallback
            FormatBitrate = Format.get('bit_rate')
            if FormatBitrate:
                try:
                    FormatBitrateKbps = int(FormatBitrate) // 1000
                    LoggingService.LogInfo(f"Found format bitrate: {FormatBitrateKbps} kbps for {AnalysisModel.FilePath}", 'FFmpegAnalysisService', 'ParseFFprobeOutput')
                    # If we don't have video bitrate, use format bitrate as video bitrate
                    if not AnalysisModel.VideoBitrateKbps:
                        AnalysisModel.VideoBitrateKbps = FormatBitrateKbps
                        LoggingService.LogInfo(f"Set video bitrate from format: {FormatBitrateKbps} kbps", 'FFmpegAnalysisService', 'ParseFFprobeOutput')
                    # If we don't have audio bitrate, estimate it (typically 10-20% of total)
                    if not AnalysisModel.AudioBitrateKbps:
                        AnalysisModel.AudioBitrateKbps = FormatBitrateKbps // 10  # Rough estimate
                        LoggingService.LogInfo(f"Set audio bitrate from format: {FormatBitrateKbps // 10} kbps", 'FFmpegAnalysisService', 'ParseFFprobeOutput')
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
            AudioStream = None
            SubtitleStreams = []
            
            for Stream in Streams:
                CodecType = Stream.get('codec_type', '')
                if CodecType == 'video' and VideoStream is None:
                    VideoStream = Stream
                elif CodecType == 'audio' and AudioStream is None:
                    AudioStream = Stream
                elif CodecType == 'subtitle':
                    SubtitleStreams.append(Stream)
            
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
                        LoggingService.LogInfo(f"Set video bitrate from stream: {AnalysisModel.VideoBitrateKbps} kbps", 'FFmpegAnalysisService', 'ParseFFprobeOutput')
                    except (ValueError, TypeError):
                        pass
                else:
                    LoggingService.LogInfo(f"No bitrate in video stream, keeping existing: {AnalysisModel.VideoBitrateKbps} kbps", 'FFmpegAnalysisService', 'ParseFFprobeOutput')
            
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
            
            # Process subtitle streams
            if SubtitleStreams:
                SubtitleLanguages = []
                for SubStream in SubtitleStreams:
                    Language = SubStream.get('tags', {}).get('language')
                    if Language:
                        SubtitleLanguages.append(Language)
                if SubtitleLanguages:
                    AnalysisModel.Subtitles = ', '.join(SubtitleLanguages)
            
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
            LoggingService.LogException("Error parsing FFprobe output", e, 'FFmpegAnalysisService', 'ParseFFprobeOutput')
    
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
            LoggingService.LogException("Error extracting metadata from filename", e, 'FFmpegAnalysisService', 'ExtractMetadataFromFilename')
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
            LoggingService.LogException("Error applying filename metadata", e, 'FFmpegAnalysisService', 'ApplyFilenameMetadata')
    
    def IsAvailable(self) -> bool:
        """Check if FFprobe is available for analysis."""
        return self.FFmpegService.IsFFprobeAvailable()
    
    def CreateFFprobeScanJob(self, JobId: str, RootFolderPath: str, Recursive: bool):
        """Create a new FFprobe scan job record in the database."""
        try:
            LoggingService.LogInfo(f"Creating FFprobe scan job {JobId} for {RootFolderPath}, Recursive: {Recursive}", 'FFmpegAnalysisService', 'CreateFFprobeScanJob')
            
            Query = """
            INSERT INTO ScanJobs (JobId, RootFolderPath, Recursive, Status, StartTime, LastUpdated, ScanType)
            VALUES (?, ?, ?, 'Pending', ?, ?, 'FFprobe')
            """
            Now = datetime.now()
            LoggingService.LogInfo(f"Executing FFprobe query with params: JobId={JobId}, RootFolderPath={RootFolderPath}, Recursive={Recursive}, Now={Now}")
            
            if self.DatabaseService:
                self.DatabaseService.ExecuteNonQuery(Query, (JobId, RootFolderPath, Recursive, Now, Now))
            else:
                LoggingService.LogWarning("DatabaseService not available", 'FFmpegAnalysisService', 'CreateFFprobeScanJob')
                return
            
            LoggingService.LogInfo(f"Successfully created FFprobe scan job {JobId} for {RootFolderPath}")
            
        except Exception as e:
            LoggingService.LogException(f"Error creating FFprobe scan job {JobId}", e, 'FFmpegAnalysisService', 'CreateFFprobeScanJob')
            raise
    
    def StartFFprobeScanning(self, RootFolderPath: str, Recursive: bool = True) -> Dict[str, Any]:
        """Start FFprobe metadata extraction for all media files in the specified directory."""
        try:
            LoggingService.LogFunctionEntry("StartFFprobeScanning", 'FFmpegAnalysisService', f"RootFolder: {RootFolderPath}, Recursive: {Recursive}")
            
            # Generate unique job ID
            JobId = f"FFprobe_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
            
            # Create FFprobe scan job
            self.CreateFFprobeScanJob(JobId, RootFolderPath, Recursive)
            
            # Update job status to running
            Query = "UPDATE ScanJobs SET Status = 'Running', ProcessId = ?, LastUpdated = ? WHERE JobId = ?"
            Now = datetime.now()
            
            if self.DatabaseService:
                self.DatabaseService.ExecuteNonQuery(Query, (os.getpid(), Now, JobId))
            else:
                LoggingService.LogWarning("DatabaseService not available", 'FFmpegAnalysisService', 'StartFFprobeScanning')
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
            LoggingService.LogException("Error starting FFprobe scan", e, 'FFmpegAnalysisService', 'StartFFprobeScanning')
            return {
                'Success': False,
                'Message': f'Error starting FFprobe scan: {str(e)}',
                'Error': 'FFprobeScanError'
            }
