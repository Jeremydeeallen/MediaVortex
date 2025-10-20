-- Enhanced Compression Potential Analysis Query
-- This query identifies files with the best compression potential considering:
-- - File size and bitrate
-- - Codec efficiency and compression potential
-- - Resolution and duration factors
-- - Processing status

SELECT 
    mf.Id,
    mf.FilePath,
    mf.FileName,
    mf.SizeMB,
    mf.VideoBitrateKbps,
    mf.AudioBitrateKbps,
    mf.Resolution,
    mf.Codec,
    mf.DurationMinutes,
    mf.FrameRate,
    mf.OverallBitrate,
    mf.AssignedProfile,
    mf.TranscodedByMediaVortex,
    mf.CodecProfile,
    mf.PixelFormat,
    mf.HasBFrames,
    mf.RefFrames,
    
    -- Calculate size-based compression potential
    CASE 
        WHEN mf.SizeMB > 2000 THEN 'Very High'  -- > 2GB files
        WHEN mf.SizeMB > 1000 THEN 'High'       -- > 1GB files
        WHEN mf.SizeMB > 500 THEN 'Medium'     -- > 500MB files
        WHEN mf.SizeMB > 200 THEN 'Low'         -- > 200MB files
        ELSE 'Very Low'
    END as SizeBasedPotential,
    
    -- Calculate bitrate-based compression potential
    CASE 
        WHEN mf.VideoBitrateKbps > 15000 THEN 'Very High'  -- > 15 Mbps
        WHEN mf.VideoBitrateKbps > 10000 THEN 'High'      -- > 10 Mbps
        WHEN mf.VideoBitrateKbps > 5000 THEN 'Medium'     -- > 5 Mbps
        WHEN mf.VideoBitrateKbps > 3000 THEN 'Low'        -- > 3 Mbps
        ELSE 'Very Low'
    END as BitrateBasedPotential,
    
    -- Calculate codec-based compression potential
    CASE 
        -- High compression potential codecs (older, less efficient)
        WHEN mf.Codec IN ('h264', 'avc', 'x264') THEN 'Very High'
        WHEN mf.Codec IN ('mpeg4', 'divx', 'xvid') THEN 'Very High'
        WHEN mf.Codec IN ('mpeg2video', 'mpeg2') THEN 'Very High'
        
        -- Medium compression potential codecs
        WHEN mf.Codec IN ('h265', 'hevc', 'x265') THEN 'Medium'
        WHEN mf.Codec IN ('vp9', 'libvpx-vp9') THEN 'Medium'
        
        -- Low compression potential codecs (already efficient)
        WHEN mf.Codec IN ('av1', 'libsvtav1', 'libaom-av1') THEN 'Low'
        WHEN mf.Codec IN ('vp8', 'libvpx') THEN 'Low'
        
        -- Unknown codecs get medium potential
        ELSE 'Medium'
    END as CodecBasedPotential,
    
    -- Calculate resolution-based compression potential
    CASE 
        WHEN mf.Resolution LIKE '%4K%' OR mf.Resolution LIKE '%2160%' THEN 'Very High'
        WHEN mf.Resolution LIKE '%1080%' OR mf.Resolution LIKE '%1920%' THEN 'High'
        WHEN mf.Resolution LIKE '%720%' OR mf.Resolution LIKE '%1280%' THEN 'Medium'
        WHEN mf.Resolution LIKE '%480%' OR mf.Resolution LIKE '%854%' THEN 'Low'
        ELSE 'Medium'
    END as ResolutionBasedPotential,
    
    -- Calculate overall compression potential score (0-100)
    (
        -- Size factor (0-25 points)
        CASE 
            WHEN mf.SizeMB > 2000 THEN 25
            WHEN mf.SizeMB > 1000 THEN 20
            WHEN mf.SizeMB > 500 THEN 15
            WHEN mf.SizeMB > 200 THEN 10
            ELSE 5
        END +
        
        -- Bitrate factor (0-25 points)
        CASE 
            WHEN mf.VideoBitrateKbps > 15000 THEN 25
            WHEN mf.VideoBitrateKbps > 10000 THEN 20
            WHEN mf.VideoBitrateKbps > 5000 THEN 15
            WHEN mf.VideoBitrateKbps > 3000 THEN 10
            ELSE 5
        END +
        
        -- Codec factor (0-25 points)
        CASE 
            WHEN mf.Codec IN ('h264', 'avc', 'x264', 'mpeg4', 'divx', 'xvid', 'mpeg2video', 'mpeg2') THEN 25
            WHEN mf.Codec IN ('h265', 'hevc', 'x265', 'vp9', 'libvpx-vp9') THEN 15
            WHEN mf.Codec IN ('av1', 'libsvtav1', 'libaom-av1', 'vp8', 'libvpx') THEN 5
            ELSE 15
        END +
        
        -- Resolution factor (0-25 points)
        CASE 
            WHEN mf.Resolution LIKE '%4K%' OR mf.Resolution LIKE '%2160%' THEN 25
            WHEN mf.Resolution LIKE '%1080%' OR mf.Resolution LIKE '%1920%' THEN 20
            WHEN mf.Resolution LIKE '%720%' OR mf.Resolution LIKE '%1280%' THEN 15
            WHEN mf.Resolution LIKE '%480%' OR mf.Resolution LIKE '%854%' THEN 10
            ELSE 15
        END
    ) as CompressionScore,
    
    -- Calculate estimated space savings based on multiple factors
    CASE 
        -- Very high potential: 40-60% reduction
        WHEN mf.SizeMB > 2000 AND mf.VideoBitrateKbps > 15000 AND mf.Codec IN ('h264', 'avc', 'x264', 'mpeg4', 'divx', 'xvid') THEN ROUND(mf.SizeMB * 0.5, 2)
        WHEN mf.SizeMB > 1000 AND mf.VideoBitrateKbps > 10000 AND mf.Codec IN ('h264', 'avc', 'x264', 'mpeg4', 'divx', 'xvid') THEN ROUND(mf.SizeMB * 0.45, 2)
        
        -- High potential: 30-40% reduction
        WHEN mf.SizeMB > 2000 AND mf.VideoBitrateKbps > 15000 THEN ROUND(mf.SizeMB * 0.35, 2)
        WHEN mf.SizeMB > 1000 AND mf.VideoBitrateKbps > 10000 THEN ROUND(mf.SizeMB * 0.3, 2)
        WHEN mf.SizeMB > 500 AND mf.VideoBitrateKbps > 5000 AND mf.Codec IN ('h264', 'avc', 'x264', 'mpeg4', 'divx', 'xvid') THEN ROUND(mf.SizeMB * 0.35, 2)
        
        -- Medium potential: 20-30% reduction
        WHEN mf.SizeMB > 500 AND mf.VideoBitrateKbps > 5000 THEN ROUND(mf.SizeMB * 0.25, 2)
        WHEN mf.SizeMB > 200 AND mf.VideoBitrateKbps > 3000 THEN ROUND(mf.SizeMB * 0.2, 2)
        
        -- Low potential: 10-20% reduction
        WHEN mf.SizeMB > 200 OR mf.VideoBitrateKbps > 3000 THEN ROUND(mf.SizeMB * 0.15, 2)
        WHEN mf.SizeMB > 100 THEN ROUND(mf.SizeMB * 0.1, 2)
        
        -- Very low potential
        ELSE 0
    END as EstimatedSpaceSavingsMB,
    
    -- Calculate potential savings percentage
    CASE 
        WHEN mf.SizeMB > 0 THEN
            ROUND(
                (CASE 
                    WHEN mf.SizeMB > 2000 AND mf.VideoBitrateKbps > 15000 AND mf.Codec IN ('h264', 'avc', 'x264', 'mpeg4', 'divx', 'xvid') THEN 50
                    WHEN mf.SizeMB > 1000 AND mf.VideoBitrateKbps > 10000 AND mf.Codec IN ('h264', 'avc', 'x264', 'mpeg4', 'divx', 'xvid') THEN 45
                    WHEN mf.SizeMB > 2000 AND mf.VideoBitrateKbps > 15000 THEN 35
                    WHEN mf.SizeMB > 1000 AND mf.VideoBitrateKbps > 10000 THEN 30
                    WHEN mf.SizeMB > 500 AND mf.VideoBitrateKbps > 5000 AND mf.Codec IN ('h264', 'avc', 'x264', 'mpeg4', 'divx', 'xvid') THEN 35
                    WHEN mf.SizeMB > 500 AND mf.VideoBitrateKbps > 5000 THEN 25
                    WHEN mf.SizeMB > 200 AND mf.VideoBitrateKbps > 3000 THEN 20
                    WHEN mf.SizeMB > 200 OR mf.VideoBitrateKbps > 3000 THEN 15
                    WHEN mf.SizeMB > 100 THEN 10
                    ELSE 0
                END), 1
            )
        ELSE 0
    END as EstimatedSavingsPercent,
    
    -- Check processing status
    CASE 
        WHEN mf.TranscodedByMediaVortex = 1 THEN 'Already Transcoded'
        WHEN mf.AssignedProfile IS NOT NULL AND mf.AssignedProfile != 'Default' THEN 'Profile Assigned'
        ELSE 'Not Processed'
    END as ProcessingStatus,
    
    -- Calculate priority score for queue ordering
    (
        -- Size priority (0-30 points)
        CASE 
            WHEN mf.SizeMB > 2000 THEN 30
            WHEN mf.SizeMB > 1000 THEN 25
            WHEN mf.SizeMB > 500 THEN 20
            WHEN mf.SizeMB > 200 THEN 15
            WHEN mf.SizeMB > 100 THEN 10
            ELSE 5
        END +
        
        -- Duration priority (0-20 points)
        CASE 
            WHEN mf.DurationMinutes > 120 THEN 20
            WHEN mf.DurationMinutes > 60 THEN 15
            WHEN mf.DurationMinutes > 30 THEN 10
            WHEN mf.DurationMinutes > 15 THEN 5
            ELSE 0
        END +
        
        -- Codec efficiency priority (0-25 points)
        CASE 
            WHEN mf.Codec IN ('h264', 'avc', 'x264', 'mpeg4', 'divx', 'xvid', 'mpeg2video', 'mpeg2') THEN 25
            WHEN mf.Codec IN ('h265', 'hevc', 'x265', 'vp9', 'libvpx-vp9') THEN 15
            WHEN mf.Codec IN ('av1', 'libsvtav1', 'libaom-av1', 'vp8', 'libvpx') THEN 5
            ELSE 15
        END +
        
        -- Bitrate priority (0-25 points)
        CASE 
            WHEN mf.VideoBitrateKbps > 15000 THEN 25
            WHEN mf.VideoBitrateKbps > 10000 THEN 20
            WHEN mf.VideoBitrateKbps > 5000 THEN 15
            WHEN mf.VideoBitrateKbps > 3000 THEN 10
            ELSE 5
        END
    ) as PriorityScore

FROM MediaFiles mf
WHERE mf.SizeMB > 100  -- Only files larger than 100MB
    AND mf.TranscodedByMediaVortex = 0  -- Not already transcoded
    AND (mf.AssignedProfile IS NULL OR mf.AssignedProfile = 'Default')  -- Not manually assigned
    AND mf.Codec IS NOT NULL  -- Must have codec information
ORDER BY 
    PriorityScore DESC,  -- Highest priority first
    CompressionScore DESC,  -- Highest compression potential first
    mf.SizeMB DESC,  -- Largest files first
    mf.VideoBitrateKbps DESC,  -- Highest bitrates first
    mf.DurationMinutes DESC  -- Longest duration first
LIMIT 50;


