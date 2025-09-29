"""
Analyze codec differences by running FFprobe on sample files and saving JSON output.
"""

import os
import sys
import json
import subprocess
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService


def FindSampleFilesByCodec():
    """Find one sample file for each codec."""
    try:
        LoggingService.LogInfo("Finding sample files for each codec...", "FindSampleFilesByCodec", "AnalyzeCodecDifferences")
        
        dbManager = DatabaseManager()
        
        # Get one file for each codec
        query = """
            SELECT Codec, FilePath, FileName
            FROM MediaFiles 
            WHERE Codec IS NOT NULL 
            GROUP BY Codec
            ORDER BY Codec
        """
        rows = dbManager.DatabaseService.ExecuteQuery(query)
        
        sampleFiles = {}
        for row in rows:
            codec = row['Codec']
            filePath = row['FilePath']
            fileName = row['FileName']
            
            # Check if file still exists
            if os.path.exists(filePath):
                sampleFiles[codec] = {
                    'FilePath': filePath,
                    'FileName': fileName
                }
                LoggingService.LogInfo(f"Found {codec}: {fileName}", "FindSampleFilesByCodec", "AnalyzeCodecDifferences")
            else:
                LoggingService.LogWarning(f"File not found for {codec}: {filePath}", "FindSampleFilesByCodec", "AnalyzeCodecDifferences")
        
        return sampleFiles
        
    except Exception as e:
        LoggingService.LogException("Error finding sample files", e, "FindSampleFilesByCodec", "AnalyzeCodecDifferences")
        return {}


def RunFFprobeOnFile(FilePath, OutputFile):
    """Run FFprobe on a file and save JSON output."""
    try:
        LoggingService.LogInfo(f"Running FFprobe on: {FilePath}", "RunFFprobeOnFile", "AnalyzeCodecDifferences")
        
        # FFprobe command - use full path to FFprobe executable
        ffprobe_path = Path(__file__).parent.parent / "FFmpegMaster" / "bin" / "ffprobe.exe"
        
        command = [
            str(ffprobe_path),
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            FilePath
        ]
        
        # Run FFprobe
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            # Save JSON output to file
            with open(OutputFile, 'w', encoding='utf-8') as f:
                f.write(result.stdout)
            
            LoggingService.LogInfo(f"FFprobe output saved to: {OutputFile}", "RunFFprobeOnFile", "AnalyzeCodecDifferences")
            return True
        else:
            LoggingService.LogError(f"FFprobe failed: {result.stderr}", "RunFFprobeOnFile", "AnalyzeCodecDifferences")
            return False
            
    except subprocess.TimeoutExpired:
        LoggingService.LogError(f"FFprobe timeout for: {FilePath}", "RunFFprobeOnFile", "AnalyzeCodecDifferences")
        return False
    except Exception as e:
        LoggingService.LogException(f"Error running FFprobe on {FilePath}", e, "RunFFprobeOnFile", "AnalyzeCodecDifferences")
        return False


def AnalyzeCodecDifferences():
    """Analyze differences between codecs by running FFprobe on sample files."""
    try:
        LoggingService.LogInfo("Starting codec difference analysis", "AnalyzeCodecDifferences", "AnalyzeCodecDifferences")
        
        # Find sample files
        sampleFiles = FindSampleFilesByCodec()
        
        if not sampleFiles:
            LoggingService.LogWarning("No sample files found", "AnalyzeCodecDifferences", "AnalyzeCodecDifferences")
            return
        
        # Create output directory
        outputDir = Path("Scripts/CodecAnalysis")
        outputDir.mkdir(exist_ok=True)
        
        # Run FFprobe on each codec
        results = {}
        for codec, fileInfo in sampleFiles.items():
            filePath = fileInfo['FilePath']
            fileName = fileInfo['FileName']
            
            # Create output filename
            outputFile = outputDir / f"{codec}_analysis.json"
            
            LoggingService.LogInfo(f"Analyzing {codec} codec...", "AnalyzeCodecDifferences", "AnalyzeCodecDifferences")
            
            if RunFFprobeOnFile(filePath, outputFile):
                results[codec] = {
                    'Success': True,
                    'OutputFile': str(outputFile),
                    'SourceFile': fileName
                }
            else:
                results[codec] = {
                    'Success': False,
                    'SourceFile': fileName
                }
        
        # Print summary
        print("\n" + "="*80)
        print("CODEC ANALYSIS COMPLETE")
        print("="*80)
        
        for codec, result in results.items():
            if result['Success']:
                print(f"✅ {codec}: {result['SourceFile']} -> {result['OutputFile']}")
            else:
                print(f"❌ {codec}: {result['SourceFile']} - FAILED")
        
        print(f"\nJSON files saved to: {outputDir}")
        print("You can now analyze these files to see codec-specific field differences.")
        
        LoggingService.LogInfo("Codec analysis completed", "AnalyzeCodecDifferences", "AnalyzeCodecDifferences")
        
    except Exception as e:
        LoggingService.LogException("Error in codec analysis", e, "AnalyzeCodecDifferences", "AnalyzeCodecDifferences")


def main():
    """Main function."""
    AnalyzeCodecDifferences()


if __name__ == "__main__":
    main()
