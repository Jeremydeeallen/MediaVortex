"""
Find one sample file for each codec to analyze FFprobe output differences.
"""

import os
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService


def FindSampleFilesByCodec():
    """Find one sample file for each codec."""
    try:
        LoggingService.LogInfo("Finding sample files for each codec...", "FindSampleFilesByCodec", "FindSampleFilesByCodec")
        
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
                LoggingService.LogInfo(f"Found {codec}: {fileName}", "FindSampleFilesByCodec", "FindSampleFilesByCodec")
            else:
                LoggingService.LogWarning(f"File not found for {codec}: {filePath}", "FindSampleFilesByCodec", "FindSampleFilesByCodec")
        
        return sampleFiles
        
    except Exception as e:
        LoggingService.LogException("Error finding sample files", e, "FindSampleFilesByCodec", "FindSampleFilesByCodec")
        return {}


def GenerateFFprobeCommands(SampleFiles):
    """Generate FFprobe commands for each codec."""
    commands = []
    
    for codec, fileInfo in SampleFiles.items():
        filePath = fileInfo['FilePath']
        fileName = fileInfo['FileName']
        
        # Generate FFprobe command
        command = f'ffprobe -v quiet -print_format json -show_format -show_streams "{filePath}"'
        
        commands.append({
            'Codec': codec,
            'FileName': fileName,
            'Command': command
        })
    
    return commands


def main():
    """Main function to find sample files and generate FFprobe commands."""
    try:
        LoggingService.LogInfo("Starting sample file analysis", "main", "FindSampleFilesByCodec")
        
        # Find sample files
        sampleFiles = FindSampleFilesByCodec()
        
        if not sampleFiles:
            LoggingService.LogWarning("No sample files found", "main", "FindSampleFilesByCodec")
            return
        
        # Generate FFprobe commands
        commands = GenerateFFprobeCommands(sampleFiles)
        
        # Print commands
        print("\n" + "="*80)
        print("FFPROBE COMMANDS TO RUN:")
        print("="*80)
        
        for cmd in commands:
            print(f"\n# {cmd['Codec']} - {cmd['FileName']}")
            print(cmd['Command'])
        
        print("\n" + "="*80)
        print("INSTRUCTIONS:")
        print("="*80)
        print("1. Run each command above")
        print("2. Save the JSON output to separate files:")
        print("   - h264_output.json")
        print("   - hevc_output.json") 
        print("   - mpeg4_output.json")
        print("   - av1_output.json")
        print("3. Share the JSON files so we can analyze field differences")
        
        LoggingService.LogInfo(f"Generated {len(commands)} FFprobe commands", "main", "FindSampleFilesByCodec")
        
    except Exception as e:
        LoggingService.LogException("Error in main function", e, "main", "FindSampleFilesByCodec")


if __name__ == "__main__":
    main()
