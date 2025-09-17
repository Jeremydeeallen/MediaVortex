from flask import Blueprint, request, jsonify
from ViewModels.FFmpegAnalysisViewModel import FFmpegAnalysisViewModel
from ViewModels.FFmpegScreenshotViewModel import FFmpegScreenshotViewModel
from ViewModels.FFmpegComparisonViewModel import FFmpegComparisonViewModel
from Services.LoggingService import LoggingService


class FFmpegController:
    """Controller for FFmpeg-related API endpoints."""
    
    def __init__(self):
        self.Blueprint = Blueprint('ffmpeg', __name__)
        self.AnalysisViewModel = FFmpegAnalysisViewModel()
        self.ScreenshotViewModel = FFmpegScreenshotViewModel()
        self.ComparisonViewModel = FFmpegComparisonViewModel()
        self.SetupRoutes()
    
    def SetupRoutes(self):
        """Setup API routes for FFmpeg operations."""
        
        # Analysis endpoints
        @self.Blueprint.route('/api/FFmpeg/Analysis/AnalyzeFile', methods=['POST'])
        def AnalyzeFile():
            """Analyze a single media file."""
            try:
                Data = request.get_json()
                FilePath = Data.get('FilePath')
                
                if not FilePath:
                    return jsonify({
                        'Success': False,
                        'ErrorMessage': 'FilePath is required'
                    }), 400
                
                Result = self.AnalysisViewModel.AnalyzeMediaFile(FilePath)
                return jsonify(Result)
                
            except Exception as e:
                LoggingService.LogException("Error in AnalyzeFile endpoint", e, 'FFmpegController', 'AnalyzeFile')
                return jsonify({
                    'Success': False,
                    'ErrorMessage': f'Analysis error: {str(e)}'
                }), 500
        
        @self.Blueprint.route('/api/FFmpeg/Analysis/AnalyzeFiles', methods=['POST'])
        def AnalyzeFiles():
            """Analyze multiple media files."""
            try:
                Data = request.get_json()
                FilePaths = Data.get('FilePaths', [])
                
                if not FilePaths:
                    return jsonify({
                        'Success': False,
                        'ErrorMessage': 'FilePaths array is required'
                    }), 400
                
                Result = self.AnalysisViewModel.AnalyzeMediaFiles(FilePaths)
                return jsonify(Result)
                
            except Exception as e:
                LoggingService.LogException("Error in AnalyzeFiles endpoint", e, 'FFmpegController', 'AnalyzeFiles')
                return jsonify({
                    'Success': False,
                    'ErrorMessage': f'Batch analysis error: {str(e)}'
                }), 500
        
        @self.Blueprint.route('/api/FFmpeg/Analysis/Capabilities', methods=['GET'])
        def GetAnalysisCapabilities():
            """Get analysis capabilities information."""
            try:
                Capabilities = self.AnalysisViewModel.GetAnalysisCapabilities()
                return jsonify({
                    'Success': True,
                    'Capabilities': Capabilities
                })
                
            except Exception as e:
                LoggingService.LogException("Error in GetAnalysisCapabilities endpoint", e, 'FFmpegController', 'GetAnalysisCapabilities')
                return jsonify({
                    'Success': False,
                    'ErrorMessage': f'Capabilities error: {str(e)}'
                }), 500
        
        # Screenshot endpoints
        @self.Blueprint.route('/api/FFmpeg/Screenshot/GenerateSingle', methods=['POST'])
        def GenerateSingleScreenshot():
            """Generate a single screenshot."""
            try:
                Data = request.get_json()
                SourceFilePath = Data.get('SourceFilePath')
                TimestampSeconds = Data.get('TimestampSeconds', 0.0)
                OutputPath = Data.get('OutputPath')
                Width = Data.get('Width')
                Height = Data.get('Height')
                Format = Data.get('Format', 'jpg')
                
                if not SourceFilePath:
                    return jsonify({
                        'Success': False,
                        'ErrorMessage': 'SourceFilePath is required'
                    }), 400
                
                Result = self.ScreenshotViewModel.GenerateScreenshot(
                    SourceFilePath, TimestampSeconds, OutputPath, Width, Height, Format
                )
                return jsonify(Result)
                
            except Exception as e:
                LoggingService.LogException("Error in GenerateSingleScreenshot endpoint", e, 'FFmpegController', 'GenerateSingleScreenshot')
                return jsonify({
                    'Success': False,
                    'ErrorMessage': f'Screenshot generation error: {str(e)}'
                }), 500
        
        @self.Blueprint.route('/api/FFmpeg/Screenshot/GenerateAtIntervals', methods=['POST'])
        def GenerateScreenshotsAtIntervals():
            """Generate screenshots at regular intervals."""
            try:
                Data = request.get_json()
                SourceFilePath = Data.get('SourceFilePath')
                IntervalSeconds = Data.get('IntervalSeconds', 60.0)
                MaxScreenshots = Data.get('MaxScreenshots', 10)
                OutputDirectory = Data.get('OutputDirectory')
                Width = Data.get('Width')
                Height = Data.get('Height')
                Format = Data.get('Format', 'jpg')
                
                if not SourceFilePath:
                    return jsonify({
                        'Success': False,
                        'ErrorMessage': 'SourceFilePath is required'
                    }), 400
                
                Result = self.ScreenshotViewModel.GenerateScreenshotsAtIntervals(
                    SourceFilePath, IntervalSeconds, MaxScreenshots, OutputDirectory, Width, Height, Format
                )
                return jsonify(Result)
                
            except Exception as e:
                LoggingService.LogException("Error in GenerateScreenshotsAtIntervals endpoint", e, 'FFmpegController', 'GenerateScreenshotsAtIntervals')
                return jsonify({
                    'Success': False,
                    'ErrorMessage': f'Interval screenshot generation error: {str(e)}'
                }), 500
        
        @self.Blueprint.route('/api/FFmpeg/Screenshot/GenerateAtTimes', methods=['POST'])
        def GenerateScreenshotsAtTimes():
            """Generate screenshots at specific timestamps."""
            try:
                Data = request.get_json()
                SourceFilePath = Data.get('SourceFilePath')
                Timestamps = Data.get('Timestamps', [])
                OutputDirectory = Data.get('OutputDirectory')
                Width = Data.get('Width')
                Height = Data.get('Height')
                Format = Data.get('Format', 'jpg')
                
                if not SourceFilePath:
                    return jsonify({
                        'Success': False,
                        'ErrorMessage': 'SourceFilePath is required'
                    }), 400
                
                if not Timestamps:
                    return jsonify({
                        'Success': False,
                        'ErrorMessage': 'Timestamps array is required'
                    }), 400
                
                Result = self.ScreenshotViewModel.GenerateScreenshotsAtSpecificTimes(
                    SourceFilePath, Timestamps, OutputDirectory, Width, Height, Format
                )
                return jsonify(Result)
                
            except Exception as e:
                LoggingService.LogException("Error in GenerateScreenshotsAtTimes endpoint", e, 'FFmpegController', 'GenerateScreenshotsAtTimes')
                return jsonify({
                    'Success': False,
                    'ErrorMessage': f'Specific time screenshot generation error: {str(e)}'
                }), 500
        
        @self.Blueprint.route('/api/FFmpeg/Screenshot/Capabilities', methods=['GET'])
        def GetScreenshotCapabilities():
            """Get screenshot capabilities information."""
            try:
                Capabilities = self.ScreenshotViewModel.GetScreenshotCapabilities()
                return jsonify({
                    'Success': True,
                    'Capabilities': Capabilities
                })
                
            except Exception as e:
                LoggingService.LogException("Error in GetScreenshotCapabilities endpoint", e, 'FFmpegController', 'GetScreenshotCapabilities')
                return jsonify({
                    'Success': False,
                    'ErrorMessage': f'Screenshot capabilities error: {str(e)}'
                }), 500
        
        # Comparison endpoints
        @self.Blueprint.route('/api/FFmpeg/Comparison/SideBySide', methods=['POST'])
        def CreateSideBySideComparison():
            """Create a side-by-side comparison video."""
            try:
                Data = request.get_json()
                OriginalFilePath = Data.get('OriginalFilePath')
                TranscodedFilePath = Data.get('TranscodedFilePath')
                OutputPath = Data.get('OutputPath')
                Width = Data.get('Width')
                Height = Data.get('Height')
                
                if not OriginalFilePath or not TranscodedFilePath:
                    return jsonify({
                        'Success': False,
                        'ErrorMessage': 'OriginalFilePath and TranscodedFilePath are required'
                    }), 400
                
                Result = self.ComparisonViewModel.CreateSideBySideComparison(
                    OriginalFilePath, TranscodedFilePath, OutputPath, Width, Height
                )
                return jsonify(Result)
                
            except Exception as e:
                LoggingService.LogException("Error in CreateSideBySideComparison endpoint", e, 'FFmpegController', 'CreateSideBySideComparison')
                return jsonify({
                    'Success': False,
                    'ErrorMessage': f'Side-by-side comparison error: {str(e)}'
                }), 500
        
        @self.Blueprint.route('/api/FFmpeg/Comparison/PictureInPicture', methods=['POST'])
        def CreatePictureInPictureComparison():
            """Create a picture-in-picture comparison video."""
            try:
                Data = request.get_json()
                OriginalFilePath = Data.get('OriginalFilePath')
                TranscodedFilePath = Data.get('TranscodedFilePath')
                OutputPath = Data.get('OutputPath')
                PiPWidth = Data.get('PiPWidth', 320)
                PiPHeight = Data.get('PiPHeight', 180)
                
                if not OriginalFilePath or not TranscodedFilePath:
                    return jsonify({
                        'Success': False,
                        'ErrorMessage': 'OriginalFilePath and TranscodedFilePath are required'
                    }), 400
                
                Result = self.ComparisonViewModel.CreatePictureInPictureComparison(
                    OriginalFilePath, TranscodedFilePath, OutputPath, PiPWidth, PiPHeight
                )
                return jsonify(Result)
                
            except Exception as e:
                LoggingService.LogException("Error in CreatePictureInPictureComparison endpoint", e, 'FFmpegController', 'CreatePictureInPictureComparison')
                return jsonify({
                    'Success': False,
                    'ErrorMessage': f'Picture-in-picture comparison error: {str(e)}'
                }), 500
        
        @self.Blueprint.route('/api/FFmpeg/Comparison/Overlay', methods=['POST'])
        def CreateOverlayComparison():
            """Create an overlay comparison video."""
            try:
                Data = request.get_json()
                OriginalFilePath = Data.get('OriginalFilePath')
                TranscodedFilePath = Data.get('TranscodedFilePath')
                OutputPath = Data.get('OutputPath')
                OverlayOpacity = Data.get('OverlayOpacity', 0.5)
                
                if not OriginalFilePath or not TranscodedFilePath:
                    return jsonify({
                        'Success': False,
                        'ErrorMessage': 'OriginalFilePath and TranscodedFilePath are required'
                    }), 400
                
                Result = self.ComparisonViewModel.CreateOverlayComparison(
                    OriginalFilePath, TranscodedFilePath, OutputPath, OverlayOpacity
                )
                return jsonify(Result)
                
            except Exception as e:
                LoggingService.LogException("Error in CreateOverlayComparison endpoint", e, 'FFmpegController', 'CreateOverlayComparison')
                return jsonify({
                    'Success': False,
                    'ErrorMessage': f'Overlay comparison error: {str(e)}'
                }), 500
        
        @self.Blueprint.route('/api/FFmpeg/Comparison/VMAF', methods=['POST'])
        def CreateVMAFComparison():
            """Create a VMAF quality comparison."""
            try:
                Data = request.get_json()
                OriginalFilePath = Data.get('OriginalFilePath')
                TranscodedFilePath = Data.get('TranscodedFilePath')
                OutputPath = Data.get('OutputPath')
                QualityWidth = Data.get('QualityWidth', 1280)
                QualityHeight = Data.get('QualityHeight', 720)
                VMAFModelPath = Data.get('VMAFModelPath')
                
                if not OriginalFilePath or not TranscodedFilePath:
                    return jsonify({
                        'Success': False,
                        'ErrorMessage': 'OriginalFilePath and TranscodedFilePath are required'
                    }), 400
                
                Result = self.ComparisonViewModel.CreateVMAFComparison(
                    OriginalFilePath, TranscodedFilePath, OutputPath, QualityWidth, QualityHeight, VMAFModelPath
                )
                return jsonify(Result)
                
            except Exception as e:
                LoggingService.LogException("Error in CreateVMAFComparison endpoint", e, 'FFmpegController', 'CreateVMAFComparison')
                return jsonify({
                    'Success': False,
                    'ErrorMessage': f'VMAF comparison error: {str(e)}'
                }), 500
        
        @self.Blueprint.route('/api/FFmpeg/Comparison/Capabilities', methods=['GET'])
        def GetComparisonCapabilities():
            """Get comparison capabilities information."""
            try:
                Capabilities = self.ComparisonViewModel.GetComparisonCapabilities()
                return jsonify({
                    'Success': True,
                    'Capabilities': Capabilities
                })
                
            except Exception as e:
                LoggingService.LogException("Error in GetComparisonCapabilities endpoint", e, 'FFmpegController', 'GetComparisonCapabilities')
                return jsonify({
                    'Success': False,
                    'ErrorMessage': f'Comparison capabilities error: {str(e)}'
                }), 500
        
        # MediaVortex title endpoints
        @self.Blueprint.route('/api/FFmpeg/Title/AddMediaVortexTitle', methods=['POST'])
        def AddMediaVortexTitle():
            """Add MediaVortex title to video metadata."""
            try:
                Data = request.get_json()
                InputFilePath = Data.get('InputFilePath')
                OutputFilePath = Data.get('OutputFilePath')
                Title = Data.get('Title')
                ShowTitle = Data.get('ShowTitle')
                EpisodeTitle = Data.get('EpisodeTitle')
                
                if not InputFilePath or not OutputFilePath:
                    return jsonify({
                        'Success': False,
                        'ErrorMessage': 'InputFilePath and OutputFilePath are required'
                    }), 400
                
                # Use the FFmpegService directly for this operation
                from Services.FFmpegService import FFmpegService
                FFmpegServiceInstance = FFmpegService()
                
                Result = FFmpegServiceInstance.AddMediaVortexTitle(
                    InputFilePath, OutputFilePath, Title, ShowTitle, EpisodeTitle
                )
                
                return jsonify(Result)
                
            except Exception as e:
                LoggingService.LogException("Error in AddMediaVortexTitle endpoint", e, 'FFmpegController', 'AddMediaVortexTitle')
                return jsonify({
                    'Success': False,
                    'ErrorMessage': f'Title addition error: {str(e)}'
                }), 500
