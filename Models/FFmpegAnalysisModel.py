from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime, timezone


@dataclass
class FFmpegAnalysisModel:
    """Represents FFmpeg media analysis results."""
    
    # File Information
    FilePath: str = ""
    FileName: str = ""
    FileSizeMB: float = 0.0
    FileExtension: Optional[str] = None
    ContainerFormat: Optional[str] = None
    
    # Video Information
    VideoCodec: Optional[str] = None
    VideoBitrateKbps: Optional[int] = None
    Resolution: Optional[str] = None
    FrameRate: Optional[float] = None
    DurationMinutes: Optional[float] = None
    
    # Audio Information
    AudioCodec: Optional[str] = None
    AudioBitrateKbps: Optional[int] = None
    AudioChannels: Optional[str] = None
    Language: Optional[str] = None
    
    # New metadata fields
    TotalFrames: Optional[int] = None
    CodecProfile: Optional[str] = None
    ColorRange: Optional[str] = None
    FieldOrder: Optional[str] = None
    HasBFrames: Optional[int] = None
    RefFrames: Optional[int] = None
    PixelFormat: Optional[str] = None
    Level: Optional[int] = None
    AudioChannels: Optional[int] = None
    AudioSampleRate: Optional[int] = None
    AudioSampleFormat: Optional[str] = None
    AudioChannelLayout: Optional[str] = None
    OverallBitrate: Optional[int] = None
    
    # Audio language tracking
    AudioLanguages: Optional[str] = None  # Comma-separated list of all audio stream languages (e.g. 'eng,jpn')
    HasExplicitEnglishAudio: Optional[bool] = None  # True if at least one stream is tagged eng/en

    # Stream Selection
    AudioStreamIndex: Optional[int] = None  # 0-based audio stream index for -map 0:a:{index}
    SubtitleStreamIndex: Optional[int] = None  # 0-based subtitle stream index for -map 0:s:{index}
    SubtitleCodec: Optional[str] = None  # Codec of selected subtitle stream (ass, srt, etc.)

    # Subtitle Information
    Subtitles: Optional[str] = None
    SubtitleFormats: Optional[str] = None
    
    # Metadata Information
    Title: Optional[str] = None
    ShowTitle: Optional[str] = None
    Season: Optional[str] = None
    Episode: Optional[str] = None
    EpisodeTitle: Optional[str] = None
    Year: Optional[int] = None
    Genre: Optional[str] = None
    ReleaseGroup: Optional[str] = None
    
    # Quality Information
    Quality: Optional[str] = None
    Source: Optional[str] = None
    
    # Timestamps
    CreationDate: Optional[datetime] = None
    ModificationDate: Optional[datetime] = None
    AnalysisDate: Optional[datetime] = None
    
    # Analysis Status
    Success: bool = False
    ErrorMessage: Optional[str] = None
    
    def __post_init__(self):
        if self.AnalysisDate is None:
            self.AnalysisDate = datetime.now(timezone.utc)
    
    def ToDict(self) -> Dict[str, Any]:
        """Convert model to dictionary for database storage."""
        return {
            'FilePath': self.FilePath,
            'FileName': self.FileName,
            'FileSizeMB': self.FileSizeMB,
            'FileExtension': self.FileExtension,
            'ContainerFormat': self.ContainerFormat,
            'VideoCodec': self.VideoCodec,
            'VideoBitrateKbps': self.VideoBitrateKbps,
            'Resolution': self.Resolution,
            'FrameRate': self.FrameRate,
            'DurationMinutes': self.DurationMinutes,
            'AudioCodec': self.AudioCodec,
            'AudioBitrateKbps': self.AudioBitrateKbps,
            'AudioChannels': self.AudioChannels,
            'Language': self.Language,
            'Subtitles': self.Subtitles,
            'SubtitleFormats': self.SubtitleFormats,
            'Title': self.Title,
            'ShowTitle': self.ShowTitle,
            'Season': self.Season,
            'Episode': self.Episode,
            'EpisodeTitle': self.EpisodeTitle,
            'Year': self.Year,
            'Genre': self.Genre,
            'ReleaseGroup': self.ReleaseGroup,
            'Quality': self.Quality,
            'Source': self.Source,
            'CreationDate': self.CreationDate,
            'ModificationDate': self.ModificationDate,
            'AnalysisDate': self.AnalysisDate,
            'Success': self.Success,
            'ErrorMessage': self.ErrorMessage,
            'TotalFrames': self.TotalFrames,
            'CodecProfile': self.CodecProfile,
            'ColorRange': self.ColorRange,
            'FieldOrder': self.FieldOrder,
            'HasBFrames': self.HasBFrames,
            'RefFrames': self.RefFrames,
            'PixelFormat': self.PixelFormat,
            'Level': self.Level,
            'AudioChannels': self.AudioChannels,
            'AudioSampleRate': self.AudioSampleRate,
            'AudioSampleFormat': self.AudioSampleFormat,
            'AudioChannelLayout': self.AudioChannelLayout,
            'OverallBitrate': self.OverallBitrate,
            'AudioLanguages': self.AudioLanguages,
            'HasExplicitEnglishAudio': self.HasExplicitEnglishAudio,
            'AudioStreamIndex': self.AudioStreamIndex,
            'SubtitleStreamIndex': self.SubtitleStreamIndex,
            'SubtitleCodec': self.SubtitleCodec
        }
    
    @classmethod
    def FromDict(cls, Data: Dict[str, Any]) -> 'FFmpegAnalysisModel':
        """Create model from dictionary."""
        return cls(**Data)
