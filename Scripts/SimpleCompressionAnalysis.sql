-- Simplified Compression Potential Analysis Query
-- Fixed syntax and focused on key compression factors

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
    
    -- Size-based compression potential
    CASE 
        WHEN mf.SizeMB > 2000 THEN 'Very High'
        WHEN mf.SizeMB > 1000 THEN 'High'
        WHEN mf.SizeMB > 500 THEN 'Medium'
        WHEN mf.SizeMB > 200 THEN 'Low'
        ELSE 'Very Low'
    END as SizePotential,
    
    -- Bitrate-based compression potential
    CASE 
        WHEN mf.VideoBitrateKbps > 15000 THEN 'Very High'
        WHEN mf.VideoBitrateKbps > 10000 THEN 'High'
        WHEN mf.VideoBitrateKbps > 5000 THEN 'Medium'
        WHEN mf.VideoBitrateKbps > 3000 THEN 'Low'
        ELSE 'Very Low'
    END as BitratePotential,
    
    -- Codec-based compression potential
    CASE 
        WHEN mf.Codec IN ('h264', 'avc', 'x264', 'mpeg4', 'divx', 'xvid', 'mpeg2video', 'mpeg2') THEN 'Very High'
        WHEN mf.Codec IN ('h265', 'hevc', 'x265', 'vp9', 'libvpx-vp9') THEN 'Medium'
        WHEN mf.Codec IN ('av1', 'libsvtav1', 'libaom-av1', 'vp8', 'libvpx') THEN 'Low'
        ELSE 'Medium'
    END as CodecPotential,
    
    -- Overall compression score (0-100)
    (
        CASE WHEN mf.SizeMB > 2000 THEN 25 WHEN mf.SizeMB > 1000 THEN 20 WHEN mf.SizeMB > 500 THEN 15 WHEN mf.SizeMB > 200 THEN 10 ELSE 5 END +
        CASE WHEN mf.VideoBitrateKbps > 15000 THEN 25 WHEN mf.VideoBitrateKbps > 10000 THEN 20 WHEN mf.VideoBitrateKbps > 5000 THEN 15 WHEN mf.VideoBitrateKbps > 3000 THEN 10 ELSE 5 END +
        CASE WHEN mf.Codec IN ('h264', 'avc', 'x264', 'mpeg4', 'divx', 'xvid', 'mpeg2video', 'mpeg2') THEN 25 WHEN mf.Codec IN ('h265', 'hevc', 'x265', 'vp9', 'libvpx-vp9') THEN 15 WHEN mf.Codec IN ('av1', 'libsvtav1', 'libaom-av1', 'vp8', 'libvpx') THEN 5 ELSE 15 END +
        CASE WHEN mf.Resolution LIKE '%4K%' OR mf.Resolution LIKE '%2160%' THEN 25 WHEN mf.Resolution LIKE '%1080%' OR mf.Resolution LIKE '%1920%' THEN 20 WHEN mf.Resolution LIKE '%720%' OR mf.Resolution LIKE '%1280%' THEN 15 WHEN mf.Resolution LIKE '%480%' OR mf.Resolution LIKE '%854%' THEN 10 ELSE 15 END
    ) as CompressionScore,
    
    -- Estimated space savings
    CASE 
        WHEN mf.SizeMB > 2000 AND mf.VideoBitrateKbps > 15000 AND mf.Codec IN ('h264', 'avc', 'x264', 'mpeg4', 'divx', 'xvid') THEN ROUND(mf.SizeMB * 0.5, 2)
        WHEN mf.SizeMB > 1000 AND mf.VideoBitrateKbps > 10000 AND mf.Codec IN ('h264', 'avc', 'x264', 'mpeg4', 'divx', 'xvid') THEN ROUND(mf.SizeMB * 0.45, 2)
        WHEN mf.SizeMB > 2000 AND mf.VideoBitrateKbps > 15000 THEN ROUND(mf.SizeMB * 0.35, 2)
        WHEN mf.SizeMB > 1000 AND mf.VideoBitrateKbps > 10000 THEN ROUND(mf.SizeMB * 0.3, 2)
        WHEN mf.SizeMB > 500 AND mf.VideoBitrateKbps > 5000 THEN ROUND(mf.SizeMB * 0.25, 2)
        WHEN mf.SizeMB > 200 AND mf.VideoBitrateKbps > 3000 THEN ROUND(mf.SizeMB * 0.2, 2)
        WHEN mf.SizeMB > 200 OR mf.VideoBitrateKbps > 3000 THEN ROUND(mf.SizeMB * 0.15, 2)
        WHEN mf.SizeMB > 100 THEN ROUND(mf.SizeMB * 0.1, 2)
        ELSE 0
    END as EstimatedSavingsMB,
    
    -- Processing status
    CASE 
        WHEN mf.TranscodedByMediaVortex = 1 THEN 'Already Transcoded'
        WHEN mf.AssignedProfile IS NOT NULL AND mf.AssignedProfile != 'Default' THEN 'Profile Assigned'
        ELSE 'Not Processed'
    END as ProcessingStatus

FROM MediaFiles mf
WHERE mf.SizeMB > 100
    AND mf.TranscodedByMediaVortex = 0
    AND (mf.AssignedProfile IS NULL OR mf.AssignedProfile = 'Default')
    AND mf.Codec IS NOT NULL
ORDER BY 
    CompressionScore DESC,
    mf.SizeMB DESC,
    mf.VideoBitrateKbps DESC
LIMIT 50;


