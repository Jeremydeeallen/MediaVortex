"""
Update existing MediaFiles with new metadata fields.
This script will run FFprobe on all existing media files and populate the new metadata fields.
"""

import os
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from Services.FileManagerService import FileManagerService
from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService


def GetAllMediaFiles(DatabaseManager):
    """Get all media files from the database."""
    try:
        query = """
            SELECT Id, SeasonId, FilePath, FileName, SizeMB, VideoBitrateKbps, AudioBitrateKbps,
                   Resolution, Codec, DurationMinutes, FrameRate, LastScannedDate,
                   CompressionPotential, AssignedProfile, FileModificationTime
            FROM MediaFiles 
            ORDER BY Id
        """
        rows = DatabaseManager.DatabaseService.ExecuteQuery(query)
        
        from Models.MediaFileModel import MediaFileModel
        mediaFiles = []
        for row in rows:
            mediaFile = MediaFileModel(
                Id=row['Id'],
                SeasonId=row['SeasonId'],
                FilePath=row['FilePath'],
                FileName=row['FileName'],
                SizeMB=row['SizeMB'],
                VideoBitrateKbps=row['VideoBitrateKbps'],
                AudioBitrateKbps=row['AudioBitrateKbps'],
                Resolution=row['Resolution'],
                Codec=row['Codec'],
                DurationMinutes=row['DurationMinutes'],
                FrameRate=row['FrameRate'],
                LastScannedDate=row['LastScannedDate'],
                CompressionPotential=row['CompressionPotential'],
                AssignedProfile=row['AssignedProfile'],
                FileModificationTime=row['FileModificationTime']
            )
            mediaFiles.append(mediaFile)
        
        return mediaFiles
    except Exception as e:
        LoggingService.LogException("Error getting media files", e, "GetAllMediaFiles", "UpdateExistingMediaFilesWithNewMetadata")
        return []


def UpdateMediaFileWithNewMetadata(MediaFile, FileManager, DatabaseManager):
    """Update a single media file with new metadata fields."""
    try:
        LoggingService.LogInfo(f"Processing: {MediaFile.FileName}", "UpdateMediaFileWithNewMetadata", "UpdateExistingMediaFilesWithNewMetadata")
        
        # Check if file still exists
        if not os.path.exists(MediaFile.FilePath):
            LoggingService.LogWarning(f"File not found: {MediaFile.FilePath}", "UpdateMediaFileWithNewMetadata", "UpdateExistingMediaFilesWithNewMetadata")
            return False
        
        # Extract new metadata (this will run FFprobe)
        metadata = FileManager.ExtractMediaMetadata(MediaFile.FilePath)
        
        if metadata.get('Success'):
            # Update with new fields
            MediaFile.TotalFrames = metadata.get('TotalFrames')
            MediaFile.CodecProfile = metadata.get('CodecProfile')
            MediaFile.ColorRange = metadata.get('ColorRange')
            MediaFile.FieldOrder = metadata.get('FieldOrder')
            MediaFile.HasBFrames = metadata.get('HasBFrames')
            MediaFile.RefFrames = metadata.get('RefFrames')
            MediaFile.PixelFormat = metadata.get('PixelFormat')
            MediaFile.Level = metadata.get('Level')
            MediaFile.AudioChannels = metadata.get('AudioChannels')
            MediaFile.AudioSampleRate = metadata.get('AudioSampleRate')
            MediaFile.AudioSampleFormat = metadata.get('AudioSampleFormat')
            MediaFile.AudioChannelLayout = metadata.get('AudioChannelLayout')
            MediaFile.ContainerFormat = metadata.get('ContainerFormat')
            MediaFile.OverallBitrate = metadata.get('OverallBitrate')
            
            # Save back to database
            DatabaseManager.SaveMediaFile(MediaFile)
            LoggingService.LogInfo(f"Successfully updated: {MediaFile.FileName}", "UpdateMediaFileWithNewMetadata", "UpdateExistingMediaFilesWithNewMetadata")
            return True
        else:
            LoggingService.LogWarning(f"Failed to extract metadata for {MediaFile.FileName}: {metadata.get('ErrorMessage', 'Unknown error')}", "UpdateMediaFileWithNewMetadata", "UpdateExistingMediaFilesWithNewMetadata")
            return False
            
    except Exception as e:
        LoggingService.LogException(f"Error updating {MediaFile.FileName}", e, "UpdateMediaFileWithNewMetadata", "UpdateExistingMediaFilesWithNewMetadata")
        return False


def main():
    """Main function to update all existing media files with new metadata."""
    try:
        LoggingService.LogInfo("Starting update of existing media files with new metadata", "main", "UpdateExistingMediaFilesWithNewMetadata")
        
        # Initialize services
        dbManager = DatabaseManager()
        fileManager = FileManagerService()
        
        # Get all existing media files
        LoggingService.LogInfo("Retrieving all media files from database...", "main", "UpdateExistingMediaFilesWithNewMetadata")
        mediaFiles = GetAllMediaFiles(dbManager)
        
        if not mediaFiles:
            LoggingService.LogWarning("No media files found in database", "main", "UpdateExistingMediaFilesWithNewMetadata")
            return
        
        LoggingService.LogInfo(f"Found {len(mediaFiles)} media files to process", "main", "UpdateExistingMediaFilesWithNewMetadata")
        
        # Process files in batches
        batch_size = 100
        total_files = len(mediaFiles)
        successful_updates = 0
        failed_updates = 0
        
        for i in range(0, total_files, batch_size):
            batch = mediaFiles[i:i+batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (total_files + batch_size - 1) // batch_size
            
            LoggingService.LogInfo(f"Processing batch {batch_num}/{total_batches} ({len(batch)} files)", "main", "UpdateExistingMediaFilesWithNewMetadata")
            
            for mediaFile in batch:
                if UpdateMediaFileWithNewMetadata(mediaFile, fileManager, dbManager):
                    successful_updates += 1
                else:
                    failed_updates += 1
                
                # Progress update every 10 files
                if (successful_updates + failed_updates) % 10 == 0:
                    LoggingService.LogInfo(f"Progress: {successful_updates + failed_updates}/{total_files} files processed", "main", "UpdateExistingMediaFilesWithNewMetadata")
        
        LoggingService.LogInfo(f"Update completed! Successfully updated: {successful_updates}, Failed: {failed_updates}", "main", "UpdateExistingMediaFilesWithNewMetadata")
        
    except Exception as e:
        LoggingService.LogException("Error in main function", e, "main", "UpdateExistingMediaFilesWithNewMetadata")


if __name__ == "__main__":
    main()
