from typing import List, Dict, Any
from Core.Database.BaseRepository import BaseRepository
from Core.Logging.LoggingService import LoggingService
from Core.Path.Path import Path, PathError
from Core.Path.PathStorageRoots import GetPrefixMap


# directive: path-schema-migration | # see path.S8
def _Synth(Sid, Rel, PrefMap):
    """Render a canonical display string from a typed pair; empty string on missing/invalid input."""
    if Sid is None:
        return ''
    try:
        return Path(Sid, Rel or '').CanonicalDisplay(PrefMap)
    except PathError:
        return ''


# directive: path-schema-migration | # see path.S8
class ActivityRepository(BaseRepository):
    """Activity dashboard counts + recent-failure queries; typed-pair canonical."""

    # directive: path-schema-migration | # see path.S8
    def GetContainerFormatCounts(self) -> List[Dict[str, Any]]:
        """Get file counts grouped by container format."""
        query = (
            "SELECT COALESCE(ContainerFormat, 'unknown') as Format, COUNT(*) as Count "
            "FROM MediaFiles GROUP BY ContainerFormat ORDER BY Count DESC"
        )
        rows = self.DatabaseService.ExecuteQuery(query)
        return [{'Format': row['Format'], 'Count': row['Count']} for row in rows]

    # directive: path-schema-migration | # see path.S8
    def GetAudioCodecCounts(self) -> List[Dict[str, Any]]:
        """Get file counts grouped by audio codec."""
        query = (
            "SELECT COALESCE(AudioCodec, 'unknown') as Codec, COUNT(*) as Count "
            "FROM MediaFiles GROUP BY AudioCodec ORDER BY Count DESC"
        )
        rows = self.DatabaseService.ExecuteQuery(query)
        return [{'Codec': row['Codec'], 'Count': row['Count']} for row in rows]

    # directive: path-schema-migration | # see path.S8
    def GetSubtitleFormatCounts(self) -> List[Dict[str, Any]]:
        """Get file counts grouped by subtitle formats."""
        query = (
            "SELECT COALESCE(SubtitleFormats, 'none') as Formats, COUNT(*) as Count "
            "FROM MediaFiles GROUP BY SubtitleFormats ORDER BY Count DESC"
        )
        rows = self.DatabaseService.ExecuteQuery(query)
        return [{'Formats': row['Formats'], 'Count': row['Count']} for row in rows]

    # directive: path-schema-migration | # see path.S8
    def GetMkvFileCount(self) -> int:
        """Get count of MKV files (remux candidates)."""
        query = "SELECT COUNT(*) as Count FROM MediaFiles WHERE LOWER(ContainerFormat) LIKE '%%matroska%%'"
        rows = self.DatabaseService.ExecuteQuery(query)
        return rows[0]['Count'] if rows else 0

    # directive: path-schema-migration | # see path.S8
    def GetTotalMediaFileCount(self) -> int:
        """Get total count of all media files."""
        query = "SELECT COUNT(*) as Count FROM MediaFiles"
        rows = self.DatabaseService.ExecuteQuery(query)
        return rows[0]['Count'] if rows else 0

    # directive: path-schema-migration | # see path.S8
    def GetLegacyCodecFiles(self, Limit: int = 100) -> List[Dict[str, Any]]:
        """Get files with legacy codecs that need full transcode."""
        query = (
            "SELECT Id, StorageRootId, RelativePath, FileName, Codec, ContainerFormat, SizeMB, Resolution "
            "FROM MediaFiles "
            "WHERE LOWER(Codec) IN ('mpeg4', 'msmpeg4v3', 'msmpeg4v2', 'mpeg2video', 'wmv3', 'wmv2', 'wmv1', 'rv40', 'rv30', 'vp6f') "
            "ORDER BY SizeMB DESC "
            "LIMIT %s"
        )
        rows = self.DatabaseService.ExecuteQuery(query, (Limit,))
        PrefMap = GetPrefixMap()
        return [{'Id': r['Id'],
                 'FilePath': _Synth(r.get('StorageRootId'), r.get('RelativePath'), PrefMap),
                 'FileName': r['FileName'],
                 'Codec': r['Codec'], 'ContainerFormat': r['ContainerFormat'],
                 'SizeMB': r['SizeMB'], 'Resolution': r['Resolution']} for r in rows]

    # directive: path-schema-migration | # see path.S8
    def GetLegacyCodecCount(self) -> int:
        """Get count of files with legacy codecs."""
        query = (
            "SELECT COUNT(*) as Count FROM MediaFiles "
            "WHERE LOWER(Codec) IN ('mpeg4', 'msmpeg4v3', 'msmpeg4v2', 'mpeg2video', 'wmv3', 'wmv2', 'wmv1', 'rv40', 'rv30', 'vp6f')"
        )
        rows = self.DatabaseService.ExecuteQuery(query)
        return rows[0]['Count'] if rows else 0

    # directive: path-schema-migration | # see path.S8
    def GetIncompatibleAudioFiles(self, Limit: int = 100) -> List[Dict[str, Any]]:
        """Get files with audio codecs that may cause transcoding on playback."""
        query = (
            "SELECT Id, StorageRootId, RelativePath, FileName, AudioCodec, ContainerFormat, SizeMB, Resolution "
            "FROM MediaFiles "
            "WHERE LOWER(AudioCodec) IN ('dts', 'truehd', 'flac', 'pcm_s16le', 'pcm_s24le', 'pcm_s32le', 'pcm_f32le') "
            "ORDER BY SizeMB DESC "
            "LIMIT %s"
        )
        rows = self.DatabaseService.ExecuteQuery(query, (Limit,))
        PrefMap = GetPrefixMap()
        return [{'Id': r['Id'],
                 'FilePath': _Synth(r.get('StorageRootId'), r.get('RelativePath'), PrefMap),
                 'FileName': r['FileName'],
                 'AudioCodec': r['AudioCodec'], 'ContainerFormat': r['ContainerFormat'],
                 'SizeMB': r['SizeMB'], 'Resolution': r['Resolution']} for r in rows]

    # directive: path-schema-migration | # see path.S8
    def GetIncompatibleAudioCount(self) -> int:
        """Get count of files with incompatible audio codecs."""
        query = (
            "SELECT COUNT(*) as Count FROM MediaFiles "
            "WHERE LOWER(AudioCodec) IN ('dts', 'truehd', 'flac', 'pcm_s16le', 'pcm_s24le', 'pcm_s32le', 'pcm_f32le')"
        )
        rows = self.DatabaseService.ExecuteQuery(query)
        return rows[0]['Count'] if rows else 0

    # directive: path-schema-migration | # see path.S8
    def GetProblematicSubtitleFiles(self, Limit: int = 100) -> List[Dict[str, Any]]:
        """Get files with subtitle formats that force burn-in transcoding."""
        query = (
            "SELECT Id, StorageRootId, RelativePath, FileName, SubtitleFormats, ContainerFormat, SizeMB, Resolution "
            "FROM MediaFiles "
            "WHERE SubtitleFormats IS NOT NULL AND SubtitleFormats != '' "
            "  AND (LOWER(SubtitleFormats) LIKE '%%ass%%' OR LOWER(SubtitleFormats) LIKE '%%ssa%%' "
            "       OR LOWER(SubtitleFormats) LIKE '%%hdmv_pgs%%' OR LOWER(SubtitleFormats) LIKE '%%pgssub%%' "
            "       OR LOWER(SubtitleFormats) LIKE '%%dvd_subtitle%%' OR LOWER(SubtitleFormats) LIKE '%%dvdsub%%') "
            "ORDER BY SizeMB DESC "
            "LIMIT %s"
        )
        rows = self.DatabaseService.ExecuteQuery(query, (Limit,))
        PrefMap = GetPrefixMap()
        return [{'Id': r['Id'],
                 'FilePath': _Synth(r.get('StorageRootId'), r.get('RelativePath'), PrefMap),
                 'FileName': r['FileName'],
                 'SubtitleFormats': r['SubtitleFormats'], 'ContainerFormat': r['ContainerFormat'],
                 'SizeMB': r['SizeMB'], 'Resolution': r['Resolution']} for r in rows]

    # directive: path-schema-migration | # see path.S8
    def GetProblematicSubtitleCount(self) -> int:
        """Get count of files with problematic subtitle formats."""
        query = (
            "SELECT COUNT(*) as Count FROM MediaFiles "
            "WHERE SubtitleFormats IS NOT NULL AND SubtitleFormats != '' "
            "  AND (LOWER(SubtitleFormats) LIKE '%%ass%%' OR LOWER(SubtitleFormats) LIKE '%%ssa%%' "
            "       OR LOWER(SubtitleFormats) LIKE '%%hdmv_pgs%%' OR LOWER(SubtitleFormats) LIKE '%%pgssub%%' "
            "       OR LOWER(SubtitleFormats) LIKE '%%dvd_subtitle%%' OR LOWER(SubtitleFormats) LIKE '%%dvdsub%%')"
        )
        rows = self.DatabaseService.ExecuteQuery(query)
        return rows[0]['Count'] if rows else 0

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C20
    def GetComplianceBreakdown(self) -> Dict[str, int]:
        """Return {Total, CompliantTrue, CompliantFalse, CompliantNull} from MediaFiles."""
        Rows = self.DatabaseService.ExecuteQuery(
            "SELECT COUNT(*) AS Total, "
            "SUM(CASE WHEN IsCompliant IS TRUE THEN 1 ELSE 0 END) AS CompliantTrue, "
            "SUM(CASE WHEN IsCompliant IS FALSE THEN 1 ELSE 0 END) AS CompliantFalse, "
            "SUM(CASE WHEN IsCompliant IS NULL THEN 1 ELSE 0 END) AS CompliantNull "
            "FROM MediaFiles"
        )
        return dict(Rows[0]) if Rows else {}

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C20
    def GetWorkBucketBreakdown(self) -> Dict[str, int]:
        """Return per-WorkBucket counts mapped to legacy Mode-breakdown keys (Transcode/Remux/AudioFix/SubtitleFix/NoMode) so the existing UI renders unchanged."""
        Rows = self.DatabaseService.ExecuteQuery(
            "SELECT "
            "SUM(CASE WHEN WorkBucket = 'Transcode' THEN 1 ELSE 0 END) AS Transcode, "
            "SUM(CASE WHEN WorkBucket = 'Remux' THEN 1 ELSE 0 END) AS Remux, "
            "SUM(CASE WHEN WorkBucket = 'AudioFixOnly' THEN 1 ELSE 0 END) AS AudioFix, "
            "SUM(CASE WHEN WorkBucket = 'SubtitleFixOnly' THEN 1 ELSE 0 END) AS SubtitleFix, "
            "SUM(CASE WHEN WorkBucket IS NULL AND IsCompliant IS FALSE THEN 1 ELSE 0 END) AS NoMode "
            "FROM MediaFiles"
        )
        return dict(Rows[0]) if Rows else {}

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C20
    def GetAudioCompleteBreakdown(self) -> Dict[str, int]:
        """Return {AudioTrue, AudioFalse, AudioNull} from MediaFiles.AudioComplete."""
        Rows = self.DatabaseService.ExecuteQuery(
            "SELECT "
            "SUM(CASE WHEN AudioComplete IS TRUE THEN 1 ELSE 0 END) AS AudioTrue, "
            "SUM(CASE WHEN AudioComplete IS FALSE THEN 1 ELSE 0 END) AS AudioFalse, "
            "SUM(CASE WHEN AudioComplete IS NULL THEN 1 ELSE 0 END) AS AudioNull "
            "FROM MediaFiles"
        )
        return dict(Rows[0]) if Rows else {}

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C20
    def GetSuspectByReason(self) -> Dict[str, int]:
        """Return {reason: count} for MediaFiles flagged AudioCorruptSuspect."""
        Rows = self.DatabaseService.ExecuteQuery(
            "SELECT COALESCE(AudioCorruptReason, 'unspecified') AS Reason, COUNT(*) AS N "
            "FROM MediaFiles WHERE AudioCorruptSuspect = TRUE GROUP BY 1 ORDER BY 2 DESC"
        )
        return {R['Reason']: R['N'] for R in Rows}

    # directive: audio-vertical-compliance-and-activity | # see audio-normalization.C6
    def GetAudioNormalizationBreakdown(self) -> Dict[str, int]:
        """Return per-AdmissionDeferReason counts owned by the audio-normalization vertical."""
        Rows = self.DatabaseService.ExecuteQuery(
            "SELECT "
            "SUM(CASE WHEN AdmissionDeferReason IS NULL THEN 1 ELSE 0 END) AS Admitted, "
            "SUM(CASE WHEN AdmissionDeferReason = 'invalid_loudness_measurement' THEN 1 ELSE 0 END) AS InvalidMeasurement, "
            "SUM(CASE WHEN AdmissionDeferReason = 'ungainable_all_streams' THEN 1 ELSE 0 END) AS Ungainable, "
            "SUM(CASE WHEN AdmissionDeferReason = 'operator_review_pending' THEN 1 ELSE 0 END) AS OperatorReview, "
            "SUM(CASE WHEN AdmissionDeferReason = 'awaiting_speech_enrichment' THEN 1 ELSE 0 END) AS AwaitingSpeech, "
            "SUM(CASE WHEN AdmissionDeferReason IS NOT NULL AND AdmissionDeferReason NOT IN ('invalid_loudness_measurement', 'ungainable_all_streams', 'operator_review_pending', 'awaiting_speech_enrichment') THEN 1 ELSE 0 END) AS OtherDeferred "
            "FROM MediaFiles"
        )
        return dict(Rows[0]) if Rows else {}

    # directive: audio-vertical-compliance-and-activity | # see audio-normalization.C15
    def GetAudioConsistencyBands(self) -> List[Dict]:
        """Return v_audio_consistency_summary rows for the Activity dashboard."""
        Rows = self.DatabaseService.ExecuteQuery(
            "SELECT LibraryId, UniformCount, AcceptableCount, DeviantCount, TotalCount "
            "FROM v_audio_consistency_summary ORDER BY LibraryId"
        )
        return [dict(R) for R in Rows] if Rows else []

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C20
    def GetLoudnessBreakdown(self) -> Dict[str, int]:
        """Return {Measured, Unmeasured, OnTarget, OffTarget, WideLRA} loudness distribution."""
        Rows = self.DatabaseService.ExecuteQuery(
            "SELECT "
            "SUM(CASE WHEN LoudnessMeasuredAt IS NOT NULL AND SourceIntegratedLufs IS NOT NULL THEN 1 ELSE 0 END) AS Measured, "
            "SUM(CASE WHEN LoudnessMeasuredAt IS NULL THEN 1 ELSE 0 END) AS Unmeasured, "
            "SUM(CASE WHEN SourceIntegratedLufs BETWEEN -24 AND -22 THEN 1 ELSE 0 END) AS OnTarget, "
            "SUM(CASE WHEN SourceIntegratedLufs IS NOT NULL AND (SourceIntegratedLufs > -20 OR SourceIntegratedLufs < -26) THEN 1 ELSE 0 END) AS OffTarget, "
            "SUM(CASE WHEN SourceLoudnessRangeLU > 18 THEN 1 ELSE 0 END) AS WideLRA "
            "FROM MediaFiles"
        )
        return dict(Rows[0]) if Rows else {}

    # directive: path-schema-migration | # see path.S8
    def GetVideoCodecCounts(self) -> List[Dict[str, Any]]:
        """Get file counts grouped by video codec."""
        query = (
            "SELECT COALESCE(Codec, 'unknown') as Codec, COUNT(*) as Count "
            "FROM MediaFiles GROUP BY Codec ORDER BY Count DESC"
        )
        rows = self.DatabaseService.ExecuteQuery(query)
        return [{'Codec': row['Codec'], 'Count': row['Count']} for row in rows]

    # directive: path-schema-migration | # see path.S8
    def GetJobCounts(self) -> Dict[str, int]:
        """Get job counts by status."""
        try:
            LoggingService.LogFunctionEntry("GetJobCounts", "ActivityRepository")
            query = (
                "SELECT Status, COUNT(*) as Count "
                "FROM TranscodeQueue "
                "GROUP BY Status"
            )
            rows = self.DatabaseService.ExecuteQuery(query)
            counts = {}
            for row in rows:
                counts[row['Status']] = row['Count']
            LoggingService.LogInfo(f"Job counts: {counts}", "ActivityRepository", "GetJobCounts")
            return counts
        except Exception as e:
            LoggingService.LogException("Exception in GetJobCounts", e, "ActivityRepository", "GetJobCounts")
            return {}

    # directive: path-schema-migration | # see path.S8
    def GetFailedFileReplacements(self, Limit: int = 20) -> List[Dict[str, Any]]:
        """Get transcoded files that passed VMAF but may have failed file replacement."""
        try:
            LoggingService.LogFunctionEntry("GetFailedFileReplacements", "ActivityRepository", Limit)
            query = (
                "SELECT ta.Id, "
                "       ta.StorageRootId AS TaStorageRootId, ta.RelativePath AS TaRelativePath, "
                "       ta.VMAF, ta.AttemptDate, ta.Success, "
                "       tfp.OutputStorageRootId AS TfpOutSid, tfp.OutputRelativePath AS TfpOutRel, "
                "       qtr.Status AS VMAFStatus "
                "FROM TranscodeAttempts ta "
                "INNER JOIN TemporaryFilePaths tfp ON ta.Id = tfp.TranscodeAttemptId "
                "INNER JOIN QualityTestResults qtr ON ta.Id = qtr.TranscodeAttemptId "
                "WHERE ta.VMAF IS NOT NULL "
                "AND ta.VMAF >= 90 "
                "AND ta.Success = TRUE "
                "AND tfp.OutputRelativePath IS NOT NULL "
                "AND qtr.Status = 'Success' "
                "AND ta.QualityTestRequired = TRUE "
                "AND qtr.DateTested IS NOT NULL "
                "ORDER BY ta.AttemptDate DESC "
                "LIMIT %s"
            )
            Rows = self.DatabaseService.ExecuteQuery(query, (Limit,))
            PrefMap = GetPrefixMap()
            Results = []
            for Row in Rows:
                Results.append({
                    "Id": Row["Id"],
                    "FilePath": _Synth(Row.get("TaStorageRootId"), Row.get("TaRelativePath"), PrefMap),
                    "VMAF": Row["VMAF"],
                    "AttemptDate": Row["AttemptDate"],
                    "Success": Row["Success"],
                    "TranscodedFilePath": _Synth(Row.get("TfpOutSid"), Row.get("TfpOutRel"), PrefMap),
                    "VMAFStatus": Row["VMAFStatus"]
                })
            LoggingService.LogInfo(f"Found {len(Results)} failed file replacements", "ActivityRepository", "GetFailedFileReplacements")
            return Results
        except Exception as e:
            LoggingService.LogException("Exception getting failed file replacements", e, "ActivityRepository", "GetFailedFileReplacements")
            return []
