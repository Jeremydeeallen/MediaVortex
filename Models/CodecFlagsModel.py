from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any
import json


@dataclass
class CodecFlagsModel:
    """Represents codec-specific configuration flags and options."""
    
    Id: Optional[int] = None
    CodecName: str = ""  # e.g., "libx265", "libsvtav1"
    DisplayName: str = ""  # e.g., "H.265 (libx265)", "AV1 (libsvtav1)"
    PresetType: str = "numeric"  # "string" or "numeric"
    PresetMin: int = 0
    PresetMax: int = 13
    PresetDefault: int = 6
    PresetOptions: Optional[str] = None  # JSON string for string presets
    FilmGrainType: str = "numeric"  # "boolean" or "numeric"
    FilmGrainMin: int = 0
    FilmGrainMax: int = 50
    FilmGrainDefault: int = 10
    TuneOptions: Optional[str] = None  # JSON string of available tune options
    CreatedDate: Optional[datetime] = None
    LastModified: Optional[datetime] = None
    
    def __post_init__(self):
        if self.CreatedDate is None:
            self.CreatedDate = datetime.now()
        if self.LastModified is None:
            self.LastModified = datetime.now()
    
    def GetPresetOptionsList(self) -> List[str]:
        """Get preset options as a list (for string presets)."""
        if self.PresetOptions:
            try:
                return json.loads(self.PresetOptions)
            except json.JSONDecodeError:
                return []
        return []
    
    def GetTuneOptionsList(self) -> List[str]:
        """Get tune options as a list."""
        if self.TuneOptions:
            try:
                return json.loads(self.TuneOptions)
            except json.JSONDecodeError:
                return []
        return []
    
    def IsPresetValid(self, preset_value: Any) -> bool:
        """Check if a preset value is valid for this codec."""
        if self.PresetType == "numeric":
            return isinstance(preset_value, (int, float)) and self.PresetMin <= preset_value <= self.PresetMax
        elif self.PresetType == "string":
            return str(preset_value) in self.GetPresetOptionsList()
        return False
    
    def IsFilmGrainValid(self, grain_value: Any) -> bool:
        """Check if a film grain value is valid for this codec."""
        if self.FilmGrainType == "boolean":
            return isinstance(grain_value, bool) or grain_value in [0, 1]
        elif self.FilmGrainType == "numeric":
            return isinstance(grain_value, (int, float)) and self.FilmGrainMin <= grain_value <= self.FilmGrainMax
        return False
    
    def GetFilmGrainFFmpegParam(self, grain_value: int) -> str:
        """Get the appropriate FFmpeg parameter for film grain based on codec type."""
        if grain_value <= 0:
            return ""
        
        if self.CodecName == "libx265":
            # H.265 uses tune grain (boolean)
            return "-tune grain"
        elif self.CodecName == "libsvtav1":
            # AV1 uses numeric film-grain parameter
            return f"-svtav1-params film-grain={grain_value}"
        elif self.CodecName == "libx264":
            # H.264 uses tune film (boolean)
            return "-tune film"
        elif self.CodecName == "libvpx-vp9":
            # VP9 doesn't have direct film grain support
            return ""
        
        return ""
    
    def GetPresetFFmpegParam(self, preset_value: Any) -> str:
        """Get the appropriate FFmpeg parameter for preset based on codec type."""
        if self.PresetType == "string":
            return f"-preset {preset_value}"
        elif self.PresetType == "numeric":
            return f"-preset {preset_value}"
        return ""
    
    def ToDict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'Id': self.Id,
            'CodecName': self.CodecName,
            'DisplayName': self.DisplayName,
            'PresetType': self.PresetType,
            'PresetMin': self.PresetMin,
            'PresetMax': self.PresetMax,
            'PresetDefault': self.PresetDefault,
            'PresetOptions': self.PresetOptions,
            'FilmGrainType': self.FilmGrainType,
            'FilmGrainMin': self.FilmGrainMin,
            'FilmGrainMax': self.FilmGrainMax,
            'FilmGrainDefault': self.FilmGrainDefault,
            'TuneOptions': self.TuneOptions,
            'CreatedDate': self.CreatedDate.isoformat() if self.CreatedDate else None,
            'LastModified': self.LastModified.isoformat() if self.LastModified else None
        }
