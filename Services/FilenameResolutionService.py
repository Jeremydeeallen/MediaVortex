import os
import re
from typing import Optional, Dict, Any
from pathlib import Path
from Services.LoggingService import LoggingService


class FilenameResolutionService:
    """Service for handling filename resolution and resolution-based naming."""
    
    def __init__(self):
        # Common resolution patterns to match and replace
        self.ResolutionPatterns = [
            r'(\d{3,4}p)',  # Matches 720p, 1080p, 2160p, etc.
            r'(4K)',        # Matches 4K
            r'(UHD)',       # Matches UHD
            r'(HD)',        # Matches HD
            r'(SD)',        # Matches SD
        ]
        
        # Resolution mapping for common transcoding targets
        self.ResolutionMapping = {
            '1080p': '720p',
            '2160p': '720p',
            '4K': '720p',
            'UHD': '720p',
            'HD': '720p',
            'SD': '720p'
        }
    
    def ExtractResolutionFromFilename(self, FileName: str) -> Optional[str]:
        """Extract resolution information from filename."""
        try:
            LoggingService.LogFunctionEntry("ExtractResolutionFromFilename", 'FilenameResolutionService', FileName)
            
            # Check each resolution pattern
            for pattern in self.ResolutionPatterns:
                match = re.search(pattern, FileName, re.IGNORECASE)
                if match:
                    resolution = match.group(1)
                    LoggingService.LogDebug(f"Found resolution '{resolution}' in filename: {FileName}", 'ExtractResolutionFromFilename', 'FilenameResolutionService')
                    return resolution
            
            LoggingService.LogDebug(f"No resolution found in filename: {FileName}", 'ExtractResolutionFromFilename', 'FilenameResolutionService')
            return None
            
        except Exception as e:
            LoggingService.LogException("Error extracting resolution from filename", e, 'ExtractResolutionFromFilename', 'FilenameResolutionService')
            return None
    
    def GenerateOutputFilename(self, OriginalFileName: str, TargetResolution: str = "720p") -> str:
        """Generate output filename with resolution-based naming."""
        try:
            LoggingService.LogFunctionEntry("GenerateOutputFilename", 'FilenameResolutionService', OriginalFileName, TargetResolution)
            
            # Get file extension
            filePath = Path(OriginalFileName)
            fileExtension = filePath.suffix
            fileNameWithoutExt = filePath.stem
            
            # Extract current resolution
            currentResolution = self.ExtractResolutionFromFilename(fileNameWithoutExt)
            
            if currentResolution:
                # Replace current resolution with target resolution
                for pattern in self.ResolutionPatterns:
                    fileNameWithoutExt = re.sub(pattern, TargetResolution, fileNameWithoutExt, flags=re.IGNORECASE)
                
                LoggingService.LogInfo(f"Resolution replaced: {currentResolution} -> {TargetResolution} in filename: {OriginalFileName}", 'GenerateOutputFilename', 'FilenameResolutionService')
            else:
                # No resolution found, append target resolution
                fileNameWithoutExt = f"{fileNameWithoutExt}-{TargetResolution}"
                LoggingService.LogInfo(f"No resolution found, appended {TargetResolution} to filename: {OriginalFileName}", 'GenerateOutputFilename', 'FilenameResolutionService')
            
            # Construct new filename with .mkv extension for transcoded files
            newFileName = f"{fileNameWithoutExt}.mkv"
            
            LoggingService.LogInfo(f"Generated output filename: {newFileName} from original: {OriginalFileName}", 'GenerateOutputFilename', 'FilenameResolutionService')
            return newFileName
            
        except Exception as e:
            LoggingService.LogException("Error generating output filename", e, 'GenerateOutputFilename', 'FilenameResolutionService')
            # Fallback: return original filename with target resolution appended
            filePath = Path(OriginalFileName)
            return f"{filePath.stem}-{TargetResolution}{filePath.suffix}"
    
    def GenerateOutputFilePath(self, OriginalFilePath: str, OutputDirectory: str, TargetResolution: str = "720p") -> str:
        """Generate complete output file path with resolution-based naming."""
        try:
            LoggingService.LogFunctionEntry("GenerateOutputFilePath", 'FilenameResolutionService', OriginalFilePath, OutputDirectory, TargetResolution)
            
            # Get original filename
            originalFileName = os.path.basename(OriginalFilePath)
            
            # Generate new filename
            newFileName = self.GenerateOutputFilename(originalFileName, TargetResolution)
            
            # Construct full output path
            outputFilePath = os.path.join(OutputDirectory, newFileName)
            
            LoggingService.LogInfo(f"Generated output file path: {outputFilePath}", 'GenerateOutputFilePath', 'FilenameResolutionService')
            return outputFilePath
            
        except Exception as e:
            LoggingService.LogException("Error generating output file path", e, 'GenerateOutputFilePath', 'FilenameResolutionService')
            # Fallback: use original filename in output directory
            originalFileName = os.path.basename(OriginalFilePath)
            return os.path.join(OutputDirectory, originalFileName)
    
    def DetermineTargetResolution(self, OriginalResolution: str, TranscodeProfile: str = None) -> str:
        """Determine target resolution based on original resolution and profile."""
        try:
            LoggingService.LogFunctionEntry("DetermineTargetResolution", 'FilenameResolutionService', OriginalResolution, TranscodeProfile)
            
            # Default target resolution
            targetResolution = "720p"
            
            if OriginalResolution:
                # Map original resolution to target resolution
                targetResolution = self.ResolutionMapping.get(OriginalResolution, "720p")
            
            # Profile-specific overrides could be added here
            if TranscodeProfile:
                # Future: Add profile-specific resolution logic
                LoggingService.LogDebug(f"Using profile '{TranscodeProfile}' for resolution determination", 'DetermineTargetResolution', 'FilenameResolutionService')
            
            LoggingService.LogInfo(f"Determined target resolution: {targetResolution} from original: {OriginalResolution}", 'DetermineTargetResolution', 'FilenameResolutionService')
            return targetResolution
            
        except Exception as e:
            LoggingService.LogException("Error determining target resolution", e, 'DetermineTargetResolution', 'FilenameResolutionService')
            return "720p"  # Safe fallback
    
    def ValidateFilenameResolution(self, FileName: str) -> Dict[str, Any]:
        """Validate filename resolution and return analysis."""
        try:
            LoggingService.LogFunctionEntry("ValidateFilenameResolution", 'FilenameResolutionService', FileName)
            
            currentResolution = self.ExtractResolutionFromFilename(FileName)
            targetResolution = self.DetermineTargetResolution(currentResolution)
            needsResolutionChange = currentResolution and currentResolution != targetResolution
            
            result = {
                'Success': True,
                'OriginalFileName': FileName,
                'CurrentResolution': currentResolution,
                'TargetResolution': targetResolution,
                'NeedsResolutionChange': needsResolutionChange,
                'NewFileName': self.GenerateOutputFilename(FileName, targetResolution) if needsResolutionChange else FileName
            }
            
            LoggingService.LogInfo(f"Filename resolution validation completed: {result}", 'ValidateFilenameResolution', 'FilenameResolutionService')
            return result
            
        except Exception as e:
            LoggingService.LogException("Error validating filename resolution", e, 'ValidateFilenameResolution', 'FilenameResolutionService')
            return {
                'Success': False,
                'OriginalFileName': FileName,
                'CurrentResolution': None,
                'TargetResolution': "720p",
                'NeedsResolutionChange': False,
                'NewFileName': FileName,
                'ErrorMessage': str(e)
            }
