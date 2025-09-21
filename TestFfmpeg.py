import subprocess as sp
import shlex
import json
import time
import os

# Input file path
InputFile = r"C:\MediaVortex\Source\P-Valley - S01E02 - Scars WEBDL-2160p.mkv"
OutputFile = r"C:\MediaVortex\test_output.mkv"

# Check if input file exists
if not os.path.exists(InputFile):
    print(f"ERROR: Input file not found: {InputFile}")
    exit(1)

print(f"Input file: {InputFile}")
print(f"Output file: {OutputFile}")
print("="*50)

# First, get total frame count using ffprobe
print("Getting total frame count...")
ProbeCommand = f'ffprobe -v error -select_streams v:0 -count_packets -show_entries stream=nb_read_packets -of csv=p=0 -of json "{InputFile}"'
print(f"Probe command: {ProbeCommand}")

try:
    ProbeData = sp.run(shlex.split(ProbeCommand), stdout=sp.PIPE, stderr=sp.PIPE)
    if ProbeData.returncode != 0:
        print(f"FFprobe error: {ProbeData.stderr.decode('utf-8')}")
        exit(1)
    
    ProbeJson = json.loads(ProbeData.stdout)
    TotalFrames = float(ProbeJson['streams'][0]['nb_read_packets'])
    print(f"Total frames: {TotalFrames}")
except Exception as e:
    print(f"Error getting frame count: {e}")
    TotalFrames = 0

print("="*50)

# Now run FFmpeg with two-pass encoding
print("Starting TWO-PASS encoding...")
print("="*50)

# First pass - analysis pass (downscaled to 720p, 10-bit)
Pass1Command = f'ffmpeg -y -loglevel info -i "{InputFile}" -c:v libx265 -preset ultrafast -x265-params "pass=1:10bit=1" -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2" -an -f null -progress pipe:1 -'
print(f"PASS 1 COMMAND: {Pass1Command}")
print("="*50)

try:
    # Run first pass
    Pass1Process = sp.Popen(shlex.split(Pass1Command), stdout=sp.PIPE, stderr=sp.STDOUT, text=True, bufsize=1, universal_newlines=True)
    
    print("PASS 1: FFmpeg process started. Reading output...")
    
    # Read first pass output
    Pass1LineCount = 0
    Pass1ProgressLines = 0
    while True:
        Line = Pass1Process.stdout.readline()
        if not Line:
            break
        
        Line = Line.strip()
        Pass1LineCount += 1
        
        # Show all lines, but highlight progress lines
        if Line.startswith("frame=") or Line.startswith("fps=") or Line.startswith("bitrate=") or Line.startswith("time="):
            Pass1ProgressLines += 1
            print(f"PASS 1 PROGRESS {Pass1ProgressLines}: {Line}")
        else:
            print(f"PASS 1 Line {Pass1LineCount}: {Line}")
    
    # Get any remaining output from first pass
    Pass1Stdout, Pass1Stderr = Pass1Process.communicate()
    Pass1ReturnCode = Pass1Process.returncode
    
    print("="*50)
    print(f"PASS 1 completed with return code: {Pass1ReturnCode}")
    print("="*50)
    
    if Pass1ReturnCode != 0:
        print("PASS 1 failed, stopping...")
        exit(1)
    
    # Second pass - encoding pass (downscaled to 720p, 10-bit)
    Pass2Command = f'ffmpeg -y -loglevel info -i "{InputFile}" -c:v libx265 -c:a aac -b:a 70k -preset fast -crf 25 -x265-params "10bit=1" -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2" -pass 2 -progress pipe:1 "{OutputFile}"'
    print(f"PASS 2 COMMAND: {Pass2Command}")
    print("="*50)
    
    # Run second pass
    Pass2Process = sp.Popen(shlex.split(Pass2Command), stdout=sp.PIPE, stderr=sp.STDOUT, text=True, bufsize=1, universal_newlines=True)
    
    print("PASS 2: FFmpeg process started. Reading output...")
    
    # Read second pass output
    Pass2LineCount = 0
    Pass2ProgressLines = 0
    while True:
        Line = Pass2Process.stdout.readline()
        if not Line:
            break
        
        Line = Line.strip()
        Pass2LineCount += 1
        
        # Show all lines, but highlight progress lines
        if Line.startswith("frame=") or Line.startswith("fps=") or Line.startswith("bitrate=") or Line.startswith("time="):
            Pass2ProgressLines += 1
            print(f"PASS 2 PROGRESS {Pass2ProgressLines}: {Line}")
        else:
            print(f"PASS 2 Line {Pass2LineCount}: {Line}")
    
    # Get any remaining output from second pass
    Pass2Stdout, Pass2Stderr = Pass2Process.communicate()
    Pass2ReturnCode = Pass2Process.returncode
    
    print("="*50)
    print(f"PASS 2 completed with return code: {Pass2ReturnCode}")
    print("="*50)
    
    # Final results
    print("TWO-PASS ENCODING COMPLETE!")
    print(f"Pass 1: {Pass1ProgressLines} progress lines, return code: {Pass1ReturnCode}")
    print(f"Pass 2: {Pass2ProgressLines} progress lines, return code: {Pass2ReturnCode}")
    
    if os.path.exists(OutputFile):
        OutputSize = os.path.getsize(OutputFile)
        print(f"Output file created: {OutputFile} ({OutputSize} bytes)")
    else:
        print("No output file was created")
        
except Exception as e:
    print(f"Error running FFmpeg: {e}")

