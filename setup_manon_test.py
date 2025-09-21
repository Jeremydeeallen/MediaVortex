#!/usr/bin/env python3
import sqlite3
import os
from datetime import datetime

# Connect to database
conn = sqlite3.connect('Data/MediaVortex.db')
cursor = conn.cursor()

# File details
ManonFilePath = r"C:\MediaVortex\Source\Manon.mkv"
ManonSize = os.path.getsize(ManonFilePath)

print(f"Setting up Manon.mkv for testing:")
print(f"  File: {ManonFilePath}")
print(f"  Size: {ManonSize} bytes")

# Check if it's already in MediaFiles
cursor.execute('SELECT Id FROM MediaFiles WHERE FilePath = ?', (ManonFilePath,))
existing = cursor.fetchone()

if existing:
    print(f"  Already in MediaFiles with ID: {existing[0]}")
    MediaFileId = existing[0]
else:
    # Add to MediaFiles table
    cursor.execute('''
        INSERT INTO MediaFiles (FilePath, FileName, SizeMB, Resolution, AssignedProfile, LastScannedDate)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        ManonFilePath,
        "Manon.mkv",
        ManonSize / (1024 * 1024),  # Convert to MB
        "1080p",  # Assume 1080p for now
        "Cartoon",  # Use Cartoon profile
        datetime.now().isoformat()
    ))
    MediaFileId = cursor.lastrowid
    print(f"  Added to MediaFiles with ID: {MediaFileId}")

# Check if it's already in TranscodeQueue
cursor.execute('SELECT Id FROM TranscodeQueue WHERE FilePath = ?', (ManonFilePath,))
existing_queue = cursor.fetchone()

if existing_queue:
    print(f"  Already in TranscodeQueue with ID: {existing_queue[0]}")
else:
    # Add to TranscodeQueue
    cursor.execute('''
        INSERT INTO TranscodeQueue (FilePath, FileName, Directory, SizeBytes, SizeMB, Priority, Status, DateAdded)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        ManonFilePath,
        "Manon.mkv",
        os.path.dirname(ManonFilePath),
        ManonSize,
        ManonSize / (1024 * 1024),  # Convert to MB
        90,   # High priority
        "Pending",
        datetime.now().isoformat()
    ))
    QueueId = cursor.lastrowid
    print(f"  Added to TranscodeQueue with ID: {QueueId}")

# Commit changes
conn.commit()
conn.close()

print("Setup complete! Manon.mkv is ready for transcoding.")
