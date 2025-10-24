"""
AnalyzeDexterTranscodes.py - Analyze transcode attempts for Dexter episode
"""

import sys
import os
import re
from typing import Dict, List, Any

# Add parent directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
root_dir = os.path.dirname(parent_dir)
sys.path.append(root_dir)

from Repositories.DatabaseManager import DatabaseManager


def ExtractCodecParameters(FfmpegCommand: str) -> Dict[str, Any]:
    """Extract codec parameters from FFmpeg command."""
    params = {}
    
    # Extract CRF
    crf_match = re.search(r'-crf\s+(\d+)', FfmpegCommand)
    if crf_match:
        params['CRF'] = int(crf_match.group(1))
    
    # Extract preset
    preset_match = re.search(r'-preset\s+(\d+)', FfmpegCommand)
    if preset_match:
        params['Preset'] = int(preset_match.group(1))
    
    # Extract film grain from svtav1-params
    grain_match = re.search(r'film-grain=(\d+)', FfmpegCommand)
    if grain_match:
        params['FilmGrain'] = int(grain_match.group(1))
    else:
        params['FilmGrain'] = 0
    
    # Extract audio bitrate
    audio_match = re.search(r'-b:a\s+(\d+)k', FfmpegCommand)
    if audio_match:
        params['AudioBitrate'] = int(audio_match.group(1))
    
    # Extract scale filter (resolution)
    scale_match = re.search(r'scale=(-?\d+):(-?\d+)', FfmpegCommand)
    if scale_match:
        params['ScaleWidth'] = scale_match.group(1)
        params['ScaleHeight'] = scale_match.group(2)
    
    return params


def AnalyzeDexterTranscodes():
    """Analyze all transcode attempts for the Dexter episode."""
    file_path = r"T:\Dexter\Season 1\Dexter - S01E02 - Crocodile Bluray-1080p Remux.mkv"
    
    db = DatabaseManager()
    
    # Get all attempts
    query = """
        SELECT Id, Quality, VMAF, ProfileName, FfpmpegCommand, NewSizeBytes, 
               TranscodeDurationSeconds, AudioBitrateKbps
        FROM TranscodeAttempts 
        WHERE LOWER(FilePath) = LOWER(?) AND Success = 1
        ORDER BY AttemptDate DESC
    """
    
    results = db.DatabaseService.ExecuteQuery(query, (file_path,))
    
    print("=" * 100)
    print("DEXTER S01E02 TRANSCODE ATTEMPTS ANALYSIS")
    print("=" * 100)
    print(f"Original File: 11,363 MB (11.1 GB)")
    print(f"Original Bitrate: 29,009 kbps video, 2,900 kbps audio")
    print(f"Resolution: 1920x1080 (h264)")
    print(f"Duration: 54.77 minutes")
    print(f"Total Frames: 78,786")
    print("=" * 100)
    print()
    
    attempts_data = []
    
    for row in results:
        attempt_id = row['Id']
        crf_quality = row['Quality']
        vmaf_score = row['VMAF']
        profile_name = row['ProfileName']
        ffmpeg_command = row['FfpmpegCommand'] or ""
        new_size_mb = row['NewSizeBytes'] / (1024 * 1024) if row['NewSizeBytes'] else 0
        duration_mins = row['TranscodeDurationSeconds'] / 60 if row['TranscodeDurationSeconds'] else 0
        audio_bitrate = row['AudioBitrateKbps']
        
        params = ExtractCodecParameters(ffmpeg_command)
        
        attempts_data.append({
            'Id': attempt_id,
            'CRF': crf_quality,
            'VMAF': vmaf_score,
            'ProfileName': profile_name,
            'SizeMB': new_size_mb,
            'DurationMins': duration_mins,
            'AudioBitrate': audio_bitrate,
            **params
        })
    
    # Print detailed analysis
    print(f"{'ID':<6} {'CRF':<5} {'VMAF':<8} {'Grain':<7} {'Preset':<8} {'Audio':<7} {'Size MB':<10} {'Profile':<50}")
    print("-" * 110)
    
    for attempt in attempts_data:
        print(f"{attempt['Id']:<6} "
              f"{attempt['CRF']:<5} "
              f"{attempt['VMAF']:<8.2f} "
              f"{attempt.get('FilmGrain', 0):<7} "
              f"{attempt.get('Preset', 'N/A'):<8} "
              f"{attempt.get('AudioBitrate', 'N/A'):<7} "
              f"{attempt['SizeMB']:<10.1f} "
              f"{attempt['ProfileName']:<50}")
    
    print()
    print("=" * 100)
    print("ANALYSIS SUMMARY")
    print("=" * 100)
    
    # Find attempts closest to 90% VMAF
    attempts_sorted_by_vmaf = sorted(attempts_data, key=lambda x: abs(x['VMAF'] - 90.0))
    
    print("\nBest Attempt (Closest to 90% VMAF but all failed):")
    print(f"  - Best VMAF achieved: {max(a['VMAF'] for a in attempts_data):.2f}%")
    print(f"  - Worst VMAF: {min(a['VMAF'] for a in attempts_data):.2f}%")
    print(f"  - Average VMAF: {sum(a['VMAF'] for a in attempts_data) / len(attempts_data):.2f}%")
    print()
    
    # Analyze correlation between parameters and VMAF
    print("PARAMETER CORRELATION ANALYSIS:")
    print("-" * 50)
    
    # CRF vs VMAF
    print("\nCRF Quality Impact:")
    crf_groups = {}
    for attempt in attempts_data:
        crf = attempt['CRF']
        if crf not in crf_groups:
            crf_groups[crf] = []
        crf_groups[crf].append(attempt['VMAF'])
    
    for crf in sorted(crf_groups.keys()):
        avg_vmaf = sum(crf_groups[crf]) / len(crf_groups[crf])
        print(f"  CRF {crf}: Average VMAF = {avg_vmaf:.2f}% ({len(crf_groups[crf])} attempts)")
    
    # Film Grain vs VMAF
    print("\nFilm Grain Impact:")
    grain_groups = {}
    for attempt in attempts_data:
        grain = attempt.get('FilmGrain', 0)
        if grain not in grain_groups:
            grain_groups[grain] = []
        grain_groups[grain].append(attempt['VMAF'])
    
    for grain in sorted(grain_groups.keys()):
        avg_vmaf = sum(grain_groups[grain]) / len(grain_groups[grain])
        print(f"  Grain {grain}: Average VMAF = {avg_vmaf:.2f}% ({len(grain_groups[grain])} attempts)")
    
    # Audio bitrate vs VMAF (size correlation)
    print("\nAudio Bitrate Impact on File Size:")
    audio_groups = {}
    for attempt in attempts_data:
        audio = attempt.get('AudioBitrate', 0)
        if audio not in audio_groups:
            audio_groups[audio] = []
        audio_groups[audio].append(attempt['SizeMB'])
    
    for audio in sorted(audio_groups.keys()):
        avg_size = sum(audio_groups[audio]) / len(audio_groups[audio])
        print(f"  Audio {audio}k: Average Size = {avg_size:.1f} MB ({len(audio_groups[audio])} attempts)")
    
    print()
    print("=" * 100)
    print("COMPARISON WITH SUCCESSFUL FILES (90%+ VMAF)")
    print("=" * 100)
    
    # Get similar successful files
    success_query = """
        SELECT Quality, VMAF, ProfileName, FfpmpegCommand, 
               OldSizeBytes, NewSizeBytes, FilePath
        FROM TranscodeAttempts 
        WHERE Success = 1 
        AND VMAF >= 90.0 
        AND VMAF < 95.0
        AND Quality BETWEEN 18 AND 28
        ORDER BY VMAF ASC
        LIMIT 20
    """
    
    success_results = db.DatabaseService.ExecuteQuery(success_query)
    
    print(f"\n{'CRF':<5} {'VMAF':<8} {'Grain':<7} {'Preset':<8} {'Compression':<12} {'Profile':<40}")
    print("-" * 90)
    
    for row in success_results:
        crf = row['Quality']
        vmaf = row['VMAF']
        profile = row['ProfileName']
        ffmpeg_cmd = row['FfpmpegCommand'] or ""
        old_size = row['OldSizeBytes'] / (1024 * 1024) if row['OldSizeBytes'] else 0
        new_size = row['NewSizeBytes'] / (1024 * 1024) if row['NewSizeBytes'] else 0
        compression_pct = ((old_size - new_size) / old_size * 100) if old_size > 0 else 0
        
        params = ExtractCodecParameters(ffmpeg_cmd)
        
        print(f"{crf:<5} "
              f"{vmaf:<8.2f} "
              f"{params.get('FilmGrain', 0):<7} "
              f"{params.get('Preset', 'N/A'):<8} "
              f"{compression_pct:<12.1f}% "
              f"{profile[:40]:<40}")
    
    print()
    print("=" * 100)
    print("MATHEMATICAL RECOMMENDATION FOR 90%+ VMAF")
    print("=" * 100)
    
    # Calculate recommendations based on patterns
    print("\nBased on analysis of your attempts and successful 90%+ VMAF transcodes:")
    print()
    print("KEY FINDINGS:")
    print("1. Your highest VMAF achieved: 77.39% (CRF 20, no film grain specified)")
    print("2. Gap to 90% target: 12.61 percentage points")
    print("3. This is a heavily grained source (Bluray remux) at 29 Mbps")
    print()
    print("MATHEMATICAL ANALYSIS:")
    print("-" * 50)
    
    # Calculate CRF needed
    highest_attempt = max(attempts_data, key=lambda x: x['VMAF'])
    print(f"Best attempt: CRF {highest_attempt['CRF']}, VMAF {highest_attempt['VMAF']:.2f}%")
    print(f"Film grain used: {highest_attempt.get('FilmGrain', 0)}")
    print()
    
    # Estimate CRF reduction needed
    vmaf_gap = 90.0 - highest_attempt['VMAF']
    # Rule of thumb: Each CRF point is worth ~1-2% VMAF for difficult content
    crf_reduction_needed = int(vmaf_gap / 1.5)  # Conservative estimate
    recommended_crf = max(15, highest_attempt['CRF'] - crf_reduction_needed)
    
    print(f"VMAF Gap: {vmaf_gap:.2f}%")
    print(f"Estimated CRF reduction needed: {crf_reduction_needed} points")
    print(f"Current best CRF: {highest_attempt['CRF']}")
    print(f"**RECOMMENDED CRF: {recommended_crf}**")
    print()
    
    # Estimate file size
    current_size = highest_attempt['SizeMB']
    # Each CRF point reduction increases size by ~15-20%
    size_increase_per_crf = 0.18  # 18% per point
    total_size_increase = (1 + size_increase_per_crf) ** crf_reduction_needed
    estimated_size = current_size * total_size_increase
    estimated_size_gb = estimated_size / 1024
    
    original_size_mb = 11363.74
    compression_pct = ((original_size_mb - estimated_size) / original_size_mb) * 100
    
    print(f"Current size at CRF {highest_attempt['CRF']}: {current_size:.1f} MB")
    print(f"Estimated size at CRF {recommended_crf}: {estimated_size:.1f} MB ({estimated_size_gb:.2f} GB)")
    print(f"Estimated compression: {compression_pct:.1f}%")
    print()
    
    print("RECOMMENDED SETTINGS FOR 90%+ VMAF:")
    print("=" * 50)
    print(f"✓ CRF Quality: {recommended_crf}")
    print(f"✓ Codec: libsvtav1")
    print(f"✓ Preset: 6 (balanced speed/quality)")
    print(f"✓ Film Grain: 15-20 (preserve source grain)")
    print(f"✓ Audio Bitrate: 256k (maintain quality)")
    print(f"✓ Target Resolution: 720p (1280x720)")
    print(f"✓ Pixel Format: yuv420p10le (10-bit)")
    print()
    print(f"Expected Result:")
    print(f"  - VMAF Score: ~90-92%")
    print(f"  - File Size: ~{estimated_size:.0f} MB ({estimated_size_gb:.2f} GB)")
    print(f"  - Compression: ~{compression_pct:.1f}%")
    print(f"  - Transcode Time: ~20-25 minutes")
    print()
    print("ALTERNATIVE APPROACHES:")
    print("-" * 50)
    print(f"Option 1 (Conservative): CRF {recommended_crf - 1}, Grain 18")
    print(f"  Expected VMAF: ~91-93%, Size: ~{estimated_size * 1.18:.0f} MB")
    print()
    print(f"Option 2 (Balanced): CRF {recommended_crf}, Grain 16")
    print(f"  Expected VMAF: ~90-91%, Size: ~{estimated_size:.0f} MB")
    print()
    print(f"Option 3 (Aggressive): CRF {recommended_crf + 1}, Grain 20")
    print(f"  Expected VMAF: ~89-90%, Size: ~{estimated_size * 0.85:.0f} MB")
    print()
    print("=" * 100)


if __name__ == "__main__":
    AnalyzeDexterTranscodes()




