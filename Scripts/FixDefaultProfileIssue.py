#!/usr/bin/env python3
"""
Script to fix the Default profile issue in MediaFiles.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService

def FixDefaultProfileIssue():
    """Fix the Default profile issue by updating MediaFiles to use a valid profile."""
    try:
        db = DatabaseManager()
        
        # Check how many files have the Default profile
        result = db.DatabaseService.ExecuteQuery("SELECT COUNT(*) as Count FROM MediaFiles WHERE AssignedProfile = 'Default'")
        default_count = result[0]["Count"] if result else 0
        print(f"Files with 'Default' profile: {default_count}")
        
        if default_count == 0:
            print("No files with 'Default' profile found. Nothing to fix.")
            return
        
        # Get a suitable replacement profile (use the first available profile)
        profiles = db.DatabaseService.ExecuteQuery("SELECT Id, ProfileName FROM Profiles ORDER BY Id LIMIT 1")
        if not profiles:
            print("No profiles found in database. Cannot fix the issue.")
            return
        
        replacement_profile = profiles[0]["ProfileName"]
        replacement_id = profiles[0]["Id"]
        print(f"Using replacement profile: {replacement_profile} (ID: {replacement_id})")
        
        # Update all MediaFiles with 'Default' profile to use the replacement profile
        update_query = "UPDATE MediaFiles SET AssignedProfile = ? WHERE AssignedProfile = 'Default'"
        affected_rows = db.DatabaseService.ExecuteNonQuery(update_query, (replacement_profile,))
        
        print(f"Updated {affected_rows} files from 'Default' to '{replacement_profile}'")
        
        # Verify the fix
        result = db.DatabaseService.ExecuteQuery("SELECT COUNT(*) as Count FROM MediaFiles WHERE AssignedProfile = 'Default'")
        remaining_default = result[0]["Count"] if result else 0
        print(f"Remaining files with 'Default' profile: {remaining_default}")
        
        if remaining_default == 0:
            print("✅ Successfully fixed the Default profile issue!")
        else:
            print("❌ Some files still have 'Default' profile")
            
    except Exception as e:
        print(f"Error fixing Default profile issue: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    FixDefaultProfileIssue()
