import os
import sys
from typing import List, Optional, Tuple, Dict, Any
from pathlib import Path
from Services.LoggingService import LoggingService
from Services.FFmpegAnalysisService import FFmpegAnalysisService
# directive: path-schema-migration | # see path.S8
from Core.Path.LocalPath import LocalBasename, LocalDirname, LocalJoin


# directive: path-schema-migration | # see path.S8
def _LocalExists(Value) -> bool:
    """Local filesystem existence check for a worker-resolved string value."""
    return bool(Value) and os.path.exists(Value)


# directive: path-schema-migration | # see path.S8
def _LocalIsFile(Value) -> bool:
    """Local filesystem isfile check for a worker-resolved string value."""
    return bool(Value) and os.path.isfile(Value)


# directive: path-schema-migration | # see path.S8
def _LocalIsDir(Value) -> bool:
    """Local filesystem isdir check for a worker-resolved string value."""
    return bool(Value) and os.path.isdir(Value)


# directive: path-schema-migration | # see path.S8
def _LocalGetSize(Value) -> int:
    """Local filesystem getsize for a worker-resolved string value."""
    return os.path.getsize(Value)


# directive: path-schema-migration | # see path.S8
def _NormalizeValue(Value) -> str:
    """Forward-slash to backslash normalization for a worker-resolved string value."""
    return (Value or "").replace("/", "\\")


# directive: path-schema-migration | # see path.S8
def _ValuesEqual(A, B) -> bool:
    """Case-insensitive equality after backslash normalization (Windows-shape semantics)."""
    return _NormalizeValue(A).lower() == _NormalizeValue(B).lower()


class FileManagerService:
    """Handles file system operations and metadata extraction with Unicode character support."""
    
    # Common media file extensions
    MediaExtensions = {
        '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp', '.mpg', '.mpeg',
        '.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a', '.opus'
    }
    
    def __init__(self, FFprobePath: str = None):
        self.EncodingErrors = []
        self.ProcessedFiles = 0
        self.SkippedFiles = 0
        self.FFmpegAnalysisService = FFmpegAnalysisService(FFprobePath=FFprobePath)
        self.ExcludedDirectories = self._LoadExcludedDirectories()

    def _LoadExcludedDirectories(self) -> List[str]:
        """Load excluded directories from SystemSettings."""
        try:
            from Repositories.DatabaseManager import DatabaseManager
            db_manager = DatabaseManager()

            # Get excluded directories setting (comma-separated list)
            excluded_setting = db_manager.GetSystemSetting('ExcludedDirectories')

            if excluded_setting:
                excluded = [_NormalizeValue(d.strip()) for d in excluded_setting.split(',') if d.strip()]
                LoggingService.LogInfo(f"Loaded {len(excluded)} excluded directories", 'FileManagerService', '_LoadExcludedDirectories')
                return excluded
            else:
                default_excluded = 'Z:\\Videos\\downloads'
                db_manager.AddOrUpdateSystemSetting('ExcludedDirectories', default_excluded, 'Comma-separated list of directories to exclude from scanning', 'text')
                LoggingService.LogInfo(f"Created ExcludedDirectories setting with default: {default_excluded}", 'FileManagerService', '_LoadExcludedDirectories')
                return [_NormalizeValue(default_excluded)]

        except Exception as e:
            LoggingService.LogException("Error loading excluded directories", e, 'FileManagerService', '_LoadExcludedDirectories')
            return []

    # directive: path-schema-migration | # see path.S8
    def ShouldExcludeDirectory(self, directory_path: str) -> bool:
        """Check if a directory should be excluded from scanning."""
        try:
            normalized_path = _NormalizeValue(directory_path)

            for excluded in self.ExcludedDirectories:
                if _ValuesEqual(normalized_path, excluded) or normalized_path.lower().startswith(excluded.lower() + os.sep):
                    LoggingService.LogDebug(f"Excluding directory: {directory_path}", 'ShouldExcludeDirectory', 'FileManagerService')
                    return True

            return False

        except Exception as e:
            LoggingService.LogException("Error checking if directory should be excluded", e, 'FileManagerService', 'ShouldExcludeDirectory')
            return False
    
    def IsMediaFile(self, filePath: str) -> bool:
        """Check if a file is a media file based on its extension.

        Skips MediaVortex artifacts:
          - `.old.<ext>` -- legacy backup left by pre-2026-05-16 file
            replacements (KeepSource=True). Not a separate media file.
          - `.inprogress` -- in-flight FFmpeg output, not yet verified.
            See worker-lifecycle.feature.md criterion 6.
          - `.orig` -- legacy mid-replacement backup from the pre-`.inprogress`
            pattern. Filtered defensively.
        See Features/FileReplacement/transcoded-output-placement.feature.md criterion 9.
        """
        try:
            FileNameLower = Path(filePath).name.lower()
            Stem = Path(FileNameLower).stem
            if Stem.endswith(".old"):
                return False
            if FileNameLower.endswith(".inprogress"):
                return False
            if FileNameLower.endswith(".orig"):
                return False
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
            
            if _LocalExists(filePath):
                sizeBytes = _LocalGetSize(filePath)
                return sizeBytes / (1024 * 1024)
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
            
            if not _LocalExists(directoryPath):
                LoggingService.LogWarning(f"Directory does not exist: {directoryPath}", 'ScanDirectory', 'FileManagerService')
                return mediaFiles

            if not _LocalIsDir(directoryPath):
                LoggingService.LogWarning(f"Path is not a directory: {directoryPath}", 'ScanDirectory', 'FileManagerService')
                return mediaFiles
            
            # Scan the directory
            if recursive:
                for root, dirs, files in os.walk(directoryPath):
                    # Filter out excluded directories (modifying dirs in-place prevents os.walk from descending into them)
                    dirs[:] = [d for d in dirs if not self.ShouldExcludeDirectory(os.path.join(root, d))]

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
                            filePath = LocalJoin(directoryPath, file)

                            if _LocalIsFile(filePath):
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
            
            if not _LocalExists(directoryPath) or not _LocalIsDir(directoryPath):
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
                        
                        if _LocalExists(filePath):
                            totalSizeBytes += _LocalGetSize(filePath)
                            
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
        """Extract filename from a path. Handles both forward and backslash
        separators regardless of the host OS, because MediaVortex stores
        Windows-shaped canonical paths (`T:\\Show\\file.mkv`) and Linux
        workers must extract the basename from those without `os.path.basename`
        (which on POSIX treats `\\` as a literal character and returns the
        whole string)."""
        try:
            isValid, validatedPath = self.ValidateUnicodePath(filePath)

            if not isValid:
                LoggingService.LogDebug(f"Unicode validation failed for path: {filePath}", 'GetFileNameFromPath', 'FileManagerService')
                self.EncodingErrors.append(f"Unicode issue: {filePath}")

            # Last segment after any '/' or '\\' separator. Works for canonical
            # Windows paths on Linux containers and for native local paths on
            # either OS.
            normalized = filePath.replace('\\', '/')
            return normalized.rsplit('/', 1)[-1]

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
    
    def SetupTranscodingDirectories(self) -> Dict[str, Any]:
        """Setup transcoding directories and return their paths."""
        try:
            import os
            from Services.LoggingService import LoggingService
            
            # Define directory paths
            mediaVortexSourceDir = r"c:\MediaVortex\Source"
            mediaVortexTempDir = r"c:\MediaVortex"
            
            # Create directories if they don't exist
            directories_created = 0
            for directory in [mediaVortexSourceDir, mediaVortexTempDir]:
                if not os.path.exists(directory):
                    os.makedirs(directory, exist_ok=True)
                    directories_created += 1
                    LoggingService.LogInfo(f"Created directory: {directory}", "FileManagerService", "SetupTranscodingDirectories")
                else:
                    LoggingService.LogInfo(f"Directory already exists: {directory}", "FileManagerService", "SetupTranscodingDirectories")
            
            LoggingService.LogInfo(f"Transcoding directories setup completed successfully. Created: {directories_created} directories", "FileManagerService", "SetupTranscodingDirectories")
            
            return {
                'Success': True,
                'MediaVortexSourceDir': mediaVortexSourceDir,
                'MediaVortexTempDir': mediaVortexTempDir,
                'DirectoriesCreated': directories_created
            }
            
        except Exception as e:
            LoggingService.LogException("Exception setting up transcoding directories", e, "FileManagerService", "SetupTranscodingDirectories")
            return {
                'Success': False,
                'ErrorMessage': f"Failed to setup transcoding directories: {str(e)}"
            }
    
    def CopyFile(self, SourcePath: str, DestinationPath: str) -> Dict[str, Any]:
        """Copy a file from source to destination."""
        try:
            import os
            import shutil
            from Services.LoggingService import LoggingService
            
            fileName = LocalBasename(SourcePath)
            LoggingService.LogInfo(f"File copy {fileName} to {DestinationPath} started", "FileManagerService", "CopyFile")

            destDir = LocalDirname(DestinationPath)
            if destDir and not _LocalExists(destDir):
                os.makedirs(destDir, exist_ok=True)
            
            # Copy the file
            shutil.copy2(SourcePath, DestinationPath)
            
            LoggingService.LogInfo(f"Successfully copied file: {SourcePath} -> {DestinationPath}", "FileManagerService", "CopyFile")
            LoggingService.LogInfo(f"File copy {fileName} complete", "FileManagerService", "CopyFile")
            
            return {
                'Success': True,
                'SourcePath': SourcePath,
                'DestinationPath': DestinationPath
            }
            
        except Exception as e:
            LoggingService.LogException(f"Exception copying file from {SourcePath} to {DestinationPath}", e, "FileManagerService", "CopyFile")
            return {
                'Success': False,
                'ErrorMessage': f"Failed to copy file: {str(e)}",
                'SourcePath': SourcePath,
                'DestinationPath': DestinationPath
            }
    
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
                    'ReleaseGroup': None,
                    'TotalFrames': None,
                    'CodecProfile': None,
                    'ColorRange': None,
                    'FieldOrder': None,
                    'HasBFrames': None,
                    'RefFrames': None,
                    'PixelFormat': None,
                    'Level': None,
                    'AudioChannels': None,
                    'AudioSampleRate': None,
                    'AudioSampleFormat': None,
                    'AudioChannelLayout': None,
                    'OverallBitrate': None
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
    
    def EnsureDirectoryExists(self, DirectoryPath: str) -> bool:
        """Ensure a directory exists, creating it if necessary with Unicode path support."""
        try:
            LoggingService.LogFunctionEntry("EnsureDirectoryExists", 'FileManagerService', DirectoryPath)
            
            # Validate the directory path
            isValid, validatedPath = self.ValidateUnicodePath(DirectoryPath)
            
            if not isValid:
                LoggingService.LogDebug(f"Unicode validation failed for directory: {DirectoryPath}", 'EnsureDirectoryExists', 'FileManagerService')
                self.EncodingErrors.append(f"Unicode issue: {DirectoryPath}")
            
            if _LocalExists(DirectoryPath):
                if _LocalIsDir(DirectoryPath):
                    LoggingService.LogDebug(f"Directory already exists: {DirectoryPath}", 'EnsureDirectoryExists', 'FileManagerService')
                    return True
                else:
                    LoggingService.LogError(f"Path exists but is not a directory: {DirectoryPath}", 'EnsureDirectoryExists', 'FileManagerService')
                    return False
            
            # Create directory and all parent directories
            os.makedirs(DirectoryPath, exist_ok=True)
            LoggingService.LogInfo(f"Created directory: {DirectoryPath}", 'EnsureDirectoryExists', 'FileManagerService')
            return True
            
        except Exception as e:
            LoggingService.LogException("Error ensuring directory exists", e, 'EnsureDirectoryExists', 'FileManagerService')
            return False
    
    def SetupTranscodingDirectories(self) -> Dict[str, Any]:
        """Setup the required transcoding directory structure."""
        try:
            LoggingService.LogFunctionEntry("SetupTranscodingDirectories", 'FileManagerService')
            
            # Define required directories
            MediaVortexSourceDir = r"c:\MediaVortex\Source"
            MediaVortexTempDir = r"c:\MediaVortex"
            
            Results = {
                'Success': True,
                'MediaVortexSourceDir': MediaVortexSourceDir,
                'MediaVortexTempDir': MediaVortexTempDir,
                'CreatedDirectories': [],
                'Errors': []
            }
            
            # Create MediaVortex\Source directory
            if self.EnsureDirectoryExists(MediaVortexSourceDir):
                Results['CreatedDirectories'].append(MediaVortexSourceDir)
                LoggingService.LogInfo(f"MediaVortex Source directory ready: {MediaVortexSourceDir}", 'SetupTranscodingDirectories', 'FileManagerService')
            else:
                Results['Success'] = False
                Results['Errors'].append(f"Failed to create MediaVortex Source directory: {MediaVortexSourceDir}")
                LoggingService.LogError(f"Failed to create MediaVortex Source directory: {MediaVortexSourceDir}", 'SetupTranscodingDirectories', 'FileManagerService')
            
            # Create MediaVortex directory
            if self.EnsureDirectoryExists(MediaVortexTempDir):
                Results['CreatedDirectories'].append(MediaVortexTempDir)
                LoggingService.LogInfo(f"MediaVortex Temp directory ready: {MediaVortexTempDir}", 'SetupTranscodingDirectories', 'FileManagerService')
            else:
                Results['Success'] = False
                Results['Errors'].append(f"Failed to create MediaVortex Temp directory: {MediaVortexTempDir}")
                LoggingService.LogError(f"Failed to create MediaVortex Temp directory: {MediaVortexTempDir}", 'SetupTranscodingDirectories', 'FileManagerService')
            
            # Log summary
            if Results['Success']:
                LoggingService.LogInfo(f"Transcoding directories setup completed successfully. Created: {len(Results['CreatedDirectories'])} directories", 'SetupTranscodingDirectories', 'FileManagerService')
            else:
                LoggingService.LogError(f"Transcoding directories setup failed. Errors: {Results['Errors']}", 'SetupTranscodingDirectories', 'FileManagerService')
            
            return Results
            
        except Exception as e:
            LoggingService.LogException("Error setting up transcoding directories", e, 'SetupTranscodingDirectories', 'FileManagerService')
            return {
                'Success': False,
                'MediaVortexSourceDir': r"c:\MediaVortex\Source",
                'MediaVortexTempDir': r"c:\MediaVortex",
                'CreatedDirectories': [],
                'Errors': [f"Setup error: {str(e)}"]
            }
    
    def ValidateFileExists(self, FilePath: str) -> bool:
        """Validate that a file exists on disk with Unicode path support."""
        try:
            LoggingService.LogFunctionEntry("ValidateFileExists", 'FileManagerService', FilePath)
            
            # Validate the path first
            isValid, validatedPath = self.ValidateUnicodePath(FilePath)
            
            if not isValid:
                LoggingService.LogDebug(f"Unicode validation failed for path: {FilePath}", 'ValidateFileExists', 'FileManagerService')
                self.EncodingErrors.append(f"Unicode issue: {FilePath}")
            
            fileExists = _LocalExists(FilePath)
            
            if not fileExists:
                LoggingService.LogDebug(f"File does not exist: {FilePath}", 'ValidateFileExists', 'FileManagerService')
            else:
                LoggingService.LogDebug(f"File exists: {FilePath}", 'ValidateFileExists', 'FileManagerService')
            
            return fileExists
            
        except Exception as e:
            LoggingService.LogException("Error validating file existence", e, 'ValidateFileExists', 'FileManagerService')
            return False
    
    def ValidateMediaFileExists(self, MediaFile) -> Dict[str, Any]:
        """Validate that a MediaFileModel exists on disk and return validation result."""
        try:
            LoggingService.LogFunctionEntry("ValidateMediaFileExists", 'FileManagerService', MediaFile.FilePath)
            
            fileExists = self.ValidateFileExists(MediaFile.FilePath)
            
            if not fileExists:
                LoggingService.LogWarning(f"Media file does not exist: {MediaFile.FileName} at {MediaFile.FilePath}", 'ValidateMediaFileExists', 'FileManagerService')
                return {
                    'Success': False,
                    'FileExists': False,
                    'ErrorMessage': f'File does not exist: {MediaFile.FileName}',
                    'FilePath': MediaFile.FilePath,
                    'FileName': MediaFile.FileName
                }
            else:
                LoggingService.LogDebug(f"Media file exists: {MediaFile.FileName}", 'ValidateMediaFileExists', 'FileManagerService')
                return {
                    'Success': True,
                    'FileExists': True,
                    'ErrorMessage': None,
                    'FilePath': MediaFile.FilePath,
                    'FileName': MediaFile.FileName
                }
                
        except Exception as e:
            LoggingService.LogException("Error validating media file existence", e, 'ValidateMediaFileExists', 'FileManagerService')
            return {
                'Success': False,
                'FileExists': False,
                'ErrorMessage': f'Validation error: {str(e)}',
                'FilePath': MediaFile.FilePath if hasattr(MediaFile, 'FilePath') else 'Unknown',
                'FileName': MediaFile.FileName if hasattr(MediaFile, 'FileName') else 'Unknown'
            }
    
    def CopyFile(self, SourceFilePath: str, DestinationFilePath: str) -> Dict[str, Any]:
        """Copy a file from source to destination with UTF-8 compatibility."""
        try:
            LoggingService.LogFunctionEntry("CopyFile", "FileManagerService", SourceFilePath, DestinationFilePath)
            
            if not _LocalExists(SourceFilePath):
                errorMsg = f"Source file does not exist: {SourceFilePath}"
                LoggingService.LogError(errorMsg, "FileManagerService", "CopyFile")
                return {'Success': False, 'ErrorMessage': errorMsg}

            destinationDir = LocalDirname(DestinationFilePath)
            if destinationDir and not _LocalExists(destinationDir):
                os.makedirs(destinationDir, exist_ok=True)
                LoggingService.LogInfo(f"Created destination directory: {destinationDir}", "FileManagerService", "CopyFile")
            
            # Copy file with UTF-8 path support
            import shutil
            shutil.copy2(SourceFilePath, DestinationFilePath)
            
            LoggingService.LogInfo(f"Successfully copied file: {SourceFilePath} -> {DestinationFilePath}", "FileManagerService", "CopyFile")
            return {'Success': True, 'DestinationFilePath': DestinationFilePath}
            
        except Exception as e:
            errorMsg = f"Error copying file: {str(e)}"
            LoggingService.LogException(errorMsg, e, "FileManagerService", "CopyFile")
            return {'Success': False, 'ErrorMessage': errorMsg}
    
    def ReplaceFile(self, OriginalFilePath: str, NewFilePath: str) -> Dict[str, Any]:
        """Replace original file with new file, handling UTF-8 paths."""
        try:
            LoggingService.LogFunctionEntry("ReplaceFile", "FileManagerService", OriginalFilePath, NewFilePath)
            
            if not _LocalExists(NewFilePath):
                errorMsg = f"New file does not exist: {NewFilePath}"
                LoggingService.LogError(errorMsg, "FileManagerService", "ReplaceFile")
                return {'Success': False, 'ErrorMessage': errorMsg}
            
            # Replace original file with new file (no backup created)
            import shutil
            shutil.move(NewFilePath, OriginalFilePath)
            
            LoggingService.LogInfo(f"Successfully replaced file: {OriginalFilePath}", "FileManagerService", "ReplaceFile")
            return {'Success': True, 'OriginalFilePath': OriginalFilePath}
            
        except Exception as e:
            errorMsg = f"Error replacing file: {str(e)}"
            LoggingService.LogException(errorMsg, e, "FileManagerService", "ReplaceFile")
            return {'Success': False, 'ErrorMessage': errorMsg}