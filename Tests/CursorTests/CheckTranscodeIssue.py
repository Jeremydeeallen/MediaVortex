#!/usr/bin/env python3
"""
Check Transcode Issue - Investigate profile assignment and transcoding settings
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Repositories.DatabaseManager import DatabaseManager

def CheckTranscodeIssue():
    """Check the transcoding issue for the specific file."""
    try:
        db = DatabaseManager()
        
        # Find the file by name
        filename = 'SexArt.25.09.14.Lilly.Mays.Project.XXX.2160p.MP4-WRB.mp4'
        query = 'SELECT * FROM MediaFiles WHERE FileName LIKE ?'
        result = db.DatabaseService.ExecuteQuery(query, (f'%{filename}%',))
        
        if result:
            file = result[0]
            print('=== MEDIA FILE INFO ===')
            print(f'File: {file["FileName"]}')
            print(f'Resolution: {file["Resolution"]}')
            print(f'Assigned Profile: {file["AssignedProfile"]}')
            print(f'Video Bitrate: {file["VideoBitrateKbps"]} kbps')
            print(f'Audio Bitrate: {file["AudioBitrateKbps"]} kbps')
            print(f'File Path: {file["FilePath"]}')
            print()
            
            # Get profile thresholds if profile is assigned
            if file['AssignedProfile']:
                # Get profile thresholds by joining with Profiles table
                profile_query = '''
                SELECT pt.*, p.ProfileName 
                FROM ProfileThresholds pt 
                JOIN Profiles p ON pt.ProfileId = p.Id 
                WHERE p.ProfileName = ?
                '''
                profile_result = db.DatabaseService.ExecuteQuery(profile_query, (file['AssignedProfile'],))
                
                if profile_result:
                    print('=== PROFILE THRESHOLDS ===')
                    for threshold in profile_result:
                        print(f'Profile: {threshold["ProfileName"]}')
                        print(f'Resolution: {threshold["Resolution"]}')
                        print(f'Video Bitrate: {threshold["VideoBitrateKbps"]} kbps')
                        print(f'Audio Bitrate: {threshold["AudioBitrateKbps"]} kbps')
                        print(f'Grain: {threshold["Grain"]}')
                        print()
                else:
                    print('No profile thresholds found for this profile')
            else:
                print('No profile assigned to this file')
                
            # Check recent transcode attempts for this file
            print('=== RECENT TRANSCODE ATTEMPTS ===')
            transcode_query = '''
            SELECT * FROM TranscodeAttempts 
            WHERE InputFilePath LIKE ? 
            ORDER BY StartTime DESC 
            LIMIT 3
            '''
            transcode_result = db.DatabaseService.ExecuteQuery(transcode_query, (f'%{filename}%',))
            
            if transcode_result:
                for attempt in transcode_result:
                    print(f'Attempt ID: {attempt["AttemptId"]}')
                    print(f'Start Time: {attempt["StartTime"]}')
                    print(f'Status: {attempt["Status"]}')
                    print(f'Profile Used: {attempt["ProfileUsed"]}')
                    print(f'Command: {attempt["Command"]}')
                    print(f'Output File: {attempt["OutputFilePath"]}')
                    print(f'Error Message: {attempt["ErrorMessage"]}')
                    print('---')
            else:
                print('No transcode attempts found for this file')
                
        else:
            print('File not found in database')
            
    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    CheckTranscodeIssue()
