import subprocess as sp
import shlex
import json
import os
import time

def RunVMAFComparison(TranscodedFile, SourceFile, OutputJsonFile):
    """Run VMAF comparison between transcoded and source files."""
    
    print(f"Running VMAF comparison...")
    print(f"Transcoded file: {TranscodedFile}")
    print(f"Source file: {SourceFile}")
    print(f"Output JSON: {OutputJsonFile}")
    print("="*50)
    
    # Check if files exist
    if not os.path.exists(TranscodedFile):
        print(f"ERROR: Transcoded file not found: {TranscodedFile}")
        return False
    
    if not os.path.exists(SourceFile):
        print(f"ERROR: Source file not found: {SourceFile}")
        return False
    
    # Build VMAF command
    VMAFCommand = f'ffmpeg -i "{TranscodedFile}" -i "{SourceFile}" -lavfi libvmaf="log_path={OutputJsonFile}:log_fmt=json" -f null -'
    print(f"VMAF Command: {VMAFCommand}")
    print("="*50)
    
    try:
        # Run VMAF comparison
        Process = sp.Popen(shlex.split(VMAFCommand), stdout=sp.PIPE, stderr=sp.STDOUT, text=True, bufsize=1, universal_newlines=True)
        
        print("VMAF process started. Reading output...")
        
        # Read output line by line
        LineCount = 0
        VMAFLines = 0
        StartTime = time.time()
        
        while True:
            Line = Process.stdout.readline()
            if not Line:
                break
            
            Line = Line.strip()
            LineCount += 1
            
            # Show all lines, but highlight VMAF-specific lines
            if "VMAF" in Line or "vmaf" in Line:
                VMAFLines += 1
                print(f"VMAF {VMAFLines}: {Line}")
            else:
                print(f"Line {LineCount}: {Line}")
        
        # Get any remaining output
        Stdout, Stderr = Process.communicate()
        ReturnCode = Process.returncode
        EndTime = time.time()
        Duration = EndTime - StartTime
        
        print("="*50)
        print(f"VMAF process completed with return code: {ReturnCode}")
        print(f"Duration: {Duration:.2f} seconds")
        print("="*50)
        
        # Check if JSON file was created and read the VMAF score
        if os.path.exists(OutputJsonFile):
            try:
                with open(OutputJsonFile, 'r') as f:
                    VMAFData = json.load(f)
                
                # Extract VMAF score
                if 'pooled_metrics' in VMAFData and 'vmaf' in VMAFData['pooled_metrics']:
                    VMAFScore = VMAFData['pooled_metrics']['vmaf']['mean']
                    print(f"VMAF Score: {VMAFScore:.3f}")
                    print(f"Quality Assessment: {'Excellent' if VMAFScore >= 95 else 'Very Good' if VMAFScore >= 90 else 'Good' if VMAFScore >= 80 else 'Fair' if VMAFScore >= 70 else 'Poor'}")
                else:
                    print("VMAF score not found in JSON output")
                    
            except Exception as e:
                print(f"Error reading VMAF JSON: {e}")
        else:
            print("VMAF JSON file was not created")
        
        return ReturnCode == 0
        
    except Exception as e:
        print(f"Error running VMAF: {e}")
        return False

# File paths
SourceFile = r"C:\MediaVortex\Source\P-Valley - S01E02 - Scars WEBDL-2160p.mkv"
TranscodedFile = r"C:\MediaVortex\test_output.mkv"
OutputJsonFile = r"C:\MediaVortex\vmaf_comparison.json"

print("VMAF Quality Comparison Test")
print("="*50)

# Run the comparison
Success = RunVMAFComparison(TranscodedFile, SourceFile, OutputJsonFile)

if Success:
    print("VMAF comparison completed successfully!")
else:
    print("VMAF comparison failed!")
