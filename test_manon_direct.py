#!/usr/bin/env python3
"""
Direct test of transcoding Manon.mkv with our fixed FFmpeg commands.
This bypasses the queue system and tests the core transcoding functionality.
"""

import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from Services.FFmpegTranscodingService import FFmpegTranscodingService
from Services.FFmpegService import FFmpegService
from Services.LoggingService import LoggingService

def TestManonTranscoding():
    """Test transcoding Manon.mkv directly."""
    print("=" * 60)
    print("DIRECT MANON.MKV TRANSCODING TEST")
    print("=" * 60)
    
    # Initialize services
    FFmpegServiceInstance = FFmpegService()
    TranscodingService = FFmpegTranscodingService(FFmpegServiceInstance)
    
    if not TranscodingService.CheckAvailability():
        print("ERROR: FFmpeg not available")
        return False
    
    # File paths
    InputFilePath = r"C:\MediaVortex\Source\Manon.mkv"
    OutputFilePath = r"C:\MediaVortex\Manon_transcoded_720p.mkv"
    
    print(f"Input: {InputFilePath}")
    print(f"Output: {OutputFilePath}")
    
    # Quality settings (Cartoon profile for 1080p -> 720p)
    QualitySettings = {
        'VideoBitrateKbps': 1300,
        'AudioBitrateKbps': 70,
        'TargetResolution': '720p',
        'Codec': 'libx265',
        'Quality': 22
    }
    
    print(f"Quality settings: {QualitySettings}")
    
    # Progress callback
    def ProgressCallback(ProgressData):
        Frame = ProgressData.get('frame', 0)
        TotalFrames = ProgressData.get('total_frames', 0)
        FPS = ProgressData.get('fps', 0)
        Bitrate = ProgressData.get('bitrate', 0)
        Time = ProgressData.get('time', 0)
        Speed = ProgressData.get('speed', 0)
        
        if TotalFrames > 0:
            ProgressPercent = min(95, int((Frame / TotalFrames) * 100))
            print(f"Progress: {ProgressPercent}% (Frame: {Frame}/{TotalFrames}, FPS: {FPS:.1f}, Speed: {Speed:.1f}x)")
        else:
            print(f"Progress: Frame {Frame}, FPS: {FPS:.1f}, Speed: {Speed:.1f}x")
    
    print("\n" + "=" * 60)
    print("STARTING TWO-PASS TRANSCODING")
    print("=" * 60)
    
    # Start transcoding
    Result = TranscodingService.TranscodeVideo(
        InputFilePath=InputFilePath,
        OutputFilePath=OutputFilePath,
        QualitySettings=QualitySettings,
        ProgressCallback=ProgressCallback,
        UseMultiPass=False  # Use our fixed two-pass method
    )
    
    print("\n" + "=" * 60)
    print("TRANSCODING RESULT")
    print("=" * 60)
    
    if Result['Success']:
        print("✓ TRANSCODING SUCCESSFUL!")
        print(f"  Output file: {Result['OutputFilePath']}")
        print(f"  Duration: {Result['Duration']:.2f} seconds")
        print(f"  Encoding method: {Result['EncodingMethod']}")
        print(f"  Return code: {Result['ReturnCode']}")
        
        # Check if output file exists and get size
        import os
        if os.path.exists(OutputFilePath):
            OutputSize = os.path.getsize(OutputFilePath)
            InputSize = os.path.getsize(InputFilePath)
            CompressionRatio = (1 - OutputSize / InputSize) * 100
            print(f"  Input size: {InputSize:,} bytes")
            print(f"  Output size: {OutputSize:,} bytes")
            print(f"  Compression: {CompressionRatio:.1f}% reduction")
        
        return True
    else:
        print("✗ TRANSCODING FAILED!")
        print(f"  Error: {Result['ErrorMessage']}")
        print(f"  Return code: {Result['ReturnCode']}")
        print(f"  Command: {Result.get('Command', 'N/A')}")
        
        # Show FFmpeg output for debugging
        if 'AllOutput' in Result:
            print("\nFFmpeg Output:")
            print("-" * 40)
            print(Result['AllOutput'][:1000] + "..." if len(Result['AllOutput']) > 1000 else Result['AllOutput'])
        
        return False

if __name__ == "__main__":
    Success = TestManonTranscoding()
    sys.exit(0 if Success else 1)
