import os
import sys
from typing import List, Optional, Tuple, Dict, Any
from pathlib import Path
from Services.LoggingService import LoggingService
from Services.FFmpegAnalysisService import FFmpegAnalysisService


class FileManagerService:
    """Handles file system operations and metadata extraction with Unicode character support."""
    
    # Common media file extensions
    MediaExtensions = {
        '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp', '.mpg', '.mpeg',
        '.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a', '.opus'
    }
    
    def __init__(self):
        self.EncodingErrors = []
        self.ProcessedFiles = 0
        self.SkippedFiles = 0
        self.FFmpegAnalysisService = FFmpegAnalysisService()
    
    def IsMediaFile(self, filePath: str) -> bool:
        """Check if a file is a media file based on its extension."""
        try:
            fileExtension = Path(filePath).suffix.lower()
            return fileExtension in self.MediaExtensions
        except Exception as e:
            LoggingService.LogException("Error checking media file extension", e, 'IsMediaFile', 'FileManagerService')
            return False
    
    def ValidateUnicodePath(self, filePath: str) -> Tuple[bool, str]:
        """Validate that file path is valid UTF-8 and return as-is (preserving all characters including Cyrillic)."""
        try:
            # Test if the path can be encoded/decoded properly with UTF-8
            encodedPath = filePath.encode('utf-8')
            decodedPath = encodedPath.decode('utf-8')
            
            if decodedPath == filePath:
                # Path is valid UTF-8, return as-is (preserving all characters including Cyrillic)
                return True, filePath
            else:
                # Path has encoding issues - log warning but still return original path
                LoggingService.LogWarning(f"Unicode encoding issue detected for path: {filePath}", 'ValidateUnicodePath', 'FileManagerService')
                return False, filePath
                
        except UnicodeEncodeError as e:
            LoggingService.LogWarning(f"Unicode encoding error for path: {filePath}", 'ValidateUnicodePath', 'FileManagerService')
            return False, filePath
        except UnicodeDecodeError as e:
            LoggingService.LogWarning(f"Unicode decoding error for path: {filePath}", 'ValidateUnicodePath', 'FileManagerService')
            return False, filePath
        except Exception as e:
            LoggingService.LogException("Unexpected error validating Unicode path", e, 'ValidateUnicodePath', 'FileManagerService')
            return False, filePath
    
    
    def GetFileSizeMB(self, filePath: str) -> float:
        """Get file size in MB with Unicode path support."""
        try:
            # Validate the path first
            isValid, validatedPath = self.ValidateUnicodePath(filePath)
            
            if not isValid:
                LoggingService.LogDebug(f"Unicode validation failed for path: {filePath}", 'GetFileSizeMB', 'FileManagerService')
                self.EncodingErrors.append(f"Unicode issue: {filePath}")
            
            # Try to get file size using the original path
            if os.path.exists(filePath):
                sizeBytes = os.path.getsize(filePath)
                return sizeBytes / (1024 * 1024)  # Convert to MB
            else:
                LoggingService.LogWarning(f"File not found: {filePath}", 'GetFileSizeMB', 'FileManagerService')
                return 0.0
                
        except Exception as e:
            LoggingService.LogException("Error getting file size", e, 'GetFileSizeMB', 'FileManagerService')
            return 0.0
    
    def ScanDirectory(self, directoryPath: str, recursive: bool = True) -> List[str]:
        """Scan directory for media files with Unicode character support."""
        mediaFiles = []
        
        try:
            LoggingService.LogFunctionEntry("ScanDirectory", 'FileManagerService', directoryPath, recursive=recursive)
            
            # Validate the directory path
            isValid, validatedPath = self.ValidateUnicodePath(directoryPath)
            
            if not isValid:
                LoggingService.LogDebug(f"Unicode validation failed for directory: {directoryPath}", 'ScanDirectory', 'FileManagerService')
                self.EncodingErrors.append(f"Unicode issue: {directoryPath}")
            
            if not os.path.exists(directoryPath):
                LoggingService.LogWarning(f"Directory does not exist: {directoryPath}", 'ScanDirectory', 'FileManagerService')
                return mediaFiles
            
            if not os.path.isdir(directoryPath):
                LoggingService.LogWarning(f"Path is not a directory: {directoryPath}", 'ScanDirectory', 'FileManagerService')
                return mediaFiles
            
            # Scan the directory
            if recursive:
                for root, dirs, files in os.walk(directoryPath):
                    for file in files:
                        try:
                            filePath = os.path.join(root, file)
                            
                            # Validate each file path
                            fileIsValid, validatedFilePath = self.ValidateUnicodePath(filePath)
                            
                            if not fileIsValid:
                                LoggingService.LogDebug(f"Unicode validation failed for file: {filePath}", 'ScanDirectory', 'FileManagerService')
                                self.EncodingErrors.append(f"Unicode issue: {filePath}")
                            
                            if self.IsMediaFile(filePath):
                                mediaFiles.append(filePath)
                                self.ProcessedFiles += 1
                            else:
                                self.SkippedFiles += 1
                                
                        except Exception as e:
                            LoggingService.LogException("Error processing file in directory scan", e, 'ScanDirectory', 'FileManagerService')
                            self.SkippedFiles += 1
                            continue
            else:
                # Non-recursive scan
                try:
                    files = os.listdir(directoryPath)
                    for file in files:
                        try:
                            filePath = os.path.join(directoryPath, file)
                            
                            if os.path.isfile(filePath):
                                # Validate each file path
                                fileIsValid, validatedFilePath = self.ValidateUnicodePath(filePath)
                                
                                if not fileIsValid:
                                    LoggingService.LogDebug(f"Unicode validation failed for file: {filePath}", 'ScanDirectory', 'FileManagerService')
                                    self.EncodingErrors.append(f"Unicode issue: {filePath}")
                                
                                if self.IsMediaFile(filePath):
                                    mediaFiles.append(filePath)
                                    self.ProcessedFiles += 1
                                else:
                                    self.SkippedFiles += 1
                                    
                        except Exception as e:
                            LoggingService.LogException("Error processing file in non-recursive scan", e, 'ScanDirectory', 'FileManagerService')
                            self.SkippedFiles += 1
                            continue
                            
                except Exception as e:
                    LoggingService.LogException("Error listing directory contents", e, 'ScanDirectory', 'FileManagerService')
                    return mediaFiles
            
            LoggingService.LogInfo(f"Directory scan completed. Found {len(mediaFiles)} media files, processed {self.ProcessedFiles}, skipped {self.SkippedFiles}", 'FileManagerService', 'ScanDirectory')
            
        except Exception as e:
            LoggingService.LogException("Error in directory scan", e, 'ScanDirectory', 'FileManagerService')
        
        return mediaFiles
    
    def CalculateDirectorySize(self, directoryPath: str) -> float:
        """Calculate total size of directory in GB with Unicode path support."""
        totalSizeBytes = 0
        
        try:
            LoggingService.LogFunctionEntry("CalculateDirectorySize", 'FileManagerService', directoryPath)
            
            # Validate the directory path
            isValid, validatedPath = self.ValidateUnicodePath(directoryPath)
            
            if not isValid:
                LoggingService.LogDebug(f"Unicode validation failed for directory: {directoryPath}", 'CalculateDirectorySize', 'FileManagerService')
                self.EncodingErrors.append(f"Unicode issue: {directoryPath}")
            
            if not os.path.exists(directoryPath) or not os.path.isdir(directoryPath):
                LoggingService.LogWarning(f"Directory does not exist or is not a directory: {directoryPath}", 'CalculateDirectorySize', 'FileManagerService')
                return 0.0
            
            # Walk through all files in the directory
            for root, dirs, files in os.walk(directoryPath):
                for file in files:
                    try:
                        filePath = os.path.join(root, file)
                        
                        # Validate each file path
                        fileIsValid, validatedFilePath = self.ValidateUnicodePath(filePath)
                        
                        if not fileIsValid:
                            LoggingService.LogDebug(f"Unicode validation failed for file: {filePath}", 'CalculateDirectorySize', 'FileManagerService')
                            self.EncodingErrors.append(f"Unicode issue: {filePath}")
                        
                        if os.path.exists(filePath):
                            totalSizeBytes += os.path.getsize(filePath)
                            
                    except Exception as e:
                        LoggingService.LogException("Error calculating file size", e, 'CalculateDirectorySize', 'FileManagerService')
                        continue
            
            # Convert to GB
            totalSizeGB = totalSizeBytes / (1024 * 1024 * 1024)
            LoggingService.LogInfo(f"Directory size calculated: {totalSizeGB} GB", 'CalculateDirectorySize', 'FileManagerService')
            
        except Exception as e:
            LoggingService.LogException("Error calculating directory size", e, 'CalculateDirectorySize', 'FileManagerService')
            return 0.0
        
        return totalSizeGB
    
    def GetFileNameFromPath(self, filePath: str) -> str:
        """Extract filename from path with Unicode support."""
        try:
            # Validate the path first
            isValid, validatedPath = self.ValidateUnicodePath(filePath)
            
            if not isValid:
                LoggingService.LogDebug(f"Unicode validation failed for path: {filePath}", 'GetFileNameFromPath', 'FileManagerService')
                self.EncodingErrors.append(f"Unicode issue: {filePath}")
            
            return os.path.basename(filePath)
            
        except Exception as e:
            LoggingService.LogException("Error extracting filename", e, 'GetFileNameFromPath', 'FileManagerService')
            return "UnknownFile"
    
    def GetEncodingErrors(self) -> List[str]:
        """Get list of encoding errors encountered during operations."""
        return self.EncodingErrors.copy()
    
    def ClearEncodingErrors(self):
        """Clear the list of encoding errors."""
        self.EncodingErrors.clear()
    
    def GetProcessingStats(self) -> dict:
        """Get processing statistics."""
        return {
            'ProcessedFiles': self.ProcessedFiles,
            'SkippedFiles': self.SkippedFiles,
            'EncodingErrors': len(self.EncodingErrors)
        }
    
    def ResetStats(self):
        """Reset processing statistics."""
        self.ProcessedFiles = 0
        self.SkippedFiles = 0
        self.EncodingErrors.clear()
    
    def ExtractMediaMetadata(self, FilePath: str) -> Dict[str, Any]:
        """Extract metadata from a media file using FFmpegAnalysisService."""
        try:
            LoggingService.LogFunctionEntry("ExtractMediaMetadata", 'FileManagerService', FilePath)
            
            if not self.FFmpegAnalysisService.IsAvailable():
                LoggingService.LogWarning("Media analysis service not available", 'ExtractMediaMetadata', 'FileManagerService')
                return {
                    'Success': False,
                    'ErrorMessage': 'Media analysis service not available',
                    'VideoBitrateKbps': None,
                    'AudioBitrateKbps': None,
                    'Resolution': None,
                    'Codec': None,
                    'DurationMinutes': None,
                    'FrameRate': None,
                    'CompressionPotential': 'Unknown',
                    'AssignedProfile': 'Default',
                    'Title': None,
                    'ShowTitle': None,
                    'Season': None,
                    'Episode': None,
                    'EpisodeTitle': None,
                    'Year': None,
                    'Genre': None,
                    'Language': None,
                    'Subtitles': None,
                    'AudioChannels': None,
                    'AudioCodec': None,
                    'VideoCodec': None,
                    'ContainerFormat': None,
                    'CreationDate': None,
                    'ModificationDate': None,
                    'FileExtension': None,
                    'Quality': None,
                    'Source': None,
                    'ReleaseGroup': None
                }
            
            # Use FFmpegAnalysisService to analyze the file
            AnalysisModel = self.FFmpegAnalysisService.AnalyzeMediaFile(FilePath)
            AnalysisResult = AnalysisModel.ToDict()
            
            LoggingService.LogDebug(f"Metadata extraction completed for: {FilePath}", 'ExtractMediaMetadata', 'FileManagerService')
            return AnalysisResult
            
        except Exception as e:
            LoggingService.LogException("Error extracting media metadata", e, 'ExtractMediaMetadata', 'FileManagerService')
            return {
                'Success': False,
                'ErrorMessage': f'Metadata extraction error: {str(e)}',
                'VideoBitrateKbps': None,
                'AudioBitrateKbps': None,
                'Resolution': None,
                'Codec': None,
                'DurationMinutes': None,
                'FrameRate': None,
                'CompressionPotential': 'Unknown',
                'AssignedProfile': 'Default',
                'Title': None,
                'ShowTitle': None,
                'Season': None,
                'Episode': None,
                'EpisodeTitle': None,
                'Year': None,
                'Genre': None,
                'Language': None,
                'Subtitles': None,
                'AudioChannels': None,
                'AudioCodec': None,
                'VideoCodec': None,
                'ContainerFormat': None,
                'CreationDate': None,
                'ModificationDate': None,
                'FileExtension': None,
                'Quality': None,
                'Source': None,
                'ReleaseGroup': None
            }
    
    def ExtractMediaMetadataBatch(self, FilePaths: List[str]) -> List[Dict[str, Any]]:
        """Extract metadata from multiple media files in batch."""
        try:
            LoggingService.LogFunctionEntry("ExtractMediaMetadataBatch", 'FileManagerService', f"Processing {len(FilePaths)} files")
            
            if not self.FFmpegAnalysisService.IsAvailable():
                LoggingService.LogWarning("Media analysis service not available for batch processing", 'ExtractMediaMetadataBatch', 'FileManagerService')
                # Return empty results for all files
                return [{
                    'FilePath': FilePath,
                    'Success': False,
                    'ErrorMessage': 'Media analysis service not available',
                    'VideoBitrateKbps': None,
                    'AudioBitrateKbps': None,
                    'Resolution': None,
                    'Codec': None,
                    'DurationMinutes': None,
                    'FrameRate': None,
                    'CompressionPotential': 'Unknown',
                    'AssignedProfile': 'Default',
                    'Title': None,
                    'ShowTitle': None,
                    'Season': None,
                    'Episode': None,
                    'EpisodeTitle': None,
                    'Year': None,
                    'Genre': None,
                    'Language': None,
                    'Subtitles': None,
                    'AudioChannels': None,
                    'AudioCodec': None,
                    'VideoCodec': None,
                    'ContainerFormat': None,
                    'CreationDate': None,
                    'ModificationDate': None,
                    'FileExtension': None,
                    'Quality': None,
                    'Source': None,
                    'ReleaseGroup': None
                } for FilePath in FilePaths]
            
            # Use FFmpegAnalysisService to analyze files in batch
            AnalysisResults = []
            for FilePath in FilePaths:
                AnalysisModel = self.FFmpegAnalysisService.AnalyzeMediaFile(FilePath)
                AnalysisResult = AnalysisModel.ToDict()
                AnalysisResult['FilePath'] = FilePath
                AnalysisResults.append(AnalysisResult)
            
            LoggingService.LogInfo(f"Batch metadata extraction completed for {len(FilePaths)} files", 'ExtractMediaMetadataBatch', 'FileManagerService')
            return AnalysisResults
            
        except Exception as e:
            LoggingService.LogException("Error in batch media metadata extraction", e, 'ExtractMediaMetadataBatch', 'FileManagerService')
            # Return error results for all files
            return [{
                'FilePath': FilePath,
                'Success': False,
                'ErrorMessage': f'Batch metadata extraction error: {str(e)}',
                'VideoBitrateKbps': None,
                'AudioBitrateKbps': None,
                'Resolution': None,
                'Codec': None,
                'DurationMinutes': None,
                'FrameRate': None,
                'CompressionPotential': 'Unknown',
                'AssignedProfile': 'Default',
                'Title': None,
                'ShowTitle': None,
                'Season': None,
                'Episode': None,
                'EpisodeTitle': None,
                'Year': None,
                'Genre': None,
                'Language': None,
                'Subtitles': None,
                'AudioChannels': None,
                'AudioCodec': None,
                'VideoCodec': None,
                'ContainerFormat': None,
                'CreationDate': None,
                'ModificationDate': None,
                'FileExtension': None,
                'Quality': None,
                'Source': None,
                'ReleaseGroup': None
            } for FilePath in FilePaths]
    
    def IsMediaAnalysisAvailable(self) -> bool:
        """Check if media analysis is available."""
        return self.FFmpegAnalysisService.IsAvailable()
    
    def GetMediaAnalysisStats(self) -> Dict[str, int]:
        """Get media analysis processing statistics."""
        return {
            'ProcessedFiles': self.ProcessedFiles,
            'SkippedFiles': self.SkippedFiles,
            'EncodingErrors': len(self.EncodingErrors)
        }
    
    def GetMediaAnalysisErrors(self) -> List[str]:
        """Get media analysis errors."""
        return self.EncodingErrors.copy()
    
    def ClearMediaAnalysisErrors(self):
        """Clear media analysis errors."""
        self.EncodingErrors.clear()
    
    def ResetMediaAnalysisStats(self):
        """Reset media analysis statistics."""
        self.ProcessedFiles = 0
        self.SkippedFiles = 0
        self.EncodingErrors.clear()
