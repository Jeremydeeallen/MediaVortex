#!/usr/bin/env python3
"""
Investigate Transcode Issue - Step by step analysis
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Repositories.DatabaseManager import DatabaseManager

def InvestigateTranscodeIssue():
    """Investigate the transcoding issue step by step."""
    try:
        db = DatabaseManager()
        
        # File we're investigating
        filename = 'SexArt.25.09.14.Lilly.Mays.Project.XXX.2160p.MP4-WRB.mp4'
        
        print("=== STEP 1: Get Media File Info ===")
        media_query = 'SELECT * FROM MediaFiles WHERE FileName LIKE ?'
        media_result = db.DatabaseService.ExecuteQuery(media_query, (f'%{filename}%',))
        
        if not media_result:
            print("File not found in MediaFiles table")
            return
            
        media_file = media_result[0]
        print(f"File: {media_file['FileName']}")
        print(f"Resolution: {media_file['Resolution']}")
        print(f"Assigned Profile: {media_file['AssignedProfile']}")
        print()
        
        print("=== STEP 2: Check Profile Thresholds for 2160p ===")
        profile_query = '''
        SELECT pt.*, p.ProfileName 
        FROM ProfileThresholds pt 
        JOIN Profiles p ON pt.ProfileId = p.Id 
        WHERE p.ProfileName = ? AND pt.Resolution = ?
        '''
        profile_result = db.DatabaseService.ExecuteQuery(profile_query, (media_file['AssignedProfile'], '2160p'))
        
        if profile_result:
            threshold = profile_result[0]
            print(f"Profile: {threshold['ProfileName']}")
            print(f"Resolution: {threshold['Resolution']}")
            print(f"TranscodeDownTo: {threshold['TranscodeDownTo']}")
            print(f"Video Bitrate: {threshold['VideoBitrateKbps']} kbps")
            print(f"Audio Bitrate: {threshold['AudioBitrateKbps']} kbps")
            print(f"Quality: {threshold['Quality']}")
            print(f"Codec: {threshold['Codec']}")
            print()
        else:
            print("No 2160p threshold found")
            return
            
        print("=== STEP 3: Check Target Resolution Settings (720p) ===")
        target_query = '''
        SELECT pt.*, p.ProfileName 
        FROM ProfileThresholds pt 
        JOIN Profiles p ON pt.ProfileId = p.Id 
        WHERE p.ProfileName = ? AND pt.Resolution = ?
        '''
        target_result = db.DatabaseService.ExecuteQuery(target_query, (media_file['AssignedProfile'], '720p'))
        
        if target_result:
            target = target_result[0]
            print(f"Target Profile: {target['ProfileName']}")
            print(f"Target Resolution: {target['Resolution']}")
            print(f"Target Video Bitrate: {target['VideoBitrateKbps']} kbps")
            print(f"Target Audio Bitrate: {target['AudioBitrateKbps']} kbps")
            print(f"Target Quality: {target['Quality']}")
            print(f"Target Codec: {target['Codec']}")
            print()
        else:
            print("No 720p target threshold found")
            return
            
        print("=== STEP 4: Check Recent Transcode Attempt ===")
        transcode_query = '''
        SELECT * FROM TranscodeAttempts 
        WHERE LOWER(FilePath) LIKE LOWER(?) 
        ORDER BY AttemptDate DESC 
        LIMIT 1
        '''
        transcode_result = db.DatabaseService.ExecuteQuery(transcode_query, (f'%{filename}%',))
        
        if transcode_result:
            attempt = transcode_result[0]
            print(f"Attempt Date: {attempt['AttemptDate']}")
            print(f"Success: {attempt['Success']}")
            print(f"Quality: {attempt['Quality']}")
            print(f"Video Bitrate: {attempt['VideoBitrateKbps']} kbps")
            print(f"Audio Bitrate: {attempt['AudioBitrateKbps']} kbps")
            print(f"FFmpeg Command: {attempt['FfpmpegCommand']}")
            print()
            
            # Check if command contains scaling
            if 'scale=' in attempt['FfpmpegCommand']:
                print("✅ FFmpeg command CONTAINS scaling filter")
            else:
                print("❌ FFmpeg command MISSING scaling filter")
        else:
            print("No transcode attempt found")
            
        print("=== STEP 5: Check Logs for Transcoding Process ===")
        log_query = '''
        SELECT * FROM Logs 
        WHERE FunctionName LIKE '%Transcoding%' 
        AND LogMessage LIKE '%SexArt%'
        ORDER BY Timestamp DESC 
        LIMIT 10
        '''
        log_result = db.DatabaseService.ExecuteQuery(log_query)
        
        if log_result:
            print("Recent transcoding logs:")
            for log in log_result:
                print(f"  {log['Timestamp']}: {log['LogMessage']}")
        else:
            print("No transcoding logs found")
            
    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    InvestigateTranscodeIssue()
