#!/usr/bin/env python3
"""
Test script to check directory scanning limits and exclusion settings.
Uses PascalCase naming convention and follows MVVM architecture patterns.
"""

import os
import sys
import sqlite3

# Add the parent directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Services.LoggingService import LoggingService


class DirectoryScanningChecker:
    """Handles checking of directory scanning limits and settings."""
    
    def __init__(self):
        self.DatabasePath = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'Data', 'MediaVortex.db')
    
    def CheckExclusionSettings(self):
        """Check if there are any exclusion directory settings."""
        try:
            Connection = sqlite3.connect(self.DatabasePath)
            Cursor = Connection.cursor()
            
            print("=== Exclusion Directory Settings ===")
            Cursor.execute("""
                SELECT SettingKey, SettingValue 
                FROM SystemSettings 
                WHERE SettingKey LIKE '%Exclusion%' OR SettingKey LIKE '%exclusion%'
            """)
            ExclusionRows = Cursor.fetchall()
            
            if ExclusionRows:
                for Row in ExclusionRows:
                    print(f"  {Row[0]}: {Row[1]}")
            else:
                print("  No exclusion directory settings found")
            
            Connection.close()
            
        except Exception as e:
            LoggingService.LogException("Error checking exclusion settings", e, "CheckExclusionSettings", "DirectoryScanningChecker")
            print(f"Error checking exclusion settings: {e}")
    
    def CheckScanDirectories(self):
        """Check current scan directory settings."""
        try:
            Connection = sqlite3.connect(self.DatabasePath)
            Cursor = Connection.cursor()
            
            print("\n=== Current Scan Directories ===")
            Cursor.execute("""
                SELECT SettingKey, SettingValue, Description 
                FROM SystemSettings 
                WHERE SettingKey LIKE 'ScanDir%'
                ORDER BY SettingKey
            """)
            ScanDirRows = Cursor.fetchall()
            
            if ScanDirRows:
                for Row in ScanDirRows:
                    print(f"  {Row[0]}: {Row[1]} - {Row[2]}")
            else:
                print("  No scan directories configured")
            
            Connection.close()
            
        except Exception as e:
            LoggingService.LogException("Error checking scan directories", e, "CheckScanDirectories", "DirectoryScanningChecker")
            print(f"Error checking scan directories: {e}")
    
    def AnalyzeDirectoryDepth(self, DirectoryPath: str, MaxDepth: int = 5):
        """Analyze directory depth to show how deep the scanning goes."""
        try:
            print(f"\n=== Directory Depth Analysis for {DirectoryPath} ===")
            
            if not os.path.exists(DirectoryPath):
                print(f"  Directory does not exist: {DirectoryPath}")
                return
            
            DepthCounts = {}
            TotalFiles = 0
            TotalDirs = 0
            
            for Root, Dirs, Files in os.walk(DirectoryPath):
                # Calculate depth
                Depth = Root.replace(DirectoryPath, '').count(os.sep)
                
                if Depth not in DepthCounts:
                    DepthCounts[Depth] = {'Files': 0, 'Dirs': 0}
                
                DepthCounts[Depth]['Files'] += len(Files)
                DepthCounts[Depth]['Dirs'] += len(Dirs)
                TotalFiles += len(Files)
                TotalDirs += len(Dirs)
                
                # Stop at max depth for analysis
                if Depth >= MaxDepth:
                    # Remove subdirectories to prevent going deeper
                    Dirs[:] = []
            
            print(f"  Total files found (up to depth {MaxDepth}): {TotalFiles}")
            print(f"  Total directories found (up to depth {MaxDepth}): {TotalDirs}")
            print(f"  Directory depth breakdown:")
            
            for Depth in sorted(DepthCounts.keys()):
                if Depth <= MaxDepth:
                    Counts = DepthCounts[Depth]
                    Indent = "  " + "  " * Depth
                    print(f"    {Indent}Depth {Depth}: {Counts['Files']} files, {Counts['Dirs']} dirs")
            
            if len(DepthCounts) > MaxDepth:
                print(f"    ... and deeper (stopped analysis at depth {MaxDepth})")
            
        except Exception as e:
            LoggingService.LogException("Error analyzing directory depth", e, "AnalyzeDirectoryDepth", "DirectoryScanningChecker")
            print(f"Error analyzing directory depth: {e}")
    
    def RunAllChecks(self):
        """Run all directory scanning checks."""
        print("=== Directory Scanning Analysis ===")
        
        self.CheckExclusionSettings()
        self.CheckScanDirectories()
        
        # Analyze the Z: drive if it exists
        if os.path.exists("Z:\\"):
            self.AnalyzeDirectoryDepth("Z:\\", MaxDepth=3)
        else:
            print("\n=== Z: Drive Analysis ===")
            print("  Z: drive not accessible")
        
        print("\n=== Recommendations ===")
        print("  1. Consider adding exclusion directories for system folders")
        print("  2. Consider adding a maximum depth limit to prevent deep scanning")
        print("  3. Consider scanning only specific subdirectories instead of the entire drive")


def Main():
    """Main function to run the directory scanning checks."""
    try:
        Checker = DirectoryScanningChecker()
        Checker.RunAllChecks()
        return 0
        
    except Exception as e:
        print(f"Error in main function: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(Main())
