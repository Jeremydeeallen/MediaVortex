from typing import Dict, Any, Optional, List
from Models.FFmpegAnalysisModel import FFmpegAnalysisModel
from Services.FFmpegAnalysisService import FFmpegAnalysisService
from Services.LoggingService import LoggingService


class FFmpegAnalysisViewModel:
    """ViewModel for FFmpeg analysis operations."""
    
    def __init__(self, AnalysisService: FFmpegAnalysisService = None):
        self.AnalysisService = AnalysisService or FFmpegAnalysisService()
    
    def AnalyzeMediaFile(self, FilePath: str) -> Dict[str, Any]:
        """Analyze a media file and return results for UI."""
        try:
            LoggingService.LogFunctionEntry("AnalyzeMediaFile", 'FFmpegAnalysisViewModel', FilePath)
            
            # Perform analysis
            AnalysisResult = self.AnalysisService.AnalyzeMediaFile(FilePath)
            
            # Convert to dictionary for JSON response
            Result = {
                'Success': AnalysisResult.Success,
                'ErrorMessage': AnalysisResult.ErrorMessage,
                'AnalysisData': AnalysisResult.ToDict()
            }
            
            if AnalysisResult.Success:
                LoggingService.LogInfo(f"Successfully analyzed file: {FilePath}", 'AnalyzeMediaFile', 'FFmpegAnalysisViewModel')
            else:
                LoggingService.LogWarning(f"Failed to analyze file: {FilePath} - {AnalysisResult.ErrorMessage}", 'AnalyzeMediaFile', 'FFmpegAnalysisViewModel')
            
            return Result
            
        except Exception as e:
            LoggingService.LogException("Error in analysis view model", e, 'AnalyzeMediaFile', 'FFmpegAnalysisViewModel')
            return {
                'Success': False,
                'ErrorMessage': f"Analysis error: {str(e)}",
                'AnalysisData': None
            }
    
    def AnalyzeMediaFiles(self, FilePaths: List[str]) -> Dict[str, Any]:
        """Analyze multiple media files and return results for UI."""
        try:
            LoggingService.LogFunctionEntry("AnalyzeMediaFiles", 'FFmpegAnalysisViewModel', f"Processing {len(FilePaths)} files")
            
            Results = []
            SuccessfulAnalyses = 0
            FailedAnalyses = 0
            
            for FilePath in FilePaths:
                AnalysisResult = self.AnalysisService.AnalyzeMediaFile(FilePath)
                
                Results.append({
                    'FilePath': FilePath,
                    'Success': AnalysisResult.Success,
                    'ErrorMessage': AnalysisResult.ErrorMessage,
                    'AnalysisData': AnalysisResult.ToDict() if AnalysisResult.Success else None
                })
                
                if AnalysisResult.Success:
                    SuccessfulAnalyses += 1
                else:
                    FailedAnalyses += 1
            
            Result = {
                'Success': True,
                'TotalFiles': len(FilePaths),
                'SuccessfulAnalyses': SuccessfulAnalyses,
                'FailedAnalyses': FailedAnalyses,
                'Results': Results
            }
            
            LoggingService.LogInfo(f"Batch analysis completed: {SuccessfulAnalyses} successful, {FailedAnalyses} failed", 'FFmpegAnalysisViewModel', 'AnalyzeMediaFiles')
            return Result
            
        except Exception as e:
            LoggingService.LogException("Error in batch analysis view model", e, 'AnalyzeMediaFiles', 'FFmpegAnalysisViewModel')
            return {
                'Success': False,
                'ErrorMessage': f"Batch analysis error: {str(e)}",
                'TotalFiles': len(FilePaths) if FilePaths else 0,
                'SuccessfulAnalyses': 0,
                'FailedAnalyses': 0,
                'Results': []
            }
    
    def IsAnalysisAvailable(self) -> bool:
        """Check if analysis service is available."""
        return self.AnalysisService.IsAvailable()
    
    def GetAnalysisCapabilities(self) -> Dict[str, Any]:
        """Get information about analysis capabilities."""
        return {
            'Available': self.AnalysisService.IsAvailable(),
            'SupportedFormats': [
                'mp4', 'mkv', 'avi', 'mov', 'wmv', 'flv', 'webm', 'm4v',
                'mp3', 'aac', 'flac', 'wav', 'ogg', 'wma'
            ],
            'MetadataExtraction': {
                'Technical': ['VideoCodec', 'AudioCodec', 'Resolution', 'Bitrate', 'FrameRate', 'Duration'],
                'Content': ['Title', 'ShowTitle', 'Season', 'Episode', 'Year', 'Genre'],
                'Quality': ['Quality', 'Source', 'ReleaseGroup'],
                'Filename': ['Pattern matching for show/episode extraction']
            }
        }
