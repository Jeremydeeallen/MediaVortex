#!/usr/bin/env python3
"""Check FilePath format in TranscodeQueue."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Repositories.DatabaseManager import DatabaseManager

db = DatabaseManager()
queue_items = db.GetAllTranscodeQueueItems()

print("Files in TranscodeQueue:")
print("-" * 80)
if queue_items:
    for item in queue_items[:5]:  # Show first 5
        normalized = item.FilePath.lower().replace('\\', '/')
        override_key = f"CRFOverride_{normalized}"
        print(f"FilePath: {item.FilePath}")
        print(f"Normalized: {normalized}")
        print(f"Override Key: {override_key}")
        
        # Check if override exists
        override = db.GetSystemSetting(override_key)
        if override:
            print(f"Override Found: CRF={override}")
        else:
            print("No override found")
        print("-" * 80)
else:
    print("No items in queue.")

