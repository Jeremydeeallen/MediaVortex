import os
import sys
from typing import List, Optional, Tuple
from pathlib import Path
from Services.DebugService import DebugService


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
    
    def IsMediaFile(self, filePath: str) -> bool:
        """Check if a file is a media file based on its extension."""
        try:
            fileExtension = Path(filePath).suffix.lower()
            return fileExtension in self.MediaExtensions
        except Exception as e:
            DebugService.LogException("Error checking media file extension", e)
            return False
    
    def ValidateUnicodePath(self, filePath: str) -> Tuple[bool, str]:
        """Validate and sanitize Unicode file paths."""
        try:
            # Test if the path can be encoded/decoded properly
            encodedPath = filePath.encode('utf-8')
            decodedPath = encodedPath.decode('utf-8')
            
            if decodedPath == filePath:
                return True, filePath
            else:
                # Path has encoding issues, create a sanitized version
                sanitizedPath = self.SanitizeUnicodePath(filePath)
                return False, sanitizedPath
                
        except UnicodeEncodeError as e:
            DebugService.Log("Unicode encoding error for path: {}", filePath)
            sanitizedPath = self.SanitizeUnicodePath(filePath)
            return False, sanitizedPath
        except UnicodeDecodeError as e:
            DebugService.Log("Unicode decoding error for path: {}", filePath)
            sanitizedPath = self.SanitizeUnicodePath(filePath)
            return False, sanitizedPath
        except Exception as e:
            DebugService.LogException("Unexpected error validating Unicode path", e)
            sanitizedPath = self.SanitizeUnicodePath(filePath)
            return False, sanitizedPath
    
    def SanitizeUnicodePath(self, filePath: str) -> str:
        """Create a sanitized version of a path with problematic Unicode characters."""
        try:
            # Replace problematic characters with safe alternatives
            sanitized = filePath
            
            # Common problematic character replacements
            replacements = {
                'Я': 'R',  # Cyrillic Ya
                'Р': 'P',  # Cyrillic Er
                'у': 'y',  # Cyrillic u
                'с': 'c',  # Cyrillic es
                'к': 'k',  # Cyrillic ka
                'и': 'i',  # Cyrillic i
                'й': 'j',  # Cyrillic short i
                'ё': 'e',  # Cyrillic yo
                'ж': 'zh', # Cyrillic zhe
                'з': 'z',  # Cyrillic ze
                'х': 'h',  # Cyrillic ha
                'ъ': '',   # Cyrillic hard sign
                'ф': 'f',  # Cyrillic ef
                'ы': 'y',  # Cyrillic yery
                'в': 'v',  # Cyrillic ve
                'а': 'a',  # Cyrillic a
                'п': 'p',  # Cyrillic pe
                'р': 'r',  # Cyrillic er
                'о': 'o',  # Cyrillic o
                'л': 'l',  # Cyrillic el
                'д': 'd',  # Cyrillic de
                'ж': 'zh', # Cyrillic zhe
                'э': 'e',  # Cyrillic e
                'щ': 'shch', # Cyrillic shcha
                'ч': 'ch', # Cyrillic che
                'с': 's',  # Cyrillic es
                'м': 'm',  # Cyrillic em
                'и': 'i',  # Cyrillic i
                'т': 't',  # Cyrillic te
                'ь': '',   # Cyrillic soft sign
                'б': 'b',  # Cyrillic be
                'ю': 'yu', # Cyrillic yu
                'я': 'ya', # Cyrillic ya
                '🎬': '[Movie]',  # Movie camera emoji
                '': '[Comedy]',  # Comedy emoji
                '€': 'EUR',      # Euro symbol
                '∑': 'SUM',      # Summation symbol
                '∞': 'INF',      # Infinity symbol
                'α': 'alpha',    # Greek alpha
                'β': 'beta',     # Greek beta
                'γ': 'gamma',    # Greek gamma
                'δ': 'delta',    # Greek delta
                'ε': 'epsilon',  # Greek epsilon
                'ζ': 'zeta',     # Greek zeta
                'η': 'eta',      # Greek eta
                'θ': 'theta',    # Greek theta
                'λ': 'lambda',   # Greek lambda
                'μ': 'mu',       # Greek mu
                'π': 'pi',       # Greek pi
                'σ': 'sigma',    # Greek sigma
                'τ': 'tau',      # Greek tau
                'φ': 'phi',      # Greek phi
                'ψ': 'psi',      # Greek psi
                'ω': 'omega',    # Greek omega
            }
            
            for original, replacement in replacements.items():
                sanitized = sanitized.replace(original, replacement)
            
            # Remove any remaining non-ASCII characters that might cause issues
            try:
                sanitized.encode('ascii')
                return sanitized
            except UnicodeEncodeError:
                # If still has non-ASCII, encode as ASCII with error handling
                return sanitized.encode('ascii', errors='replace').decode('ascii')
                
        except Exception as e:
            DebugService.LogException("Error sanitizing Unicode path", e)
            # Fallback: return a safe filename
            return f"SanitizedFile{hash(filePath) % 10000}"
    
    def GetFileSizeMB(self, filePath: str) -> float:
        """Get file size in MB with Unicode path support."""
        try:
            # Validate the path first
            isValid, safePath = self.ValidateUnicodePath(filePath)
            
            if not isValid:
                DebugService.Log("Using sanitized path for file size: {}", safePath)
                self.EncodingErrors.append(f"Unicode issue: {filePath} -> {safePath}")
            
            # Try to get file size
            if os.path.exists(safePath):
                sizeBytes = os.path.getsize(safePath)
                return sizeBytes / (1024 * 1024)  # Convert to MB
            else:
                DebugService.Log("File not found: {}", safePath)
                return 0.0
                
        except Exception as e:
            DebugService.LogException("Error getting file size", e)
            return 0.0
    
    def ScanDirectory(self, directoryPath: str, recursive: bool = True) -> List[str]:
        """Scan directory for media files with Unicode character support."""
        mediaFiles = []
        
        try:
            DebugService.LogFunctionEntry("ScanDirectory", directoryPath, recursive)
            
            # Validate the directory path
            isValid, safePath = self.ValidateUnicodePath(directoryPath)
            
            if not isValid:
                DebugService.Log("Using sanitized path for directory scan: {}", safePath)
                self.EncodingErrors.append(f"Unicode issue: {directoryPath} -> {safePath}")
            
            if not os.path.exists(safePath):
                DebugService.Log("Directory does not exist: {}", safePath)
                return mediaFiles
            
            if not os.path.isdir(safePath):
                DebugService.Log("Path is not a directory: {}", safePath)
                return mediaFiles
            
            # Scan the directory
            if recursive:
                for root, dirs, files in os.walk(safePath):
                    for file in files:
                        try:
                            filePath = os.path.join(root, file)
                            
                            # Validate each file path
                            fileIsValid, safeFilePath = self.ValidateUnicodePath(filePath)
                            
                            if not fileIsValid:
                                DebugService.Log("Using sanitized path for file: {}", safeFilePath)
                                self.EncodingErrors.append(f"Unicode issue: {filePath} -> {safeFilePath}")
                            
                            if self.IsMediaFile(safeFilePath):
                                mediaFiles.append(safeFilePath)
                                self.ProcessedFiles += 1
                            else:
                                self.SkippedFiles += 1
                                
                        except Exception as e:
                            DebugService.LogException("Error processing file in directory scan", e)
                            self.SkippedFiles += 1
                            continue
            else:
                # Non-recursive scan
                try:
                    files = os.listdir(safePath)
                    for file in files:
                        try:
                            filePath = os.path.join(safePath, file)
                            
                            if os.path.isfile(filePath):
                                # Validate each file path
                                fileIsValid, safeFilePath = self.ValidateUnicodePath(filePath)
                                
                                if not fileIsValid:
                                    DebugService.Log("Using sanitized path for file: {}", safeFilePath)
                                    self.EncodingErrors.append(f"Unicode issue: {filePath} -> {safeFilePath}")
                                
                                if self.IsMediaFile(safeFilePath):
                                    mediaFiles.append(safeFilePath)
                                    self.ProcessedFiles += 1
                                else:
                                    self.SkippedFiles += 1
                                    
                        except Exception as e:
                            DebugService.LogException("Error processing file in non-recursive scan", e)
                            self.SkippedFiles += 1
                            continue
                            
                except Exception as e:
                    DebugService.LogException("Error listing directory contents", e)
                    return mediaFiles
            
            DebugService.Log("Directory scan completed. Found {} media files, processed {}, skipped {}", 
                           len(mediaFiles), self.ProcessedFiles, self.SkippedFiles)
            
        except Exception as e:
            DebugService.LogException("Error in directory scan", e)
        
        return mediaFiles
    
    def CalculateDirectorySize(self, directoryPath: str) -> float:
        """Calculate total size of directory in GB with Unicode path support."""
        totalSizeBytes = 0
        
        try:
            DebugService.LogFunctionEntry("CalculateDirectorySize", directoryPath)
            
            # Validate the directory path
            isValid, safePath = self.ValidateUnicodePath(directoryPath)
            
            if not isValid:
                DebugService.Log("Using sanitized path for directory size calculation: {}", safePath)
                self.EncodingErrors.append(f"Unicode issue: {directoryPath} -> {safePath}")
            
            if not os.path.exists(safePath) or not os.path.isdir(safePath):
                DebugService.Log("Directory does not exist or is not a directory: {}", safePath)
                return 0.0
            
            # Walk through all files in the directory
            for root, dirs, files in os.walk(safePath):
                for file in files:
                    try:
                        filePath = os.path.join(root, file)
                        
                        # Validate each file path
                        fileIsValid, safeFilePath = self.ValidateUnicodePath(filePath)
                        
                        if not fileIsValid:
                            DebugService.Log("Using sanitized path for file size calculation: {}", safeFilePath)
                            self.EncodingErrors.append(f"Unicode issue: {filePath} -> {safeFilePath}")
                        
                        if os.path.exists(safeFilePath):
                            totalSizeBytes += os.path.getsize(safeFilePath)
                            
                    except Exception as e:
                        DebugService.LogException("Error calculating file size", e)
                        continue
            
            # Convert to GB
            totalSizeGB = totalSizeBytes / (1024 * 1024 * 1024)
            DebugService.Log("Directory size calculated: {} GB", totalSizeGB)
            
        except Exception as e:
            DebugService.LogException("Error calculating directory size", e)
            return 0.0
        
        return totalSizeGB
    
    def GetFileNameFromPath(self, filePath: str) -> str:
        """Extract filename from path with Unicode support."""
        try:
            # Validate the path first
            isValid, safePath = self.ValidateUnicodePath(filePath)
            
            if not isValid:
                DebugService.Log("Using sanitized path for filename extraction: {}", safePath)
                self.EncodingErrors.append(f"Unicode issue: {filePath} -> {safePath}")
            
            return os.path.basename(safePath)
            
        except Exception as e:
            DebugService.LogException("Error extracting filename", e)
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
