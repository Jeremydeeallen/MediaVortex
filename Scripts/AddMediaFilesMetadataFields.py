#!/usr/bin/env python3
"""
Add metadata fields to MediaFiles table for enhanced video analysis.
This script adds fields for frame count, audio analysis, and video characteristics.
"""

import sqlite3
import os
import sys
from pathlib import Path

# Add parent directory to path to import shared services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Services.LoggingService import LoggingService


def AddMediaFilesMetadataFields():
    """Add new metadata fields to MediaFiles table."""
    try:
        LoggingService.LogInfo("Starting MediaFiles metadata fields addition", "AddMediaFilesMetadataFields")
        
        # Database path
        DatabasePath = os.path.join("Data", "MediaVortex.db")
        
        if not os.path.exists(DatabasePath):
            LoggingService.LogError(f"Database not found at {DatabasePath}", "AddMediaFilesMetadataFields")
            return False
        
        # Connect to database
        Connection = sqlite3.connect(DatabasePath)
        Cursor = Connection.cursor()
        
        # List of new fields to add
        NewFields = [
            # Frame and progress tracking
            ("TotalFrames", "INTEGER", "Total number of frames in video"),
            
            # Video characteristics
            ("CodecProfile", "TEXT", "Codec profile (Main, High, etc.)"),
            ("ColorRange", "TEXT", "Color range (tv, pc)"),
            ("FieldOrder", "TEXT", "Field order (progressive, tff, bff)"),
            ("HasBFrames", "INTEGER", "Number of B-frames (0 = none)"),
            ("RefFrames", "INTEGER", "Number of reference frames"),
            ("PixelFormat", "TEXT", "Pixel format (yuv420p, yuv420p10le, etc.)"),
            ("Level", "INTEGER", "Codec level"),
            
            # Audio characteristics
            ("AudioChannels", "INTEGER", "Number of audio channels"),
            ("AudioSampleRate", "INTEGER", "Audio sample rate in Hz"),
            ("AudioSampleFormat", "TEXT", "Audio sample format (fltp, s16, etc.)"),
            ("AudioChannelLayout", "TEXT", "Audio channel layout (stereo, 5.1, etc.)"),
            
            # Container information
            ("ContainerFormat", "TEXT", "Container format (mov,mp4,m4a,3gp,3g2,mj2)"),
            ("OverallBitrate", "INTEGER", "Overall bitrate in bps")
        ]
        
        # Check which fields already exist
        Cursor.execute("PRAGMA table_info(MediaFiles)")
        ExistingColumns = [row[1] for row in Cursor.fetchall()]
        
        FieldsToAdd = []
        for FieldName, FieldType, Description in NewFields:
            if FieldName not in ExistingColumns:
                FieldsToAdd.append((FieldName, FieldType, Description))
                LoggingService.LogInfo(f"Will add field: {FieldName} ({FieldType})", "AddMediaFilesMetadataFields")
            else:
                LoggingService.LogInfo(f"Field already exists: {FieldName}", "AddMediaFilesMetadataFields")
        
        if not FieldsToAdd:
            LoggingService.LogInfo("All fields already exist, no changes needed", "AddMediaFilesMetadataFields")
            return True
        
        # Add each field
        for FieldName, FieldType, Description in FieldsToAdd:
            try:
                AlterQuery = f"ALTER TABLE MediaFiles ADD COLUMN {FieldName} {FieldType}"
                Cursor.execute(AlterQuery)
                LoggingService.LogInfo(f"Added field: {FieldName} ({FieldType})", "AddMediaFilesMetadataFields")
                
            except sqlite3.Error as e:
                LoggingService.LogError(f"Failed to add field {FieldName}: {str(e)}", "AddMediaFilesMetadataFields")
                return False
        
        # Commit changes
        Connection.commit()
        LoggingService.LogInfo(f"Successfully added {len(FieldsToAdd)} fields to MediaFiles table", "AddMediaFilesMetadataFields")
        
        # Verify the changes
        Cursor.execute("PRAGMA table_info(MediaFiles)")
        UpdatedColumns = [row[1] for row in Cursor.fetchall()]
        
        LoggingService.LogInfo(f"MediaFiles table now has {len(UpdatedColumns)} columns", "AddMediaFilesMetadataFields")
        
        # Show the new fields
        for FieldName, FieldType, Description in FieldsToAdd:
            if FieldName in UpdatedColumns:
                LoggingService.LogInfo(f"✓ {FieldName} ({FieldType}) - {Description}", "AddMediaFilesMetadataFields")
        
        return True
        
    except Exception as e:
        LoggingService.LogException("Exception adding MediaFiles metadata fields", e, "AddMediaFilesMetadataFields")
        return False
        
    finally:
        if 'Connection' in locals():
            Connection.close()


def VerifyFields():
    """Verify that all new fields were added successfully."""
    try:
        DatabasePath = os.path.join("Data", "MediaVortex.db")
        Connection = sqlite3.connect(DatabasePath)
        Cursor = Connection.cursor()
        
        # Get all columns
        Cursor.execute("PRAGMA table_info(MediaFiles)")
        Columns = Cursor.fetchall()
        
        LoggingService.LogInfo("Current MediaFiles table structure:", "VerifyFields")
        for Column in Columns:
            LoggingService.LogInfo(f"  {Column[1]} ({Column[2]})", "VerifyFields")
        
        Connection.close()
        return True
        
    except Exception as e:
        LoggingService.LogException("Exception verifying fields", e, "VerifyFields")
        return False


if __name__ == "__main__":
    print("Adding MediaFiles metadata fields...")
    
    Success = AddMediaFilesMetadataFields()
    
    if Success:
        print("✓ MediaFiles metadata fields added successfully")
        print("\nVerifying table structure...")
        VerifyFields()
    else:
        print("✗ Failed to add MediaFiles metadata fields")
        sys.exit(1)
