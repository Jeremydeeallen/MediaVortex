from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime


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
    
    # Subtitle Information
    Subtitles: Optional[str] = None
    
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
            self.AnalysisDate = datetime.now()
    
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
            'ErrorMessage': self.ErrorMessage
        }
    
    @classmethod
    def FromDict(cls, Data: Dict[str, Any]) -> 'FFmpegAnalysisModel':
        """Create model from dictionary."""
        return cls(**Data)
