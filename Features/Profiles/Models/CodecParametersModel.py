from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Any, Union


@dataclass
class CodecParametersModel:
    """Represents individual codec parameters with FFmpeg flags and validation."""
    
    Id: Optional[int] = None
    CodecFlagsId: int = 0
    ParameterName: str = ""  # e.g., "crf", "preset", "film-grain"
    ParameterType: str = ""  # "integer", "float", "string", "boolean"
    MinValue: Optional[float] = None
    MaxValue: Optional[float] = None
    DefaultValue: str = ""
    Description: str = ""
    FFmpegFlag: str = ""  # e.g., "-crf", "-svtav1-params film-grain"
    CreatedDate: Optional[datetime] = None
    
    def __post_init__(self):
        if self.CreatedDate is None:
            self.CreatedDate = datetime.now(timezone.utc)
    
    def IsValueValid(self, value: Any) -> bool:
        """Check if a parameter value is valid for this parameter."""
        try:
            if self.ParameterType == "integer":
                int_value = int(value)
                if self.MinValue is not None and int_value < self.MinValue:
                    return False
                if self.MaxValue is not None and int_value > self.MaxValue:
                    return False
                return True
            elif self.ParameterType == "float":
                float_value = float(value)
                if self.MinValue is not None and float_value < self.MinValue:
                    return False
                if self.MaxValue is not None and float_value > self.MaxValue:
                    return False
                return True
            elif self.ParameterType == "string":
                return isinstance(value, str) and len(value) > 0
            elif self.ParameterType == "boolean":
                return isinstance(value, bool) or value in [0, 1, "0", "1", "true", "false"]
            return False
        except (ValueError, TypeError):
            return False
    
    def GetValidatedValue(self, value: Any) -> Union[int, float, str, bool]:
        """Get a validated and converted parameter value."""
        if not self.IsValueValid(value):
            return self.GetDefaultValue()
        
        try:
            if self.ParameterType == "integer":
                return int(value)
            elif self.ParameterType == "float":
                return float(value)
            elif self.ParameterType == "string":
                return str(value)
            elif self.ParameterType == "boolean":
                if isinstance(value, bool):
                    return value
                elif value in [0, "0", "false"]:
                    return False
                elif value in [1, "1", "true"]:
                    return True
                else:
                    return bool(value)
            return value
        except (ValueError, TypeError):
            return self.GetDefaultValue()
    
    def GetDefaultValue(self) -> Union[int, float, str, bool]:
        """Get the default value converted to the appropriate type."""
        try:
            if self.ParameterType == "integer":
                return int(self.DefaultValue) if self.DefaultValue else 0
            elif self.ParameterType == "float":
                return float(self.DefaultValue) if self.DefaultValue else 0.0
            elif self.ParameterType == "string":
                return self.DefaultValue if self.DefaultValue else ""
            elif self.ParameterType == "boolean":
                if self.DefaultValue.lower() in ["true", "1"]:
                    return True
                elif self.DefaultValue.lower() in ["false", "0"]:
                    return False
                else:
                    return bool(self.DefaultValue)
            return self.DefaultValue
        except (ValueError, TypeError):
            return "" if self.ParameterType == "string" else 0
    
    def GetFFmpegArgument(self, value: Any) -> str:
        """Generate the FFmpeg argument for this parameter with the given value."""
        validated_value = self.GetValidatedValue(value)
        
        if self.FFmpegFlag.startswith("-") and " " not in self.FFmpegFlag:
            # Simple flag with value (e.g., "-crf")
            if self.ParameterType == "boolean":
                if validated_value:
                    return self.FFmpegFlag
                else:
                    return ""  # Don't include boolean false flags
            else:
                return f"{self.FFmpegFlag} {validated_value}"
        else:
            # Complex flag (like "-svtav1-params film-grain")
            if self.ParameterType == "boolean":
                if validated_value:
                    return f"{self.FFmpegFlag}"
                else:
                    return ""
            else:
                return f"{self.FFmpegFlag}={validated_value}"
    
    def GetFFmpegArguments(self, value: Any) -> list:
        """Generate FFmpeg arguments as a list for this parameter."""
        argument = self.GetFFmpegArgument(value)
        if not argument:
            return []
        
        # Return as single argument - let subprocess handle it
        return [argument]
    
    def ToDict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'Id': self.Id,
            'CodecFlagsId': self.CodecFlagsId,
            'ParameterName': self.ParameterName,
            'ParameterType': self.ParameterType,
            'MinValue': self.MinValue,
            'MaxValue': self.MaxValue,
            'DefaultValue': self.DefaultValue,
            'Description': self.Description,
            'FFmpegFlag': self.FFmpegFlag,
            'CreatedDate': self.CreatedDate.isoformat() if self.CreatedDate else None
        }
    
    @classmethod
    def FromDict(cls, data: dict) -> 'CodecParametersModel':
        """Create instance from dictionary."""
        return cls(
            Id=data.get('Id'),
            CodecFlagsId=data.get('CodecFlagsId', 0),
            ParameterName=data.get('ParameterName', ''),
            ParameterType=data.get('ParameterType', ''),
            MinValue=data.get('MinValue'),
            MaxValue=data.get('MaxValue'),
            DefaultValue=data.get('DefaultValue', ''),
            Description=data.get('Description', ''),
            FFmpegFlag=data.get('FFmpegFlag', ''),
            CreatedDate=datetime.fromisoformat(data['CreatedDate']) if data.get('CreatedDate') else None
        )
