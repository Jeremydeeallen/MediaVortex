import os
from typing import Optional
from pathlib import Path
from Models.FFmpegComparisonModel import FFmpegComparisonModel
from Models.FFmpegVMAFComparisonModel import FFmpegVMAFComparisonModel
from Services.FFmpegService import FFmpegService
from Services.LoggingService import LoggingService


class FFmpegComparisonService:
    """Business service for FFmpeg video comparison operations."""
    
    def __init__(self, FFmpegServiceInstance: FFmpegService = None):
        self.FFmpegService = FFmpegServiceInstance or FFmpegService()
    
    def CreateSideBySideComparison(self, OriginalFilePath: str, TranscodedFilePath: str,
                                 OutputPath: str = None, Width: int = None, Height: int = None) -> FFmpegComparisonModel:
        """Create a side-by-side comparison video."""
        try:
            LoggingService.LogFunctionEntry("CreateSideBySideComparison", 'FFmpegComparisonService', 
                                          f"Original: {OriginalFilePath}, Transcoded: {TranscodedFilePath}")
            
            # Create comparison model
            ComparisonModel = FFmpegComparisonModel()
            ComparisonModel.OriginalFilePath = OriginalFilePath
            ComparisonModel.TranscodedFilePath = TranscodedFilePath
            ComparisonModel.OriginalFileName = os.path.basename(OriginalFilePath)
            ComparisonModel.TranscodedFileName = os.path.basename(TranscodedFilePath)
            ComparisonModel.ComparisonType = "side_by_side"
            
            # Generate output path if not provided
            if not OutputPath:
                OriginalDir = os.path.dirname(OriginalFilePath)
                OriginalName = Path(OriginalFilePath).stem
                TranscodedName = Path(TranscodedFilePath).stem
                OutputPath = os.path.join(OriginalDir, f"{OriginalName}_vs_{TranscodedName}_comparison.mp4")
            
            ComparisonModel.ComparisonVideoPath = OutputPath
            
            # Build FFmpeg filter for side-by-side comparison
            FilterComplex = "[0:v][1:v]hstack=inputs=2[v]"
            
            # Add size constraints if specified
            if Width and Height:
                FilterComplex = f"[0:v]scale={Width//2}:{Height}[left];[1:v]scale={Width//2}:{Height}[right];[left][right]hstack[v]"
                ComparisonModel.Width = Width
                ComparisonModel.Height = Height
            elif Width:
                FilterComplex = f"[0:v]scale={Width//2}:-1[left];[1:v]scale={Width//2}:-1[right];[left][right]hstack[v]"
                ComparisonModel.Width = Width
            elif Height:
                FilterComplex = f"[0:v]scale=-1:{Height}[left];[1:v]scale=-1:{Height}[right];[left][right]hstack[v]"
                ComparisonModel.Height = Height
            
            # Build FFmpeg arguments
            Arguments = [
                '-i', OriginalFilePath,      # First input (original)
                '-i', TranscodedFilePath,    # Second input (transcoded)
                '-filter_complex', FilterComplex,
                '-map', '[v]',               # Map the combined video
                '-c:v', 'libx264',           # Video codec
                '-preset', 'fast',           # Encoding preset
                '-crf', '23'                 # Quality setting
            ]
            
            # Execute FFmpeg command
            Result = self.FFmpegService.ExecuteFFmpeg(Arguments, OutputFile=OutputPath)
            
            if Result['Success']:
                ComparisonModel.Success = True
                LoggingService.LogInfo(f"Successfully created side-by-side comparison: {OutputPath}", 'CreateSideBySideComparison', 'FFmpegComparisonService')
            else:
                ComparisonModel.Success = False
                ComparisonModel.ErrorMessage = Result.get('ErrorMessage', 'Comparison generation failed')
                LoggingService.LogWarning(f"Failed to create comparison: {ComparisonModel.ErrorMessage}", 'CreateSideBySideComparison', 'FFmpegComparisonService')
            
            return ComparisonModel
            
        except Exception as e:
            LoggingService.LogException("Error creating side-by-side comparison", e, 'CreateSideBySideComparison', 'FFmpegComparisonService')
            ComparisonModel = FFmpegComparisonModel()
            ComparisonModel.OriginalFilePath = OriginalFilePath
            ComparisonModel.TranscodedFilePath = TranscodedFilePath
            ComparisonModel.Success = False
            ComparisonModel.ErrorMessage = f"Comparison generation error: {str(e)}"
            return ComparisonModel
    
    def CreatePictureInPictureComparison(self, OriginalFilePath: str, TranscodedFilePath: str,
                                       OutputPath: str = None, PiPWidth: int = 320, PiPHeight: int = 180) -> FFmpegComparisonModel:
        """Create a picture-in-picture comparison video."""
        try:
            LoggingService.LogFunctionEntry("CreatePictureInPictureComparison", 'FFmpegComparisonService', 
                                          f"Original: {OriginalFilePath}, Transcoded: {TranscodedFilePath}")
            
            # Create comparison model
            ComparisonModel = FFmpegComparisonModel()
            ComparisonModel.OriginalFilePath = OriginalFilePath
            ComparisonModel.TranscodedFilePath = TranscodedFilePath
            ComparisonModel.OriginalFileName = os.path.basename(OriginalFilePath)
            ComparisonModel.TranscodedFileName = os.path.basename(TranscodedFilePath)
            ComparisonModel.ComparisonType = "picture_in_picture"
            
            # Generate output path if not provided
            if not OutputPath:
                OriginalDir = os.path.dirname(OriginalFilePath)
                OriginalName = Path(OriginalFilePath).stem
                TranscodedName = Path(TranscodedFilePath).stem
                OutputPath = os.path.join(OriginalDir, f"{OriginalName}_vs_{TranscodedName}_pip.mp4")
            
            ComparisonModel.ComparisonVideoPath = OutputPath
            
            # Build FFmpeg filter for picture-in-picture
            FilterComplex = f"[1:v]scale={PiPWidth}:{PiPHeight}[pip];[0:v][pip]overlay=W-w-10:H-h-10[v]"
            
            # Build FFmpeg arguments
            Arguments = [
                '-i', OriginalFilePath,      # Main video (original)
                '-i', TranscodedFilePath,    # Picture-in-picture video (transcoded)
                '-filter_complex', FilterComplex,
                '-map', '[v]',               # Map the combined video
                '-c:v', 'libx264',           # Video codec
                '-preset', 'fast',           # Encoding preset
                '-crf', '23'                 # Quality setting
            ]
            
            # Execute FFmpeg command
            Result = self.FFmpegService.ExecuteFFmpeg(Arguments, OutputFile=OutputPath)
            
            if Result['Success']:
                ComparisonModel.Success = True
                LoggingService.LogInfo(f"Successfully created picture-in-picture comparison: {OutputPath}", 'CreatePictureInPictureComparison', 'FFmpegComparisonService')
            else:
                ComparisonModel.Success = False
                ComparisonModel.ErrorMessage = Result.get('ErrorMessage', 'Comparison generation failed')
                LoggingService.LogWarning(f"Failed to create comparison: {ComparisonModel.ErrorMessage}", 'CreatePictureInPictureComparison', 'FFmpegComparisonService')
            
            return ComparisonModel
            
        except Exception as e:
            LoggingService.LogException("Error creating picture-in-picture comparison", e, 'CreatePictureInPictureComparison', 'FFmpegComparisonService')
            ComparisonModel = FFmpegComparisonModel()
            ComparisonModel.OriginalFilePath = OriginalFilePath
            ComparisonModel.TranscodedFilePath = TranscodedFilePath
            ComparisonModel.Success = False
            ComparisonModel.ErrorMessage = f"Comparison generation error: {str(e)}"
            return ComparisonModel
    
    def CreateOverlayComparison(self, OriginalFilePath: str, TranscodedFilePath: str,
                              OutputPath: str = None, OverlayOpacity: float = 0.5) -> FFmpegComparisonModel:
        """Create an overlay comparison video (transparency blend)."""
        try:
            LoggingService.LogFunctionEntry("CreateOverlayComparison", 'FFmpegComparisonService', 
                                          f"Original: {OriginalFilePath}, Transcoded: {TranscodedFilePath}")
            
            # Create comparison model
            ComparisonModel = FFmpegComparisonModel()
            ComparisonModel.OriginalFilePath = OriginalFilePath
            ComparisonModel.TranscodedFilePath = TranscodedFilePath
            ComparisonModel.OriginalFileName = os.path.basename(OriginalFilePath)
            ComparisonModel.TranscodedFileName = os.path.basename(TranscodedFilePath)
            ComparisonModel.ComparisonType = "overlay"
            
            # Generate output path if not provided
            if not OutputPath:
                OriginalDir = os.path.dirname(OriginalFilePath)
                OriginalName = Path(OriginalFilePath).stem
                TranscodedName = Path(TranscodedFilePath).stem
                OutputPath = os.path.join(OriginalDir, f"{OriginalName}_vs_{TranscodedName}_overlay.mp4")
            
            ComparisonModel.ComparisonVideoPath = OutputPath
            
            # Build FFmpeg filter for overlay comparison
            FilterComplex = f"[0:v][1:v]blend=all_mode=overlay:all_opacity={OverlayOpacity}[v]"
            
            # Build FFmpeg arguments
            Arguments = [
                '-i', OriginalFilePath,      # First input (original)
                '-i', TranscodedFilePath,    # Second input (transcoded)
                '-filter_complex', FilterComplex,
                '-map', '[v]',               # Map the combined video
                '-c:v', 'libx264',           # Video codec
                '-preset', 'fast',           # Encoding preset
                '-crf', '23'                 # Quality setting
            ]
            
            # Execute FFmpeg command
            Result = self.FFmpegService.ExecuteFFmpeg(Arguments, OutputFile=OutputPath)
            
            if Result['Success']:
                ComparisonModel.Success = True
                LoggingService.LogInfo(f"Successfully created overlay comparison: {OutputPath}", 'CreateOverlayComparison', 'FFmpegComparisonService')
            else:
                ComparisonModel.Success = False
                ComparisonModel.ErrorMessage = Result.get('ErrorMessage', 'Comparison generation failed')
                LoggingService.LogWarning(f"Failed to create comparison: {ComparisonModel.ErrorMessage}", 'CreateOverlayComparison', 'FFmpegComparisonService')
            
            return ComparisonModel
            
        except Exception as e:
            LoggingService.LogException("Error creating overlay comparison", e, 'CreateOverlayComparison', 'FFmpegComparisonService')
            ComparisonModel = FFmpegComparisonModel()
            ComparisonModel.OriginalFilePath = OriginalFilePath
            ComparisonModel.TranscodedFilePath = TranscodedFilePath
            ComparisonModel.Success = False
            ComparisonModel.ErrorMessage = f"Comparison generation error: {str(e)}"
            return ComparisonModel
    
    def CreateVMAFComparison(self, OriginalFilePath: str, TranscodedFilePath: str,
                            OutputPath: str = None, QualityWidth: int = 1280, 
                            QualityHeight: int = 720, VMAFModelPath: str = None) -> FFmpegVMAFComparisonModel:
        """Create a VMAF quality comparison between original and transcoded videos."""
        try:
            LoggingService.LogFunctionEntry("CreateVMAFComparison", 'FFmpegComparisonService', 
                                          f"Original: {OriginalFilePath}, Transcoded: {TranscodedFilePath}")
            
            # Create VMAF comparison model
            VMAFModel = FFmpegVMAFComparisonModel()
            VMAFModel.OriginalFilePath = OriginalFilePath
            VMAFModel.TranscodedFilePath = TranscodedFilePath
            VMAFModel.OriginalFileName = os.path.basename(OriginalFilePath)
            VMAFModel.TranscodedFileName = os.path.basename(TranscodedFilePath)
            VMAFModel.QualityWidth = QualityWidth
            VMAFModel.QualityHeight = QualityHeight
            
            # Set output path for compatibility (not used for file generation)
            if not OutputPath:
                TranscodedDir = os.path.dirname(TranscodedFilePath)
                TranscodedName = Path(TranscodedFilePath).stem
                OutputPath = os.path.join(TranscodedDir, f"{TranscodedName}_vmaf_output.txt")
            
            VMAFModel.VMAFResultsPath = OutputPath
            VMAFModel.VMAFResultsFileName = os.path.basename(OutputPath)
            
            # VMAF model path not needed for basic VMAF comparison
            
            # Build FFmpeg filter for VMAF comparison (output score to stderr only)
            FilterComplex = f"[0:v]scale={QualityWidth}x{QualityHeight}[dist];[1:v]scale={QualityWidth}x{QualityHeight}[ref];[dist][ref]libvmaf"
            
            # Build FFmpeg arguments (ExecuteFFmpegCommand will add -progress pipe:2 automatically if callback provided)
            Arguments = [
                '-i', TranscodedFilePath,    # First input (transcoded file)
                '-i', OriginalFilePath,      # Second input (original file)
                '-lavfi', FilterComplex,     # Use lavfi instead of filter_complex
                '-f', 'null',                # Null output format
                '-'                          # Output to stdout
            ]
            
            # Log VMAF analysis start
            LoggingService.LogInfo(f"Starting VMAF quality analysis: {os.path.basename(OriginalFilePath)} vs {os.path.basename(TranscodedFilePath)}", 'CreateVMAFComparison', 'FFmpegComparisonService')
            
            # Create progress callback to log VMAF process details
            def vmaf_progress_callback(progress_data):
                try:
                    # Log VMAF progress details to database
                    LoggingService.LogInfo(f"VMAF Analysis Progress: {progress_data}", 'CreateVMAFComparison', 'FFmpegComparisonService')
                except Exception as e:
                    LoggingService.LogException("Exception in VMAF progress callback", e, 'CreateVMAFComparison', 'FFmpegComparisonService')
            
            # Execute FFmpeg command with progress monitoring (VMAF score will be extracted from output)
            Result = self.FFmpegService.ExecuteFFmpegCommand(Arguments, vmaf_progress_callback)
            
            if Result['Success']:
                # Extract VMAF score from FFmpeg output
                VMAFScore = self.ExtractVMAFScoreFromOutput(Result.get('AllOutput', ''))
                if VMAFScore is not None:
                    VMAFModel.OverallVMAFScore = VMAFScore
                    VMAFModel.Success = True
                    LoggingService.LogInfo(f"VMAF analysis completed successfully (extracted from output): Score: {VMAFScore:.2f}", 'CreateVMAFComparison', 'FFmpegComparisonService')
                else:
                    VMAFModel.Success = False
                    VMAFModel.ErrorMessage = "No VMAF score found in FFmpeg output"
                    LoggingService.LogWarning("No VMAF score found in FFmpeg output", 'CreateVMAFComparison', 'FFmpegComparisonService')
            else:
                VMAFModel.Success = False
                VMAFModel.ErrorMessage = Result.get('ErrorMessage', 'VMAF comparison generation failed')
                LoggingService.LogWarning(f"VMAF analysis failed: {VMAFModel.ErrorMessage}", 'CreateVMAFComparison', 'FFmpegComparisonService')
            
            return VMAFModel
            
        except Exception as e:
            LoggingService.LogException("Error creating VMAF comparison", e, 'CreateVMAFComparison', 'FFmpegComparisonService')
            VMAFModel = FFmpegVMAFComparisonModel()
            VMAFModel.OriginalFilePath = OriginalFilePath
            VMAFModel.TranscodedFilePath = TranscodedFilePath
            VMAFModel.Success = False
            VMAFModel.ErrorMessage = f"VMAF comparison generation error: {str(e)}"
            return VMAFModel
    
    def ExtractVMAFScoreFromOutput(self, OutputText: str) -> Optional[float]:
        """Extract VMAF score from FFmpeg output text."""
        try:
            import re
            
            # Look for VMAF score pattern in the output
            # Pattern: [Parsed_libvmaf_2 @ 0000017fe03cc300] VMAF score: 92.342158
            VMAFPattern = r'\[Parsed_libvmaf[^\]]*\]\s*VMAF\s+score:\s*([0-9]+\.?[0-9]*)'
            
            Match = re.search(VMAFPattern, OutputText, re.IGNORECASE)
            if Match:
                VMAFScore = float(Match.group(1))
                LoggingService.LogInfo(f"Extracted VMAF score from output: {VMAFScore:.6f}", 'ExtractVMAFScoreFromOutput', 'FFmpegComparisonService')
                return VMAFScore
            
            # Alternative pattern: VMAF score: 92.342158 (without the parsed filter prefix)
            AlternativePattern = r'VMAF\s+score:\s*([0-9]+\.?[0-9]*)'
            Match = re.search(AlternativePattern, OutputText, re.IGNORECASE)
            if Match:
                VMAFScore = float(Match.group(1))
                LoggingService.LogInfo(f"Extracted VMAF score from output (alternative pattern): {VMAFScore:.6f}", 'ExtractVMAFScoreFromOutput', 'FFmpegComparisonService')
                return VMAFScore
            
            LoggingService.LogWarning("No VMAF score found in FFmpeg output", 'ExtractVMAFScoreFromOutput', 'FFmpegComparisonService')
            return None
            
        except Exception as e:
            LoggingService.LogException("Error extracting VMAF score from output", e, 'ExtractVMAFScoreFromOutput', 'FFmpegComparisonService')
            return None

    def IsAvailable(self) -> bool:
        """Check if FFmpeg is available for comparison generation."""
        return self.FFmpegService.IsFFmpegAvailable()
