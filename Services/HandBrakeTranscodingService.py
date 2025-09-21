import os
import subprocess
import time
import re
import threading
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path
from Services.LoggingService import LoggingService
from Repositories.DatabaseManager import DatabaseManager
from Services.DatabaseService import DatabaseService


class HandBrakeTranscodingService:
    """
    HandBrake CLI transcoding service for 2-pass x265 10-bit encoding.
    Based on TestFfmpeg.py implementation with database progress tracking.
    """
    
    # Static flag to log initialization only once
    _logged_initialization = False
    
    def __init__(self, DatabaseServiceInstance: DatabaseService = None):
        self.DatabaseService = DatabaseServiceInstance or DatabaseService()
        self.DatabaseManager = DatabaseManager(self.DatabaseService)
        
        # HandBrake CLI path
        self.HandBrakePath = r"C:\MediaVortex\HandBrakeCLI\HandBrakeCLI.exe"
        self.IsAvailable = os.path.exists(self.HandBrakePath)
        
        # Only log initialization once per class
        if not HandBrakeTranscodingService._logged_initialization:
            if self.IsAvailable:
                LoggingService.LogInfo(f"HandBrakeTranscodingService initialized with HandBrake CLI at: {self.HandBrakePath}", "HandBrakeTranscodingService", "__init__")
            else:
                LoggingService.LogError(f"HandBrake CLI not found at: {self.HandBrakePath}", "HandBrakeTranscodingService", "__init__")
            HandBrakeTranscodingService._logged_initialization = True
    
    def TranscodeVideo(self, InputFilePath: str, OutputFilePath: str, QualitySettings: Dict[str, Any], ProgressCallback=None, TranscodeAttemptId: int = None) -> Dict[str, Any]:
        """
        Transcode video using HandBrake CLI with 2-pass x265 10-bit encoding.
        Based on TestFfmpeg.py implementation with database progress tracking.
        
        Args:
            InputFilePath: Source video file path
            OutputFilePath: Destination video file path
            QualitySettings: Dictionary containing transcoding settings from ProfileThresholds
            ProgressCallback: Optional callback function for progress updates
            TranscodeAttemptId: Database ID for progress tracking
            
        Returns:
            Dictionary with Success, ErrorMessage, ReturnCode, and other results
        """
        try:
            LoggingService.LogFunctionEntry("TranscodeVideo", "HandBrakeTranscodingService", InputFilePath, OutputFilePath, QualitySettings, TranscodeAttemptId)
            
            if not self.IsAvailable:
                ErrorMsg = "HandBrake CLI not available for transcoding"
                LoggingService.LogError(ErrorMsg, "HandBrakeTranscodingService", "TranscodeVideo")
                return {"Success": False, "ErrorMessage": ErrorMsg, "ReturnCode": -1}
                return {"Success": False, "ErrorMessage": ErrorMsg, "ReturnCode": -1}
            
            # Validate input file exists
            if not os.path.exists(InputFilePath):
                ErrorMsg = f"Input file does not exist: {InputFilePath}"
                LoggingService.LogError(ErrorMsg, "HandBrakeTranscodingService", "TranscodeVideo")
                return {"Success": False, "ErrorMessage": ErrorMsg, "ReturnCode": -1}
            
            # Ensure output directory exists
            OutputDir = os.path.dirname(OutputFilePath)
            if OutputDir and not os.path.exists(OutputDir):
                os.makedirs(OutputDir, exist_ok=True)
                LoggingService.LogInfo(f"Created output directory: {OutputDir}", "HandBrakeTranscodingService", "TranscodeVideo")
            
            # Extract quality settings from ProfileThresholds
            CRF = str(QualitySettings.get('Quality', 22))  # Default to CRF 22
            AudioBitrate = str(QualitySettings.get('AudioBitrateKbps', 128))  # Default to 128kbps
            TargetResolution = QualitySettings.get('TargetResolution', '720p')
            
            # Create a transcoding attempt record if not provided
            if not TranscodeAttemptId:
                InitialCommand = f"HandBrake CLI 2-pass x265 CRF {CRF}, Audio {AudioBitrate}k"
                TranscodeAttemptId = self.CreateTranscodeAttempt(InputFilePath, CRF, AudioBitrate, InitialCommand)
                if not TranscodeAttemptId:
                    ErrorMsg = "Failed to create transcoding attempt record"
                    LoggingService.LogError(ErrorMsg, "HandBrakeTranscodingService", "TranscodeVideo")
                    return {"Success": False, "ErrorMessage": ErrorMsg, "ReturnCode": -1}
            
            StartTime = time.time()
            
            # Single-pass CRF encoding (no need for 2-pass with CRF)
            Pass2Result = self.RunPass2(InputFilePath, OutputFilePath, CRF, AudioBitrate, TargetResolution, TranscodeAttemptId)
            
            if not Pass2Result["Success"]:
                return Pass2Result
            
            TotalDuration = time.time() - StartTime
            
            # Check if output file exists and get size
            OutputFileSize = 0
            if os.path.exists(OutputFilePath):
                OutputFileSize = os.path.getsize(OutputFilePath)
            
            LoggingService.LogInfo(f"HandBrake 2-pass encoding completed successfully in {TotalDuration:.2f} seconds", "HandBrakeTranscodingService", "TranscodeVideo")
            
            return {
                "Success": True,
                "OutputFilePath": OutputFilePath,
                "OutputFileSize": OutputFileSize,
                "Duration": TotalDuration,
                "Pass2Duration": Pass2Result.get("Duration", 0),
                "TranscodeAttemptId": TranscodeAttemptId,
                "ReturnCode": 0
            }
            
        except Exception as e:
            LoggingService.LogException("Exception in HandBrake transcoding", e, "HandBrakeTranscodingService", "TranscodeVideo")
            return {
                "Success": False,
                "ErrorMessage": f"Transcoding exception: {str(e)}",
                "ReturnCode": -1
            }
    
    def RunPass1(self, InputFilePath: str, CRF: str, TranscodeAttemptId: int = None) -> Dict[str, Any]:
        """Run HandBrake Pass 1: Analysis (ultra-fast preset, no audio, null output)."""
        try:
            Pass1Command = [
                self.HandBrakePath,
                '--input', InputFilePath,                    # Input file
                '--output', 'NUL',                           # Null output (Windows)
                '--encoder', 'x265_10bit',                   # x265 10-bit encoder
                '--quality', CRF,                            # CRF quality
                '--encoder-preset', 'ultrafast',             # Ultra-fast preset for analysis
                '--encoder-profile', 'main10',               # 10-bit profile
                '--encoder-level', 'auto',                   # Auto level
                '--audio', 'none',                           # No audio processing
                '--verbose'                                  # Verbose output
            ]
            
            # Add resolution preservation parameters to maintain source resolution
            # Use HandBrake's automatic resolution detection but prevent unnecessary scaling
            Pass1Command.extend([
                '--keep-aspect-ratio'                            # Preserve source aspect ratio and resolution
            ])
            
            # Capture the complete command string for storage
            Pass1CommandString = ' '.join(f'"{Arg}"' if ' ' in Arg else Arg for Arg in Pass1Command)
            
            # No console output in production - database logging only
            Pass1Start = time.time()
            
            # Initialize Pass 1 progress
            if TranscodeAttemptId:
                self.DatabaseManager.SaveHandBrakeProgress(
                    TranscodeAttemptId=TranscodeAttemptId,
                    PassNumber=1,
                    PassType="analysis",
                    Status="running",
                    CurrentPhase="Starting Pass 1: Analysis"
                )
            
            # Run Pass 1 with progress monitoring
            Pass1Result = self.RunHandBrakeWithProgress(
                Pass1Command, 
                TranscodeAttemptId, 
                1, 
                "analysis"
            )
            Pass1Duration = time.time() - Pass1Start
            
            # Mark Pass 1 as completed
            if TranscodeAttemptId:
                self.DatabaseManager.SaveHandBrakeProgress(
                    TranscodeAttemptId=TranscodeAttemptId,
                    PassNumber=1,
                    PassType="analysis",
                    Status="completed",
                    PassDuration=Pass1Duration,
                    ProgressPercent=100.0
                )
            
            LoggingService.LogInfo(f"Pass 1 completed successfully in {Pass1Duration:.2f} seconds", "HandBrakeTranscodingService", "_RunPass1")
            
            return {
                "Success": True,
                "Duration": Pass1Duration,
                "ReturnCode": 0,
                "Command": Pass1CommandString
            }
            
        except subprocess.CalledProcessError as e:
            # Mark Pass 1 as failed
            if TranscodeAttemptId:
                self.DatabaseManager.SaveHandBrakeProgress(
                    TranscodeAttemptId=TranscodeAttemptId,
                    PassNumber=1,
                    PassType="analysis",
                    Status="failed"
                )
            LoggingService.LogError(f"Pass 1 failed with return code {e.returncode}", "HandBrakeTranscodingService", "_RunPass1")
            return {
                "Success": False,
                "ErrorMessage": f"Pass 1 failed with return code {e.returncode}",
                "ReturnCode": e.returncode
            }
    
    def RunPass2(self, InputFilePath: str, OutputFilePath: str, CRF: str, AudioBitrate: str, TargetResolution: str, TranscodeAttemptId: int = None) -> Dict[str, Any]:
        """Run HandBrake Pass 2: Encoding (fast preset, with audio, actual output)."""
        try:
            Pass2Command = [
                self.HandBrakePath,
                '--input', InputFilePath,                    # Input file
                '--output', OutputFilePath,                  # Output file
                '--encoder', 'x265_10bit',                   # x265 10-bit encoder
                '--quality', CRF,                            # CRF quality
                '--encoder-preset', 'fast',                  # Fast preset for encoding
                '--encoder-profile', 'main10',               # 10-bit profile
                '--encoder-level', 'auto',                   # Auto level
                '--audio', '1',                              # Select first audio track
                '--aencoder', 'av_aac',                      # AAC audio encoder
                '--ab', AudioBitrate,                        # Audio bitrate
                '--verbose'                                  # Verbose output
            ]
            
            # Add resolution preservation parameters to maintain source resolution
            # Use HandBrake's automatic resolution detection but prevent unnecessary scaling
            Pass2Command.extend([
                '--keep-aspect-ratio'                            # Preserve source aspect ratio and resolution
            ])
            LoggingService.LogInfo(f"Added resolution preservation parameters: keep-aspect-ratio (target: {TargetResolution})", "HandBrakeTranscodingService", "RunPass2")
            
            # Capture the complete command string for storage
            Pass2CommandString = ' '.join(f'"{Arg}"' if ' ' in Arg else Arg for Arg in Pass2Command)
            
            # No console output in production - database logging only
            Pass2Start = time.time()
            
            # Initialize Pass 2 progress
            if TranscodeAttemptId:
                self.DatabaseManager.SaveHandBrakeProgress(
                    TranscodeAttemptId=TranscodeAttemptId,
                    PassNumber=2,
                    PassType="encoding",
                    Status="running",
                    CurrentPhase="Starting Pass 2: Encoding"
                )
            
            # Run Pass 2 with progress monitoring
            Pass2Result = self.RunHandBrakeWithProgress(
                Pass2Command, 
                TranscodeAttemptId, 
                2, 
                "encoding"
            )
            Pass2Duration = time.time() - Pass2Start
            
            # Mark Pass 2 as completed
            if TranscodeAttemptId:
                self.DatabaseManager.SaveHandBrakeProgress(
                    TranscodeAttemptId=TranscodeAttemptId,
                    PassNumber=2,
                    PassType="encoding",
                    Status="completed",
                    PassDuration=Pass2Duration,
                    ProgressPercent=100.0
                )
            
            LoggingService.LogInfo(f"Pass 2 completed successfully in {Pass2Duration:.2f} seconds", "HandBrakeTranscodingService", "_RunPass2")
            
            return {
                "Success": True,
                "Duration": Pass2Duration,
                "ReturnCode": 0,
                "Command": Pass2CommandString
            }
            
        except subprocess.CalledProcessError as e:
            # Mark Pass 2 as failed
            if TranscodeAttemptId:
                self.DatabaseManager.SaveHandBrakeProgress(
                    TranscodeAttemptId=TranscodeAttemptId,
                    PassNumber=2,
                    PassType="encoding",
                    Status="failed"
                )
            LoggingService.LogError(f"Pass 2 failed with return code {e.returncode}", "HandBrakeTranscodingService", "_RunPass2")
            return {
                "Success": False,
                "ErrorMessage": f"Pass 2 failed with return code {e.returncode}",
                "ReturnCode": e.returncode
            }
    
    def RunHandBrakeWithProgress(self, Command: List[str], TranscodeAttemptId: int, PassNumber: int, PassType: str) -> bool:
        """Run HandBrake command with progress monitoring and database updates."""
        try:
            # Store the complete HandBrake command in the TranscodeAttempt record immediately before execution
            if TranscodeAttemptId and PassNumber == 2:  # Only store for Pass 2 (the actual encoding command)
                try:
                    from Models.TranscodeAttemptModel import TranscodeAttemptModel
                    Attempt = self.DatabaseManager.GetTranscodeAttemptById(TranscodeAttemptId)
                    if Attempt:
                        # Capture the complete command string for storage
                        CommandString = ' '.join(f'"{Arg}"' if ' ' in Arg else Arg for Arg in Command)
                        Attempt.FfpmpegCommand = CommandString
                        self.DatabaseManager.SaveTranscodeAttempt(Attempt)
                        LoggingService.LogInfo(f"Stored complete HandBrake command in TranscodeAttempt {TranscodeAttemptId}: {CommandString}", "HandBrakeTranscodingService", "_RunHandBrakeWithProgress")
                except Exception as e:
                    LoggingService.LogException("Failed to store HandBrake command in TranscodeAttempt", e, "HandBrakeTranscodingService", "_RunHandBrakeWithProgress")
            
            # Start the process
            Process = subprocess.Popen(
                Command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            
            # Variables for progress tracking
            TotalFrames = None
            CurrentFrame = 0
            ProgressPercent = 0.0
            CurrentFPS = 0.0
            AverageFPS = 0.0
            ETA = "--"
            CurrentBitrate = "--"
            LastUpdate = time.time()
            
            # Read output line by line
            for Line in Process.stdout:
                Line = Line.strip()
                if Line:
                    # Parse HandBrake progress output
                    ProgressData = self.ParseHandBrakeOutput(Line)
                    if ProgressData:
                        # Update progress variables
                        if ProgressData.get('TotalFrames'):
                            TotalFrames = ProgressData['TotalFrames']
                        if ProgressData.get('CurrentFrame'):
                            CurrentFrame = ProgressData['CurrentFrame']
                        if ProgressData.get('ProgressPercent'):
                            ProgressPercent = ProgressData['ProgressPercent']
                        if ProgressData.get('CurrentFPS'):
                            CurrentFPS = ProgressData['CurrentFPS']
                        if ProgressData.get('AverageFPS'):
                            AverageFPS = ProgressData['AverageFPS']
                        if ProgressData.get('ETA'):
                            ETA = ProgressData['ETA']
                        if ProgressData.get('CurrentBitrate'):
                            CurrentBitrate = ProgressData['CurrentBitrate']
                        
                        # Update database every 5 seconds or on significant progress changes
                        CurrentTime = time.time()
                        ShouldUpdate = False
                        
                        # Check if we have new progress data
                        if ProgressData.get('ProgressPercent') is not None:
                            NewProgress = ProgressData['ProgressPercent']
                            if NewProgress != ProgressPercent:
                                ShouldUpdate = True
                                ProgressPercent = NewProgress
                        
                        # Update every 5 seconds or on significant progress changes
                        if ShouldUpdate or (CurrentTime - LastUpdate >= 5.0):
                            if TranscodeAttemptId:
                                self.DatabaseManager.SaveHandBrakeProgress(
                                    TranscodeAttemptId=TranscodeAttemptId,
                                    PassNumber=PassNumber,
                                    PassType=PassType,
                                    CurrentPhase=f"Pass {PassNumber}: {PassType.title()}",
                                    ProgressPercent=ProgressPercent,
                                    CurrentFrame=CurrentFrame,
                                    TotalFrames=TotalFrames,
                                    CurrentFPS=CurrentFPS,
                                    AverageFPS=AverageFPS,
                                    CurrentBitrate=CurrentBitrate,
                                    ETA=ETA,
                                    Status="running"
                                )
                            LastUpdate = CurrentTime
            
            # Wait for process to complete
            ReturnCode = Process.wait()
            
            if ReturnCode != 0:
                raise subprocess.CalledProcessError(ReturnCode, Command)
            
            return True
            
        except Exception as e:
            LoggingService.LogException("Exception running HandBrake with progress", e, "HandBrakeTranscodingService", "RunHandBrakeWithProgress")
            raise
    
    def ParseHandBrakeOutput(self, Line: str) -> Optional[Dict[str, Any]]:
        """Parse HandBrake output line to extract progress information."""
        try:
            ProgressData = {}
            
            # Parse HandBrake progress line: "Encoding: task 1 of 1, 76.21 % (468.97 fps, avg 478.85 fps, ETA 00h00m05s)"
            ProgressMatch = re.search(r'Encoding: task \d+ of \d+, ([\d.]+) % \(([\d.]+) fps, avg ([\d.]+) fps, ETA ([^)]+)\)', Line)
            if ProgressMatch:
                ProgressData['ProgressPercent'] = float(ProgressMatch.group(1))
                ProgressData['CurrentFPS'] = float(ProgressMatch.group(2))
                ProgressData['AverageFPS'] = float(ProgressMatch.group(3))
                ProgressData['ETA'] = ProgressMatch.group(4)
            
            # Parse total frames from HandBrake scan output: "sync: expecting 9505 video frames"
            TotalFramesMatch = re.search(r'sync: expecting (\d+) video frames', Line)
            if TotalFramesMatch:
                ProgressData['TotalFrames'] = int(TotalFramesMatch.group(1))
            
            # Parse total frames from completion: "encoded 9505 frames in 20.36s"
            EncodedFramesMatch = re.search(r'encoded (\d+) frames', Line)
            if EncodedFramesMatch:
                ProgressData['TotalFrames'] = int(EncodedFramesMatch.group(1))
            
            # Calculate current frame from progress percentage if we have total frames
            if ProgressData.get('ProgressPercent') is not None and ProgressData.get('TotalFrames'):
                CurrentFrame = int((ProgressData['ProgressPercent'] / 100.0) * ProgressData['TotalFrames'])
                ProgressData['CurrentFrame'] = CurrentFrame
            
            return ProgressData if ProgressData else None
            
        except Exception as e:
            LoggingService.LogException("Exception parsing HandBrake output", e, "HandBrakeTranscodingService", "ParseHandBrakeOutput")
            return None
    
    def CreateTranscodeAttempt(self, SourceFile: str, CRF: str, AudioBitrate: str, Command: str = None) -> Optional[int]:
        """Create a transcoding attempt record in the database."""
        try:
            from Models.TranscodeAttemptModel import TranscodeAttemptModel
            
            # Get file size
            FileSize = os.path.getsize(SourceFile) if os.path.exists(SourceFile) else 0
            
            # Create attempt record
            Attempt = TranscodeAttemptModel(
                Id=None,
                FilePath=SourceFile,
                AttemptDate=datetime.now(),
                Quality=int(CRF),
                OldSizeBytes=FileSize,
                NewSizeBytes=None,
                Success=False,
                SizeReductionBytes=None,
                SizeReductionPercent=None,
                ErrorMessage=None,
                TranscodeDurationSeconds=None,
                FfpmpegCommand=Command or f"HandBrake CLI with x265 CRF {CRF}",
                AudioBitrateKbps=int(AudioBitrate),
                VideoBitrateKbps=None,
                ProfileName="HandBrake Profile",
                VMAF=None
            )
            
            # Save to database
            AttemptId = self.DatabaseManager.SaveTranscodeAttempt(Attempt)
            return AttemptId
            
        except Exception as e:
            LoggingService.LogException("Error creating transcoding attempt", e, "HandBrakeTranscodingService", "_CreateTranscodeAttempt")
            return None
