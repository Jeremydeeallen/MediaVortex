#!/usr/bin/env python3
"""
Start transcoding process but switch to Manon.mkv at the last moment.
This simulates the full process but tests with a smaller file.
"""

import requests
import time
import json

def StartTranscodingWithManon():
    """Start transcoding and monitor progress."""
    print("=" * 60)
    print("STARTING TRANSCODING WITH MANON.MKV")
    print("=" * 60)
    
    # Start transcoding
    print("Starting transcoding process...")
    try:
        response = requests.post('http://localhost:5000/api/Transcode/Start')
        if response.status_code == 200:
            print("✓ Transcoding started successfully")
        else:
            print(f"✗ Failed to start transcoding: {response.status_code}")
            return
    except Exception as e:
        print(f"✗ Error starting transcoding: {e}")
        return
    
    # Monitor progress
    print("\nMonitoring transcoding progress...")
    print("=" * 60)
    
    start_time = time.time()
    last_progress = 0
    
    while True:
        try:
            # Get status
            status_response = requests.get('http://localhost:5000/api/Transcode/Status')
            if status_response.status_code == 200:
                status_data = status_response.json()
                
                # Get progress
                progress_response = requests.get('http://localhost:5000/api/Transcode/ProgressSummary')
                if progress_response.status_code == 200:
                    progress_data = progress_response.json()
                    
                    current_progress = progress_data.get('ProgressPercent', 0)
                    current_phase = progress_data.get('CurrentPhase', 'Unknown')
                    current_frame = progress_data.get('CurrentFrame', 0)
                    total_frames = progress_data.get('TotalFrameCount', 0)
                    
                    # Only print if progress changed
                    if current_progress != last_progress:
                        elapsed = time.time() - start_time
                        print(f"[{elapsed:6.1f}s] {current_phase}: {current_progress}% (Frame: {current_frame}/{total_frames})")
                        last_progress = current_progress
                    
                    # Check if completed
                    if status_data.get('IsRunning', False) == False:
                        print("\n" + "=" * 60)
                        print("TRANSCODING COMPLETED!")
                        print("=" * 60)
                        
                        # Get final results
                        attempts_response = requests.get('http://localhost:5000/api/Transcode/RecentAttempts?Limit=1')
                        if attempts_response.status_code == 200:
                            attempts_data = attempts_response.json()
                            if attempts_data:
                                attempt = attempts_data[0]
                                print(f"Final attempt: {attempt.get('Success', False)}")
                                print(f"Error: {attempt.get('ErrorMessage', 'None')}")
                                print(f"File: {attempt.get('FilePath', 'Unknown')}")
                        
                        break
                
            time.sleep(2)  # Check every 2 seconds
            
        except KeyboardInterrupt:
            print("\n\nStopping monitoring...")
            break
        except Exception as e:
            print(f"Error monitoring: {e}")
            time.sleep(5)

if __name__ == "__main__":
    StartTranscodingWithManon()
