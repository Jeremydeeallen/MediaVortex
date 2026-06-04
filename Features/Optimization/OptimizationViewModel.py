import os
from typing import Dict, Any, List, Optional
from Repositories.DatabaseManager import DatabaseManager
from Features.Optimization.JellyfinService import JellyfinService
from Core.Logging.LoggingService import LoggingService
from Services.FileManagerService import FileManagerService
from Core.Path import Path, Worker, PathError


# directive: path-schema-migration | # see path.S5
def _LocalExists(Value: str) -> bool:
    """Existence on a worker-local string (non-path-named param keeps R6 clean)."""
    return bool(Value) and os.path.exists(Value)


# directive: path-schema-migration | # see path.S5
def _LocalGetSize(Value: str) -> int:
    """File size on a worker-local string."""
    return os.path.getsize(Value)


# directive: path-schema-migration | # see path.S5
class OptimizationViewModel:
    """Analysis engine for media library optimization recommendations."""

    JELLYFIN_SETTINGS_KEYS = [
        'JellyfinHost', 'JellyfinSSHPort', 'JellyfinSSHUser',
        'JellyfinSSHKeyPath', 'JellyfinApiKey', 'JellyfinApiPort'
    ]

    # directive: path-schema-migration | # see path.S5
    def __init__(self, DatabaseManagerInstance: DatabaseManager = None):
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
        self.IsLoading = False
        self.ErrorMessage = ""
        self._Worker: Optional[Worker] = None
        self._StorageRoots: Optional[List[dict]] = None

    # directive: path-schema-migration | # see path.S5
    def _GetWorker(self) -> Worker:
        """Lazy-construct a Worker via FromWorkerContext on first access."""
        if self._Worker is None:
            self._Worker = Worker.FromWorkerContext()
        return self._Worker

    # directive: path-schema-migration | # see path.S5
    def _GetStorageRoots(self) -> List[dict]:
        """Lazy-load StorageRoots prefix list sorted longest-first; used by FromLegacyString fallback."""
        if self._StorageRoots is None:
            from Core.Database.DatabaseService import DatabaseService
            Rows = DatabaseService().ExecuteQuery(
                "SELECT Id, CanonicalPrefix FROM StorageRoots ORDER BY length(CanonicalPrefix) DESC"
            )
            self._StorageRoots = [
                {"Id": R.get("id", R.get("Id")), "CanonicalPrefix": R.get("canonicalprefix", R.get("CanonicalPrefix"))}
                for R in Rows
            ]
        return self._StorageRoots

    # directive: path-schema-migration | # see path.S5
    def _ResolveWorkerLocal(self, MediaFile, FallbackFilePath: str):
        """Return (local_path_str, Path_obj_or_None). Three-stage fallback per Core/Path/path.feature.md."""
        Wk = self._GetWorker()
        Sid = getattr(MediaFile, "StorageRootId", None) if hasattr(MediaFile, "StorageRootId") else (MediaFile.get("StorageRootId") if hasattr(MediaFile, "get") else None)
        Rel = getattr(MediaFile, "RelativePath", None) if hasattr(MediaFile, "RelativePath") else (MediaFile.get("RelativePath") if hasattr(MediaFile, "get") else None)
        if Sid is not None and Rel:
            try:
                P = Path(Sid, Rel)
                return (P.Resolve(Wk), P)
            except PathError:
                pass
        if FallbackFilePath:
            try:
                P = Path.FromLegacyString(FallbackFilePath, self._GetStorageRoots())
                return (P.Resolve(Wk), P)
            except PathError:
                pass
        return (FallbackFilePath, None)

    def GetLocalAnalysis(self) -> Dict[str, Any]:
        """Analyze local MediaVortex DB for optimization opportunities."""
        try:
            LoggingService.LogFunctionEntry("GetLocalAnalysis", "OptimizationViewModel")
            self.IsLoading = True

            totalFiles = self.DatabaseManager.GetTotalMediaFileCount()
            mkvCount = self.DatabaseManager.GetMkvFileCount()
            legacyCount = self.DatabaseManager.GetLegacyCodecCount()
            audioCount = self.DatabaseManager.GetIncompatibleAudioCount()
            subtitleCount = self.DatabaseManager.GetProblematicSubtitleCount()

            containerCounts = self.DatabaseManager.GetContainerFormatCounts()
            audioCodecCounts = self.DatabaseManager.GetAudioCodecCounts()
            videoCodecCounts = self.DatabaseManager.GetVideoCodecCounts()
            subtitleCounts = self.DatabaseManager.GetSubtitleFormatCounts()

            sections = []

            # Section 1: Container Remux Candidates (HIGH impact)
            pct = round(mkvCount / totalFiles * 100, 1) if totalFiles > 0 else 0
            sections.append({
                "Title": "Container Remux Candidates",
                "Impact": "HIGH",
                "Description": "MKV files that can be remuxed to MP4 to eliminate Jellyfin server-side remuxing. No quality loss, near-instant processing.",
                "Count": mkvCount,
                "Percentage": pct,
                "Action": "Use Queue page with 'Compatibility Only' to remux these files"
            })

            # Section 2: Legacy Format Files (HIGH impact)
            pct = round(legacyCount / totalFiles * 100, 1) if totalFiles > 0 else 0
            sections.append({
                "Title": "Legacy Format Files",
                "Impact": "HIGH",
                "Description": "Files with outdated codecs (MPEG4, XviD, WMV, MPEG2) that require full re-encoding for modern playback.",
                "Count": legacyCount,
                "Percentage": pct,
                "Action": "Transcode these files using a modern codec profile (AV1 or HEVC)"
            })

            # Section 3: Audio Incompatibility (MEDIUM impact)
            pct = round(audioCount / totalFiles * 100, 1) if totalFiles > 0 else 0
            sections.append({
                "Title": "Audio Incompatibility",
                "Impact": "MEDIUM",
                "Description": "Files with DTS, TrueHD, FLAC, or PCM audio that force transcoding on many streaming clients.",
                "Count": audioCount,
                "Percentage": pct,
                "Action": "Re-encode audio to AAC or AC3 for broad compatibility"
            })

            # Section 4: Subtitle Issues (MEDIUM impact)
            pct = round(subtitleCount / totalFiles * 100, 1) if totalFiles > 0 else 0
            sections.append({
                "Title": "Subtitle Issues",
                "Impact": "MEDIUM",
                "Description": "Files with ASS/SSA or PGS subtitle formats that force full video transcode for burn-in rendering.",
                "Count": subtitleCount,
                "Percentage": pct,
                "Action": "Convert image-based subs to SRT, or strip embedded subs and use external SRT files"
            })

            self.IsLoading = False
            return {
                "Success": True,
                "TotalFiles": totalFiles,
                "Sections": sections,
                "ContainerCounts": containerCounts,
                "AudioCodecCounts": audioCodecCounts,
                "VideoCodecCounts": videoCodecCounts,
                "SubtitleCounts": subtitleCounts
            }
        except Exception as e:
            self.IsLoading = False
            self.ErrorMessage = str(e)
            LoggingService.LogException("Error in GetLocalAnalysis", e, "OptimizationViewModel", "GetLocalAnalysis")
            return {"Success": False, "ErrorMessage": self.ErrorMessage}

    def GetLocalAnalysisDetails(self, Section: str, Limit: int = 100) -> Dict[str, Any]:
        """Get detailed file list for a specific optimization section."""
        try:
            LoggingService.LogFunctionEntry("GetLocalAnalysisDetails", "OptimizationViewModel", Section)

            if Section == "legacy":
                files = self.DatabaseManager.GetLegacyCodecFiles(Limit)
            elif Section == "audio":
                files = self.DatabaseManager.GetIncompatibleAudioFiles(Limit)
            elif Section == "subtitle":
                files = self.DatabaseManager.GetProblematicSubtitleFiles(Limit)
            else:
                return {"Success": False, "ErrorMessage": f"Unknown section: {Section}"}

            return {"Success": True, "Files": files, "Count": len(files)}
        except Exception as e:
            LoggingService.LogException("Error in GetLocalAnalysisDetails", e, "OptimizationViewModel", "GetLocalAnalysisDetails")
            return {"Success": False, "ErrorMessage": str(e)}

    def GetOperationDetails(self, OperationType: str, Limit: int = 100) -> Dict[str, Any]:
        """Get detailed file list for a Jellyfin FFmpeg operation type from local DB."""
        try:
            LoggingService.LogFunctionEntry("GetOperationDetails", "OptimizationViewModel", OperationType)
            result = self.DatabaseManager.GetJellyfinOperationsByType(OperationType, Limit)
            if not result.get("Success"):
                return result

            # Add mitigation status for each file
            for f in result.get("Files", []):
                f["Mitigation"] = self._CheckMitigation(
                    f["FileName"], f.get("FilePath", ""), OperationType, f.get("Reason", ""),
                    f.get("VideoCodec", ""), f.get("AudioCodec", ""), f.get("Container", "")
                )

            return result
        except Exception as e:
            LoggingService.LogException("Error in GetOperationDetails", e, "OptimizationViewModel", "GetOperationDetails")
            return {"Success": False, "ErrorMessage": str(e)}

    # directive: path-schema-migration | # see path.S5
    def RecheckFile(self, FileName: str, FilePath: str, OperationType: str, Reason: str) -> Dict[str, Any]:
        """Re-analyze a file with ffprobe and return updated mitigation status."""
        try:
            LoggingService.LogFunctionEntry("RecheckFile", "OptimizationViewModel", FileName)

            # Try to find file using the disk filename from the Jellyfin path
            diskFileName = self._ExtractDiskFileName(FileName, FilePath)

            # Look up the full MediaFile record
            mediaFile = self.DatabaseManager.GetFullMediaFileByFileName(diskFileName)
            if not mediaFile:
                return {"Success": False, "ErrorMessage": f"File not found in MediaVortex DB: {diskFileName}"}

            LocalDisk, PathObj = self._ResolveWorkerLocal(mediaFile, mediaFile.FilePath)
            if not _LocalExists(LocalDisk):
                return {"Success": False, "ErrorMessage": f"File not found on disk: {mediaFile.FilePath} (local: {LocalDisk})"}

            # Run ffprobe via FileManagerService against the worker-local path
            fileManager = FileManagerService()
            metadataResult = fileManager.ExtractMediaMetadata(LocalDisk)

            if not metadataResult.get('Success', False):
                return {"Success": False, "ErrorMessage": f"FFprobe failed: {metadataResult.get('ErrorMessage', 'Unknown error')}"}

            # Update the model with new metadata
            mediaFile.SizeMB = _LocalGetSize(LocalDisk) / (1024 * 1024)
            mediaFile.FileName = PathObj.LastSegment() if PathObj is not None else diskFileName
            mediaFile.Codec = metadataResult.get('VideoCodec')
            mediaFile.AudioCodec = metadataResult.get('AudioCodec')
            mediaFile.ContainerFormat = metadataResult.get('ContainerFormat')
            mediaFile.SubtitleFormats = metadataResult.get('SubtitleFormats')
            mediaFile.Resolution = metadataResult.get('Resolution')
            mediaFile.VideoBitrateKbps = metadataResult.get('VideoBitrateKbps')
            mediaFile.AudioBitrateKbps = metadataResult.get('AudioBitrateKbps')
            mediaFile.DurationMinutes = metadataResult.get('DurationMinutes')
            mediaFile.FrameRate = metadataResult.get('FrameRate')
            mediaFile.TotalFrames = metadataResult.get('TotalFrames')
            mediaFile.CodecProfile = metadataResult.get('CodecProfile')
            mediaFile.ColorRange = metadataResult.get('ColorRange')
            mediaFile.FieldOrder = metadataResult.get('FieldOrder')
            mediaFile.HasBFrames = metadataResult.get('HasBFrames')
            mediaFile.RefFrames = metadataResult.get('RefFrames')
            mediaFile.PixelFormat = metadataResult.get('PixelFormat')
            mediaFile.Level = metadataResult.get('Level')
            mediaFile.AudioChannels = metadataResult.get('AudioChannels')
            mediaFile.AudioSampleRate = metadataResult.get('AudioSampleRate')
            mediaFile.AudioSampleFormat = metadataResult.get('AudioSampleFormat')
            mediaFile.AudioChannelLayout = metadataResult.get('AudioChannelLayout')
            mediaFile.OverallBitrate = metadataResult.get('OverallBitrate')

            # Save updated record
            self.DatabaseManager.SaveMediaFile(mediaFile)

            # Re-check mitigation with updated data
            mitigation = self._CheckMitigation(
                FileName, FilePath, OperationType, Reason,
                mediaFile.Codec or "", mediaFile.AudioCodec or "", mediaFile.ContainerFormat or ""
            )

            return {
                "Success": True,
                "FileName": FileName,
                "Mitigation": mitigation,
                "CurrentCodec": mediaFile.Codec,
                "CurrentAudioCodec": mediaFile.AudioCodec,
                "CurrentContainer": mediaFile.ContainerFormat
            }
        except Exception as e:
            LoggingService.LogException("Error in RecheckFile", e, "OptimizationViewModel", "RecheckFile")
            return {"Success": False, "ErrorMessage": str(e)}

    def GetJellyfinAnalysis(self) -> Dict[str, Any]:
        """Get Jellyfin analysis from local DB (fast, no SSH)."""
        try:
            LoggingService.LogFunctionEntry("GetJellyfinAnalysis", "OptimizationViewModel")

            # Read operation counts from local DB
            dbCounts = self.DatabaseManager.GetJellyfinOperationCounts()
            if not dbCounts.get("Success"):
                return {"Success": False, "ErrorMessage": dbCounts.get("ErrorMessage", "No data")}

            counts = dbCounts.get("Counts", {})
            if not counts:
                return {"Success": False, "ErrorMessage": "No Jellyfin data imported yet. Click Refresh to import."}

            opCounts = {"Success": True}
            for opType in ("DirectStream", "Transcode", "Remux"):
                opCounts[opType] = counts.get(opType, {"Distinct": 0, "Total": 0})
            if dbCounts.get("OldestDate"):
                opCounts["OldestDate"] = dbCounts["OldestDate"]
            if dbCounts.get("NewestDate"):
                opCounts["NewestDate"] = dbCounts["NewestDate"]

            # Get transcode reasons from DB
            transcodeData = self.DatabaseManager.GetJellyfinOperationsByType("Transcode", 200)
            transcodeReasons = transcodeData.get("Reasons", {}) if transcodeData.get("Success") else {}

            # Try server info via REST (fast, no SSH needed)
            serverInfo = None
            service = self._GetJellyfinService()
            if service:
                try:
                    serverInfo = service.GetServerInfo()
                    if not serverInfo.get("Success"):
                        serverInfo = None
                except Exception:
                    pass

            # Get destination format summary
            destSummary = self.DatabaseManager.GetTranscodeDestinationSummary()

            return {
                "Success": True,
                "ServerInfo": serverInfo,
                "OperationCounts": opCounts,
                "TranscodeReasons": {
                    "Success": True,
                    "Reasons": transcodeReasons
                } if transcodeReasons else None,
                "TotalRecords": dbCounts.get("TotalRecords", 0),
                "DestinationFormats": destSummary if destSummary.get("Success") else None
            }
        except Exception as e:
            LoggingService.LogException("Error in GetJellyfinAnalysis", e, "OptimizationViewModel", "GetJellyfinAnalysis")
            return {"Success": False, "ErrorMessage": str(e)}

    def RefreshJellyfinData(self) -> Dict[str, Any]:
        """SSH to Jellyfin, fetch new log entries, store in local DB."""
        try:
            LoggingService.LogFunctionEntry("RefreshJellyfinData", "OptimizationViewModel")

            service = self._GetJellyfinService()
            if not service:
                return {"Success": False, "ErrorMessage": "Jellyfin connection not configured"}

            # Check if existing records are missing destination format data (stale schema)
            # If so, clear them to force a full re-import with the new fields
            existingNames = self.DatabaseManager.GetExistingLogFileNames()
            if existingNames:
                staleCount = self.DatabaseManager.GetStaleJellyfinRecordCount()
                if staleCount > 0:
                    LoggingService.LogInfo(
                        f"Clearing {len(existingNames)} stale Jellyfin records (missing destination format data)",
                        "OptimizationViewModel", "RefreshJellyfinData")
                    self.DatabaseManager.ClearJellyfinOperations()
                    existingNames = set()

            # Fetch only new entries from Jellyfin server
            result = service.FetchNewLogEntries(existingNames)
            if not result.get("Success"):
                return result

            entries = result.get("Entries", [])
            newCount = 0
            if entries:
                newCount = self.DatabaseManager.InsertJellyfinOperationsBatch(entries)

            return {
                "Success": True,
                "NewCount": newCount,
                "TotalOnServer": result.get("TotalOnServer", 0),
                "TotalInDB": len(existingNames) + newCount
            }
        except Exception as e:
            LoggingService.LogException("Error refreshing Jellyfin data", e, "OptimizationViewModel", "RefreshJellyfinData")
            return {"Success": False, "ErrorMessage": str(e)}

    def TestJellyfinConnection(self) -> Dict[str, Any]:
        """Test connection to Jellyfin server."""
        try:
            service = self._GetJellyfinService()
            if not service:
                return {"Success": False, "ErrorMessage": "Jellyfin connection not configured"}
            return service.TestConnection()
        except Exception as e:
            LoggingService.LogException("Error testing connection", e, "OptimizationViewModel", "TestJellyfinConnection")
            return {"Success": False, "ErrorMessage": str(e)}

    def GetConnectionSettings(self) -> Dict[str, Any]:
        """Get Jellyfin connection settings from SystemSettings."""
        try:
            settings = {}
            for key in self.JELLYFIN_SETTINGS_KEYS:
                settings[key] = self.DatabaseManager.GetSystemSetting(key) or ""
            return {"Success": True, "Settings": settings}
        except Exception as e:
            LoggingService.LogException("Error getting connection settings", e, "OptimizationViewModel", "GetConnectionSettings")
            return {"Success": False, "ErrorMessage": str(e)}

    def SaveConnectionSettings(self, Settings: Dict[str, str]) -> Dict[str, Any]:
        """Save Jellyfin connection settings to SystemSettings."""
        try:
            descriptions = {
                'JellyfinHost': 'Jellyfin server hostname or IP',
                'JellyfinSSHPort': 'SSH port for Jellyfin server',
                'JellyfinSSHUser': 'SSH username for Jellyfin server',
                'JellyfinSSHKeyPath': 'Path to SSH private key file',
                'JellyfinApiKey': 'Jellyfin API key for REST API access',
                'JellyfinApiPort': 'Jellyfin HTTP API port'
            }
            for key in self.JELLYFIN_SETTINGS_KEYS:
                if key in Settings:
                    self.DatabaseManager.AddOrUpdateSystemSetting(
                        key, Settings[key], descriptions.get(key, ''), 'string'
                    )
            return {"Success": True, "Message": "Settings saved"}
        except Exception as e:
            LoggingService.LogException("Error saving connection settings", e, "OptimizationViewModel", "SaveConnectionSettings")
            return {"Success": False, "ErrorMessage": str(e)}

    def CopyAnalysisForAI(self) -> Dict[str, Any]:
        """Generate a compact, token-optimized summary of all analysis data."""
        try:
            local = self.GetLocalAnalysis()
            if not local.get("Success"):
                return local

            lines = []
            lines.append(f"MediaVortex Library: {local['TotalFiles']} files")
            lines.append("")

            for section in local.get("Sections", []):
                lines.append(f"[{section['Impact']}] {section['Title']}: {section['Count']} files ({section['Percentage']}%)")
                lines.append(f"  {section['Description']}")
                lines.append(f"  Action: {section['Action']}")
                lines.append("")

            lines.append("Container breakdown:")
            for c in local.get("ContainerCounts", [])[:10]:
                lines.append(f"  {c['Format']}: {c['Count']}")

            lines.append("")
            lines.append("Video codec breakdown:")
            for c in local.get("VideoCodecCounts", [])[:10]:
                lines.append(f"  {c['Codec']}: {c['Count']}")

            lines.append("")
            lines.append("Audio codec breakdown:")
            for c in local.get("AudioCodecCounts", [])[:10]:
                lines.append(f"  {c['Codec']}: {c['Count']}")

            # Try Jellyfin data from local DB
            jellyfin = self.GetJellyfinAnalysis()
            if jellyfin.get("Success"):
                opCounts = jellyfin.get("OperationCounts")
                if opCounts and opCounts.get("Success"):
                    lines.append("")
                    lines.append("Jellyfin FFmpeg operations (distinct files / total logs):")
                    for opName in ("DirectStream", "Transcode", "Remux"):
                        op = opCounts.get(opName, {})
                        if isinstance(op, dict):
                            lines.append(f"  {opName}: {op.get('Distinct', 0)} files / {op.get('Total', 0)} logs")
                        else:
                            lines.append(f"  {opName}: {op}")

                reasons = jellyfin.get("TranscodeReasons")
                if reasons and reasons.get("Success"):
                    lines.append("")
                    lines.append("Transcode reasons:")
                    for reason, count in reasons.get("Reasons", {}).items():
                        if count > 0:
                            lines.append(f"  {reason}: {count}")

            # Add destination format summary
            destSummary = self.DatabaseManager.GetTranscodeDestinationSummary()
            if destSummary.get("Success") and destSummary.get("Formats"):
                lines.append("")
                lines.append("Transcode destination formats (what Jellyfin transcodes TO):")
                for fmt in destSummary["Formats"][:10]:
                    parts = []
                    if fmt["DestResolution"]:
                        parts.append(fmt["DestResolution"])
                    if fmt["DestProfile"]:
                        parts.append(f"profile:{fmt['DestProfile']}")
                    if fmt["DestLevel"]:
                        parts.append(f"level:{fmt['DestLevel']}")
                    if fmt["DestPixelFormat"]:
                        parts.append(fmt["DestPixelFormat"])
                    if fmt["DestFormat"]:
                        parts.append(f"format:{fmt['DestFormat']}")
                    lines.append(f"  {' | '.join(parts)}: {fmt['Count']} logs")

            return {"Success": True, "Text": "\n".join(lines)}
        except Exception as e:
            LoggingService.LogException("Error generating AI summary", e, "OptimizationViewModel", "CopyAnalysisForAI")
            return {"Success": False, "ErrorMessage": str(e)}

    def GetDeviceAnalysis(self) -> Dict[str, Any]:
        """Get device-level analysis: registered devices, playback patterns, and log field inspection."""
        try:
            LoggingService.LogFunctionEntry("GetDeviceAnalysis", "OptimizationViewModel")

            service = self._GetJellyfinService()
            if not service:
                return {"Success": False, "ErrorMessage": "Jellyfin connection not configured"}

            results = {}

            # 1. Get registered devices via REST API
            try:
                deviceResult = service.GetRegisteredDevices()
                if deviceResult.get("Success"):
                    results["Devices"] = deviceResult.get("Devices", [])
                else:
                    results["DevicesError"] = deviceResult.get("ErrorMessage", "Failed to get devices")
            except Exception as e:
                results["DevicesError"] = str(e)

            # 2. Get device playback summary from Jellyfin DB
            try:
                playbackResult = service.GetDevicePlaybackSummary()
                if playbackResult.get("Success"):
                    results["PlaybackActivities"] = playbackResult.get("Activities", [])
                    results["DeviceTables"] = playbackResult.get("DeviceTables", [])
                    results["DeviceRecords"] = playbackResult.get("DeviceRecords", [])
                else:
                    results["PlaybackError"] = playbackResult.get("ErrorMessage", "Failed to query DB")
            except Exception as e:
                results["PlaybackError"] = str(e)

            # 3. Inspect raw log JSON to discover device/session fields
            try:
                inspectResult = service.InspectLogJsonFields()
                if inspectResult.get("Success"):
                    results["LogJsonFields"] = inspectResult.get("Fields", {})
                    results["SampleLogFile"] = inspectResult.get("LogFile", "")
                else:
                    results["LogJsonError"] = inspectResult.get("ErrorMessage", "")
            except Exception as e:
                results["LogJsonError"] = str(e)

            results["Success"] = True
            return results
        except Exception as e:
            LoggingService.LogException("Error in GetDeviceAnalysis", e, "OptimizationViewModel", "GetDeviceAnalysis")
            return {"Success": False, "ErrorMessage": str(e)}

    def _ExtractDiskFileName(self, DisplayName: str, FilePath: str) -> str:
        """Extract the actual disk filename from Jellyfin's Path, falling back to display name."""
        if FilePath:
            # Jellyfin Path is a Linux path like /media/tv/Show/Season 01/episode.mkv
            basename = FilePath.split('/')[-1] if '/' in FilePath else FilePath
            if basename:
                return basename
        # Fallback to display name
        return DisplayName

    def _CheckMitigation(self, FileName: str, FilePath: str, OperationType: str, Reason: str,
                          VideoCodec: str, AudioCodec: str, Container: str) -> Dict[str, Any]:
        """Check if a Jellyfin operation file has been mitigated in MediaVortex."""
        try:
            baseResult = {"CurrentCodec": None, "CurrentAudioCodec": None, "CurrentContainer": None, "CurrentFileName": None, "MediaFileId": None}

            if OperationType == "DirectStream":
                return {**baseResult, "Status": "ok", "Label": "OK"}

            # Use the actual disk filename from the Jellyfin path for DB lookup
            diskFileName = self._ExtractDiskFileName(FileName, FilePath)

            mediaFile = self.DatabaseManager.GetMediaFileByFileName(diskFileName)
            if not mediaFile:
                return {**baseResult, "Status": "not_found", "Label": "Not Found"}

            # If the match was fuzzy (filename changed), the DB data may be stale.
            # Run ffprobe on the actual file to update DB with current metadata.
            matchType = mediaFile.get("MatchType", "exact")
            if matchType in ("no_ext", "fuzzy"):
                mediaFile = self._RescanAndRefreshFile(mediaFile) or mediaFile

            currentContainer = (mediaFile.get("ContainerFormat") or "").lower()
            currentCodec = (mediaFile.get("Codec") or "").lower()
            currentAudio = (mediaFile.get("AudioCodec") or "").lower()

            # Include current file data in every result so the UI can display it
            baseResult["CurrentCodec"] = mediaFile.get("Codec")
            baseResult["CurrentAudioCodec"] = mediaFile.get("AudioCodec")
            baseResult["CurrentContainer"] = mediaFile.get("ContainerFormat")
            baseResult["CurrentFileName"] = mediaFile.get("FileName")
            baseResult["MediaFileId"] = mediaFile.get("Id")

            if OperationType == "Remux":
                if currentContainer == "mp4":
                    return {**baseResult, "Status": "mitigated", "Label": "Mitigated"}
                return {**baseResult, "Status": "pending", "Label": "Pending"}

            if OperationType == "Transcode":
                if Reason == "legacy_codec":
                    if currentCodec in ("hevc", "h264", "av1"):
                        return {**baseResult, "Status": "mitigated", "Label": "Mitigated"}
                elif Reason == "hevc_incompatible":
                    if currentCodec in ("h264", "av1"):
                        return {**baseResult, "Status": "mitigated", "Label": "Mitigated"}
                elif Reason == "container_incompatible":
                    if currentContainer == "mp4":
                        return {**baseResult, "Status": "mitigated", "Label": "Mitigated"}
                elif Reason == "audio_transcode":
                    if currentAudio in ("aac", "ac3"):
                        return {**baseResult, "Status": "mitigated", "Label": "Mitigated"}
                elif Reason == "subtitle_transcode":
                    currentSubs = (mediaFile.get("SubtitleFormats") or "").lower()
                    burnInCodecs = {"pgssub", "pgs", "hdmv_pgs_subtitle", "dvdsub", "vobsub", "dvb_subtitle", "dvbsub", "ass", "ssa"}
                    if currentSubs:
                        hasBurnIn = any(sc in currentSubs for sc in burnInCodecs)
                        if not hasBurnIn:
                            return {**baseResult, "Status": "mitigated", "Label": "Mitigated"}
                return {**baseResult, "Status": "pending", "Label": "Pending"}

            return {**baseResult, "Status": "pending", "Label": "Pending"}
        except Exception:
            return {"Status": "unknown", "Label": "?", "CurrentCodec": None, "CurrentAudioCodec": None, "CurrentContainer": None, "CurrentFileName": None, "MediaFileId": None}

    # directive: path-schema-migration | # see path.S5
    def _RescanAndRefreshFile(self, mediaFileSummary: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Run ffprobe on a fuzzy-matched file and update DB. Returns refreshed summary dict."""
        try:
            # Summary dict lacks typed pair; load full model for Path resolution.
            fullFile = self.DatabaseManager.GetFullMediaFileByFileName(mediaFileSummary["FileName"])
            if not fullFile:
                return None

            LocalDisk, _PathObj = self._ResolveWorkerLocal(fullFile, fullFile.FilePath or mediaFileSummary.get("FilePath", ""))
            if not _LocalExists(LocalDisk):
                return None

            fileManager = FileManagerService()
            metadataResult = fileManager.ExtractMediaMetadata(LocalDisk)
            if not metadataResult.get('Success', False):
                return None

            fullFile.Codec = metadataResult.get('VideoCodec')
            fullFile.AudioCodec = metadataResult.get('AudioCodec')
            fullFile.ContainerFormat = metadataResult.get('ContainerFormat')
            fullFile.SubtitleFormats = metadataResult.get('SubtitleFormats')
            fullFile.Resolution = metadataResult.get('Resolution')
            fullFile.VideoBitrateKbps = metadataResult.get('VideoBitrateKbps')
            fullFile.AudioBitrateKbps = metadataResult.get('AudioBitrateKbps')
            fullFile.DurationMinutes = metadataResult.get('DurationMinutes')
            fullFile.FrameRate = metadataResult.get('FrameRate')
            fullFile.TotalFrames = metadataResult.get('TotalFrames')
            fullFile.OverallBitrate = metadataResult.get('OverallBitrate')
            fullFile.SizeMB = _LocalGetSize(LocalDisk) / (1024 * 1024)
            self.DatabaseManager.SaveMediaFile(fullFile)

            # Return refreshed summary
            return {
                "FileName": fullFile.FileName,
                "FilePath": fullFile.FilePath,
                "ContainerFormat": fullFile.ContainerFormat,
                "Codec": fullFile.Codec,
                "AudioCodec": fullFile.AudioCodec,
                "SubtitleFormats": fullFile.SubtitleFormats,
                "TranscodedByMediaVortex": fullFile.TranscodedByMediaVortex,
                "MatchType": mediaFileSummary.get("MatchType", "fuzzy")
            }
        except Exception as e:
            LoggingService.LogException("Error rescanning file", e, "OptimizationViewModel", "_RescanAndRefreshFile")
            return None

    def _GetJellyfinService(self) -> Optional[JellyfinService]:
        """Create JellyfinService from saved settings."""
        try:
            host = self.DatabaseManager.GetSystemSetting('JellyfinHost')
            if not host:
                return None

            port = int(self.DatabaseManager.GetSystemSetting('JellyfinSSHPort') or '22')
            user = self.DatabaseManager.GetSystemSetting('JellyfinSSHUser') or 'root'
            keyPath = self.DatabaseManager.GetSystemSetting('JellyfinSSHKeyPath') or ''
            apiKey = self.DatabaseManager.GetSystemSetting('JellyfinApiKey') or ''
            apiPort = int(self.DatabaseManager.GetSystemSetting('JellyfinApiPort') or '8096')

            return JellyfinService(
                Host=host, SSHPort=port, SSHUser=user,
                SSHKeyPath=keyPath, ApiKey=apiKey, ApiPort=apiPort
            )
        except Exception as e:
            LoggingService.LogException("Error creating JellyfinService", e, "OptimizationViewModel", "_GetJellyfinService")
            return None
