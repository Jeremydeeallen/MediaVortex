import os
import json
from typing import Optional
from pathlib import Path
from Models.FFmpegComparisonModel import FFmpegComparisonModel
from Models.FFmpegVMAFComparisonModel import FFmpegVMAFComparisonModel, VMAFFrameData, VMAFPooledMetrics
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
            
            # Generate output path if not provided
            if not OutputPath:
                TranscodedDir = os.path.dirname(TranscodedFilePath)
                TranscodedName = Path(TranscodedFilePath).stem
                OutputPath = os.path.join(TranscodedDir, f"{TranscodedName}.json")
            
            VMAFModel.VMAFResultsPath = OutputPath
            VMAFModel.VMAFResultsFileName = os.path.basename(OutputPath)
            
            # Set default VMAF model path if not provided
            if not VMAFModelPath:
                # Look for VMAF model files in parent directory
                ParentDir = Path(__file__).parent.parent.parent
                VMAFModelPath = str(ParentDir / "vmaf-8bit.json")
            
            # Build FFmpeg filter for VMAF comparison
            FilterComplex = f"[0:v]scale={QualityWidth}:{QualityHeight},setsar=1[ref];[1:v]setsar=1[distorted];[distorted][ref]libvmaf=log_path=\"{OutputPath}\":log_fmt=json:model_path=\"{VMAFModelPath}\""
            
            # Build FFmpeg arguments
            Arguments = [
                '-i', OriginalFilePath,      # First input (original)
                '-i', TranscodedFilePath,    # Second input (transcoded)
                '-filter_complex', FilterComplex,
                '-an',                       # No audio
                '-f', 'null',                # Null output format
                '-'                          # Output to stdout
            ]
            
            # Execute FFmpeg command directly (VMAF results are saved via log_path in filter)
            Result = self.FFmpegService.ExecuteFFmpegCommand(Arguments)
            
            if Result['Success']:
                # Parse VMAF results from XML file
                if os.path.exists(OutputPath):
                    self.ParseVMAFResults(VMAFModel, OutputPath)
                    VMAFModel.Success = True
                    LoggingService.LogInfo(f"Successfully created VMAF comparison: {OutputPath}", 'CreateVMAFComparison', 'FFmpegComparisonService')
                else:
                    VMAFModel.Success = False
                    VMAFModel.ErrorMessage = "VMAF results file was not created"
                    LoggingService.LogWarning("VMAF results file was not created", 'CreateVMAFComparison', 'FFmpegComparisonService')
            else:
                VMAFModel.Success = False
                VMAFModel.ErrorMessage = Result.get('ErrorMessage', 'VMAF comparison generation failed')
                LoggingService.LogWarning(f"Failed to create VMAF comparison: {VMAFModel.ErrorMessage}", 'CreateVMAFComparison', 'FFmpegComparisonService')
            
            return VMAFModel
            
        except Exception as e:
            LoggingService.LogException("Error creating VMAF comparison", e, 'CreateVMAFComparison', 'FFmpegComparisonService')
            VMAFModel = FFmpegVMAFComparisonModel()
            VMAFModel.OriginalFilePath = OriginalFilePath
            VMAFModel.TranscodedFilePath = TranscodedFilePath
            VMAFModel.Success = False
            VMAFModel.ErrorMessage = f"VMAF comparison generation error: {str(e)}"
            return VMAFModel
    
    def ParseVMAFResults(self, VMAFModel: FFmpegVMAFComparisonModel, ResultsPath: str):
        """Parse VMAF results from JSON file."""
        try:
            if not os.path.exists(ResultsPath):
                VMAFModel.ErrorMessage = "VMAF results file not found"
                return
            
            # Parse JSON file
            with open(ResultsPath, 'r', encoding='utf-8') as File:
                VMAFData = json.load(File)
            
            # Extract VMAF version and parameters
            VMAFModel.VMAFVersion = VMAFData.get('version', '3.0.0')
            
            # Extract quality parameters
            Params = VMAFData.get('params', {})
            VMAFModel.QualityWidth = Params.get('qualityWidth', VMAFModel.QualityWidth)
            VMAFModel.QualityHeight = Params.get('qualityHeight', VMAFModel.QualityHeight)
            
            # Extract FPS
            FYI = VMAFData.get('fyi', {})
            VMAFModel.FPS = FYI.get('fps', 0.0)
            
            # Parse frame data
            Frames = VMAFData.get('frames', [])
            for Frame in Frames:
                FrameData = VMAFFrameData()
                FrameData.FrameNumber = Frame.get('frameNum', 0)
                FrameData.VMAFScore = Frame.get('vmaf', 0.0)
                FrameData.IntegerADM2 = Frame.get('integer_adm2', 0.0)
                FrameData.IntegerADMScale0 = Frame.get('integer_adm_scale0', 0.0)
                FrameData.IntegerADMScale1 = Frame.get('integer_adm_scale1', 0.0)
                FrameData.IntegerADMScale2 = Frame.get('integer_adm_scale2', 0.0)
                FrameData.IntegerADMScale3 = Frame.get('integer_adm_scale3', 0.0)
                FrameData.IntegerMotion2 = Frame.get('integer_motion2', 0.0)
                FrameData.IntegerMotion = Frame.get('integer_motion', 0.0)
                FrameData.IntegerVIFScale0 = Frame.get('integer_vif_scale0', 0.0)
                FrameData.IntegerVIFScale1 = Frame.get('integer_vif_scale1', 0.0)
                FrameData.IntegerVIFScale2 = Frame.get('integer_vif_scale2', 0.0)
                FrameData.IntegerVIFScale3 = Frame.get('integer_vif_scale3', 0.0)
                
                VMAFModel.FrameData.append(FrameData)
            
            VMAFModel.TotalFrames = len(VMAFModel.FrameData)
            
            # Parse pooled metrics
            PooledMetrics = VMAFData.get('pooled_metrics', [])
            for Metric in PooledMetrics:
                MetricData = VMAFPooledMetrics()
                MetricData.MetricName = Metric.get('name', '')
                MetricData.MinValue = Metric.get('min', 0.0)
                MetricData.MaxValue = Metric.get('max', 0.0)
                MetricData.MeanValue = Metric.get('mean', 0.0)
                MetricData.HarmonicMean = Metric.get('harmonic_mean', 0.0)
                
                VMAFModel.PooledMetrics.append(MetricData)
                
                # Extract overall VMAF score from pooled metrics
                if MetricData.MetricName == 'vmaf':
                    VMAFModel.OverallVMAFScore = MetricData.MeanValue
            
            LoggingService.LogInfo(f"Successfully parsed VMAF results: {VMAFModel.TotalFrames} frames, Overall VMAF: {VMAFModel.OverallVMAFScore:.2f}", 
                                 'FFmpegComparisonService', 'ParseVMAFResults')
            
        except Exception as e:
            LoggingService.LogException("Error parsing VMAF results", e, 'ParseVMAFResults', 'FFmpegComparisonService')
            VMAFModel.ErrorMessage = f"VMAF results parsing error: {str(e)}"
    
    def IsAvailable(self) -> bool:
        """Check if FFmpeg is available for comparison generation."""
        return self.FFmpegService.IsFFmpegAvailable()
