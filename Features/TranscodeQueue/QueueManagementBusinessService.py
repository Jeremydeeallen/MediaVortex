from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timezone
import ntpath
import os
from Features.TranscodeQueue.Models.TranscodeQueueModel import TranscodeQueueModel
from Core.Models.MediaFileModel import MediaFileModel
from Features.Profiles.Models.ProfileThresholdModel import ProfileThresholdModel
from Features.Profiles.Models.TranscodeProfileModel import TranscodeProfileModel
from Features.TranscodeQueue.TranscodeQueueRepository import TranscodeQueueRepository
from Features.TranscodeQueue.CrfBitrateEstimateRepository import CrfBitrateEstimateRepository
from Features.TranscodeQueue.QueueAdmissionConfigRepository import QueueAdmissionConfigRepository
from Features.TranscodeQueue.CodecCompatibilityRepository import CodecCompatibilityRepository
from Core.Logging.LoggingService import LoggingService
from Core.PathNormalize import ExtractShowFolder
from Services.FileManagerService import FileManagerService
from Repositories.DatabaseManager import DatabaseManager


# directive: transcodequeue-uses-path | # see path.S5
def _LocalExists(Value: str) -> bool:
    """Module-level helper: existence check on a worker-local string."""
    return bool(Value) and os.path.exists(Value)


# directive: transcodequeue-uses-path | # see path.S5
def _LastSegment(Value: str) -> str:
    """Module-level helper: filename component of a canonical Windows-shape path."""
    return ntpath.basename(Value or "")


# directive: transcodequeue-uses-path | # see path.S5
def _ParentDir(Value: str) -> str:
    """Module-level helper: parent directory component of a canonical Windows-shape path."""
    return ntpath.dirname(Value or "")


class QueueManagementBusinessService:
    """Handles transcoding queue operations and population logic."""

    # Resolution rank used by the compliance cascade for "is this a downscale?".
    # Codec/container/audio acceptability and the savings threshold moved to
    # normalized DB tables (CodecCompatibility, QueueAdmissionConfig) -- see
    # marginal-savings-gate.feature.md.
    RESOLUTION_RANK = {'480p': 0, '720p': 1, '1080p': 2, '2160p': 3}

    def __init__(self, RepositoryInstance: TranscodeQueueRepository = None):
        self.Repository = RepositoryInstance or TranscodeQueueRepository()
        self.DatabaseManager = DatabaseManager()
        self.FileManager = FileManagerService()
        # Data-driven gate config (per marginal-savings-gate.feature.md). Each
        # call site reads fresh from these repositories; no in-memory caching.
        self.CrfBitrateEstimateRepo = CrfBitrateEstimateRepository()
        self.QueueAdmissionConfigRepo = QueueAdmissionConfigRepository()
        self.CodecCompatibilityRepo = CodecCompatibilityRepository()

    def PopulateQueueFromMediaFiles(self, RootFolderPath: str = None, ProfileId: int = None, CompatibilityOnly: bool = False) -> Dict[str, Any]:
        """Populate transcoding queue from MediaFiles that have assigned profiles, ordered by largest disk space."""
        try:
            LoggingService.LogFunctionEntry("PopulateQueueFromMediaFiles", "QueueManagementBusinessService", RootFolderPath, ProfileId, CompatibilityOnly)

            # Remux path: only MKV files, no profile/resolution requirements
            if CompatibilityOnly:
                return self.PopulateQueueForRemux(RootFolderPath)

            # If RootFolderPath is provided, always use resolution filtering
            if RootFolderPath:
                if ProfileId is not None:
                    # Use selected profile for filtering
                    mediaFilesWithProfiles = self.GetMediaFilesByFolderAndResolutionFilter(RootFolderPath, ProfileId)
                    LoggingService.LogInfo(f"Found {len(mediaFilesWithProfiles)} media files matching resolution filter with selected profile", "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")
                else:
                    # Use each file's assigned profile for filtering
                    mediaFilesWithProfiles = self.GetMediaFilesByFolderWithResolutionFilterUsingAssignedProfiles(RootFolderPath)
                    LoggingService.LogInfo(f"Found {len(mediaFilesWithProfiles)} media files matching resolution filter using assigned profiles", "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")
            else:
                # No folder specified, use existing behavior: get media files with assigned profiles, ordered by size (largest first)
                mediaFilesWithProfiles = self.GetMediaFilesWithProfilesOrderedBySize(RootFolderPath)
                LoggingService.LogInfo(f"Found {len(mediaFilesWithProfiles)} media files with assigned profiles", "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")

            if not mediaFilesWithProfiles:
                if ProfileId is not None and RootFolderPath:
                    friendlyMessage = f"No media files found in folder '{RootFolderPath}' with resolution greater than the target resolution for the selected profile."
                elif RootFolderPath:
                    friendlyMessage = f"No media files found with assigned profiles in folder '{RootFolderPath}'. Please assign profiles to your media files in Settings > Profile Management before adding them to the transcoding queue."
                else:
                    friendlyMessage = "No media files found with assigned profiles. Please assign profiles to your media files in Settings > Profile Management before adding them to the transcoding queue."
                LoggingService.LogWarning("No media files found matching criteria", "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")
                return {"Success": False, "ErrorMessage": friendlyMessage, "ItemsAdded": 0}

            # Get existing queue FilePaths to avoid duplicates (lightweight -- paths only)
            existingFilePaths = self.Repository.GetExistingQueueFilePaths()
            LoggingService.LogInfo(f"Found {len(existingFilePaths)} existing queue items", "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")

            # Get files already successfully transcoded (paths only)
            from Core.Database.DatabaseService import DatabaseService as _DbSvc
            _SuccessRows = _DbSvc().ExecuteQuery(
                "SELECT FilePath FROM TranscodeFiles WHERE SuccessfullyTranscoded = true"
            )
            successfullyTranscodedPaths = {R.get('FilePath', '') for R in _SuccessRows}
            LoggingService.LogInfo(f"Found {len(successfullyTranscodedPaths)} already successfully transcoded files", "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")

            # Import adaptive quality service for VMAF-based retranscode checks
            from Services.AdaptiveQualityService import AdaptiveQualityService
            adaptiveService = AdaptiveQualityService(self.DatabaseManager)

            itemsAdded = 0
            itemsSkipped = 0
            itemsSkippedDueToResolution = 0
            itemsSkippedDueToQuality = 0  # Track files skipped because VMAF >= 80
            itemsSkippedDueToAudio = 0  # Track files skipped because no English audio found
            # Per-reason counters for the marginal-savings gate (criterion 16).
            gateCounts = {'Upscale': 0, 'MarginalSavings': 0, 'MissingProfile': 0, 'MissingEstimate': 0}
            # Load admission config once -- shared across all rows in this run.
            admissionConfig = self.QueueAdmissionConfigRepo.Get()
            pendingInserts: List[TranscodeQueueModel] = []

            for mediaFile in mediaFilesWithProfiles:
                # Skip if already in queue
                if mediaFile.FilePath in existingFilePaths:
                    itemsSkipped += 1
                    continue

                # Check if file was previously transcoded - if so, check VMAF for retranscode decision
                if mediaFile.FilePath in successfullyTranscodedPaths:
                    # Check if file should be retranscoded based on VMAF
                    shouldRetranscode, previousAttempt = adaptiveService.ShouldRetranscode(mediaFile.Id)

                    if not shouldRetranscode:
                        # VMAF >= 80, quality already acceptable - skip retranscode
                        itemsSkipped += 1
                        itemsSkippedDueToQuality += 1
                        LoggingService.LogInfo(f"Skipping {mediaFile.FileName}: Quality already acceptable (VMAF >= 80)", "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")
                        continue

                    # VMAF < 80, check if CRF adjustment would fail
                    if previousAttempt:
                        previousCRF = previousAttempt.get('Quality')
                        vmafScore = previousAttempt.get('VMAF')

                        if previousCRF and vmafScore is not None and vmafScore < 80:
                            # Calculate what the adjusted CRF would be
                            adjustedCRF = adaptiveService.CalculateAdjustedCRF(previousCRF, vmafScore)

                            # Validate adjustment
                            minCRF = 15
                            if adjustedCRF < minCRF:
                                # Cannot adjust further - log critical error and skip
                                errorMsg = f"Cannot adjust CRF further for {mediaFile.FileName}: Previous CRF={previousCRF}, VMAF={vmafScore:.2f}, Adjusted CRF={adjustedCRF} would be below minimum {minCRF}"

                                # Extract directory for ProblemFiles
                                directory = os.path.dirname(mediaFile.FilePath)

                                # Log to ProblemFiles
                                problemFileId = self.Repository.AddProblemFile(
                                    mediaFile.FilePath,
                                    "CRF_Adjustment_Failed",
                                    f"CRF adjustment failed: Previous CRF={previousCRF}, VMAF={vmafScore:.2f}, Calculated CRF={adjustedCRF} is below minimum threshold (15). Quality threshold unreachable."
                                )

                                if problemFileId:
                                    LoggingService.LogError(f"Logged CRF adjustment failure to ProblemFiles (ID: {problemFileId}): {errorMsg}",
                                                          "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")

                                itemsSkipped += 1
                                continue

                    # VMAF < 80 and CRF adjustment is valid - allow retranscode by continuing to add to queue
                    LoggingService.LogInfo(f"File {mediaFile.FileName} will be retranscoded: Previous VMAF < 80", "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")
                # else: File not in successfullyTranscodedPaths, proceed with normal queue addition

                # Marginal-savings gate (replaces ShouldSkipDueToResolution -- see
                # marginal-savings-gate.feature.md). Resolution filtering is
                # already applied when RootFolderPath is set, so this only fires
                # in the no-folder-specified path.
                if not RootFolderPath:
                    shouldSkip, skipReason = self.EvaluateQueueAdmissionForProfile(
                        mediaFile, mediaFile.AssignedProfile, AdmissionConfig=admissionConfig
                    )
                    if shouldSkip:
                        itemsSkippedDueToResolution += 1
                        # Bucket per reason for the rolled-up summary.
                        for Bucket in gateCounts:
                            if skipReason.startswith(Bucket):
                                gateCounts[Bucket] += 1
                                break
                        LoggingService.LogInfo(f"Skipped {mediaFile.FileName}: {skipReason}", "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")
                        continue

                # Skip files without confirmed English audio to prevent destructive transcoding
                if mediaFile.HasExplicitEnglishAudio is False:
                    itemsSkippedDueToAudio += 1
                    LoggingService.LogWarning(f"Skipped {mediaFile.FileName}: No English audio track found (languages: {mediaFile.AudioLanguages or 'unknown'})", "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")
                    continue

                # Create queue item (no need to find threshold since profile is already assigned)
                queueItem = self.CreateQueueItemFromMediaFileWithProfile(mediaFile)
                if queueItem:
                    pendingInserts.append(queueItem)
                    existingFilePaths.add(mediaFile.FilePath)  # Prevent duplicates in this run

            # Bulk insert all collected items in one transaction
            itemsAdded = 0
            if pendingInserts:
                try:
                    itemsAdded = self.Repository.BulkInsertQueueItems(pendingInserts)
                except Exception as e:
                    LoggingService.LogException("Bulk insert failed, falling back to per-item insert", e, "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")
                    for queueItem in pendingInserts:
                        try:
                            self.Repository.SaveTranscodeQueueItem(queueItem)
                            itemsAdded += 1
                        except Exception as e2:
                            LoggingService.LogException(f"Error saving queue item for {queueItem.FileName}", e2, "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")

            # Add friendly message based on results
            skipDetails = []
            if itemsSkipped > 0:
                skipDetails.append(f"{itemsSkipped} files were skipped")
            if itemsSkippedDueToQuality > 0:
                skipDetails.append(f"{itemsSkippedDueToQuality} skipped (quality already acceptable - VMAF >= 80)")
            if itemsSkippedDueToResolution > 0:
                skipDetails.append(f"{itemsSkippedDueToResolution} skipped (resolution check)")
            if itemsSkippedDueToAudio > 0:
                skipDetails.append(f"{itemsSkippedDueToAudio} skipped (no confirmed English audio - needs manual review)")

            skipMessage = ", ".join(skipDetails) if skipDetails else "no files were skipped"

            if itemsAdded == 0:
                if itemsSkipped == len(mediaFilesWithProfiles):
                    if itemsSkippedDueToQuality > 0:
                        friendlyMessage = f"All {len(mediaFilesWithProfiles)} media files with assigned profiles have acceptable quality (VMAF >= 80) or are already in the queue. No new items were added."
                    else:
                        friendlyMessage = f"All {len(mediaFilesWithProfiles)} media files with assigned profiles are already in the queue or have been successfully transcoded. No new items were added."
                else:
                    friendlyMessage = f"No new items were added to the queue. {skipMessage}."
            else:
                friendlyMessage = f"Successfully added {itemsAdded} items to the transcoding queue. {skipMessage}."

            result = {
                "Success": True,
                "ItemsEvaluated": len(mediaFilesWithProfiles),
                "ItemsAdded": itemsAdded,
                "ItemsSkipped": itemsSkipped,
                "ItemsSkippedDueToResolution": itemsSkippedDueToResolution,
                "ItemsSkippedDueToQuality": itemsSkippedDueToQuality,
                "ItemsSkippedDueToAudio": itemsSkippedDueToAudio,
                "Message": friendlyMessage
            }

            LoggingService.LogInfo(f"Queue population completed: {itemsAdded} added, {itemsSkipped} skipped (duplicate/transcoded), {itemsSkippedDueToQuality} skipped (quality acceptable), {itemsSkippedDueToResolution} skipped (gate), {itemsSkippedDueToAudio} skipped (no English audio) from {len(mediaFilesWithProfiles)} files with profiles", "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")
            # Marginal-savings gate rolled-up summary (criterion 16).
            LoggingService.LogInfo(
                f"Marginal-savings gate: {itemsAdded} admitted, {itemsSkippedDueToResolution} blocked "
                f"(Marginal: {gateCounts['MarginalSavings']}, Upscale: {gateCounts['Upscale']}, "
                f"MissingEstimate: {gateCounts['MissingEstimate']}, MissingProfile: {gateCounts['MissingProfile']})",
                "QueueManagementBusinessService", "PopulateQueueFromMediaFiles",
            )
            return result

        except Exception as e:
            errorMsg = f"Exception populating queue: {str(e)}"
            LoggingService.LogException(errorMsg, e, "QueueManagementBusinessService", "PopulateQueueFromMediaFiles")
            return {"Success": False, "ErrorMessage": errorMsg, "ItemsAdded": 0}

    def SmartPopulateQueue(self, Limit: int = 100, Offset: int = 0, Drive: str = '',
                            Search: Optional[str] = None, Mode: Optional[str] = None,
                            Focus: Optional[str] = None) -> Dict[str, Any]:
        """Get untranscoded MediaFiles ranked by materialized PriorityScore.

        Reads MediaFiles.PriorityScore (maintained by the priority-materialization
        pipeline -- see transcode.flow.md Stage 3.5). NULL scores sort last, with
        SizeMB DESC as tiebreaker so unscored files still land in a sensible order.

        Excludes files already in queue and already-MediaVortex-transcoded files.
        Optional Drive filter (e.g. 'T:'), Search substring filter, and Mode
        filter ('Transcode' | 'Remux') that scopes by `MediaFiles.RecommendedMode`
        per `Features/ShowSettings/remux-populate-card.feature.md` criterion 4.
        Invalid Mode is silently ignored (returns the unscoped set).
        """
        try:
            LoggingService.LogFunctionEntry("SmartPopulateQueue", "QueueManagementBusinessService", Limit, Offset, Drive, Search, Mode)

            from Core.Database.DatabaseService import DatabaseService, EscapeLikePattern

            # Validate Limit: coerce to [1, 1000]. Display cap reflects DOM-render
            # cost; bulk-drain use case goes through QueueAllMatching, not pagination.
            try:
                Limit = max(1, min(1000, int(Limit)))
            except (TypeError, ValueError):
                Limit = 100
            try:
                Offset = max(0, int(Offset))
            except (TypeError, ValueError):
                Offset = 0

            # Predicate uses IS NOT TRUE so the partial index idx_mediafiles_smartpopulate
            # is usable (criterion 16 of smart-populate.feature.md).
            Params = []
            WhereSql = """
                WHERE m.TranscodedByMediaVortex IS NOT TRUE
                  AND m.Id NOT IN (SELECT MediaFileId FROM TranscodeQueue WHERE MediaFileId IS NOT NULL)
                  AND m.SizeMB > 0
                  AND (m.HasExplicitEnglishAudio IS NULL OR m.HasExplicitEnglishAudio = true)
            """

            # Mode filter. Post-2026-05-17 the cascade tracks two independent
            # flags (NeedsQuick, NeedsTranscode) so a file can appear in BOTH
            # tabs when both apply. We filter on the flags directly, not the
            # singular RecommendedMode -- that lets a file needing Transcode +
            # Audio surface in the Quick Fix tab too, so the operator can do
            # the cheap audio pass first regardless of whether heavy video
            # work is also pending.
            if Mode == 'Quick':
                WhereSql += " AND m.NeedsQuick = TRUE"
            elif Mode == 'Transcode':
                WhereSql += " AND m.NeedsTranscode = TRUE"
            elif Mode in ('Remux', 'AudioFix'):
                # Legacy modes -- preserve old semantics for backward compat
                WhereSql += " AND m.RecommendedMode = %s"
                Params.append(Mode)

            if Drive:
                DrivePrefix = Drive.rstrip(':\\/') + ':'
                WhereSql += " AND m.FilePath LIKE %s ESCAPE '!'"
                Params.append(EscapeLikePattern(DrivePrefix) + '%')

            if Search and Search.strip():
                # Case-insensitive substring match on FileName OR the show-folder
                # segment (the path component immediately under the drive root).
                # SPLIT_PART(FilePath, separator, n) -- segment 2 of "T:\Show\..." is "Show".
                # We escape the user input via EscapeLikePattern + ESCAPE '!'.
                Term = '%' + EscapeLikePattern(Search.strip().lower()) + '%'
                WhereSql += """
                    AND (LOWER(m.FileName) LIKE %s ESCAPE '!'
                         OR LOWER(SPLIT_PART(REPLACE(m.FilePath, '\\\\', '/'), '/', 2)) LIKE %s ESCAPE '!')
                """
                Params.append(Term)
                Params.append(Term)

            ParamsTuple = tuple(Params)

            # Cheap COUNT query for total candidates (reflects all filters).
            CountSql = f"SELECT COUNT(*) as TotalCount FROM MediaFiles m {WhereSql}"
            CountRows = DatabaseService().ExecuteQuery(CountSql, ParamsTuple)
            TotalCandidates = int(CountRows[0].get('TotalCount', 0)) if CountRows else 0

            # Focus controls ORDER BY when Mode='Quick' (media-tabs-and-loudness.feature.md C17a).
            # Audio focus rank:
            #   0 = LUFS measured AND off-target (outside [-24, -22]) -- CONFIRMED needs work
            #   1 = LUFS NULL AND AudioComplete=false                 -- unknown, might need work
            #   2 = on-target measured OR AudioComplete=true          -- audio fine; here only for container
            # Container focus rank:
            #   0 = container is not MP4-family                       -- CONFIRMED container fix
            #   1 = container is MP4 (here only because audio not done)
            FocusSql = ""
            if Mode == 'Quick':
                if Focus == 'Audio':
                    FocusSql = (
                        "(CASE "
                        "  WHEN m.SourceIntegratedLufs IS NOT NULL "
                        "       AND (m.SourceIntegratedLufs < -24 OR m.SourceIntegratedLufs > -22) THEN 0 "
                        "  WHEN m.SourceIntegratedLufs IS NULL AND m.AudioComplete IS FALSE THEN 1 "
                        "  ELSE 2 "
                        "END), "
                    )
                elif Focus == 'Container':
                    # Literal % must be doubled because the f-string is passed to
                    # psycopg2's parameter substitution layer -- a bare % triggers
                    # an IndexError when no matching param exists.
                    FocusSql = (
                        "(CASE "
                        "  WHEN LOWER(COALESCE(m.ContainerFormat,'')) NOT LIKE '%%mp4%%' THEN 0 "
                        "  ELSE 1 "
                        "END), "
                    )

            Sql = f"""
                SELECT m.Id, m.FilePath, m.FileName, m.SizeMB, m.VideoBitrateKbps,
                       m.Codec, m.Resolution, m.ResolutionCategory, m.ContainerFormat,
                       m.PriorityScore, m.AudioCodec, m.AudioComplete,
                       m.SourceIntegratedLufs, m.SourceLoudnessRangeLU
                FROM MediaFiles m
                {WhereSql}
                ORDER BY {FocusSql}m.PriorityScore DESC NULLS LAST, m.SizeMB DESC NULLS LAST
                LIMIT {int(Limit)} OFFSET {int(Offset)}
            """
            Rows = DatabaseService().ExecuteQuery(Sql, ParamsTuple)

            Suggestions = []
            for Row in Rows:
                FilePath = Row.get('FilePath', '')
                FileName = Row.get('FileName', '')
                ShowName = ExtractShowFolder(FilePath)

                Suggestions.append({
                    'MediaFileId': Row.get('Id'),
                    'FilePath': FilePath,
                    'FileName': FileName,
                    'ShowName': ShowName,
                    'SizeMB': round(float(Row.get('SizeMB', 0) or 0), 1),
                    'Codec': Row.get('Codec', 'Unknown') or 'Unknown',
                    'Resolution': Row.get('Resolution', 'Unknown') or 'Unknown',
                    'ResolutionCategory': Row.get('ResolutionCategory', '') or '',
                    'BitrateKbps': int(Row.get('VideoBitrateKbps', 0) or 0),
                    'ContainerFormat': Row.get('ContainerFormat', '') or '',
                    'PriorityScore': Row.get('PriorityScore'),
                    'Mode': Mode if Mode in ('Transcode', 'Remux', 'AudioFix', 'Quick') else 'Transcode',
                    # Audio metadata for the Quick Fix tab columns
                    'AudioCodec': Row.get('AudioCodec'),
                    'AudioComplete': Row.get('AudioComplete'),
                    'SourceIntegratedLufs': Row.get('SourceIntegratedLufs'),
                    'SourceLoudnessRangeLU': Row.get('SourceLoudnessRangeLU'),
                })

            Result = {
                "Success": True,
                "Suggestions": Suggestions,
                "TotalCandidates": TotalCandidates,
                "Offset": Offset,
                "Limit": Limit,
                "Search": Search or '',
                "Mode": Mode if Mode in ('Transcode', 'Remux', 'AudioFix', 'Quick') else None,
                "HasMore": (Offset + len(Suggestions)) < TotalCandidates,
            }
            LoggingService.LogInfo(f"SmartPopulate: fetched {len(Rows)} of {TotalCandidates} candidates (offset={Offset}, search='{Search or ''}')", "QueueManagementBusinessService", "SmartPopulateQueue")
            return Result

        except Exception as Ex:
            ErrorMsg = f"Exception in SmartPopulateQueue: {str(Ex)}"
            LoggingService.LogException(ErrorMsg, Ex, "QueueManagementBusinessService", "SmartPopulateQueue")
            return {"Success": False, "ErrorMessage": ErrorMsg, "Suggestions": []}

    # PostgreSQL fragment: priority computed inline from MediaFiles.SizeMB
    # using the SizeMB-based fallback formula (matches CalculatePriority's
    # fallback path; verified bit-for-bit against the Python implementation).
    # Used inside COALESCE so a materialized PriorityScore wins when present.
    _SIZE_PRIORITY_SQL = (
        "GREATEST(1, LEAST(194, ROUND(1 + LEAST(193, "
        "LOG(10::numeric, GREATEST(m.SizeMB * 0.5, 0)::numeric + 1) / 5.0 * 193))::int))"
    )

    def AddSuggestionsToQueue(self,
                              MediaFileIds: Optional[List[int]] = None,
                              Items: Optional[List[Dict[str, Any]]] = None,
                              ProfileId: int = None,
                              Mode: str = None) -> Dict[str, Any]:
        """Queue media files in a single round-trip INSERT...SELECT.

        Accepts MediaFileIds (preferred) or a legacy Items list (only the
        MediaFileId field is read; FilePath/SizeMB/etc come from MediaFiles).

        For Mode='Transcode' with ProfileId: bulk-assigns the chosen profile
        on MediaFiles. PriorityScore is left to the next RecomputeForFiles
        cron (cascade-resolved priority is close enough for queue order;
        the formula is log-scaled).

        Priority on each new TranscodeQueue row is COALESCE(materialized
        PriorityScore, SizeMB-based fallback). No per-item DB lookup.
        """
        try:
            # Normalize input. Accept either MediaFileIds or legacy Items.
            if MediaFileIds is None and Items:
                MediaFileIds = [I.get('MediaFileId') for I in Items
                                if I.get('MediaFileId') is not None]
            try:
                NormalizedIds = list(dict.fromkeys(int(x) for x in (MediaFileIds or [])))
            except (TypeError, ValueError):
                return {"Success": False, "ErrorMessage": "Invalid MediaFileIds", "ItemsAdded": 0}
            if not NormalizedIds:
                return {"Success": False, "ErrorMessage": "No MediaFileIds provided", "ItemsAdded": 0}

            if Mode not in ('Transcode', 'Remux', 'AudioFix', 'Quick'):
                Mode = 'Transcode'

            # Resolve profile name. Transcode allows a profile choice; Remux
            # has no profile by design (cascade pre-decided no-re-encode).
            ProfileName = None
            if Mode == 'Transcode' and ProfileId is not None:
                Profile = self.DatabaseManager.GetProfileById(ProfileId)
                if not Profile:
                    return {"Success": False, "ErrorMessage": f"Profile with ID {ProfileId} not found", "ItemsAdded": 0}
                ProfileName = Profile.ProfileName

            from Core.Database.DatabaseService import DatabaseService
            Db = DatabaseService()

            # Honor operator's profile choice by writing it to MediaFiles.
            # Skip rows where it already matches to avoid unnecessary writes.
            if ProfileName:
                Db.ExecuteNonQuery(
                    "UPDATE MediaFiles SET AssignedProfile = %s "
                    "WHERE Id = ANY(%s) AND AssignedProfile IS DISTINCT FROM %s",
                    (ProfileName, NormalizedIds, ProfileName)
                )

            InsertSql = r"""
                INSERT INTO TranscodeQueue
                    (StorageRootId, RelativePath, FilePath, FileName, Directory,
                     SizeBytes, SizeMB, Priority, Status, DateAdded,
                     ProcessingMode, MediaFileId)
                SELECT m.StorageRootId,
                       COALESCE(m.RelativePath, ''),
                       m.FilePath,
                       m.FileName,
                       regexp_replace(replace(m.FilePath, E'\\', '/'), '/[^/]+$', ''),
                       (m.SizeMB * 1024 * 1024)::bigint,
                       m.SizeMB,
                       COALESCE(m.PriorityScore, """ + self._SIZE_PRIORITY_SQL + r"""),
                       'Pending',
                       NOW() AT TIME ZONE 'UTC',
                       %s,
                       m.Id
                FROM MediaFiles m
                WHERE m.Id = ANY(%s)
                  AND m.SizeMB > 0
                  AND NOT EXISTS (SELECT 1 FROM TranscodeQueue tq WHERE tq.FilePath = m.FilePath)
            """

            Connection = Db.GetConnection()
            try:
                Cursor = Connection.cursor()
                Cursor.execute(InsertSql, (Mode, NormalizedIds))
                ItemsAdded = Cursor.rowcount
                Connection.commit()
            finally:
                Db.CloseConnection(Connection)

            ItemsSkipped = len(NormalizedIds) - ItemsAdded
            LoggingService.LogInfo(
                f"AddSuggestionsToQueue: {ItemsAdded} added, {ItemsSkipped} skipped "
                f"(mode={Mode}, profile={ProfileName})",
                "QueueManagementBusinessService", "AddSuggestionsToQueue"
            )
            return {"Success": True, "ItemsAdded": ItemsAdded, "ItemsSkipped": ItemsSkipped}

        except Exception as Ex:
            ErrorMsg = f"Exception in AddSuggestionsToQueue: {str(Ex)}"
            LoggingService.LogException(ErrorMsg, Ex, "QueueManagementBusinessService", "AddSuggestionsToQueue")
            return {"Success": False, "ErrorMessage": ErrorMsg, "ItemsAdded": 0}

    def QueueAllMatching(self, Mode: str, Search: str = '', Drive: str = '') -> Dict[str, Any]:
        """Queue every cascade-classified candidate matching the optional filters,
        in one INSERT...SELECT. No client-side ID enumeration. Mirrors the
        SmartPopulateQueue WHERE clause but inserts instead of selecting.

        Mode must be 'Transcode' or 'Remux' -- filters MediaFiles by
        RecommendedMode. Files already in queue are excluded via NOT EXISTS.
        Returns ItemsAdded.
        """
        try:
            if Mode not in ('Transcode', 'Remux', 'AudioFix', 'Quick'):
                return {"Success": False, "ErrorMessage": "Mode must be 'Transcode', 'Quick', 'Remux' (legacy), or 'AudioFix' (legacy)", "ItemsAdded": 0}

            from Core.Database.DatabaseService import DatabaseService, EscapeLikePattern

            Params: list = [Mode, Mode]  # ProcessingMode in SELECT, RecommendedMode in WHERE
            WhereSql = """
                WHERE m.TranscodedByMediaVortex IS NOT TRUE
                  AND m.SizeMB > 0
                  AND (m.HasExplicitEnglishAudio IS NULL OR m.HasExplicitEnglishAudio = true)
                  AND m.RecommendedMode = %s
                  AND NOT EXISTS (SELECT 1 FROM TranscodeQueue tq WHERE tq.FilePath = m.FilePath)
            """

            if Drive:
                DrivePrefix = Drive.rstrip(':\\/') + ':'
                WhereSql += " AND m.FilePath LIKE %s ESCAPE '!'"
                Params.append(EscapeLikePattern(DrivePrefix) + '%')

            if Search and Search.strip():
                Term = '%' + EscapeLikePattern(Search.strip().lower()) + '%'
                WhereSql += (
                    " AND (LOWER(m.FileName) LIKE %s ESCAPE '!'"
                    "      OR LOWER(SPLIT_PART(REPLACE(m.FilePath, '\\\\', '/'), '/', 2)) LIKE %s ESCAPE '!')"
                )
                Params.append(Term)
                Params.append(Term)

            InsertSql = r"""
                INSERT INTO TranscodeQueue
                    (StorageRootId, RelativePath, FilePath, FileName, Directory,
                     SizeBytes, SizeMB, Priority, Status, DateAdded,
                     ProcessingMode, MediaFileId)
                SELECT m.StorageRootId,
                       COALESCE(m.RelativePath, ''),
                       m.FilePath,
                       m.FileName,
                       regexp_replace(replace(m.FilePath, E'\\', '/'), '/[^/]+$', ''),
                       (m.SizeMB * 1024 * 1024)::bigint,
                       m.SizeMB,
                       COALESCE(m.PriorityScore, """ + self._SIZE_PRIORITY_SQL + r"""),
                       'Pending',
                       NOW() AT TIME ZONE 'UTC',
                       %s,
                       m.Id
                FROM MediaFiles m
            """ + WhereSql

            Db = DatabaseService()
            Connection = Db.GetConnection()
            try:
                Cursor = Connection.cursor()
                Cursor.execute(InsertSql, tuple(Params))
                ItemsAdded = Cursor.rowcount
                Connection.commit()
            finally:
                Db.CloseConnection(Connection)

            LoggingService.LogInfo(
                f"QueueAllMatching: {ItemsAdded} added (mode={Mode}, search='{Search or ''}', drive='{Drive or ''}')",
                "QueueManagementBusinessService", "QueueAllMatching"
            )
            return {"Success": True, "ItemsAdded": ItemsAdded}

        except Exception as Ex:
            ErrorMsg = f"Exception in QueueAllMatching: {str(Ex)}"
            LoggingService.LogException(ErrorMsg, Ex, "QueueManagementBusinessService", "QueueAllMatching")
            return {"Success": False, "ErrorMessage": ErrorMsg, "ItemsAdded": 0}

    def GetMediaFilesWithProfilesOrderedBySize(self, RootFolderPath: str = None) -> List[MediaFileModel]:
        """Get media files that have assigned profiles, ordered by size (largest first).
        Uses SQL-side filtering instead of loading all rows into Python."""
        try:
            LoggingService.LogFunctionEntry("GetMediaFilesWithProfilesOrderedBySize", "QueueManagementBusinessService", RootFolderPath)

            from Core.Database.DatabaseService import DatabaseService, EscapeLikePattern

            WhereClauses = ["AssignedProfile IS NOT NULL", "TRIM(AssignedProfile) != ''"]
            Params: list = []

            if RootFolderPath:
                NormalizedPath = RootFolderPath.replace('/', '\\').rstrip('\\')
                WhereClauses.append("FilePath LIKE %s ESCAPE '!'")
                Params.append(EscapeLikePattern(NormalizedPath) + '%')

            Sql = f"""
                SELECT Id, SeasonId, StorageRootId, RelativePath, FilePath, FileName, SizeMB,
                       VideoBitrateKbps, AudioBitrateKbps, Resolution, Codec, DurationMinutes,
                       FrameRate, LastScannedDate, CompressionPotential, AssignedProfile,
                       IsInterlaced, ResolutionCategory, FileModificationTime, TotalFrames,
                       CodecProfile, ColorRange, FieldOrder, HasBFrames, RefFrames, PixelFormat,
                       Level, AudioChannels, AudioSampleRate, AudioSampleFormat,
                       AudioChannelLayout, AudioCodec, SubtitleFormats, ContainerFormat,
                       OverallBitrate, TranscodedByMediaVortex,
                       AudioLanguages, HasExplicitEnglishAudio
                FROM MediaFiles
                WHERE {' AND '.join(WhereClauses)}
                ORDER BY SizeMB DESC NULLS LAST
            """
            Rows = DatabaseService().ExecuteQuery(Sql, tuple(Params))

            filesWithProfiles = []
            for Row in Rows:
                mf = MediaFileModel(
                    Id=Row.get('Id'),
                    SeasonId=Row.get('SeasonId'),
                    StorageRootId=Row.get('StorageRootId'),
                    RelativePath=Row.get('RelativePath') or '',
                    FilePath=Row.get('FilePath', ''),
                    FileName=Row.get('FileName', ''),
                    SizeMB=Row.get('SizeMB') or 0.0,
                    VideoBitrateKbps=Row.get('VideoBitrateKbps'),
                    AudioBitrateKbps=Row.get('AudioBitrateKbps'),
                    Resolution=Row.get('Resolution'),
                    Codec=Row.get('Codec'),
                    DurationMinutes=Row.get('DurationMinutes'),
                    FrameRate=Row.get('FrameRate'),
                    LastScannedDate=Row.get('LastScannedDate'),
                    CompressionPotential=Row.get('CompressionPotential'),
                    AssignedProfile=Row.get('AssignedProfile'),
                    IsInterlaced=Row.get('IsInterlaced'),
                    ResolutionCategory=Row.get('ResolutionCategory'),
                    FileModificationTime=Row.get('FileModificationTime'),
                    TotalFrames=Row.get('TotalFrames'),
                    CodecProfile=Row.get('CodecProfile'),
                    ColorRange=Row.get('ColorRange'),
                    FieldOrder=Row.get('FieldOrder'),
                    HasBFrames=Row.get('HasBFrames'),
                    RefFrames=Row.get('RefFrames'),
                    PixelFormat=Row.get('PixelFormat'),
                    Level=Row.get('Level'),
                    AudioChannels=Row.get('AudioChannels'),
                    AudioSampleRate=Row.get('AudioSampleRate'),
                    AudioSampleFormat=Row.get('AudioSampleFormat'),
                    AudioChannelLayout=Row.get('AudioChannelLayout'),
                    AudioCodec=Row.get('AudioCodec'),
                    SubtitleFormats=Row.get('SubtitleFormats'),
                    ContainerFormat=Row.get('ContainerFormat'),
                    OverallBitrate=Row.get('OverallBitrate'),
                    TranscodedByMediaVortex=Row.get('TranscodedByMediaVortex'),
                    AudioLanguages=Row.get('AudioLanguages'),
                    HasExplicitEnglishAudio=Row.get('HasExplicitEnglishAudio'),
                )
                filesWithProfiles.append(mf)

            LoggingService.LogInfo(f"Found {len(filesWithProfiles)} media files with assigned profiles", "QueueManagementBusinessService", "GetMediaFilesWithProfilesOrderedBySize")
            return filesWithProfiles

        except Exception as e:
            LoggingService.LogException("Exception getting media files with profiles", e, "QueueManagementBusinessService", "GetMediaFilesWithProfilesOrderedBySize")
            return []

    def GetMediaFilesByFolderAndResolutionFilter(self, RootFolderPath: str, ProfileId: int) -> List[MediaFileModel]:
        """
        Get media files in a folder that have resolution > target resolution for the specified profile.
        Updates all files in the folder to the selected profile, then returns files where resolution > target.

        Args:
            RootFolderPath: The root folder path to query
            ProfileId: The profile ID to use for resolution filtering

        Returns:
            List of MediaFileModel objects where resolution > target resolution
        """
        try:
            LoggingService.LogFunctionEntry("GetMediaFilesByFolderAndResolutionFilter", "QueueManagementBusinessService", RootFolderPath, ProfileId)

            # Get the profile
            profile = self.DatabaseManager.GetProfileById(ProfileId)
            if not profile:
                LoggingService.LogError(f"Profile with ID {ProfileId} not found", "QueueManagementBusinessService", "GetMediaFilesByFolderAndResolutionFilter")
                return []

            # Get profile thresholds
            profileThresholds = self.DatabaseManager.GetThresholdsByProfileId(ProfileId)
            if not profileThresholds:
                LoggingService.LogWarning(f"No profile thresholds found for profile {profile.ProfileName}", "QueueManagementBusinessService", "GetMediaFilesByFolderAndResolutionFilter")
                return []

            # Step 1: Get target resolution once from profile thresholds
            # Find a threshold with a valid TranscodeDownTo value (use first one found)
            targetResolution = None
            for threshold in profileThresholds:
                transcodeDownTo = threshold.TranscodeDownTo or ""
                if transcodeDownTo and transcodeDownTo.strip() != "" and transcodeDownTo.lower() != "no downscaling":
                    targetResolution = transcodeDownTo.strip()
                    break

            if not targetResolution:
                LoggingService.LogWarning(f"No valid TranscodeDownTo found in profile {profile.ProfileName} thresholds", "QueueManagementBusinessService", "GetMediaFilesByFolderAndResolutionFilter")
                return []

            LoggingService.LogInfo(f"Target resolution for profile {profile.ProfileName}: {targetResolution}", "QueueManagementBusinessService", "GetMediaFilesByFolderAndResolutionFilter")

            # Normalize the root folder path to match database format (handle Z: vs Z:\)
            # Database paths use backslashes: Z:\Videos\Couple\...
            normalizedRootPath = RootFolderPath.replace('/', '\\').strip()
            # Handle drive letter without backslash (Z:Videos -> Z:\Videos)
            if len(normalizedRootPath) >= 2 and normalizedRootPath[1] == ':' and len(normalizedRootPath) > 2 and normalizedRootPath[2] != '\\':
                normalizedRootPath = normalizedRootPath[0:2] + '\\' + normalizedRootPath[2:]
            # Ensure path doesn't end with backslash for LIKE matching (we'll add % in the query)

            LoggingService.LogInfo(f"Normalized root folder path: '{RootFolderPath}' -> '{normalizedRootPath}'", "QueueManagementBusinessService", "GetMediaFilesByFolderAndResolutionFilter")

            # Step 2: Update all files in folder to selected profile (bulk update)
            filesUpdated = self.DatabaseManager.UpdateMediaFilesProfileByRootFolder(normalizedRootPath, ProfileId)
            LoggingService.LogInfo(f"Updated {filesUpdated} files in folder {normalizedRootPath} to profile {profile.ProfileName}", "QueueManagementBusinessService", "GetMediaFilesByFolderAndResolutionFilter")

            # Step 3: Get all media files in the folder (they now all have the profile)
            allMediaFiles = self.DatabaseManager.GetMediaFilesByRootFolder(normalizedRootPath)
            LoggingService.LogInfo(f"Found {len(allMediaFiles)} media files in folder {RootFolderPath}", "QueueManagementBusinessService", "GetMediaFilesByFolderAndResolutionFilter")

            # Step 4: Simple loop - compare each file's resolution to target resolution
            from Services.ResolutionService import ResolutionService
            resolutionService = ResolutionService()
            matchingFiles = []

            # Load ShowSettings for per-show target resolution overrides
            ShowSettingsRepo = None
            try:
                from Features.ShowSettings.ShowSettingsRepository import ShowSettingsRepository
                ShowSettingsRepo = ShowSettingsRepository()
            except Exception:
                pass  # ShowSettings table may not exist yet

            for mediaFile in allMediaFiles:
                sourceResolution = mediaFile.Resolution or ""
                if not sourceResolution:
                    if not self.ProbeAndUpdateMissingMetadata(mediaFile):
                        continue
                    sourceResolution = mediaFile.Resolution or ""
                    if not sourceResolution:
                        continue

                # Check for per-show target resolution override (specific only).
                # The `*` global default does NOT override the profile target
                # here -- profile.TranscodeDownTo is the default. See
                # ShowSettings.feature.md criterion 1.
                FileTargetResolution = targetResolution
                if ShowSettingsRepo:
                    try:
                        ShowOverride = ShowSettingsRepo.GetTargetResolutionForFile(mediaFile.FilePath)
                        if ShowOverride:
                            FileTargetResolution = ShowOverride
                    except Exception:
                        pass

                # Compare file resolution to target resolution
                comparison = resolutionService.CompareResolutions(sourceResolution, FileTargetResolution)

                # If comparison cannot be determined, skip
                if comparison is None:
                    LoggingService.LogWarning(f"Cannot compare resolutions for {mediaFile.FileName}: source={sourceResolution}, target={targetResolution}", "QueueManagementBusinessService", "GetMediaFilesByFolderAndResolutionFilter")
                    continue

                # Only include files where resolution > target (comparison > 0)
                if comparison > 0:
                    matchingFiles.append(mediaFile)
                    LoggingService.LogDebug(f"Including {mediaFile.FileName}: {sourceResolution} > {targetResolution}", "QueueManagementBusinessService", "GetMediaFilesByFolderAndResolutionFilter")
                else:
                    LoggingService.LogDebug(f"Skipping {mediaFile.FileName}: {sourceResolution} <= {targetResolution}", "QueueManagementBusinessService", "GetMediaFilesByFolderAndResolutionFilter")

            # Sort by size (largest first)
            matchingFiles.sort(key=lambda x: x.SizeMB or 0, reverse=True)

            LoggingService.LogInfo(f"Found {len(matchingFiles)} media files with resolution > {targetResolution} for profile {profile.ProfileName} in folder {RootFolderPath}", "QueueManagementBusinessService", "GetMediaFilesByFolderAndResolutionFilter")
            return matchingFiles

        except Exception as e:
            LoggingService.LogException("Exception getting media files by folder and resolution filter", e, "QueueManagementBusinessService", "GetMediaFilesByFolderAndResolutionFilter")
            return []

    def GetMediaFilesByFolderWithResolutionFilterUsingAssignedProfiles(self, RootFolderPath: str) -> List[MediaFileModel]:
        """
        Get media files in a folder that have resolution > target resolution using each file's assigned profile.
        Only includes files that have an assigned profile and pass the resolution check.

        Args:
            RootFolderPath: The root folder path to query

        Returns:
            List of MediaFileModel objects that match the criteria
        """
        try:
            LoggingService.LogFunctionEntry("GetMediaFilesByFolderWithResolutionFilterUsingAssignedProfiles", "QueueManagementBusinessService", RootFolderPath)

            # Get all media files in the folder
            allMediaFiles = self.DatabaseManager.GetMediaFilesByRootFolder(RootFolderPath)
            LoggingService.LogInfo(f"Found {len(allMediaFiles)} media files in folder {RootFolderPath}", "QueueManagementBusinessService", "GetMediaFilesByFolderWithResolutionFilterUsingAssignedProfiles")

            matchingFiles = []

            for mediaFile in allMediaFiles:
                # Skip files without assigned profiles
                if not mediaFile.AssignedProfile or mediaFile.AssignedProfile.strip() == "":
                    LoggingService.LogInfo(f"Skipping {mediaFile.FileName}: no assigned profile", "QueueManagementBusinessService", "GetMediaFilesByFolderWithResolutionFilterUsingAssignedProfiles")
                    continue

                # Probe missing resolution before checking
                if not mediaFile.Resolution:
                    self.ProbeAndUpdateMissingMetadata(mediaFile)

                # Marginal-savings gate (replaces ShouldSkipDueToResolution).
                shouldSkip, skipReason = self.EvaluateQueueAdmissionForProfile(mediaFile, mediaFile.AssignedProfile)
                if shouldSkip:
                    LoggingService.LogDebug(f"Skipping {mediaFile.FileName}: {skipReason}", "QueueManagementBusinessService", "GetMediaFilesByFolderWithResolutionFilterUsingAssignedProfiles")
                    continue

                # File passed resolution check, include it
                matchingFiles.append(mediaFile)

            # Sort by size (largest first)
            matchingFiles.sort(key=lambda x: x.SizeMB or 0, reverse=True)

            LoggingService.LogInfo(f"Found {len(matchingFiles)} media files with resolution > target in folder {RootFolderPath}", "QueueManagementBusinessService", "GetMediaFilesByFolderWithResolutionFilterUsingAssignedProfiles")
            return matchingFiles

        except Exception as e:
            LoggingService.LogException("Exception getting media files by folder with resolution filter using assigned profiles", e, "QueueManagementBusinessService", "GetMediaFilesByFolderWithResolutionFilterUsingAssignedProfiles")
            return []

    def CreateQueueItemFromMediaFileSimple(self, MediaFile: MediaFileModel) -> Optional[TranscodeQueueModel]:
        """Create a queue item directly from a media file without threshold matching."""
        try:
            LoggingService.LogFunctionEntry("CreateQueueItemFromMediaFileSimple", "QueueManagementBusinessService", MediaFile.FileName)

            # Create queue item with basic information
            queueItem = TranscodeQueueModel(
                FilePath=MediaFile.FilePath,
                FileName=MediaFile.FileName,
                Directory=os.path.dirname(MediaFile.FilePath) if MediaFile.FilePath else '',
                SizeBytes=int((MediaFile.SizeMB or 0) * 1024 * 1024),
                SizeMB=MediaFile.SizeMB or 0,
                Priority=self.CalculatePriority(MediaFile),
                Status='Pending',
                DateAdded=datetime.now(timezone.utc)
            )

            LoggingService.LogInfo(f"Created simple queue item for {MediaFile.FileName}", "QueueManagementBusinessService", "CreateQueueItemFromMediaFileSimple")
            return queueItem

        except Exception as e:
            LoggingService.LogException("Exception creating simple queue item", e, "QueueManagementBusinessService", "CreateQueueItemFromMediaFileSimple")
            return None

    def CreateQueueItemFromMediaFileWithProfile(self, MediaFile: MediaFileModel) -> Optional[TranscodeQueueModel]:
        """Create a queue item from a media file that already has an assigned profile."""
        try:
            LoggingService.LogFunctionEntry("CreateQueueItemFromMediaFileWithProfile", "QueueManagementBusinessService", MediaFile.FileName, MediaFile.AssignedProfile)

            # Profile-target priority: look up the matching ProfileThresholds row for
            # this file's resolution and pass bitrates to CalculatePriority. Falls back
            # gracefully if the lookup returns nothing (function logs a warning).
            targetVideoKbps = None
            targetAudioKbps = None
            try:
                profileSettings = self.DatabaseManager.GetProfileSettingsForTargetResolution(
                    MediaFile.AssignedProfile, MediaFile.Resolution
                )
                if profileSettings:
                    targetVideoKbps = profileSettings.get('VideoBitrateKbps')
                    targetAudioKbps = profileSettings.get('AudioBitrateKbps')
            except Exception as Ex:
                LoggingService.LogException(
                    f"Could not look up ProfileThresholds for priority calc on {MediaFile.FileName}",
                    Ex, "QueueManagementBusinessService", "CreateQueueItemFromMediaFileWithProfile"
                )

            priority = self.CalculatePriority(
                MediaFile,
                TargetVideoKbps=targetVideoKbps,
                TargetAudioKbps=targetAudioKbps,
            )

            # Extract directory from file path
            filePath = MediaFile.FilePath or ""
            directory = ""
            fileName = MediaFile.FileName or ""

            if filePath:
                directory = _ParentDir(filePath).replace("\\", "/")
                fileName = _LastSegment(filePath) or fileName

            queueItem = TranscodeQueueModel(
                FilePath=filePath,
                FileName=fileName,
                Directory=directory,
                SizeBytes=int((MediaFile.SizeMB or 0) * 1024 * 1024),
                SizeMB=MediaFile.SizeMB or 0.0,
                Priority=priority,
                Status="Pending",
                DateAdded=datetime.now(timezone.utc)
            )

            LoggingService.LogInfo(f"Created queue item for {fileName} with profile {MediaFile.AssignedProfile} and priority {priority}", "QueueManagementBusinessService", "CreateQueueItemFromMediaFileWithProfile")
            return queueItem

        except Exception as e:
            LoggingService.LogException("Exception creating queue item from media file with profile", e, "QueueManagementBusinessService", "CreateQueueItemFromMediaFileWithProfile")
            return None

    def PopulateQueueForRemux(self, RootFolderPath: str = None) -> Dict[str, Any]:
        """Populate queue with MKV files for remuxing (container change to MP4 only).
        Uses SQL-filtered MKV query and bulk insert for speed."""
        try:
            LoggingService.LogFunctionEntry("PopulateQueueForRemux", "QueueManagementBusinessService", RootFolderPath)

            mkvFiles = self.GetMkvFilesForRemux(RootFolderPath)
            if not mkvFiles:
                friendlyMessage = f"No MKV files found{' in folder ' + RootFolderPath if RootFolderPath else ''} for remuxing."
                return {"Success": False, "ErrorMessage": friendlyMessage, "ItemsAdded": 0}

            # Lightweight duplicate check -- only fetch FilePaths, not full models
            existingFilePaths = self.Repository.GetExistingQueueFilePaths()

            # Separate new items from existing-but-need-mode-switch
            itemsToInsert: List[TranscodeQueueModel] = []
            itemsUpdated = 0

            # For mode-switch we still need to load existing items by path, but only
            # for the intersection (much smaller than loading everything).
            existingQueueByPath: Dict[str, Any] = {}
            NeedModeCheck = [mf for mf in mkvFiles if mf.FilePath in existingFilePaths]
            if NeedModeCheck:
                # Load only the items we need to check for mode switch
                existingQueueItems = self.Repository.GetAllTranscodeQueueItems()
                existingQueueByPath = {item.FilePath: item for item in existingQueueItems}

            for mediaFile in mkvFiles:
                if mediaFile.FilePath in existingFilePaths:
                    existingItem = existingQueueByPath.get(mediaFile.FilePath)
                    if existingItem and existingItem.ProcessingMode != "Remux" and existingItem.Status == "Pending":
                        existingItem.ProcessingMode = "Remux"
                        self.Repository.SaveTranscodeQueueItem(existingItem)
                        itemsUpdated += 1
                        LoggingService.LogInfo(f"Switched queue item {existingItem.Id} ({mediaFile.FileName}) from Transcode to Remux", "QueueManagementBusinessService", "PopulateQueueForRemux")
                    continue

                queueItem = self.CreateRemuxQueueItem(mediaFile)
                if queueItem:
                    itemsToInsert.append(queueItem)
                    existingFilePaths.add(mediaFile.FilePath)

            # Bulk insert all new items in one transaction
            itemsAdded = 0
            if itemsToInsert:
                try:
                    itemsAdded = self.Repository.BulkInsertQueueItems(itemsToInsert)
                except Exception as e:
                    LoggingService.LogException("Bulk insert failed, falling back to per-item insert", e, "QueueManagementBusinessService", "PopulateQueueForRemux")
                    for queueItem in itemsToInsert:
                        try:
                            self.Repository.SaveTranscodeQueueItem(queueItem)
                            itemsAdded += 1
                        except Exception as e2:
                            LoggingService.LogException(f"Error saving remux queue item for {queueItem.FileName}", e2, "QueueManagementBusinessService", "PopulateQueueForRemux")

            details = []
            if itemsAdded > 0:
                details.append(f"{itemsAdded} added")
            if itemsUpdated > 0:
                details.append(f"{itemsUpdated} switched from Transcode to Remux")
            friendlyMessage = f"Remux queue: {', '.join(details)}." if details else "No changes needed - all MKV files already queued for remux."

            return {
                "Success": True,
                "ItemsAdded": itemsAdded,
                "ItemsUpdated": itemsUpdated,
                "Message": friendlyMessage
            }

        except Exception as e:
            errorMsg = f"Exception populating remux queue: {str(e)}"
            LoggingService.LogException(errorMsg, e, "QueueManagementBusinessService", "PopulateQueueForRemux")
            return {"Success": False, "ErrorMessage": errorMsg, "ItemsAdded": 0}

    def GetMkvFilesForRemux(self, RootFolderPath: str = None) -> List[MediaFileModel]:
        """Get MKV media files eligible for remuxing, ordered by size (largest first).
        Uses SQL-side filtering instead of loading all 59K+ rows into Python."""
        try:
            from Core.Database.DatabaseService import DatabaseService, EscapeLikePattern

            WhereClauses = ["LOWER(FileName) LIKE %s"]
            Params: list = ['%.mkv']

            if RootFolderPath:
                NormalizedPath = RootFolderPath.replace('/', '\\').rstrip('\\')
                WhereClauses.append("FilePath LIKE %s ESCAPE '!'")
                Params.append(EscapeLikePattern(NormalizedPath) + '%')

            Sql = f"""
                SELECT Id, StorageRootId, RelativePath, FilePath, FileName, SizeMB,
                       DurationMinutes, Resolution, Codec, ContainerFormat
                FROM MediaFiles
                WHERE {' AND '.join(WhereClauses)}
                ORDER BY SizeMB DESC NULLS LAST
            """
            Rows = DatabaseService().ExecuteQuery(Sql, tuple(Params))

            mkvFiles = []
            for Row in Rows:
                mf = MediaFileModel(
                    Id=Row.get('Id'),
                    StorageRootId=Row.get('StorageRootId'),
                    RelativePath=Row.get('RelativePath') or '',
                    FilePath=Row.get('FilePath', ''),
                    FileName=Row.get('FileName', ''),
                    SizeMB=Row.get('SizeMB') or 0.0,
                    DurationMinutes=Row.get('DurationMinutes'),
                    Resolution=Row.get('Resolution'),
                    Codec=Row.get('Codec'),
                    ContainerFormat=Row.get('ContainerFormat'),
                )
                mkvFiles.append(mf)

            LoggingService.LogInfo(f"Found {len(mkvFiles)} MKV files for remux", "QueueManagementBusinessService", "GetMkvFilesForRemux")
            return mkvFiles

        except Exception as e:
            LoggingService.LogException("Exception getting MKV files for remux", e, "QueueManagementBusinessService", "GetMkvFilesForRemux")
            return []

    def CreateRemuxQueueItem(self, MediaFile: MediaFileModel) -> Optional[TranscodeQueueModel]:
        """Create a queue item for remuxing (container change only)."""
        try:
            filePath = MediaFile.FilePath or ""
            directory = ""
            fileName = MediaFile.FileName or ""

            if filePath:
                directory = _ParentDir(filePath).replace("\\", "/")
                fileName = _LastSegment(filePath) or fileName

            queueItem = TranscodeQueueModel(
                FilePath=filePath,
                FileName=fileName,
                Directory=directory,
                SizeBytes=int((MediaFile.SizeMB or 0) * 1024 * 1024),
                SizeMB=MediaFile.SizeMB or 0.0,
                Priority=self.CalculatePriority(MediaFile),
                Status="Pending",
                ProcessingMode="Remux",
                DateAdded=datetime.now(timezone.utc)
            )

            LoggingService.LogInfo(f"Created remux queue item for {fileName}", "QueueManagementBusinessService", "CreateRemuxQueueItem")
            return queueItem

        except Exception as e:
            LoggingService.LogException("Exception creating remux queue item", e, "QueueManagementBusinessService", "CreateRemuxQueueItem")
            return None

    def FindMatchingProfileThreshold(self, MediaFile: MediaFileModel, ProfileThresholds: List[ProfileThresholdModel], AllowAssignedProfile: bool = False) -> Optional[ProfileThresholdModel]:
        """Find the best matching profile threshold for a media file."""
        try:
            LoggingService.LogFunctionEntry("FindMatchingProfileThreshold", "QueueManagementBusinessService", MediaFile.FileName, MediaFile.Resolution)

            # Use ResolutionService to find matching threshold
            from Services.ResolutionService import ResolutionService
            resolutionService = ResolutionService()
            matchingThreshold = resolutionService.FindMatchingThreshold(MediaFile.Resolution or "", ProfileThresholds)

            # If no exact match and this is a manually assigned profile, use the first available threshold
            if not matchingThreshold and AllowAssignedProfile:
                LoggingService.LogInfo(f"No exact resolution match found for {MediaFile.Resolution}, using first available threshold for manually assigned profile", "QueueManagementBusinessService", "FindMatchingProfileThreshold")
                matchingThreshold = ProfileThresholds[0] if ProfileThresholds else None

            if not matchingThreshold:
                LoggingService.LogDebug(f"No thresholds found for resolution {MediaFile.Resolution}", "QueueManagementBusinessService", "FindMatchingProfileThreshold")
                return None

            # Check if the matching threshold meets the criteria
            durationMinutes = MediaFile.DurationMinutes or 0
            if self.EvaluateThresholdCriteria(MediaFile, matchingThreshold, durationMinutes, AllowAssignedProfile):
                LoggingService.LogInfo(f"Found matching threshold for {MediaFile.FileName}: {matchingThreshold.ProfileId} (Resolution: {matchingThreshold.Resolution}, TranscodeDownTo: {matchingThreshold.TranscodeDownTo})", "QueueManagementBusinessService", "FindMatchingProfileThreshold")
                return matchingThreshold

            LoggingService.LogDebug(f"No matching threshold found for {MediaFile.FileName}", "QueueManagementBusinessService", "FindMatchingProfileThreshold")
            return None

        except Exception as e:
            LoggingService.LogException("Exception finding matching profile threshold", e, "QueueManagementBusinessService", "FindMatchingProfileThreshold")
            return None


    def EvaluateThresholdCriteria(self, MediaFile: MediaFileModel, Threshold: ProfileThresholdModel, DurationMinutes: float, AllowAssignedProfile: bool = False) -> bool:
        """Evaluate if a media file meets the threshold criteria for transcoding."""
        try:
            LoggingService.LogFunctionEntry("EvaluateThresholdCriteria", "QueueManagementBusinessService", MediaFile.FileName, DurationMinutes, Threshold.ProfileId)

            # Check 1: Skip if already transcoded by MediaVortex
            if MediaFile.TranscodedByMediaVortex:
                LoggingService.LogDebug(f"Skipped {MediaFile.FileName}: already transcoded by MediaVortex",
                                       "QueueManagementBusinessService", "EvaluateThresholdCriteria")
                return False

            # Check 2: Skip if source resolution <= target resolution
            try:
                # Get profile name from ProfileId
                profile = self.DatabaseManager.GetProfileById(Threshold.ProfileId)
                if profile and profile.ProfileName:
                    # Marginal-savings gate (replaces ShouldSkipDueToResolution).
                    shouldSkip, reason = self.EvaluateQueueAdmissionForProfile(MediaFile, profile.ProfileName)
                    if shouldSkip:
                        LoggingService.LogDebug(f"Skipped {MediaFile.FileName}: {reason}",
                                               "QueueManagementBusinessService", "EvaluateThresholdCriteria")
                        return False
                else:
                    LoggingService.LogWarning(f"Could not get profile name for ProfileId {Threshold.ProfileId}, skipping admission check",
                                            "QueueManagementBusinessService", "EvaluateThresholdCriteria")
            except Exception as e:
                LoggingService.LogException("Exception checking resolution skip", e, "QueueManagementBusinessService", "EvaluateThresholdCriteria")
                # Continue with other checks if resolution check fails

            # Check file size against threshold based on duration
            fileSizeMB = MediaFile.SizeMB or 0

            if DurationMinutes <= 30:
                thresholdSize = Threshold.Under30MinMB or 0
            elif DurationMinutes <= 65:
                thresholdSize = Threshold.Under65MinMB or 0
            else:
                thresholdSize = Threshold.Over65MinMB or 0

            # File should be larger than threshold to warrant transcoding
            meetsSizeThreshold = fileSizeMB > thresholdSize

            # Check compression potential
            compressionPotential = MediaFile.CompressionPotential or ""
            hasCompressionPotential = compressionPotential.lower() in ['high', 'medium', 'low']

            # Check if already has assigned profile (might indicate it was processed before)
            hasAssignedProfile = MediaFile.AssignedProfile and MediaFile.AssignedProfile.strip()

            # Allow files with assigned profiles if explicitly requested (for manual profile selection)
            profileCheck = not hasAssignedProfile if not AllowAssignedProfile else True

            result = meetsSizeThreshold and hasCompressionPotential and profileCheck

            LoggingService.LogDebug(f"Threshold evaluation for {MediaFile.FileName}: size={fileSizeMB}MB vs {thresholdSize}MB, compression={compressionPotential}, assigned={hasAssignedProfile}, allowAssigned={AllowAssignedProfile} -> {result}", "QueueManagementBusinessService", "EvaluateThresholdCriteria")

            return result

        except Exception as e:
            LoggingService.LogException("Exception evaluating threshold criteria", e, "QueueManagementBusinessService", "EvaluateThresholdCriteria")
            return False

    def CreateQueueItemFromMediaFile(self, MediaFile: MediaFileModel, Threshold: ProfileThresholdModel) -> Optional[TranscodeQueueModel]:
        """Create a queue item from a media file and threshold."""
        try:
            LoggingService.LogFunctionEntry("CreateQueueItemFromMediaFile", "QueueManagementBusinessService", MediaFile.FileName, Threshold.ProfileId)

            # Profile-target priority: pass the threshold's bitrates so CalculatePriority
            # uses the deterministic post-transcode size estimate (see queue-priority.feature.md A2).
            priority = self.CalculatePriority(
                MediaFile,
                TargetVideoKbps=Threshold.VideoBitrateKbps,
                TargetAudioKbps=Threshold.AudioBitrateKbps,
            )

            # Extract directory from file path
            filePath = MediaFile.FilePath or ""
            directory = ""
            fileName = MediaFile.FileName or ""

            if filePath:
                directory = _ParentDir(filePath).replace("\\", "/")
                fileName = _LastSegment(filePath) or fileName

            queueItem = TranscodeQueueModel(
                FilePath=filePath,
                FileName=fileName,
                Directory=directory,
                SizeBytes=int((MediaFile.SizeMB or 0) * 1024 * 1024),
                SizeMB=MediaFile.SizeMB or 0.0,
                Priority=priority,
                Status="Pending",
                DateAdded=datetime.now(timezone.utc)
            )

            LoggingService.LogInfo(f"Created queue item for {fileName} with priority {priority}", "QueueManagementBusinessService", "CreateQueueItemFromMediaFile")
            return queueItem

        except Exception as e:
            LoggingService.LogException("Exception creating queue item", e, "QueueManagementBusinessService", "CreateQueueItemFromMediaFile")
            return None

    def CalculatePriority(self, MediaFile: MediaFileModel,
                          TargetVideoKbps: Optional[int] = None,
                          TargetAudioKbps: Optional[int] = None,
                          SuppressFallbackWarning: bool = False) -> int:
        """Calculate impact-based priority for a queue item, range 1-194.

        See Features/TranscodeQueue/queue-priority.feature.md for the contract.
        Workers claim with ORDER BY Priority DESC, so higher priority is more urgent.
        The 6-slot window 195-200 is reserved for manual user overrides; this
        function never produces a value in that range.

        Inputs:
            MediaFile: source row (uses SizeMB and DurationMinutes)
            TargetVideoKbps / TargetAudioKbps: from the matching ProfileThresholds row
                for the file's resolution category. When BOTH are provided AND
                MediaFile.DurationMinutes is set, the formula uses the deterministic
                profile-target estimate. Otherwise it falls back to SizeMB * 0.5
                with a loud warning (per Phase 2a loud-failure rule).

        Returns int in [1, 194].
        """
        try:
            import math

            sizeMB = MediaFile.SizeMB or 0
            if sizeMB <= 0:
                # NULL or 0 size: no meaningful estimate, lowest non-zero priority.
                return 1

            durationMinutes = MediaFile.DurationMinutes or 0

            if (TargetVideoKbps is not None and TargetAudioKbps is not None
                    and durationMinutes > 0):
                # Profile-target path -- deterministic from configured profile bitrate.
                # target_size_mb = total_kbps * seconds / (8 bits/byte * 1024 KB/MB)
                targetSizeMB = ((TargetVideoKbps + TargetAudioKbps)
                                * durationMinutes * 60.0) / (8 * 1024)
                estimatedSavingsMB = max(0, sizeMB - targetSizeMB)
            else:
                # Fallback path. Loud-failure rule applies at the queue-write
                # caller (one row at a time, operator-visible). Bulk recompute
                # callers pass SuppressFallbackWarning=True and emit a single
                # rolled-up warning at the end.
                if not SuppressFallbackWarning:
                    missing = []
                    if TargetVideoKbps is None or TargetAudioKbps is None:
                        missing.append("ProfileThresholds bitrate")
                    if durationMinutes <= 0:
                        missing.append("MediaFile.DurationMinutes")
                    LoggingService.LogWarning(
                        f"CalculatePriority falling back to size*0.5 for "
                        f"MediaFileId={MediaFile.Id} ({MediaFile.FileName}) -- "
                        f"missing: {', '.join(missing)}",
                        "QueueManagementBusinessService", "CalculatePriority"
                    )
                estimatedSavingsMB = sizeMB * 0.5

            score = math.log10(estimatedSavingsMB + 1)  # 0..5+
            priority = int(round(1 + min(193, (score / 5.0) * 193)))
            priority = max(1, min(194, priority))

            LoggingService.LogDebug(
                f"Priority {priority} for {MediaFile.FileName} "
                f"(size={sizeMB:.0f}MB, savings_est={estimatedSavingsMB:.0f}MB)",
                "QueueManagementBusinessService", "CalculatePriority"
            )
            return priority

        except Exception as e:
            LoggingService.LogException(
                f"Exception calculating priority for MediaFileId={getattr(MediaFile, 'Id', '?')}",
                e, "QueueManagementBusinessService", "CalculatePriority"
            )
            return 1  # Lowest non-zero so the queue item still saves; never 0

    def _LoadPriorityLookupTable(self) -> Dict[tuple, tuple]:
        """Pre-compute {(ProfileName, SourceResolutionCategory): (TargetVideoKbps, TargetAudioKbps, TargetResolutionCategory)}.

        Resolves TranscodeDownTo: when a source resolution downscales to a different
        target, the target's bitrates are returned. The third tuple element is the
        target ResolutionCategory after downscale (same as source if no downscale),
        used by compliance evaluation to detect "this file is above the configured
        downscale target." ProfileThresholds is small (~50 rows), so this is one DB
        round-trip and then everything is in-memory.

        Used by RecomputeForFiles bulk path. Single-file path goes through
        DatabaseManager.GetProfileSettingsForTargetResolution which has additional
        VR-resolution fallback logic.
        """
        from Core.Database.DatabaseService import DatabaseService
        rows = DatabaseService().ExecuteQuery("""
            SELECT p.ProfileName, pt.Resolution, pt.TranscodeDownTo,
                   pt.VideoBitrateKbps, pt.AudioBitrateKbps
            FROM ProfileThresholds pt
            JOIN Profiles p ON pt.ProfileId = p.Id
        """)
        by_profile: Dict[str, Dict[str, tuple]] = {}
        for r in rows:
            pn = r['ProfileName']
            by_profile.setdefault(pn, {})[r['Resolution']] = (
                (r['TranscodeDownTo'] or 'No downscaling'),
                r['VideoBitrateKbps'],
                r['AudioBitrateKbps'],
            )
        lookup: Dict[tuple, tuple] = {}
        for pn, by_res in by_profile.items():
            for src_res, (downto, vk, ak) in by_res.items():
                if downto and downto != 'No downscaling' and downto in by_res:
                    _, target_vk, target_ak = by_res[downto]
                    lookup[(pn, src_res)] = (target_vk, target_ak, downto)
                else:
                    lookup[(pn, src_res)] = (vk, ak, src_res)
        return lookup

    def _LoadDefaultProfileName(self) -> Optional[str]:
        """Read SystemSetting('DefaultProfileName'). One query per recompute call."""
        try:
            from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository
            return SystemSettingsRepository().GetSystemSetting('DefaultProfileName')
        except Exception as Ex:
            LoggingService.LogException(
                "Failed to read SystemSetting('DefaultProfileName'); compliance evaluation will be undecidable",
                Ex, "QueueManagementBusinessService", "_LoadDefaultProfileName"
            )
            return None

    def _LoadShowProfileOverrides(self) -> Dict[str, str]:
        """Return {ShowFolder: AssignedProfile} for shows with a non-NULL override.

        ShowFolder is stored as 'T:\\Survivor' (drive letter + first segment).
        Used by _GetEffectiveProfileFromCache to resolve per-show overrides.
        """
        from Core.Database.DatabaseService import DatabaseService
        try:
            rows = DatabaseService().ExecuteQuery(
                "SELECT ShowFolder, AssignedProfile FROM ShowSettings WHERE AssignedProfile IS NOT NULL"
            )
            return {(r['ShowFolder'] or '').lower(): r['AssignedProfile'] for r in rows if r['ShowFolder']}
        except Exception as Ex:
            LoggingService.LogException(
                "Failed to load ShowSettings overrides; per-show overrides will not apply this cycle",
                Ex, "QueueManagementBusinessService", "_LoadShowProfileOverrides"
            )
            return {}

    @staticmethod
    def _ResolutionCategoryFromPixels(Resolution: Optional[str]) -> Optional[str]:
        """Derive '480p' / '720p' / '1080p' / '2160p' from a 'WIDTHxHEIGHT' string.

        Width-primary because mastering targets are width-fixed (1280 = 720p,
        1920 = 1080p, 3840 = 4K) but heights vary with cropping/letterboxing
        (1280x718 is real broadcast 720p with 2-pixel crop). A strict
        height-based cutoff misclassifies thousands of real files (~7,300
        files in the live DB had height 700-720 misclassified as 480p
        before this fix).

        Falls back to height-based discrimination for narrow/portrait video
        where width-primary would give the wrong answer.

        Returns None on bad input. Used as a fallback in the compliance
        cascade when the cached ResolutionCategory column is NULL.

        Same logic as MediaProbeBusinessService._DeriveResolutionCategory and
        DatabaseManager._ConvertPixelDimensionsToResolutionCategory; the three
        should be unified into a Core helper in a follow-up.
        """
        if not Resolution or 'x' not in Resolution:
            return None
        try:
            Parts = Resolution.split('x', 1)
            Width = int(Parts[0])
            Height = int(Parts[1])
        except (ValueError, IndexError):
            return None
        # Width-primary discrimination (handles broadcast cropping).
        if Width >= 3000:
            return '2160p'
        if Width >= 1700:
            return '1080p'
        if Width >= 1100:
            return '720p'
        if Width >= 600:
            return '480p'
        # Fall through to height for narrow/portrait content.
        if Height >= 2000:
            return '2160p'
        if Height >= 950:
            return '1080p'
        if Height >= 650:
            return '720p'
        return '480p'

    @staticmethod
    def _ExtractShowFolder(FilePath: Optional[str]) -> Optional[str]:
        """Extract 'T:\\Survivor' from 'T:\\Survivor\\Season 1\\file.mkv'. Same shape
        as ShowSettings.ShowFolder so a dict lookup matches without normalization."""
        if not FilePath:
            return None
        from Core.PathNormalize import NormalizeCanonical, ExtractShowFolder
        Normalized = NormalizeCanonical(FilePath)
        Show = ExtractShowFolder(Normalized)
        if Show == 'Unknown':
            return None
        Parts = Normalized.split('\\', 1)
        if not Parts or not Parts[0]:
            return None
        return Parts[0] + '\\' + Show

    def _GetEffectiveProfileFromCache(
        self,
        FilePath: Optional[str],
        ShowOverrides: Dict[str, str],
        DefaultProfileName: Optional[str],
    ) -> Optional[str]:
        """Resolve the cascade: ShowSettings.AssignedProfile -> SystemSettings('DefaultProfileName').

        Pure function over the pre-loaded caches -- no DB calls. Used per row in
        the bulk RecomputeForFiles loop. Returns None if the SystemSetting is
        unset (compliance becomes undecidable).
        """
        ShowFolder = self._ExtractShowFolder(FilePath)
        if ShowFolder:
            Override = ShowOverrides.get(ShowFolder.lower())
            if Override:
                return Override
        return DefaultProfileName

    def _EvaluateCompliance(
        self,
        Row: Dict[str, Any],
        EffectiveProfile: Optional[str],
        Lookup: Dict[tuple, tuple],
        AcceptableVideoCodecs: Optional[set] = None,
        AcceptableContainers: Optional[set] = None,
        AcceptableAudioCodecsMp4: Optional[set] = None,
        MinSavingsMB: Optional[int] = None,
        FloorCfg: Optional[Any] = None,
    ) -> tuple:
        """Pure compliance cascade. Returns (IsCompliant, RecommendedMode).

        Mirrors transcode-vs-remux-routing.feature.md criterion 11 plus the
        audio-completion.feature.md criteria 13-15.

        None for IsCompliant means "undecidable" (hard-block or missing
        inputs); otherwise true/false. RecommendedMode is 'Transcode',
        'Remux', or None.

        Codec / container / audio acceptability, savings threshold, and
        audio bitrate floor are loaded from the data-driven tables
        (`CodecCompatibility`, `QueueAdmissionConfig`). Callers in tight
        loops should pass the pre-loaded sets / config to avoid per-row
        DB round-trips. When omitted, this method loads them fresh per call.
        """
        # Reset transient row flags so stale values from a prior call don't leak.
        Row['_DeferReason'] = None
        Row['_RefusalReason'] = None

        # a. Hard block: no English audio (includes files with zero audio streams)
        if Row.get('HasExplicitEnglishAudio') is False:
            Row['_RefusalReason'] = 'no_english_audio'
            return (None, None)

        # a2. Hard block: AudioCompletionService flagged this row as suspect
        # (no_audio_stream / incompatible_codec_unsupported). The audio cannot
        # be safely re-encoded or stream-copied; surface for operator review.
        if Row.get('AudioCorruptSuspect') is True:
            Row['_RefusalReason'] = 'audio_corrupt_suspect'
            return (None, None)

        # a3. Hard block: probed file with no audio stream at all.
        # Belt-and-suspenders with a2 -- backfill marks these Suspect, but
        # newly-probed rows without a recompute pass yet still need the
        # in-cascade check.
        if Row.get('HasExplicitEnglishAudio') is not None and not Row.get('AudioCodec') and Row.get('Resolution'):
            Row['_RefusalReason'] = 'no_audio_stream'
            return (None, None)

        # a4. Measurement gate (linear-loudnorm.feature.md C9): any file that
        # might run a loudnorm pass (AudioComplete is not True) requires all
        # four ebur128 measurements present. Three sub-states:
        #   LoudnessMeasuredAt IS NULL              -> never attempted; the
        #     probe co-trigger will catch it. AdmissionDeferReason=
        #     'awaiting_loudness_measurement'.
        #   FailureReason IS NOT NULL               -> ebur128 ran and produced
        #     no usable numbers (timeout, decode error, etc.). Needs operator
        #     intervention. AdmissionDeferReason=
        #     'loudness_measurement_failed'.
        #   Measured but Threshold IS NULL          -> pre-threshold-capture
        #     legacy data. The Step 3 backfill (BackfillLoudnessThreshold.py)
        #     will catch up. Treat as 'awaiting' so it surfaces in the same
        #     bucket as never-measured rows.
        if Row.get('AudioComplete') is not True:
            if (Row.get('SourceIntegratedLufs') is None
                    or Row.get('SourceLoudnessRangeLU') is None
                    or Row.get('SourceTruePeakDbtp') is None
                    or Row.get('SourceIntegratedThresholdLufs') is None):
                if Row.get('LoudnessMeasurementFailureReason') is not None:
                    Row['_DeferReason'] = 'loudness_measurement_failed'
                    Row['_RefusalReason'] = 'loudness_measurement_failed'
                else:
                    Row['_DeferReason'] = 'awaiting_loudness_measurement'
                    Row['_RefusalReason'] = 'awaiting_loudness_measurement'
                return (None, None)

        # b. Effective profile cannot be resolved
        if not EffectiveProfile:
            Row['_RefusalReason'] = 'no_effective_profile'
            return (None, None)

        # Lazy-load gate config when caller didn't provide pre-loaded sets.
        if AcceptableVideoCodecs is None:
            AcceptableVideoCodecs = self.CodecCompatibilityRepo.GetAcceptableSet('VideoCodec')
        if AcceptableContainers is None:
            AcceptableContainers = self.CodecCompatibilityRepo.GetAcceptableSet('Container')
        if AcceptableAudioCodecsMp4 is None:
            AcceptableAudioCodecsMp4 = self.CodecCompatibilityRepo.GetAcceptableSet('AudioCodecMp4')
        if MinSavingsMB is None or FloorCfg is None:
            Cfg = self.QueueAdmissionConfigRepo.Get()
            if MinSavingsMB is None:
                MinSavingsMB = Cfg.MinTranscodeSavingsMB
            if FloorCfg is None:
                FloorCfg = Cfg

        # Need a resolution category for the lookup key. Prefer the cached
        # ResolutionCategory column; fall back to deriving from raw Resolution
        # when the cache is NULL (older MediaVortex outputs and pre-cache rows).
        ResKey = Row.get('ResolutionCategory')
        if not ResKey:
            ResKey = self._ResolutionCategoryFromPixels(Row.get('Resolution'))
        if not ResKey:
            Row['_RefusalReason'] = 'no_resolution_category'
            return (None, None)

        Settings = Lookup.get((EffectiveProfile, ResKey))
        if not Settings:
            Row['_RefusalReason'] = 'no_profile_thresholds'
            return (None, None)

        TargetVideoKbps, TargetAudioKbps, TargetResCat = Settings
        if TargetVideoKbps is None or TargetAudioKbps is None:
            Row['_RefusalReason'] = 'no_profile_thresholds'
            return (None, None)

        # Audio bitrate floor guard: a sub-floor source must never go through
        # the Transcode path (audio re-encode would damage already-low-bitrate
        # audio). See audio-completion.feature.md C15.
        from Features.AudioCompletion.AudioCompletionService import AudioCompletionService
        AudioBitrate = Row.get('AudioBitrateKbps')
        AudioChannels = Row.get('AudioChannels')
        BelowAudioFloor = (
            AudioBitrate is not None
            and AudioChannels is not None
            and int(AudioBitrate) <= AudioCompletionService.FloorForChannels(AudioChannels, FloorCfg)
        )

        # Compute the two independent eligibility flags
        # (media-tabs-and-loudness.feature.md C15-C17, revised 2026-05-17).
        ContainerRaw = (Row.get('ContainerFormat') or '').lower()
        ContainerParts = {p.strip() for p in ContainerRaw.split(',') if p.strip()}
        AudioCodec = (Row.get('AudioCodec') or '').lower()
        IsNormalized = Row.get('AudioComplete') is True

        # NeedsQuick: any of these makes the file a Quick Fix candidate
        # (BuildRemuxCommand handles them all in one I/O-bound pass).
        # Audio is only a "needs work" signal when LUFS is measured AND
        # off-target. Without LUFS we don't claim audio needs work --
        # avoids polluting the Quick Fix tab with unconfirmed candidates
        # whose normalize pass might be a no-op (feature criterion 15,
        # revised 2026-05-17 per operator data-driven feedback).
        ContainerWrong = bool(ContainerParts and not (ContainerParts & AcceptableContainers))
        AudioCodecWrong = bool(AudioCodec and AudioCodec not in AcceptableAudioCodecsMp4)
        SourceLufs = Row.get('SourceIntegratedLufs')
        AudioConfirmedOffTarget = (
            (not IsNormalized)
            and SourceLufs is not None
            and (SourceLufs < AudioCompletionService.TARGET_LUFS - AudioCompletionService.TARGET_LUFS_TOLERANCE
                 or SourceLufs > AudioCompletionService.TARGET_LUFS + AudioCompletionService.TARGET_LUFS_TOLERANCE)
        )
        NeedsQuick = ContainerWrong or AudioCodecWrong or AudioConfirmedOffTarget

        # NeedsTranscode: any of these makes the file a Transcode candidate.
        # The bitrate-floor guard prevents thrashing audio quality via
        # generational re-encode; if floor is hit, suppress Transcode signals.
        VideoCodec = (Row.get('Codec') or '').lower()
        VideoCodecWrong = bool(VideoCodec and VideoCodec not in AcceptableVideoCodecs)

        SrcRank = self.RESOLUTION_RANK.get(ResKey, -1)
        TgtRank = self.RESOLUTION_RANK.get(TargetResCat, -1)
        DownscaleNeeded = SrcRank > 0 and TgtRank >= 0 and SrcRank > TgtRank

        SizeMB = Row.get('SizeMB') or 0
        DurationMin = Row.get('DurationMinutes') or 0
        SavingsExceedsThreshold = False
        if SizeMB > 0 and DurationMin > 0 and (TargetVideoKbps or 0) > 0:
            TargetSizeMB = ((TargetVideoKbps + (TargetAudioKbps or 0)) * DurationMin * 60.0) / (8 * 1024)
            SavingsExceedsThreshold = (SizeMB - TargetSizeMB) >= MinSavingsMB

        NeedsTranscode = (VideoCodecWrong or DownscaleNeeded or SavingsExceedsThreshold) and not BelowAudioFloor

        # Persist the flags via Row mutation so RecomputeForFiles can pick
        # them up in the same UPDATE pass without re-evaluating.
        Row['_NeedsQuick'] = NeedsQuick
        Row['_NeedsTranscode'] = NeedsTranscode

        # RecommendedMode is the single "primary" mode for display/badging --
        # Transcode wins for badge purposes when both flags fire (heaviest
        # operation is the most informative summary). Tabs read the flags
        # directly, not RecommendedMode, so a file with both is still
        # offered in the Quick Fix tab.
        if NeedsTranscode:
            if VideoCodecWrong:
                Row['_RefusalReason'] = 'video_codec_not_acceptable'
            elif DownscaleNeeded:
                Row['_RefusalReason'] = 'downscale_needed'
            elif SavingsExceedsThreshold:
                Row['_RefusalReason'] = 'savings_exceeds_threshold'
            else:
                Row['_RefusalReason'] = 'needs_transcode'
            return (False, 'Transcode')
        if NeedsQuick:
            if ContainerWrong:
                Row['_RefusalReason'] = 'container_not_acceptable'
            elif AudioCodecWrong:
                Row['_RefusalReason'] = 'audio_codec_not_acceptable'
            elif AudioConfirmedOffTarget:
                Row['_RefusalReason'] = 'audio_not_normalized'
            else:
                Row['_RefusalReason'] = 'needs_quick'
            return (False, 'Quick')
        return (True, None)

    def EvaluateCandidateCompliance(
        self,
        CandidateRow: Dict[str, Any],
        EffectiveProfile: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Public wrapper over `_EvaluateCompliance` for callers that want to
        ask "would this MediaFile-shaped row admit through the cascade?"
        without joining the bulk RecomputeForFiles loop.

        Owns `compliance-gated-rename.feature.md` criterion 1 (the predicate
        used by FileReplacement's pre-rename gate). Returns a dict for clarity:
            {
              'IsCompliant':     True | False | None,
              'RecommendedMode': 'Transcode' | 'Quick' | None,
              'RefusalReason':   <stable_snake_case_string> | None,
            }
        RefusalReason is None only when IsCompliant is True. For every other
        outcome it carries the specific cascade reason (e.g. 'video_codec_not_acceptable',
        'audio_not_normalized', 'awaiting_loudness_measurement'). Stable enough
        to use as the disposition audit payload.

        EffectiveProfile is resolved via the same cascade RecomputeForFiles uses
        (ShowSettings -> SystemSettings.DefaultProfileName) when not supplied.
        """
        Lookup = self._LoadPriorityLookupTable()
        if EffectiveProfile is None:
            DefaultProfile = self._LoadDefaultProfileName()
            ShowOverrides = self._LoadShowProfileOverrides()
            EffectiveProfile = self._GetEffectiveProfileFromCache(
                CandidateRow.get('FilePath'), ShowOverrides, DefaultProfile
            )
        IsCompliant, RecommendedMode = self._EvaluateCompliance(
            CandidateRow, EffectiveProfile, Lookup,
        )
        return {
            'IsCompliant': IsCompliant,
            'RecommendedMode': RecommendedMode,
            'RefusalReason': CandidateRow.get('_RefusalReason'),
        }

    # ─── Marginal-savings gate (data-driven queue admission) ──────────────
    # Owns marginal-savings-gate.feature.md criteria 1-7. Two collaborators:
    #   EstimateTargetSizeMB -- bitrate formula or CRF lookup
    #   EvaluateQueueAdmission -- upscale + savings checks against config

    def EstimateTargetSizeMB(
        self,
        MediaFile: MediaFileModel,
        ProfileSettings: Dict[str, Any],
    ) -> Tuple[Optional[float], bool]:
        """Estimate the post-transcode size in MB.

        Returns (target_mb, missing_estimate_flag). Branches:

          - Profile.VideoBitrateKbps > 0 -> bitrate formula. Returns (mb, False).
          - Profile.VideoBitrateKbps == 0 (CRF only) -> CrfBitrateEstimates lookup
            keyed on (Codec, TargetResolution, Quality/CRF). Found -> (mb, False);
            not found -> (None, True) -- caller decides admit/block.
          - DurationMinutes <= 0 -> (None, False). Cannot estimate; not a missing-
            estimate problem.
        """
        if not ProfileSettings:
            return (None, False)

        Duration = getattr(MediaFile, 'DurationMinutes', None) or 0
        if Duration <= 0:
            return (None, False)

        VideoKbps = ProfileSettings.get('VideoBitrateKbps') or 0
        AudioKbps = ProfileSettings.get('AudioBitrateKbps') or 0

        if VideoKbps > 0:
            TargetKbps = VideoKbps + (AudioKbps or 0)
            TargetMB = (TargetKbps * Duration * 60.0) / (8.0 * 1024.0)
            return (TargetMB, False)

        # CRF-only profile -- look up the empirical estimate for this
        # (Codec, TargetResolution, CRF) triple.
        Codec = (ProfileSettings.get('Codec') or '').lower()
        TargetResolution = ProfileSettings.get('TargetResolution') or ''
        Crf = ProfileSettings.get('Quality')
        if not Codec or not TargetResolution or Crf is None:
            return (None, True)

        # Normalize TargetResolution -- it may be canonical category ('720p')
        # or a pixel string ('1280x720'). The estimate table keys on category.
        ResolutionCategory = TargetResolution
        if 'x' in str(TargetResolution):
            ResolutionCategory = self._ResolutionCategoryFromPixels(TargetResolution) or TargetResolution

        try:
            CrfInt = int(Crf)
        except (TypeError, ValueError):
            return (None, True)

        EstimatedKbps = self.CrfBitrateEstimateRepo.GetEstimatedKbps(
            Codec, ResolutionCategory, CrfInt
        )
        if EstimatedKbps is None:
            return (None, True)

        TargetMB = (EstimatedKbps * Duration * 60.0) / (8.0 * 1024.0)
        return (TargetMB, False)

    def EvaluateQueueAdmission(
        self,
        MediaFile: MediaFileModel,
        ProfileSettings: Dict[str, Any],
        AdmissionConfig=None,
    ) -> Tuple[bool, str]:
        """Decide whether a file should be admitted to the transcode queue.

        Returns (should_block, reason). When should_block is False, reason is
        empty. When True, reason is one of: 'Upscale', 'MarginalSavings',
        'MissingProfile', 'MissingEstimate'.

        Replaces ShouldSkipDueToResolution. Same-resolution + sufficient-savings
        is admitted; only true upscales (source < target) are hard-blocked.

        AdmissionConfig may be passed in for tight-loop callers; otherwise
        loaded fresh per call.
        """
        if not ProfileSettings:
            return (True, 'MissingProfile')

        if AdmissionConfig is None:
            AdmissionConfig = self.QueueAdmissionConfigRepo.Get()

        # 1. Upscale block: source resolution < target resolution.
        SourceResolution = getattr(MediaFile, 'Resolution', None) or ''
        TargetResolution = ProfileSettings.get('TargetResolution') or ''
        if SourceResolution and TargetResolution:
            try:
                from Services.ResolutionService import ResolutionService
                Cmp = ResolutionService().CompareResolutions(SourceResolution, TargetResolution)
                if Cmp is not None and Cmp < 0:
                    return (True, f"Upscale (source {SourceResolution} < target {TargetResolution})")
            except Exception as Ex:
                LoggingService.LogException(
                    f"Resolution compare failed for {SourceResolution} vs {TargetResolution}",
                    Ex, "QueueManagementBusinessService", "EvaluateQueueAdmission",
                )

        # 2. Estimated savings gate.
        TargetMB, MissingEstimate = self.EstimateTargetSizeMB(MediaFile, ProfileSettings)
        if MissingEstimate:
            if AdmissionConfig.MissingEstimatePolicy == 'block':
                return (True, 'MissingEstimate')
            return (False, '')  # admit fail-open; caller logs rolled-up summary

        if TargetMB is None:
            # Couldn't estimate (e.g. duration unknown). Admit -- duration gaps
            # are surfaced via CalculatePriority's existing fallback warnings.
            return (False, '')

        SourceMB = getattr(MediaFile, 'SizeMB', None) or 0
        if SourceMB <= 0:
            return (False, '')  # no source size to compare against; admit

        EstimatedSavingsMB = SourceMB - TargetMB
        if EstimatedSavingsMB < AdmissionConfig.MinTranscodeSavingsMB:
            return (
                True,
                f"MarginalSavings (source={SourceMB:.0f}MB target={TargetMB:.0f}MB "
                f"savings={EstimatedSavingsMB:.0f}MB threshold={AdmissionConfig.MinTranscodeSavingsMB}MB)",
            )

        return (False, '')

    def EvaluateQueueAdmissionForProfile(
        self,
        MediaFile: MediaFileModel,
        ProfileName: str,
        AdmissionConfig=None,
    ) -> Tuple[bool, str]:
        """Resolve ProfileSettings from ProfileName + MediaFile.Resolution, then
        delegate to EvaluateQueueAdmission. Convenience wrapper for callers that
        only have a profile name -- the four queue-admission entry paths.
        """
        if not ProfileName or not getattr(MediaFile, 'Resolution', None):
            return (True, 'MissingProfile')
        try:
            ProfileSettings = self.DatabaseManager.GetProfileSettingsForTargetResolution(
                ProfileName, MediaFile.Resolution
            )
        except Exception as Ex:
            LoggingService.LogException(
                f"Failed to load ProfileSettings for {ProfileName} / {MediaFile.Resolution}",
                Ex, "QueueManagementBusinessService", "EvaluateQueueAdmissionForProfile",
            )
            return (True, 'MissingProfile')
        return self.EvaluateQueueAdmission(MediaFile, ProfileSettings or {}, AdmissionConfig)

    def ComputePriorityScore(self, MediaFileId: int) -> Optional[int]:
        """Recompute and persist MediaFiles.PriorityScore for a single file.

        Returns the new score, or None if the recompute could not run (in which
        case the existing PriorityScore in the DB is left untouched, per
        priority-materialization.feature.md criterion 15).
        """
        try:
            mediaFile = self.DatabaseManager.GetMediaFileById(MediaFileId)
            if not mediaFile:
                LoggingService.LogWarning(
                    f"ComputePriorityScore: MediaFileId={MediaFileId} not found",
                    "QueueManagementBusinessService", "ComputePriorityScore"
                )
                return None

            targetVideoKbps = None
            targetAudioKbps = None
            if mediaFile.AssignedProfile and mediaFile.Resolution:
                try:
                    profileSettings = self.DatabaseManager.GetProfileSettingsForTargetResolution(
                        mediaFile.AssignedProfile, mediaFile.Resolution
                    )
                    if profileSettings:
                        targetVideoKbps = profileSettings.get('VideoBitrateKbps')
                        targetAudioKbps = profileSettings.get('AudioBitrateKbps')
                except Exception as Ex:
                    LoggingService.LogException(
                        f"ProfileThresholds lookup failed for MediaFileId={MediaFileId}",
                        Ex, "QueueManagementBusinessService", "ComputePriorityScore"
                    )
                    # Fall through to CalculatePriority's fallback path

            score = self.CalculatePriority(mediaFile, TargetVideoKbps=targetVideoKbps, TargetAudioKbps=targetAudioKbps)

            from Core.Database.DatabaseService import DatabaseService
            DatabaseService().ExecuteNonQuery(
                "UPDATE MediaFiles SET PriorityScore = %s WHERE Id = %s",
                (score, MediaFileId)
            )
            return score
        except Exception as Ex:
            LoggingService.LogException(
                f"ComputePriorityScore failed for MediaFileId={MediaFileId}",
                Ex, "QueueManagementBusinessService", "ComputePriorityScore"
            )
            return None

    def RecomputeForFiles(self, MediaFileIds: List[int]) -> int:
        """Bulk-recompute the four cached fields on MediaFiles for the given IDs.

        Computes in a single pass per row:
          - AssignedProfile  (cascade: ShowSettings -> SystemSettings.DefaultProfileName)
          - PriorityScore    (existing impact-based score against the cascade-resolved profile)
          - IsCompliant      (NULL/true/false per the compliance cascade)
          - RecommendedMode  ('Transcode' / 'Remux' / NULL)

        Single round-trip for the rows; one bulk UPDATE FROM VALUES for the writes.
        Replaces the prior ComputePriorityScoresForFiles. Returns rows updated.
        Failures on individual rows do not abort the batch.
        """
        if not MediaFileIds:
            return 0
        try:
            from Core.Database.DatabaseService import DatabaseService
            db = DatabaseService()

            # Load all caches once per call.
            Lookup = self._LoadPriorityLookupTable()
            DefaultProfile = self._LoadDefaultProfileName()
            ShowOverrides = self._LoadShowProfileOverrides()
            # Gate config -- load once, pass through to _EvaluateCompliance per row.
            AcceptableVideoCodecs = self.CodecCompatibilityRepo.GetAcceptableSet('VideoCodec')
            AcceptableContainers = self.CodecCompatibilityRepo.GetAcceptableSet('Container')
            AcceptableAudioCodecsMp4 = self.CodecCompatibilityRepo.GetAcceptableSet('AudioCodecMp4')
            FloorCfg = self.QueueAdmissionConfigRepo.Get()
            MinSavingsMB = FloorCfg.MinTranscodeSavingsMB

            # AudioFix folder pins (media-tabs-and-loudness.feature.md C22).
            # Load once per call; apply per-row to PriorityScore when the file
            # would route to RecommendedMode='AudioFix' and its FilePath matches.
            AudioFixPins = []
            try:
                AudioFixPins = [
                    (P['FolderPattern'].lower(), int(P['BoostedPriority']))
                    for P in db.ExecuteQuery(
                        "SELECT FolderPattern, BoostedPriority FROM AudioFixPriorityHints"
                    )
                ]
            except Exception:
                pass  # table may not exist on older DBs; no-op

            placeholders = ','.join(['%s'] * len(MediaFileIds))
            rows = db.ExecuteQuery(
                f"""
                SELECT Id, FilePath, FileName, SizeMB, DurationMinutes, AssignedProfile,
                       ResolutionCategory, Resolution, Codec, ContainerFormat,
                       AudioCodec, HasExplicitEnglishAudio,
                       AudioComplete, AudioCorruptSuspect, AudioBitrateKbps, AudioChannels,
                       SourceIntegratedLufs, SourceLoudnessRangeLU, SourceTruePeakDbtp,
                       SourceIntegratedThresholdLufs, LoudnessMeasuredAt,
                       LoudnessMeasurementFailureReason
                FROM MediaFiles WHERE Id IN ({placeholders})
                """,
                tuple(MediaFileIds)
            )

            updates = []  # list[(id, profile_or_none, score, is_compliant_or_none, recommended_or_none)]
            NoAudioFiles = []  # list of (FilePath, MediaFileId) for ProblemFile flagging
            for r in rows:
                try:
                    EffectiveProfile = self._GetEffectiveProfileFromCache(
                        r.get('FilePath'), ShowOverrides, DefaultProfile
                    )

                    # Priority calc -- prefer ResolutionCategory, derive from
                    # raw Resolution as fallback (same logic the compliance
                    # cascade uses).
                    ResKey = r.get('ResolutionCategory')
                    if not ResKey:
                        ResKey = self._ResolutionCategoryFromPixels(r.get('Resolution'))
                    TargetVideoKbps = None
                    TargetAudioKbps = None
                    if EffectiveProfile and ResKey:
                        Settings = Lookup.get((EffectiveProfile, ResKey))
                        if Settings:
                            TargetVideoKbps = Settings[0]
                            TargetAudioKbps = Settings[1]

                    class _Row:
                        pass
                    M = _Row()
                    M.Id = r['Id']
                    M.FileName = r.get('FileName')
                    M.SizeMB = r.get('SizeMB') or 0
                    M.DurationMinutes = r.get('DurationMinutes') or 0
                    Score = self.CalculatePriority(
                        M,
                        TargetVideoKbps=TargetVideoKbps,
                        TargetAudioKbps=TargetAudioKbps,
                        SuppressFallbackWarning=True,
                    )

                    # Compliance evaluation -- pre-loaded gate config keeps
                    # this loop's DB round-trips bounded.
                    IsCompliant, RecommendedMode = self._EvaluateCompliance(
                        r, EffectiveProfile, Lookup,
                        AcceptableVideoCodecs=AcceptableVideoCodecs,
                        AcceptableContainers=AcceptableContainers,
                        AcceptableAudioCodecsMp4=AcceptableAudioCodecsMp4,
                        MinSavingsMB=MinSavingsMB,
                        FloorCfg=FloorCfg,
                    )

                    # AudioFix folder-pin boost: when the cascade routes a
                    # file to 'AudioFix' AND its FilePath matches a pinned
                    # folder pattern, override PriorityScore with the max of
                    # (computed score, BoostedPriority). All downstream queue
                    # inserts read m.PriorityScore so the boost propagates.
                    FinalScore = int(Score)
                    if RecommendedMode == 'AudioFix' and AudioFixPins:
                        FilePathLower = (r.get('FilePath') or '').lower()
                        for Pattern, Boost in AudioFixPins:
                            if Pattern and Pattern in FilePathLower:
                                if Boost > FinalScore:
                                    FinalScore = Boost
                                break  # first matching pin wins

                    updates.append((
                        int(r['Id']),
                        EffectiveProfile,
                        FinalScore,
                        IsCompliant,
                        RecommendedMode,
                        bool(r.get('_NeedsQuick', False)),
                        bool(r.get('_NeedsTranscode', False)),
                        r.get('_DeferReason'),
                    ))

                    # Detect probed files with no audio stream (possibly corrupt).
                    # HasExplicitEnglishAudio != None means audio probe ran.
                    if r.get('HasExplicitEnglishAudio') is not None and not r.get('AudioCodec') and r.get('Resolution'):
                        NoAudioFiles.append((r.get('FilePath', ''), int(r['Id'])))

                except Exception as RowEx:
                    LoggingService.LogException(
                        f"Per-row recompute failed for MediaFileId={r.get('Id')}",
                        RowEx, "QueueManagementBusinessService", "RecomputeForFiles"
                    )
                    continue

            # Flag no-audio files as ProblemFiles (likely corrupt).
            if NoAudioFiles:
                from Repositories.DatabaseManager import DatabaseManager
                DM = DatabaseManager()
                for FP, MfId in NoAudioFiles:
                    try:
                        DM.AddProblemFile(
                            FP,
                            'No_Audio_Stream',
                            f'Probed file has no audio stream (video-only). Possibly corrupt. MediaFileId={MfId}'
                        )
                    except Exception:
                        pass  # Best-effort; don't block the recompute batch

            if not updates:
                return 0

            # Bulk UPDATE via VALUES. Quote NULLable text fields properly. id and
            # score are ints (validated). Booleans -> 'true'/'false'/'NULL'.
            def _SqlText(s):
                if s is None:
                    return 'NULL'
                # Escape single quotes to keep the inline VALUES safe. ProfileName
                # comes from Profiles.ProfileName which we control, but defense in
                # depth -- this isn't a tight loop.
                return "'" + str(s).replace("'", "''") + "'"

            def _SqlBool(b):
                if b is None:
                    return 'NULL'
                return 'true' if b else 'false'

            values_clause = ','.join(
                f"({i},{_SqlText(p)},{s},{_SqlBool(ic)},{_SqlText(rm)},{_SqlBool(nq)},{_SqlBool(nt)},{_SqlText(dr)})"
                for i, p, s, ic, rm, nq, nt, dr in updates
            )
            db.ExecuteNonQuery(f"""
                UPDATE MediaFiles
                SET AssignedProfile = v.profile,
                    PriorityScore = v.score,
                    IsCompliant = v.compliant::boolean,
                    RecommendedMode = v.mode,
                    NeedsQuick = v.needs_quick::boolean,
                    NeedsTranscode = v.needs_transcode::boolean,
                    AdmissionDeferReason = v.defer_reason
                FROM (VALUES {values_clause}) AS v(id, profile, score, compliant, mode, needs_quick, needs_transcode, defer_reason)
                WHERE MediaFiles.Id = v.id
            """)
            return len(updates)
        except Exception as Ex:
            LoggingService.LogException(
                f"RecomputeForFiles failed for {len(MediaFileIds)} ids",
                Ex, "QueueManagementBusinessService", "RecomputeForFiles"
            )
            return 0

    def ComputePriorityScoresForFiles(self, MediaFileIds: List[int]) -> int:
        """Backwards-compat alias for RecomputeForFiles.

        Older callers (BackfillPriorityScores.py, queue-time recompute hooks
        added by priority-materialization.feature.md) still use this name. Now
        wired to the unified updater; computes priority + compliance + cached
        AssignedProfile in one pass.
        """
        return self.RecomputeForFiles(MediaFileIds)

    def AddJobToQueue(self, MediaFileId: int, Priority: int = None, ProfileId: int = None, StartTime: str = None, ForceAdd: bool = False) -> Dict[str, Any]:
        """Add a specific media file to the transcoding queue. Simple logic: if it has a profile or user selects one, add it."""
        try:
            LoggingService.LogFunctionEntry("AddJobToQueue", "QueueManagementBusinessService", MediaFileId, Priority)

            # Get media file
            mediaFile = self.DatabaseManager.GetMediaFileById(MediaFileId)
            if not mediaFile:
                errorMsg = f"Media file with ID {MediaFileId} not found"
                LoggingService.LogError(errorMsg, "QueueManagementBusinessService", "AddJobToQueue")
                return {"Success": False, "ErrorMessage": errorMsg}

            # Check if already in queue
            existingQueueItems = self.Repository.GetAllTranscodeQueueItems()
            if any(item.FilePath == mediaFile.FilePath for item in existingQueueItems):
                errorMsg = f"File {mediaFile.FileName} is already in the transcoding queue"
                LoggingService.LogWarning(errorMsg, "QueueManagementBusinessService", "AddJobToQueue")
                return {"Success": False, "ErrorMessage": errorMsg}

            # Handle profile assignment if ProfileId is provided (user selected a profile)
            if ProfileId is not None:
                # Get the profile and update the media file's assigned profile
                profile = self.DatabaseManager.GetProfileById(ProfileId)
                if not profile:
                    errorMsg = f"Profile with ID {ProfileId} not found"
                    LoggingService.LogError(errorMsg, "QueueManagementBusinessService", "AddJobToQueue")
                    return {"Success": False, "ErrorMessage": errorMsg}

                # Update media file's assigned profile
                mediaFile.AssignedProfile = profile.ProfileName
                self.DatabaseManager.SaveMediaFile(mediaFile)
                LoggingService.LogInfo(f"Updated media file {mediaFile.FileName} to use profile {profile.ProfileName}", "QueueManagementBusinessService", "AddJobToQueue")

            # Check if file has a profile (either existing or just assigned)
            if not mediaFile.AssignedProfile or mediaFile.AssignedProfile.strip() == '':
                errorMsg = f"File {mediaFile.FileName} has no profile assigned. Please select a profile first."
                LoggingService.LogWarning(errorMsg, "QueueManagementBusinessService", "AddJobToQueue")
                return {"Success": False, "ErrorMessage": errorMsg}

            # Marginal-savings gate (replaces ShouldSkipDueToResolution). The
            # ForceAdd path bypasses the gate entirely so an operator can pin
            # a same-resolution compression-only re-encode through the manual
            # /AddJob endpoint regardless of estimated savings.
            if not ForceAdd:
                shouldSkip, skipReason = self.EvaluateQueueAdmissionForProfile(mediaFile, mediaFile.AssignedProfile)
                if shouldSkip:
                    errorMsg = f"Cannot add {mediaFile.FileName} to queue: {skipReason}"
                    LoggingService.LogInfo(errorMsg, "QueueManagementBusinessService", "AddJobToQueue")
                    return {"Success": False, "ErrorMessage": errorMsg, "CanOverride": True}
            else:
                LoggingService.LogWarning(f"Force adding {mediaFile.FileName} to queue (admission gate overridden)", "QueueManagementBusinessService", "AddJobToQueue")

            # Check for previous attempts and validate CRF adjustment
            from Services.AdaptiveQualityService import AdaptiveQualityService
            adaptiveService = AdaptiveQualityService(self.DatabaseManager)
            shouldRetranscode, previousAttempt = adaptiveService.ShouldRetranscode(mediaFile.Id)

            if not shouldRetranscode:
                # VMAF >= 80, quality already acceptable - skip retranscode
                skipMsg = f"Quality already acceptable (VMAF >= 80), skipping retranscode for {mediaFile.FileName}"
                LoggingService.LogInfo(skipMsg, "QueueManagementBusinessService", "AddJobToQueue")
                return {
                    "Success": True,
                    "Skipped": True,
                    "Message": "Quality already acceptable, skipping retranscode",
                    "FileName": mediaFile.FileName
                }

            # Check if CRF adjustment would fail
            if previousAttempt:
                previousCRF = previousAttempt.get('Quality')
                vmafScore = previousAttempt.get('VMAF')

                if previousCRF and vmafScore is not None and vmafScore < 80:
                    # Calculate what the adjusted CRF would be
                    adjustedCRF = adaptiveService.CalculateAdjustedCRF(previousCRF, vmafScore)

                    # Validate adjustment
                    minCRF = 15
                    if adjustedCRF < minCRF:
                        # Cannot adjust further - log critical error
                        errorMsg = f"Cannot adjust CRF further for {mediaFile.FileName}: Previous CRF={previousCRF}, VMAF={vmafScore:.2f}, Adjusted CRF={adjustedCRF} would be below minimum {minCRF}"

                        # Extract directory for ProblemFiles
                        import os
                        directory = os.path.dirname(mediaFile.FilePath)

                        # Log to ProblemFiles
                        problemFileId = self.Repository.AddProblemFile(
                            mediaFile.FilePath,
                            "CRF_Adjustment_Failed",
                            f"CRF adjustment failed: Previous CRF={previousCRF}, VMAF={vmafScore:.2f}, Calculated CRF={adjustedCRF} is below minimum threshold (15). Quality threshold unreachable."
                        )

                        if problemFileId:
                            LoggingService.LogError(f"Logged CRF adjustment failure to ProblemFiles (ID: {problemFileId}): {errorMsg}",
                                                  "QueueManagementBusinessService", "AddJobToQueue")

                        return {"Success": False, "ErrorMessage": errorMsg}

            # Create queue item -- use the profile-aware path when the MediaFile
            # has a profile assigned so CalculatePriority can use the deterministic
            # profile-target formula. Falls back to the Simple path otherwise.
            if mediaFile.AssignedProfile:
                queueItem = self.CreateQueueItemFromMediaFileWithProfile(mediaFile)
            else:
                queueItem = self.CreateQueueItemFromMediaFileSimple(mediaFile)
            if not queueItem:
                errorMsg = f"Failed to create queue item for {mediaFile.FileName}"
                LoggingService.LogError(errorMsg, "QueueManagementBusinessService", "AddJobToQueue")
                return {"Success": False, "ErrorMessage": errorMsg}

            # Override priority if specified (operator can set 1-200 explicitly,
            # including the 195-200 manual-override window). Otherwise add a small
            # bonus to acknowledge that the user explicitly clicked + (this file is
            # more important to them than a generic queue-populate batch).
            if Priority is not None:
                queueItem.Priority = Priority
            else:
                # +15 bonus, capped at 194 so auto-assignment never leaks into the
                # manual-override window (195-200 is reserved per queue-priority.feature.md).
                queueItem.Priority = min(194, queueItem.Priority + 15)
                LoggingService.LogInfo(
                    f"Added manual addition bonus (+15, capped at 194) to priority for {mediaFile.FileName}. New priority: {queueItem.Priority}",
                    "QueueManagementBusinessService", "AddJobToQueue"
                )

            # Save to database
            itemId = self.Repository.SaveTranscodeQueueItem(queueItem)

            result = {
                "Success": True,
                "ItemId": itemId,
                "FileName": mediaFile.FileName,
                "Priority": queueItem.Priority
            }

            LoggingService.LogInfo(f"Added job {itemId} to queue for {mediaFile.FileName} with priority {queueItem.Priority}", "QueueManagementBusinessService", "AddJobToQueue")
            return result

        except Exception as e:
            errorMsg = f"Exception adding job to queue: {str(e)}"
            LoggingService.LogException(errorMsg, e, "QueueManagementBusinessService", "AddJobToQueue")
            return {"Success": False, "ErrorMessage": errorMsg}

    def RemoveJobFromQueue(self, ItemId: int) -> Dict[str, Any]:
        """Remove a job from the transcoding queue. If the job is running, kill FFmpeg and clean up first."""
        try:
            LoggingService.LogFunctionEntry("RemoveJobFromQueue", "QueueManagementBusinessService", ItemId)

            # Get queue item to verify it exists
            queueItem = self.Repository.GetTranscodeQueueItemById(ItemId)
            if not queueItem:
                errorMsg = f"Queue item with ID {ItemId} not found"
                LoggingService.LogError(errorMsg, "QueueManagementBusinessService", "RemoveJobFromQueue")
                return {"Success": False, "ErrorMessage": errorMsg}

            # If job is running, kill FFmpeg and clean up associated records first
            if queueItem.Status == "Running":
                LoggingService.LogInfo(f"Cancelling running job {ItemId} ({queueItem.FileName}) before removal",
                                     "QueueManagementBusinessService", "RemoveJobFromQueue")
                self._CancelRunningJob(ItemId, queueItem)

            # Delete from database
            success = self.Repository.DeleteTranscodeQueueItem(ItemId)

            # BUG-0001 criterion 16: any ActiveJobs row still pointing at this
            # QueueId must go with it. _CancelRunningJob covers the Running
            # path; this catches the non-Running residue (e.g. crashed worker
            # left ActiveJobs behind, queue row sat in Failed, user removed it).
            try:
                self.Repository.DatabaseService.ExecuteNonQuery(
                    "DELETE FROM ActiveJobs WHERE ServiceName = %s AND QueueId = %s",
                    ('TranscodeService', ItemId),
                )
            except Exception as e:
                LoggingService.LogException(
                    f"Failed to clean ActiveJobs for removed queue item {ItemId}",
                    e, "QueueManagementBusinessService", "RemoveJobFromQueue",
                )

            if success:
                result = {
                    "Success": True,
                    "ItemId": ItemId,
                    "FileName": queueItem.FileName
                }
                LoggingService.LogInfo(f"Removed job {ItemId} ({queueItem.FileName}) from queue", "QueueManagementBusinessService", "RemoveJobFromQueue")
                return result
            else:
                errorMsg = f"Failed to delete queue item {ItemId}"
                LoggingService.LogError(errorMsg, "QueueManagementBusinessService", "RemoveJobFromQueue")
                return {"Success": False, "ErrorMessage": errorMsg}

        except Exception as e:
            errorMsg = f"Exception removing job from queue: {str(e)}"
            LoggingService.LogException(errorMsg, e, "QueueManagementBusinessService", "RemoveJobFromQueue")
            return {"Success": False, "ErrorMessage": errorMsg}

    def _CancelRunningJob(self, JobId: int, QueueItem) -> None:
        """Kill the FFmpeg process and clean up database records for a running job."""
        try:
            # 1. Kill FFmpeg process via ActiveJobs PID
            activeJobs = self.Repository.GetActiveJobsByService("TranscodeService")
            for activeJob in activeJobs:
                if activeJob.get('QueueId') == JobId:
                    processId = activeJob.get('ProcessId')
                    if processId:
                        try:
                            from Services.ProcessManagementService import ProcessManagementService
                            ProcessManagementService().KillProcess(processId, Graceful=True)
                            LoggingService.LogInfo(f"Killed FFmpeg process {processId} for job {JobId}",
                                                 "QueueManagementBusinessService", "_CancelRunningJob")
                        except Exception as e:
                            LoggingService.LogException(f"Error killing FFmpeg process {processId}", e,
                                                      "QueueManagementBusinessService", "_CancelRunningJob")

                    # Mark ActiveJob as failed/cancelled
                    self.Repository.CompleteActiveJob(activeJob['Id'], False, "Cancelled by user - job removed from queue")
                    break

            # 2. Mark TranscodeAttempts as cancelled
            try:
                self.Repository.DatabaseService.ExecuteNonQuery(
                    "UPDATE TranscodeAttempts SET Success = FALSE, ErrorMessage = 'Cancelled by user' WHERE MediaFileId = %s AND Success IS NULL",
                    (QueueItem.MediaFileId,)
                )
            except Exception as e:
                LoggingService.LogException(f"Error updating TranscodeAttempts for job {JobId}", e,
                                          "QueueManagementBusinessService", "_CancelRunningJob")

            # 3. Clean up TranscodeProgress records
            try:
                self.Repository.DatabaseService.ExecuteNonQuery(
                    """DELETE FROM TranscodeProgress WHERE TranscodeAttemptId IN (
                        SELECT Id FROM TranscodeAttempts WHERE MediaFileId = %s AND Success = FALSE
                    )""",
                    (QueueItem.MediaFileId,)
                )
            except Exception as e:
                LoggingService.LogException(f"Error cleaning TranscodeProgress for job {JobId}", e,
                                          "QueueManagementBusinessService", "_CancelRunningJob")

            LoggingService.LogInfo(f"Cleaned up running job {JobId} ({QueueItem.FileName})",
                                 "QueueManagementBusinessService", "_CancelRunningJob")

        except Exception as e:
            LoggingService.LogException(f"Error cancelling running job {JobId}", e,
                                      "QueueManagementBusinessService", "_CancelRunningJob")

    def PrioritizeJob(self, ItemId: int, NewPriority: int) -> Dict[str, Any]:
        """Update the priority of a queue item."""
        try:
            LoggingService.LogFunctionEntry("PrioritizeJob", "QueueManagementBusinessService", ItemId, NewPriority)

            # Validate priority range. Auto-assigned values land in [1, 194];
            # the manual-override window is [195, 200] (queue-priority.feature.md
            # criterion 6). The 1-100 check this used to have was left over
            # from the pre-impact-based-priority era and should have been
            # raised when the controller bound was raised to 200.
            if NewPriority < 1 or NewPriority > 200:
                errorMsg = f"Priority must be between 1 and 200, got {NewPriority}"
                LoggingService.LogError(errorMsg, "QueueManagementBusinessService", "PrioritizeJob")
                return {"Success": False, "ErrorMessage": errorMsg}

            # Get queue item
            queueItem = self.Repository.GetTranscodeQueueItemById(ItemId)
            if not queueItem:
                errorMsg = f"Queue item with ID {ItemId} not found"
                LoggingService.LogError(errorMsg, "QueueManagementBusinessService", "PrioritizeJob")
                return {"Success": False, "ErrorMessage": errorMsg}

            # Update priority
            oldPriority = queueItem.Priority
            queueItem.Priority = NewPriority

            self.Repository.SaveTranscodeQueueItem(queueItem)

            result = {
                "Success": True,
                "ItemId": ItemId,
                "OldPriority": oldPriority,
                "NewPriority": NewPriority,
                "FileName": queueItem.FileName
            }

            LoggingService.LogInfo(f"Updated priority for job {ItemId} ({queueItem.FileName}) from {oldPriority} to {NewPriority}", "QueueManagementBusinessService", "PrioritizeJob")
            return result

        except Exception as e:
            errorMsg = f"Exception prioritizing job: {str(e)}"
            LoggingService.LogException(errorMsg, e, "QueueManagementBusinessService", "PrioritizeJob")
            return {"Success": False, "ErrorMessage": errorMsg}

    def GetQueueStatistics(self) -> Dict[str, Any]:
        """Get current queue statistics."""
        try:
            LoggingService.LogFunctionEntry("GetQueueStatistics", "QueueManagementBusinessService")

            statistics = self.Repository.GetQueueStatistics()

            # Add additional business logic statistics
            allQueueItems = self.Repository.GetAllTranscodeQueueItems()

            # Calculate average priority
            if allQueueItems:
                totalPriority = sum(item.Priority for item in allQueueItems)
                statistics["AveragePriority"] = totalPriority / len(allQueueItems)
            else:
                statistics["AveragePriority"] = 0.0

            # Calculate total queue size in MB
            totalSizeMB = sum(item.SizeMB for item in allQueueItems)
            statistics["TotalQueueSizeMB"] = totalSizeMB
            statistics["TotalQueueSizeGB"] = totalSizeMB / 1024.0

            # Reduced logging verbosity for routine queue statistics
            return statistics

        except Exception as e:
            LoggingService.LogException("Exception getting queue statistics", e, "QueueManagementBusinessService", "GetQueueStatistics")
            return {}

    def ProbeAndUpdateMissingMetadata(self, MediaFile: MediaFileModel) -> bool:
        """FFprobe a media file that has no resolution, update the DB, and set fields on the model.
        Returns True if resolution was successfully obtained, False otherwise."""
        try:
            FilePath = MediaFile.FilePath or ""
            if not FilePath or not _LocalExists(FilePath):
                LoggingService.LogWarning(f"Cannot probe {MediaFile.FileName}: file not found at {FilePath}", "QueueManagementBusinessService", "ProbeAndUpdateMissingMetadata")
                return False

            LoggingService.LogInfo(f"Probing missing metadata for {MediaFile.FileName}", "QueueManagementBusinessService", "ProbeAndUpdateMissingMetadata")
            MetadataResult = self.FileManager.ExtractMediaMetadata(FilePath)

            if not MetadataResult.get('Success', False):
                ErrorMessage = MetadataResult.get('ErrorMessage', 'Unknown error')
                LoggingService.LogWarning(f"FFprobe failed for {MediaFile.FileName}: {ErrorMessage}", "QueueManagementBusinessService", "ProbeAndUpdateMissingMetadata")
                return False

            # Map metadata fields onto the model (mirrors FileScanningBusinessService.ExtractAndUpdateMetadata)
            MediaFile.VideoBitrateKbps = MetadataResult.get('VideoBitrateKbps')
            MediaFile.AudioBitrateKbps = MetadataResult.get('AudioBitrateKbps')
            MediaFile.Resolution = MetadataResult.get('Resolution')
            MediaFile.Codec = MetadataResult.get('VideoCodec')
            MediaFile.DurationMinutes = MetadataResult.get('DurationMinutes')
            MediaFile.FrameRate = MetadataResult.get('FrameRate')
            MediaFile.TotalFrames = MetadataResult.get('TotalFrames')
            MediaFile.CodecProfile = MetadataResult.get('CodecProfile')
            MediaFile.ColorRange = MetadataResult.get('ColorRange')
            MediaFile.FieldOrder = MetadataResult.get('FieldOrder')
            MediaFile.HasBFrames = MetadataResult.get('HasBFrames')
            MediaFile.RefFrames = MetadataResult.get('RefFrames')
            MediaFile.PixelFormat = MetadataResult.get('PixelFormat')
            MediaFile.Level = MetadataResult.get('Level')
            MediaFile.AudioChannels = MetadataResult.get('AudioChannels')
            MediaFile.AudioSampleRate = MetadataResult.get('AudioSampleRate')
            MediaFile.AudioSampleFormat = MetadataResult.get('AudioSampleFormat')
            MediaFile.AudioChannelLayout = MetadataResult.get('AudioChannelLayout')
            MediaFile.AudioCodec = MetadataResult.get('AudioCodec')
            MediaFile.SubtitleFormats = MetadataResult.get('SubtitleFormats')
            MediaFile.ContainerFormat = MetadataResult.get('ContainerFormat')
            MediaFile.OverallBitrate = MetadataResult.get('OverallBitrate')

            # Persist to DB
            self.DatabaseManager.SaveMediaFile(MediaFile)

            if MediaFile.Resolution:
                LoggingService.LogInfo(f"Probed and updated {MediaFile.FileName}: Resolution={MediaFile.Resolution}", "QueueManagementBusinessService", "ProbeAndUpdateMissingMetadata")
                return True
            else:
                LoggingService.LogWarning(f"Probed {MediaFile.FileName} but resolution still empty", "QueueManagementBusinessService", "ProbeAndUpdateMissingMetadata")
                return False

        except Exception as e:
            LoggingService.LogException(f"Exception probing metadata for {MediaFile.FileName}", e, "QueueManagementBusinessService", "ProbeAndUpdateMissingMetadata")
            return False

    # ShouldSkipDueToResolution removed 2026-05-10 -- replaced by
    # EvaluateQueueAdmissionForProfile / EvaluateQueueAdmission per
    # marginal-savings-gate.feature.md. Same-resolution + sufficient-savings
    # is now admitted; only true upscales and marginal-savings cases are
    # blocked.

    def GetMkvFileCount(self) -> int:
        """Get count of MKV files in the database."""
        try:
            mkvFiles = self.GetMkvFilesForRemux()
            return len(mkvFiles)
        except Exception as e:
            LoggingService.LogException("Exception getting MKV file count", e, "QueueManagementBusinessService", "GetMkvFileCount")
            return 0

    def PopulateQueueForSubtitleFix(self, FileIds: list = None) -> Dict[str, Any]:
        """Queue specific files (by MediaFile ID) or all eligible files for subtitle fix processing.
        Eligible = has ASS/SSA subtitle formats and is not already in queue."""
        try:
            LoggingService.LogFunctionEntry("PopulateQueueForSubtitleFix", "QueueManagementBusinessService", FileIds)

            if FileIds:
                # Queue specific files by ID
                mediaFiles = []
                for fileId in FileIds:
                    mf = self.DatabaseManager.GetMediaFileById(fileId)
                    if mf:
                        mediaFiles.append(mf)
            else:
                # Find all eligible files: SubtitleFormats contains ass or ssa
                mediaFiles = self._GetSubtitleFixEligibleFiles()

            if not mediaFiles:
                return {"Success": False, "ErrorMessage": "No eligible files found for subtitle fix.", "ItemsAdded": 0}

            # Get existing queue items to avoid duplicates
            existingQueueItems = self.Repository.GetAllTranscodeQueueItems()
            existingFilePaths = {item.FilePath for item in existingQueueItems}

            itemsAdded = 0
            itemsSkipped = 0

            for mediaFile in mediaFiles:
                if mediaFile.FilePath in existingFilePaths:
                    itemsSkipped += 1
                    continue

                queueItem = TranscodeQueueModel(
                    FilePath=mediaFile.FilePath,
                    FileName=mediaFile.FileName,
                    Directory=os.path.dirname(mediaFile.FilePath) if mediaFile.FilePath else '',
                    SizeBytes=int((mediaFile.SizeMB or 0) * 1024 * 1024),
                    SizeMB=mediaFile.SizeMB or 0.0,
                    Priority=self.CalculatePriority(mediaFile),
                    Status="Pending",
                    ProcessingMode="SubtitleFix",
                    DateAdded=datetime.now(timezone.utc)
                )

                try:
                    itemId = self.Repository.SaveTranscodeQueueItem(queueItem)
                    LoggingService.LogInfo(f"Added subtitle fix queue item {itemId} for {mediaFile.FileName}", "QueueManagementBusinessService", "PopulateQueueForSubtitleFix")
                    itemsAdded += 1
                    existingFilePaths.add(mediaFile.FilePath)
                except Exception as e:
                    LoggingService.LogException(f"Error saving subtitle fix queue item for {mediaFile.FileName}", e, "QueueManagementBusinessService", "PopulateQueueForSubtitleFix")

            if itemsAdded > 0:
                friendlyMessage = f"Added {itemsAdded} files to queue for subtitle fix."
            else:
                friendlyMessage = "No new files added — all eligible files are already in the queue."
            if itemsSkipped > 0:
                friendlyMessage += f" {itemsSkipped} skipped (already queued)."

            return {"Success": True, "ItemsAdded": itemsAdded, "ItemsSkipped": itemsSkipped, "Message": friendlyMessage}

        except Exception as e:
            errorMsg = f"Exception populating subtitle fix queue: {str(e)}"
            LoggingService.LogException(errorMsg, e, "QueueManagementBusinessService", "PopulateQueueForSubtitleFix")
            return {"Success": False, "ErrorMessage": errorMsg, "ItemsAdded": 0}

    def _GetSubtitleFixEligibleFiles(self) -> List[MediaFileModel]:
        """Find MediaFiles where SubtitleFormats contains ASS or SSA (burn-in candidates)."""
        try:
            allMediaFiles = self.DatabaseManager.GetAllMediaFiles()
            burnInCodecs = {'ass', 'ssa'}
            eligible = []
            for mf in allMediaFiles:
                subFormats = (mf.SubtitleFormats or "").lower()
                if any(codec in subFormats for codec in burnInCodecs):
                    eligible.append(mf)
            eligible.sort(key=lambda x: x.SizeMB or 0, reverse=True)
            LoggingService.LogInfo(f"Found {len(eligible)} files eligible for subtitle fix", "QueueManagementBusinessService", "_GetSubtitleFixEligibleFiles")
            return eligible
        except Exception as e:
            LoggingService.LogException("Exception getting subtitle fix eligible files", e, "QueueManagementBusinessService", "_GetSubtitleFixEligibleFiles")
            return []

    def GetNextJob(self) -> Optional[TranscodeQueueModel]:
        """Get the next job to process from the queue."""
        try:
            LoggingService.LogFunctionEntry("GetNextJob", "QueueManagementBusinessService")

            # Get pending jobs ordered by priority and date
            pendingJobs = self.Repository.GetTranscodeQueueItemsByStatus("Pending")

            if not pendingJobs:
                LoggingService.LogInfo("No pending jobs in queue", "QueueManagementBusinessService", "GetNextJob")
                return None

            # Sort by priority (descending) then by date (ascending)
            pendingJobs.sort(key=lambda x: (-x.Priority, x.DateAdded))

            nextJob = pendingJobs[0]
            LoggingService.LogInfo(f"Next job: {nextJob.FileName} (ID: {nextJob.Id}, Priority: {nextJob.Priority})", "QueueManagementBusinessService", "GetNextJob")
            return nextJob

        except Exception as e:
            LoggingService.LogException("Exception getting next job", e, "QueueManagementBusinessService", "GetNextJob")
            return None
