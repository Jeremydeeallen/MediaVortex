from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from Services.DatabaseService import DatabaseService
from Services.LoggingService import LoggingService
from Core.Database.DatabaseService import EscapeLikePattern


class CodecFlagsRepository:
    def __init__(self, DatabaseServiceInstance: Optional[DatabaseService] = None):
        self.DatabaseService = DatabaseServiceInstance or DatabaseService()


    def GetCodecFlagsByCodecName(self, CodecName: str) -> Optional[Dict[str, Any]]:
        """Get codec flags by codec name."""
        try:
            LoggingService.LogFunctionEntry("GetCodecFlagsByCodecName", "DatabaseManager", CodecName)
            
            query = """
            SELECT Id, CodecName, DisplayName, PresetType, PresetMin, PresetMax, PresetDefault, 
                   PresetOptions, FilmGrainType, FilmGrainMin, FilmGrainMax, FilmGrainDefault, 
                   TuneOptions, CreatedDate, LastModified
            FROM CodecFlags 
            WHERE CodecName = %s
            """
            rows = self.DatabaseService.ExecuteQuery(query, (CodecName,))
            
            if not rows:
                LoggingService.LogWarning(f"No codec flags found for codec: {CodecName}", "DatabaseManager", "GetCodecFlagsByCodecName")
                return None
            
            row = rows[0]
            LoggingService.LogInfo(f"Retrieved codec flags for {CodecName}", "DatabaseManager", "GetCodecFlagsByCodecName")
            return row
            
        except Exception as e:
            LoggingService.LogException("Exception getting codec flags by codec name", e, "DatabaseManager", "GetCodecFlagsByCodecName")
            return None

    def GetCodecParametersByCodecFlagsId(self, CodecFlagsId: int) -> List[Dict[str, Any]]:
        """Get codec parameters by codec flags ID."""
        try:
            LoggingService.LogFunctionEntry("GetCodecParametersByCodecFlagsId", "DatabaseManager", CodecFlagsId)
            
            query = """
            SELECT Id, CodecFlagsId, ParameterName, ParameterType, MinValue, MaxValue, 
                   DefaultValue, Description, FFmpegFlag, CreatedDate
            FROM CodecParameters 
            WHERE CodecFlagsId = %s
            ORDER BY ParameterName
            """
            rows = self.DatabaseService.ExecuteQuery(query, (CodecFlagsId,))
            
            LoggingService.LogInfo(f"Retrieved {len(rows)} codec parameters for CodecFlagsId {CodecFlagsId}", "DatabaseManager", "GetCodecParametersByCodecFlagsId")
            return list(rows)
            
        except Exception as e:
            LoggingService.LogException("Exception getting codec parameters by codec flags ID", e, "DatabaseManager", "GetCodecParametersByCodecFlagsId")
            return []
