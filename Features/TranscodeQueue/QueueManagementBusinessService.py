from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timezone
import os
import ntpath
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
from Core.Path import Path, PathError
from Core.Path.LocalPath import LocalExists
from Services.FileManagerService import FileManagerService
from Repositories.DatabaseManager import DatabaseManager
from Features.Profiles.ProfileRepository import ProfileRepository
# directive: transcode-worker-unification | # see profiles.C23
from Features.Profiles.EffectiveProfileResolver import EffectiveProfileResolver


# directive: path-class-perfection | # see path.C18
def _GetStorageRoots() -> List[dict]:
    """Fresh-per-call StorageRoots prefix list; delegates to Core.Path.PathStorageRoots (no module cache; db-is-authority)."""
    from Core.Path.PathStorageRoots import GetStorageRoots
    return GetStorageRoots()


# directive: path-schema-migration | # see path.S8
def _ResolveFolderToTypedPair(FolderPath: str) -> Tuple[Optional[int], str]:
    """Parse a legacy folder display path into (StorageRootId, RelativePath); (None, '') on no prefix match."""
    if not FolderPath:
        return (None, '')
    try:
        P = Path.FromLegacyString(FolderPath, _GetStorageRoots())
        return (P.StorageRootId, P.RelativePath)
    except PathError:
        return (None, '')


# directive: path-schema-migration | # see path.S8
def _ResolveStorageRootIdForDrivePrefixFn(DrivePrefix: str) -> Optional[int]:
    """Resolve a 'X:' style drive prefix to its StorageRootId; None if no match."""
    if not DrivePrefix:
        return None
    Needle = DrivePrefix.upper().rstrip('\\/')
    for Sr in _GetStorageRoots():
        Prefix = (Sr.get("CanonicalPrefix") or "").upper().rstrip('\\/')
        if Prefix and Prefix == Needle:
            return Sr.get("Id")
    return None


class QueueManagementBusinessService:
    """Handles transcoding queue operations and population logic."""

    # see marginal-savings-gate.feature.md -- resolution rank for downscale check; savings threshold + codec acceptability in DB tables.
    RESOLUTION_RANK = {'480p': 0, '720p': 1, '1080p': 2, '2160p': 3}

    # directive: transcode-worker-unification | # see profiles.C24
    def __init__(self, RepositoryInstance: TranscodeQueueRepository = None, ProfileRepositoryInstance: Optional[ProfileRepository] = None):
        self.Repository = RepositoryInstance or TranscodeQueueRepository()
        self.DatabaseManager = DatabaseManager()
        self.FileManager = FileManagerService()
        # Data-driven gate config per marginal-savings-gate.feature.md; no in-memory caching.
        self.CrfBitrateEstimateRepo = CrfBitrateEstimateRepository()
        self.QueueAdmissionConfigRepo = QueueAdmissionConfigRepository()
        self.CodecCompatibilityRepo = CodecCompatibilityRepository()
        self.ProfileRepository = ProfileRepositoryInstance or ProfileRepository()
        self.Resolver = EffectiveProfileResolver()

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

            # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C10
            from Features.QualityTesting.Disposition.RetranscodeDecider import RetranscodeDecider
            from Features.TranscodeJob.Adjustments.AdjustmentRegistry import AdjustmentRegistry
            retranscodeDecider = RetranscodeDecider(AttemptRepository=self.DatabaseManager)
            adjustmentRegistry = AdjustmentRegistry()

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
                    shouldRetranscode, previousAttempt = retranscodeDecider.Decide(mediaFile.Id)

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
                            adjustedCRF = adjustmentRegistry.Get('cq').Calculate(
                                PreviousAttempt={'Quality': previousCRF, 'VMAF': vmafScore},
                                ProfileSettings={}, GateThreshold=80.0,
                            ).CRF

                            # Validate adjustment
                            minCRF = 15
                            if adjustedCRF < minCRF:
                                # Cannot adjust further - log critical error and skip
                                errorMsg = f"Cannot adjust CRF further for {mediaFile.FileName}: Previous CRF={previousCRF}, VMAF={vmafScore:.2f}, Adjusted CRF={adjustedCRF} would be below minimum {minCRF}"

                                # Extract directory for ProblemFiles
                                directory = ntpath.dirname(mediaFile.FilePath)  # canonical display

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
        """Untranscoded MediaFiles ranked by PriorityScore; optional Drive/Search/Mode filters scope by MediaFiles.WorkBucket; see transcode.flow.md ST3.5 + transcode-vs-remux-routing.feature.md C4."""
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

            # directive: failure-accounting | # see failure-accounting.C6
            from Core.Database.FailureBudgetPredicate import BuildCapPredicate
            CapPredicateFragment, _CapParams = BuildCapPredicate("m.Id")
            Params = []
            WhereSql = (
                " WHERE m.TranscodedByMediaVortex IS NOT TRUE "
                "AND m.Id NOT IN (SELECT MediaFileId FROM TranscodeQueue WHERE MediaFileId IS NOT NULL) "
                "AND m.SizeMB > 0 "
                "AND (m.HasExplicitEnglishAudio IS NULL OR m.HasExplicitEnglishAudio = true) "
                "AND " + CapPredicateFragment
            )

            # directive: transcode-flow-canonical | # see transcode.ST2
            from Features.TranscodeJob import ProcessingModeMetadata
            _AdmissionMeta = ProcessingModeMetadata.Get(Mode)
            if _AdmissionMeta and _AdmissionMeta.get('WorkBucketFilterSql'):
                WhereSql += " AND " + _AdmissionMeta['WorkBucketFilterSql']

            if Drive:
                DrivePrefix = Drive.rstrip(':\\/') + ':'
                DriveStorageRootId = _ResolveStorageRootIdForDrivePrefixFn(DrivePrefix)
                if DriveStorageRootId is None:
                    LoggingService.LogInfo(f"SmartPopulateQueue: Drive {Drive!r} did not match any StorageRoot; returning empty", "QueueManagementBusinessService", "SmartPopulateQueue")
                    return {"Success": True, "Suggestions": [], "TotalCandidates": 0, "Offset": Offset, "Limit": Limit, "Search": Search or '', "Mode": Mode if ProcessingModeMetadata.IsKnown(Mode) else None, "HasMore": False}
                WhereSql += " AND m.StorageRootId = %s"
                Params.append(DriveStorageRootId)

            if Search and Search.strip():
                # directive: path-schema-migration | # see path.S8
                Term = '%' + EscapeLikePattern(Search.strip().lower()) + '%'
                WhereSql += (
                    " AND (LOWER(m.FileName) LIKE %s ESCAPE '!'"
                    "      OR LOWER(SPLIT_PART(COALESCE(m.RelativePath, ''), '/', 1)) LIKE %s ESCAPE '!')"
                )
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
            if _AdmissionMeta and _AdmissionMeta.get('SupportsFocus'):
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

            # directive: path-schema-migration | # see path.S8
            Sql = (
                "SELECT m.Id, m.StorageRootId, m.RelativePath, m.FileName, m.SizeMB, m.VideoBitrateKbps, "
                "m.Codec, m.Resolution, m.ResolutionCategory, m.ContainerFormat, "
                "m.PriorityScore, m.AudioCodec, m.AudioComplete, "
                "m.SourceIntegratedLufs, m.SourceLoudnessRangeLU "
                "FROM MediaFiles m"
                + WhereSql +
                " ORDER BY " + FocusSql + "m.PriorityScore DESC NULLS LAST, m.SizeMB DESC NULLS LAST "
                "LIMIT " + str(int(Limit)) + " OFFSET " + str(int(Offset))
            )
            Rows = DatabaseService().ExecuteQuery(Sql, ParamsTuple)

            _SmartPrefixes = {Sr["Id"]: Sr["CanonicalPrefix"] for Sr in _GetStorageRoots()}
            Suggestions = []
            for Row in Rows:
                _Sid = Row.get('StorageRootId')
                _Rel = Row.get('RelativePath')
                try:
                    FilePath = Path(_Sid, _Rel or '').CanonicalDisplay(_SmartPrefixes) if _Sid is not None else ''
                except PathError:
                    FilePath = ''
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
                    'Mode': Mode if ProcessingModeMetadata.IsKnown(Mode) else 'Transcode',
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
                "Mode": Mode if ProcessingModeMetadata.IsKnown(Mode) else None,
                "HasMore": (Offset + len(Suggestions)) < TotalCandidates,
            }
            LoggingService.LogInfo(f"SmartPopulate: fetched {len(Rows)} of {TotalCandidates} candidates (offset={Offset}, search='{Search or ''}')", "QueueManagementBusinessService", "SmartPopulateQueue")
            return Result

        except Exception as Ex:
            ErrorMsg = f"Exception in SmartPopulateQueue: {str(Ex)}"
            LoggingService.LogException(ErrorMsg, Ex, "QueueManagementBusinessService", "SmartPopulateQueue")
            return {"Success": False, "ErrorMessage": ErrorMsg, "Suggestions": []}

    def NextTranscodeBatch(self, Limit: int = 100, Offset: int = 0, Drive: str = '',
                            Search: Optional[str] = None) -> Dict[str, Any]:
        """Largest non-compliant transcode candidates -- WHERE WorkBucket='Transcode' ORDER BY SizeMB DESC."""
        try:
            LoggingService.LogFunctionEntry("NextTranscodeBatch", "QueueManagementBusinessService", Limit, Offset, Drive, Search)
            from Core.Database.DatabaseService import DatabaseService, EscapeLikePattern

            try:
                Limit = max(1, min(1000, int(Limit)))
            except (TypeError, ValueError):
                Limit = 100
            try:
                Offset = max(0, int(Offset))
            except (TypeError, ValueError):
                Offset = 0

            Params: List[Any] = []
            # directive: failure-accounting | # see failure-accounting.C6
            from Core.Database.FailureBudgetPredicate import BuildCapPredicate
            CapPredicateFragment, _CapParams = BuildCapPredicate("m.Id")
            WhereSql = (
                " WHERE m.WorkBucket = 'Transcode' "
                "AND m.Id NOT IN (SELECT MediaFileId FROM TranscodeQueue WHERE MediaFileId IS NOT NULL) "
                "AND m.SizeMB > 0 "
                "AND m.HasExplicitEnglishAudio IS NOT FALSE "
                "AND " + CapPredicateFragment
            )

            if Drive:
                DrivePrefix = Drive.rstrip(':\\/') + ':'
                DriveStorageRootId = _ResolveStorageRootIdForDrivePrefixFn(DrivePrefix)
                if DriveStorageRootId is None:
                    LoggingService.LogInfo(f"NextTranscodeBatch: Drive {Drive!r} did not match any StorageRoot; returning empty", "QueueManagementBusinessService", "NextTranscodeBatch")
                    return {"Success": True, "Suggestions": [], "TotalCandidates": 0, "Offset": Offset, "Limit": Limit, "Search": Search or '', "HasMore": False}
                WhereSql += " AND m.StorageRootId = %s"
                Params.append(DriveStorageRootId)

            if Search and Search.strip():
                Term = '%' + EscapeLikePattern(Search.strip().lower()) + '%'
                WhereSql += (
                    " AND (LOWER(m.FileName) LIKE %s ESCAPE '!'"
                    "      OR LOWER(SPLIT_PART(COALESCE(m.RelativePath, ''), '/', 1)) LIKE %s ESCAPE '!')"
                )
                Params.append(Term)
                Params.append(Term)

            Sql = (
                "SELECT m.Id, m.StorageRootId, m.RelativePath, m.FileName, m.SizeMB, m.VideoBitrateKbps, "
                "m.Codec, m.Resolution, m.ResolutionCategory, m.ContainerFormat, "
                "COUNT(*) OVER() AS TotalCount "
                "FROM MediaFiles m"
                + WhereSql +
                " ORDER BY m.SizeMB DESC NULLS LAST "
                "LIMIT " + str(int(Limit)) + " OFFSET " + str(int(Offset))
            )
            Rows = DatabaseService().ExecuteQuery(Sql, tuple(Params))

            TotalCandidates = int(Rows[0].get('TotalCount', 0)) if Rows else 0

            _Prefixes = {Sr["Id"]: Sr["CanonicalPrefix"] for Sr in _GetStorageRoots()}
            Suggestions = []
            for Row in Rows:
                _Sid = Row.get('StorageRootId')
                _Rel = Row.get('RelativePath')
                try:
                    FilePath = Path(_Sid, _Rel or '').CanonicalDisplay(_Prefixes) if _Sid is not None else ''
                except PathError:
                    FilePath = ''
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
                    'Mode': 'Transcode',
                })

            Result = {
                "Success": True,
                "Suggestions": Suggestions,
                "TotalCandidates": TotalCandidates,
                "Offset": Offset,
                "Limit": Limit,
                "Search": Search or '',
                "HasMore": (Offset + len(Suggestions)) < TotalCandidates,
            }
            LoggingService.LogInfo(f"NextTranscodeBatch: fetched {len(Rows)} of {TotalCandidates} candidates (offset={Offset}, search='{Search or ''}')", "QueueManagementBusinessService", "NextTranscodeBatch")
            return Result

        except Exception as Ex:
            ErrorMsg = f"Exception in NextTranscodeBatch: {str(Ex)}"
            LoggingService.LogException(ErrorMsg, Ex, "QueueManagementBusinessService", "NextTranscodeBatch")
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

            # directive: transcode-flow-canonical | # see transcode.ST2
            from Features.TranscodeJob import ProcessingModeMetadata
            if not ProcessingModeMetadata.IsKnown(Mode):
                Mode = 'Transcode'
            _AddMeta = ProcessingModeMetadata.Get(Mode)

            ProfileName = None
            if _AddMeta['RequiresProfileGates'] and ProfileId is not None:
                Profile = self.ProfileRepository.GetProfileById(ProfileId)
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

            # directive: failure-accounting | # see failure-accounting.C6
            from Core.Database.FailureBudgetPredicate import BuildCapPredicate
            CapPredicateFragment, _CapParams = BuildCapPredicate("m.Id")
            InsertSql = (
                "INSERT INTO TranscodeQueue "
                "(StorageRootId, RelativePath, FileName, Directory, "
                "SizeBytes, SizeMB, Priority, Status, DateAdded, "
                "ProcessingMode, MediaFileId) "
                "SELECT m.StorageRootId, "
                "COALESCE(m.RelativePath, ''), "
                "m.FileName, "
                "regexp_replace(COALESCE(m.RelativePath, ''), '/[^/]+$', ''), "
                "(m.SizeMB * 1024 * 1024)::bigint, "
                "m.SizeMB, "
                "COALESCE(m.PriorityScore, " + self._SIZE_PRIORITY_SQL + "), "
                "'Pending', "
                "NOW() AT TIME ZONE 'UTC', "
                "%s, "
                "m.Id "
                "FROM MediaFiles m "
                "WHERE m.Id = ANY(%s) "
                "AND m.SizeMB > 0 "
                "AND " + CapPredicateFragment + " "
                "ON CONFLICT (MediaFileId) WHERE Status = 'Pending' AND TestVariantSetId IS NULL DO NOTHING"
            )

            Connection = Db.GetConnection()
            try:
                Cursor = Connection.cursor()
                Cursor.execute(InsertSql, (Mode, NormalizedIds))
                ItemsAdded = Cursor.rowcount
                Connection.commit()
            finally:
                Db.CloseConnection(Connection)

            self._SnapshotAudioPoliciesOnRecentInserts()

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
        """Queue every WorkBucket-classified candidate matching the optional filters via one INSERT...SELECT; Mode must be a known ProcessingModes row; returns ItemsAdded."""
        try:
            # directive: transcode-flow-canonical | # see transcode.ST2
            from Features.TranscodeJob import ProcessingModeMetadata
            _QamMeta = ProcessingModeMetadata.Get(Mode)
            if not _QamMeta or not _QamMeta.get('WorkBucketFilterSql'):
                return {"Success": False, "ErrorMessage": f"Mode {Mode!r} is not a known admission mode", "ItemsAdded": 0}

            from Core.Database.DatabaseService import DatabaseService, EscapeLikePattern

            Params: list = [Mode]
            BucketSql = "AND " + _QamMeta['WorkBucketFilterSql'] + " "
            # directive: failure-accounting | # see failure-accounting.C6
            from Core.Database.FailureBudgetPredicate import BuildCapPredicate
            CapPredicateFragment, _CapParams = BuildCapPredicate("m.Id")
            WhereSql = (
                " WHERE m.TranscodedByMediaVortex IS NOT TRUE "
                "AND m.SizeMB > 0 "
                "AND (m.HasExplicitEnglishAudio IS NULL OR m.HasExplicitEnglishAudio = true) "
                + BucketSql +
                "AND " + CapPredicateFragment + " "
                "AND NOT EXISTS (SELECT 1 FROM TranscodeQueue tq WHERE tq.StorageRootId = m.StorageRootId AND tq.RelativePath = m.RelativePath)"
            )

            if Drive:
                DrivePrefix = Drive.rstrip(':\\/') + ':'
                DriveStorageRootId = _ResolveStorageRootIdForDrivePrefixFn(DrivePrefix)
                if DriveStorageRootId is None:
                    LoggingService.LogInfo(f"QueueAllMatching: Drive {Drive!r} did not match any StorageRoot; returning 0", "QueueManagementBusinessService", "QueueAllMatching")
                    return {"Success": True, "ItemsAdded": 0}
                WhereSql += " AND m.StorageRootId = %s"
                Params.append(DriveStorageRootId)

            if Search and Search.strip():
                Term = '%' + EscapeLikePattern(Search.strip().lower()) + '%'
                WhereSql += (
                    " AND (LOWER(m.FileName) LIKE %s ESCAPE '!'"
                    "      OR LOWER(SPLIT_PART(COALESCE(m.RelativePath, ''), '/', 1)) LIKE %s ESCAPE '!')"
                )
                Params.append(Term)
                Params.append(Term)

            # directive: path-schema-migration | # see path.S8
            InsertSql = (
                "INSERT INTO TranscodeQueue "
                "(StorageRootId, RelativePath, FileName, Directory, "
                "SizeBytes, SizeMB, Priority, Status, DateAdded, "
                "ProcessingMode, MediaFileId) "
                "SELECT m.StorageRootId, "
                "COALESCE(m.RelativePath, ''), "
                "m.FileName, "
                "regexp_replace(COALESCE(m.RelativePath, ''), '/[^/]+$', ''), "
                "(m.SizeMB * 1024 * 1024)::bigint, "
                "m.SizeMB, "
                "COALESCE(m.PriorityScore, " + self._SIZE_PRIORITY_SQL + "), "
                "'Pending', "
                "NOW() AT TIME ZONE 'UTC', "
                "%s, "
                "m.Id "
                "FROM MediaFiles m"
            ) + WhereSql + " ON CONFLICT (MediaFileId) WHERE Status = 'Pending' AND TestVariantSetId IS NULL DO NOTHING"

            Db = DatabaseService()
            Connection = Db.GetConnection()
            try:
                Cursor = Connection.cursor()
                Cursor.execute(InsertSql, tuple(Params))
                ItemsAdded = Cursor.rowcount
                Connection.commit()
            finally:
                Db.CloseConnection(Connection)

            self._SnapshotAudioPoliciesOnRecentInserts()

            LoggingService.LogInfo(
                f"QueueAllMatching: {ItemsAdded} added (mode={Mode}, search='{Search or ''}', drive='{Drive or ''}')",
                "QueueManagementBusinessService", "QueueAllMatching"
            )
            return {"Success": True, "ItemsAdded": ItemsAdded}

        except Exception as Ex:
            ErrorMsg = f"Exception in QueueAllMatching: {str(Ex)}"
            LoggingService.LogException(ErrorMsg, Ex, "QueueManagementBusinessService", "QueueAllMatching")
            return {"Success": False, "ErrorMessage": ErrorMsg, "ItemsAdded": 0}

    # directive: audio-vertical-live-encode-gaps | # see audio-normalization.C12
    def _SnapshotAudioPoliciesOnRecentInserts(self):
        """Backfill AudioPolicyJson on every Pending TranscodeQueue row with NULL snapshot; failure never breaks queue admission."""
        try:
            from Features.AudioNormalization.AudioPolicyAdmissionGate import AudioPolicyAdmissionGate
            AudioPolicyAdmissionGate().BackfillAllPending()
        except Exception as Ex:
            LoggingService.LogException(
                "Audio policy snapshot backfill failed -- queue rows may have NULL AudioPolicyJson",
                Ex, "QueueManagementBusinessService", "_SnapshotAudioPoliciesOnRecentInserts",
            )

    # directive: path-schema-migration | # see path.S8
    def GetMediaFilesWithProfilesOrderedBySize(self, RootFolderPath: str = None) -> List[MediaFileModel]:
        """Get media files with assigned profiles, ordered by size (largest first); typed-pair filter."""
        try:
            LoggingService.LogFunctionEntry("GetMediaFilesWithProfilesOrderedBySize", "QueueManagementBusinessService", RootFolderPath)

            from Core.Database.DatabaseService import DatabaseService, EscapeLikePattern

            WhereClauses = ["AssignedProfile IS NOT NULL", "TRIM(AssignedProfile) != ''"]
            Params: list = []

            if RootFolderPath:
                FolderSid, FolderRel = _ResolveFolderToTypedPair(RootFolderPath)
                if FolderSid is None:
                    LoggingService.LogInfo(f"GetMediaFilesWithProfilesOrderedBySize: RootFolderPath {RootFolderPath!r} did not match any StorageRoot; returning []", "QueueManagementBusinessService", "GetMediaFilesWithProfilesOrderedBySize")
                    return []
                WhereClauses.append("StorageRootId = %s")
                Params.append(FolderSid)
                if FolderRel:
                    WhereClauses.append("(RelativePath = %s OR RelativePath LIKE %s ESCAPE '!')")
                    Params.append(FolderRel)
                    Params.append(EscapeLikePattern(FolderRel) + '/%')

            Sql = (
                "SELECT Id, SeasonId, StorageRootId, RelativePath, FileName, SizeMB, "
                "VideoBitrateKbps, AudioBitrateKbps, Resolution, Codec, DurationMinutes, "
                "FrameRate, LastScannedDate, CompressionPotential, AssignedProfile, "
                "IsInterlaced, ResolutionCategory, FileModificationTime, TotalFrames, "
                "CodecProfile, ColorRange, FieldOrder, HasBFrames, RefFrames, PixelFormat, "
                "Level, AudioChannels, AudioSampleRate, AudioSampleFormat, "
                "AudioChannelLayout, AudioCodec, SubtitleFormats, ContainerFormat, "
                "OverallBitrate, TranscodedByMediaVortex, "
                "AudioLanguages, HasExplicitEnglishAudio "
                "FROM MediaFiles "
                "WHERE " + ' AND '.join(WhereClauses) + " "
                "ORDER BY SizeMB DESC NULLS LAST"
            )
            Rows = DatabaseService().ExecuteQuery(Sql, tuple(Params))

            filesWithProfiles = []
            for Row in Rows:
                mf = MediaFileModel(
                    Id=Row.get('Id'),
                    SeasonId=Row.get('SeasonId'),
                    StorageRootId=Row.get('StorageRootId'),
                    RelativePath=Row.get('RelativePath') or '',
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
            profile = self.ProfileRepository.GetProfileById(ProfileId)
            if not profile:
                LoggingService.LogError(f"Profile with ID {ProfileId} not found", "QueueManagementBusinessService", "GetMediaFilesByFolderAndResolutionFilter")
                return []

            # Get profile thresholds
            profileThresholds = self.ProfileRepository.GetThresholdsByProfileId(ProfileId)
            if not profileThresholds:
                LoggingService.LogWarning(f"No profile thresholds found for profile {profile.ProfileName}", "QueueManagementBusinessService", "GetMediaFilesByFolderAndResolutionFilter")
                return []

            # Step 1: profile-max-target -- # see marginal-savings-gate.C2b
            targetResolution = self.ProfileRepository.GetProfileMaxTarget(profile.ProfileName)

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

            for mediaFile in allMediaFiles:
                sourceResolution = mediaFile.Resolution or ""
                if not sourceResolution:
                    if not self.ProbeAndUpdateMissingMetadata(mediaFile):
                        continue
                    sourceResolution = mediaFile.Resolution or ""
                    if not sourceResolution:
                        continue

                FileTargetResolution = targetResolution

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

    # directive: path-schema-migration | # see path.S8
    def CreateQueueItemFromMediaFileSimple(self, MediaFile: MediaFileModel) -> Optional[TranscodeQueueModel]:
        """Create a queue item directly from a media file without threshold matching; typed pair is canonical identity."""
        try:
            LoggingService.LogFunctionEntry("CreateQueueItemFromMediaFileSimple", "QueueManagementBusinessService", MediaFile.FileName)

            # Compute Directory from the source MediaFile's typed pair (R6: no os.path on path-named var)
            _DirCanonical = ntpath.dirname(MediaFile.FilePath or "") if MediaFile.FilePath else ''

            # Create queue item from the typed pair; FilePath is a derived property
            queueItem = TranscodeQueueModel(
                StorageRootId=MediaFile.StorageRootId,
                RelativePath=MediaFile.RelativePath or '',
                FileName=MediaFile.FileName,
                Directory=_DirCanonical,
                SizeBytes=int((MediaFile.SizeMB or 0) * 1024 * 1024),
                SizeMB=MediaFile.SizeMB or 0,
                Priority=0,
                Status='Pending',
                DateAdded=datetime.now(timezone.utc)
            )

            LoggingService.LogInfo(f"Created simple queue item for {MediaFile.FileName}", "QueueManagementBusinessService", "CreateQueueItemFromMediaFileSimple")
            return queueItem

        except Exception as e:
            LoggingService.LogException("Exception creating simple queue item", e, "QueueManagementBusinessService", "CreateQueueItemFromMediaFileSimple")
            return None

    # directive: path-schema-migration | # see path.S8
    def CreateQueueItemFromMediaFileWithProfile(self, MediaFile: MediaFileModel) -> Optional[TranscodeQueueModel]:
        """Create a queue item from a media file that already has an assigned profile; typed pair is canonical identity."""
        try:
            LoggingService.LogFunctionEntry("CreateQueueItemFromMediaFileWithProfile", "QueueManagementBusinessService", MediaFile.FileName, MediaFile.AssignedProfile)

            filePath = MediaFile.FilePath or ""
            directory = ""
            fileName = MediaFile.FileName or ""

            if filePath:
                directory = ntpath.dirname(filePath or "")
                fileName = ntpath.basename(filePath or "") or fileName

            queueItem = TranscodeQueueModel(
                StorageRootId=MediaFile.StorageRootId,
                RelativePath=MediaFile.RelativePath or '',
                FileName=fileName,
                Directory=directory,
                SizeBytes=int((MediaFile.SizeMB or 0) * 1024 * 1024),
                SizeMB=MediaFile.SizeMB or 0.0,
                Priority=0,
                Status="Pending",
                DateAdded=datetime.now(timezone.utc)
            )

            LoggingService.LogInfo(f"Created queue item for {fileName} with profile {MediaFile.AssignedProfile}", "QueueManagementBusinessService", "CreateQueueItemFromMediaFileWithProfile")
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

            # directive: path-schema-migration | # see path.S8
            from Core.Database.DatabaseService import DatabaseService as _DbSvcRemux
            existingPairs = {
                (R.get('StorageRootId'), R.get('RelativePath') or '')
                for R in _DbSvcRemux().ExecuteQuery("SELECT StorageRootId, RelativePath FROM TranscodeQueue")
            }

            # Separate new items from existing-but-need-mode-switch
            itemsToInsert: List[TranscodeQueueModel] = []
            itemsUpdated = 0

            # For mode-switch we still need to load existing items, but only for the intersection.
            existingQueueByPair: Dict[tuple, Any] = {}
            NeedModeCheck = [mf for mf in mkvFiles if (mf.StorageRootId, mf.RelativePath or '') in existingPairs]
            if NeedModeCheck:
                existingQueueItems = self.Repository.GetAllTranscodeQueueItems()
                existingQueueByPair = {(item.StorageRootId, item.RelativePath or ''): item for item in existingQueueItems}

            # directive: transcode-flow-canonical | # see transcode.ST2
            TargetMode = 'Remux'
            for mediaFile in mkvFiles:
                _Pair = (mediaFile.StorageRootId, mediaFile.RelativePath or '')
                if _Pair in existingPairs:
                    existingItem = existingQueueByPair.get(_Pair)
                    if existingItem and existingItem.ProcessingMode != TargetMode and existingItem.Status == "Pending":
                        existingItem.ProcessingMode = TargetMode
                        self.Repository.SaveTranscodeQueueItem(existingItem)
                        itemsUpdated += 1
                        LoggingService.LogInfo(f"Switched queue item {existingItem.Id} ({mediaFile.FileName}) to {TargetMode}", "QueueManagementBusinessService", "PopulateQueueForRemux")
                    continue

                queueItem = self.CreateRemuxQueueItem(mediaFile)
                if queueItem:
                    itemsToInsert.append(queueItem)
                    existingPairs.add(_Pair)

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

    # directive: path-schema-migration | # see path.S8
    def GetMkvFilesForRemux(self, RootFolderPath: str = None) -> List[MediaFileModel]:
        """Get MKV media files eligible for remuxing, ordered by size (largest first); typed-pair filter."""
        try:
            from Core.Database.DatabaseService import DatabaseService, EscapeLikePattern

            WhereClauses = ["LOWER(FileName) LIKE %s"]
            Params: list = ['%.mkv']

            if RootFolderPath:
                FolderSid, FolderRel = _ResolveFolderToTypedPair(RootFolderPath)
                if FolderSid is None:
                    LoggingService.LogInfo(f"GetMkvFilesForRemux: RootFolderPath {RootFolderPath!r} did not match any StorageRoot; returning []", "QueueManagementBusinessService", "GetMkvFilesForRemux")
                    return []
                WhereClauses.append("StorageRootId = %s")
                Params.append(FolderSid)
                if FolderRel:
                    WhereClauses.append("(RelativePath = %s OR RelativePath LIKE %s ESCAPE '!')")
                    Params.append(FolderRel)
                    Params.append(EscapeLikePattern(FolderRel) + '/%')

            Sql = (
                "SELECT Id, StorageRootId, RelativePath, FileName, SizeMB, "
                "DurationMinutes, Resolution, Codec, ContainerFormat "
                "FROM MediaFiles "
                "WHERE " + ' AND '.join(WhereClauses) + " "
                "ORDER BY SizeMB DESC NULLS LAST"
            )
            Rows = DatabaseService().ExecuteQuery(Sql, tuple(Params))

            mkvFiles = []
            for Row in Rows:
                mf = MediaFileModel(
                    Id=Row.get('Id'),
                    StorageRootId=Row.get('StorageRootId'),
                    RelativePath=Row.get('RelativePath') or '',
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

    # directive: path-schema-migration | # see path.S8
    def CreateRemuxQueueItem(self, MediaFile: MediaFileModel) -> Optional[TranscodeQueueModel]:
        """Create a queue item for remuxing (container change only); typed pair is canonical identity."""
        try:
            filePath = MediaFile.FilePath or ""
            directory = ""
            fileName = MediaFile.FileName or ""

            if filePath:
                directory = ntpath.dirname(filePath or "")
                fileName = ntpath.basename(filePath or "") or fileName

            queueItem = TranscodeQueueModel(
                StorageRootId=MediaFile.StorageRootId,
                RelativePath=MediaFile.RelativePath or '',
                FileName=fileName,
                Directory=directory,
                SizeBytes=int((MediaFile.SizeMB or 0) * 1024 * 1024),
                SizeMB=MediaFile.SizeMB or 0.0,
                Priority=0,
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
                profile = self.ProfileRepository.GetProfileById(Threshold.ProfileId)
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

    # directive: path-schema-migration | # see path.S8
    def CreateQueueItemFromMediaFile(self, MediaFile: MediaFileModel, Threshold: ProfileThresholdModel) -> Optional[TranscodeQueueModel]:
        """Create a queue item from a media file and threshold; typed pair is canonical identity."""
        try:
            LoggingService.LogFunctionEntry("CreateQueueItemFromMediaFile", "QueueManagementBusinessService", MediaFile.FileName, Threshold.ProfileId)

            filePath = MediaFile.FilePath or ""
            directory = ""
            fileName = MediaFile.FileName or ""

            if filePath:
                directory = ntpath.dirname(filePath or "")
                fileName = ntpath.basename(filePath or "") or fileName

            queueItem = TranscodeQueueModel(
                StorageRootId=MediaFile.StorageRootId,
                RelativePath=MediaFile.RelativePath or '',
                FileName=fileName,
                Directory=directory,
                SizeBytes=int((MediaFile.SizeMB or 0) * 1024 * 1024),
                SizeMB=MediaFile.SizeMB or 0.0,
                Priority=0,
                Status="Pending",
                DateAdded=datetime.now(timezone.utc)
            )

            LoggingService.LogInfo(f"Created queue item for {fileName}", "QueueManagementBusinessService", "CreateQueueItemFromMediaFile")
            return queueItem

        except Exception as e:
            LoggingService.LogException("Exception creating queue item", e, "QueueManagementBusinessService", "CreateQueueItemFromMediaFile")
            return None

    def CalculatePriority(self, MediaFile: MediaFileModel,
                          TargetVideoKbps: Optional[int] = None,
                          TargetAudioKbps: Optional[int] = None,
                          SuppressFallbackWarning: bool = False) -> int:
        """Impact-based score in [1, 194] for MediaFiles.PriorityScore consumers (SmartPopulate helpers, backfill); NOT consulted on the claim path -- see queue-priority.feature.md."""
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

    # directive: compliance-rip
    def EvaluateCandidateCompliance(self, CandidateRow: Dict[str, Any], EffectiveProfile: Optional[str] = None) -> Dict[str, Any]:
        """Pre-rename compliance check via three pure vertical Evaluate calls. Returns {IsCompliant, WorkBucket, RefusalReason} for ComplianceGate.Evaluate."""
        from Features.AudioNormalization.AudioVertical import AudioVertical
        from Features.VideoEncoding.VideoVertical import VideoVertical
        from Features.ContainerFormat.ContainerVertical import ContainerVertical
        Mf = self._RowToMediaFileForCompliance(CandidateRow)
        AudioOk, AudioReason = AudioVertical().Evaluate(Mf)
        VideoOk, VideoReason = VideoVertical().Evaluate(Mf)
        ContainerOk, ContainerReason = ContainerVertical().Evaluate(Mf)
        if AudioOk is None or VideoOk is None or ContainerOk is None:
            WorkBucket, IsCompliant, RefusalReason = None, None, (AudioReason or VideoReason or ContainerReason)
        elif not VideoOk:
            WorkBucket, IsCompliant, RefusalReason = 'Transcode', False, VideoReason
        elif not ContainerOk:
            WorkBucket, IsCompliant, RefusalReason = 'Remux', False, ContainerReason
        elif not AudioOk:
            WorkBucket, IsCompliant, RefusalReason = 'AudioFix', False, AudioReason
        else:
            WorkBucket, IsCompliant, RefusalReason = None, True, None
        CandidateRow['_RefusalReason'] = RefusalReason
        return {'IsCompliant': IsCompliant, 'WorkBucket': WorkBucket, 'RefusalReason': RefusalReason}

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C9
    def _RowToMediaFileForCompliance(self, Row: Dict[str, Any]):
        """Helper for legacy-shim callers (RecomputeForFiles row, EvaluateCandidateCompliance CandidateRow) -- build a MediaFileModel from the dict for the new engine."""
        from Models.MediaFileModel import MediaFileModel
        return MediaFileModel(
            Id=Row.get('Id') or Row.get('id'),
            FileName=Row.get('FileName') or '',
            SizeMB=float(Row.get('SizeMB') or 0),
            DurationMinutes=Row.get('DurationMinutes'),
            Resolution=Row.get('Resolution'),
            ResolutionCategory=Row.get('ResolutionCategory') or self._ResolutionCategoryFromPixels(Row.get('Resolution')),
            Codec=Row.get('Codec'),
            VideoBitrateKbps=Row.get('VideoBitrateKbps'),
            AudioCodec=Row.get('AudioCodec'),
            AudioChannels=Row.get('AudioChannels'),
            AudioBitrateKbps=Row.get('AudioBitrateKbps'),
            AudioComplete=Row.get('AudioComplete'),
            AudioCorruptSuspect=Row.get('AudioCorruptSuspect') if Row.get('AudioCorruptSuspect') is not None else False,
            ContainerFormat=Row.get('ContainerFormat'),
            SubtitleFormats=Row.get('SubtitleFormats'),
            AssignedProfile=Row.get('AssignedProfile'),
            HasExplicitEnglishAudio=Row.get('HasExplicitEnglishAudio'),
            HasForcedSubtitles=Row.get('HasForcedSubtitles'),
            SourceIntegratedLufs=Row.get('SourceIntegratedLufs'),
            SourceLoudnessRangeLU=Row.get('SourceLoudnessRangeLU'),
            SourceTruePeakDbtp=Row.get('SourceTruePeakDbtp'),
            SourceIntegratedThresholdLufs=Row.get('SourceIntegratedThresholdLufs'),
            LoudnessMeasurementFailureReason=Row.get('LoudnessMeasurementFailureReason'),
            # directive: mv-trust-savings-and-clamp -- AC3 wiring.
            TranscodedByMediaVortex=bool(Row.get('TranscodedByMediaVortex')) if Row.get('TranscodedByMediaVortex') is not None else None,
        )

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C12
    def _BuildEffectiveProfileObj(self, ProfileName: Optional[str], ResolutionCategory: Optional[str], Lookup: Dict[tuple, tuple], VideoBitrateKbps: Optional[int] = None):
        """Delegate to EffectiveProfileResolver -- profile name + source resolution + optional source video kbps fold into a synthesized MediaFileModel-shaped input; resolver handles fixed/VBR/CRF strategy dispatch."""
        from Features.Profiles.EffectiveProfileResolver import EffectiveProfileResolver
        from Models.MediaFileModel import MediaFileModel
        if not ProfileName:
            return None
        SyntheticMf = MediaFileModel(AssignedProfile=ProfileName, ResolutionCategory=ResolutionCategory, VideoBitrateKbps=VideoBitrateKbps)
        return EffectiveProfileResolver().Resolve(SyntheticMf)

    @staticmethod
    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C13
    def _LegacyRefusalReasonFromDecision(Decision) -> Optional[str]:
        """Map ComplianceDecision to a single legacy snake_case refusal string -- gate name when blocked; first applies-reason rule name when non-compliant; None when compliant."""
        if Decision.GateBlocked is not None:
            GateMap = {'EnglishAudio': 'no_english_audio', 'AudioCorruptSuspect': 'audio_corrupt_suspect', 'AudioStream': 'no_audio_stream', 'LoudnessMeasurements': 'awaiting_loudness_measurement', 'ProbeMetadata': 'no_probe_metadata', 'EffectiveProfile': 'no_effective_profile', 'ResolutionCategory': 'no_resolution_category', 'ProfileThresholds': 'no_profile_thresholds'}
            return GateMap.get(Decision.GateBlocked, Decision.GateBlocked.lower())
        if Decision.IsCompliant is True:
            return None
        for R in Decision.Reasons:
            if R.get('Outcome') == 'applies':
                Rule = R.get('Rule', '')
                if Rule == 'ResolutionExceedsProfileTarget':
                    return 'downscale_needed'
                if Rule == 'AcceptableVideoCodecsCsv':
                    return 'video_codec_not_acceptable'
                if Rule == 'EstimatedSavingsMBThreshold':
                    return 'savings_exceeds_threshold'
                if Rule == 'AcceptableContainersCsv':
                    return 'container_not_acceptable'
                if Rule == 'AcceptableAudioCodecsMp4Csv':
                    return 'audio_codec_not_acceptable'
                if Rule == 'RequireAudioNormalized':
                    return 'audio_not_normalized'
                if Rule == 'LoudnessOffTarget':
                    return 'audio_not_normalized'
                if Rule == 'SubtitleFixApplies':
                    return 'subtitle_format_not_acceptable'
        return 'needs_work'

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

        # 1. Upscale block -- # see marginal-savings-gate.C2b
        SourceResolution = getattr(MediaFile, 'Resolution', None) or ''
        UpscaleTarget = ProfileSettings.get('ProfileMaxTarget') or ProfileSettings.get('TargetResolution') or ''
        if SourceResolution and UpscaleTarget:
            try:
                from Services.ResolutionService import ResolutionService
                Cmp = ResolutionService().CompareResolutions(SourceResolution, UpscaleTarget)
                if Cmp is not None and Cmp < 0:
                    return (True, f"Upscale (source {SourceResolution} < profile target {UpscaleTarget})")
            except Exception as Ex:
                LoggingService.LogException(
                    f"Resolution compare failed for {SourceResolution} vs {UpscaleTarget}",
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
            ProfileSettings = self.ProfileRepository.GetProfileSettingsForTargetResolution(
                ProfileName, MediaFile.Resolution
            )
            ProfileMaxTarget = self.ProfileRepository.GetProfileMaxTarget(ProfileName)
        except Exception as Ex:
            LoggingService.LogException(
                f"Failed to load ProfileSettings for {ProfileName} / {MediaFile.Resolution}",
                Ex, "QueueManagementBusinessService", "EvaluateQueueAdmissionForProfile",
            )
            return (True, 'MissingProfile')
        Settings = dict(ProfileSettings) if ProfileSettings else {}
        if Settings and ProfileMaxTarget:
            Settings['ProfileMaxTarget'] = ProfileMaxTarget
        return self.EvaluateQueueAdmission(MediaFile, Settings, AdmissionConfig)

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
                    profileSettings = self.ProfileRepository.GetProfileSettingsForTargetResolution(
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
        """Recompute compliance + AssignedProfile + PriorityScore for the given ids. Phase 1: three verticals write booleans (trigger derives WorkBucket). Phase 2: re-fetch + compute profile + priority + AudioFix folder pin + bulk UPDATE. Returns rows updated."""
        if not MediaFileIds:
            return 0
        try:
            from Core.Database.DatabaseService import DatabaseService
            db = DatabaseService()
            # directive: compliance-rip
            from Features.AudioNormalization.AudioVertical import AudioVertical
            from Features.VideoEncoding.VideoVertical import VideoVertical
            from Features.ContainerFormat.ContainerVertical import ContainerVertical
            AudioVertical().RecomputeFor(MediaFileIds)
            VideoVertical().RecomputeFor(MediaFileIds)
            ContainerVertical().RecomputeFor(MediaFileIds)

            Lookup = self._LoadPriorityLookupTable()

            # AudioFix folder pins (media-tabs-and-loudness.feature.md C22): boost PriorityScore when WorkBucket='AudioFix' and FilePath matches a hint pattern.
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
            # directive: path-schema-migration | # see path.S8
            rows = db.ExecuteQuery(
                "SELECT Id, StorageRootId, RelativePath, FileName, SizeMB, DurationMinutes, AssignedProfile, "
                "ResolutionCategory, Resolution, Codec, VideoBitrateKbps, ContainerFormat, "
                "AudioCodec, HasExplicitEnglishAudio, HasForcedSubtitles, SubtitleFormats, "
                "AudioComplete, AudioCorruptSuspect, AudioBitrateKbps, AudioChannels, "
                "SourceIntegratedLufs, SourceLoudnessRangeLU, SourceTruePeakDbtp, "
                "SourceIntegratedThresholdLufs, LoudnessMeasuredAt, "
                "LoudnessMeasurementFailureReason, TranscodedByMediaVortex, "
                "WorkBucket "
                "FROM MediaFiles WHERE Id IN (" + placeholders + ")",
                tuple(MediaFileIds)
            )
            # Synthesize FilePath display string per row for downstream consumers (read-only).
            _Prefixes = {Sr["Id"]: Sr["CanonicalPrefix"] for Sr in _GetStorageRoots()}
            for _R in rows:
                _Sid = _R.get('StorageRootId')
                _Rel = _R.get('RelativePath')
                if _Sid is not None and _Rel is not None:
                    try:
                        _R['FilePath'] = Path(_Sid, _Rel or '').CanonicalDisplay(_Prefixes)
                    except PathError:
                        _R['FilePath'] = ''
                else:
                    _R['FilePath'] = ''

            updates = []  # list[(id, profile_or_none, score, is_compliant_or_none, recommended_or_none)]
            NoAudioFiles = []  # list of (FilePath, MediaFileId) for ProblemFile flagging
            for r in rows:
                try:
                    # directive: transcode-worker-unification | # see profiles.C24
                    EffectiveProfile = self.Resolver.ResolveProfileName(
                        MediaFileModel(AssignedProfile=r.get('AssignedProfile'))
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

                    # directive: compliance-rip -- WorkBucket comes from the GENERATED column, up-to-date because the three verticals ran above
                    WorkBucket = r.get('WorkBucket')

                    # AudioFix folder-pin boost: see media-tabs-and-loudness.feature.md C22
                    FinalScore = int(Score)
                    if WorkBucket == 'AudioFix' and AudioFixPins:
                        FilePathLower = (r.get('FilePath') or '').lower()
                        for Pattern, Boost in AudioFixPins:
                            if Pattern and Pattern in FilePathLower:
                                if Boost > FinalScore:
                                    FinalScore = Boost
                                break

                    updates.append((int(r['Id']), EffectiveProfile, FinalScore))

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

            # directive: compliance-rip -- bulk UPDATE for AssignedProfile + PriorityScore (WorkBucket is GENERATED, IsCompliant flows from it)
            def _SqlText(V):
                if V is None:
                    return 'NULL'
                return "'" + str(V).replace("'", "''") + "'"
            ValuesClause = ','.join(
                f"({int(Id)},{_SqlText(P)},{int(S)})" for Id, P, S in updates
            )
            db.ExecuteNonQuery(
                "UPDATE MediaFiles "
                "SET AssignedProfile = v.profile, PriorityScore = v.score "
                "FROM (VALUES " + ValuesClause + ") "
                "AS v(id, profile, score) "
                "WHERE MediaFiles.Id = v.id"
            )
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

    # directive: path-schema-migration | # see path.S8
    def AddJobToQueue(self, MediaFileId: int, Priority: int = None, ProfileId: int = None, StartTime: str = None, ForceAdd: bool = False, ProcessingMode: str = None) -> Dict[str, Any]:
        """Add a specific media file to the transcoding queue; dedupe via typed-pair identity. ProcessingMode overrides default 'Transcode'; non-Transcode modes skip profile/savings/VMAF gates."""
        # directive: transcode-flow-canonical | # see transcode.ST2
        from Features.TranscodeJob import ProcessingModeMetadata
        EffectiveMode = ProcessingMode or 'Transcode'
        IsTranscodeMode = ProcessingModeMetadata.GetOrDefault(EffectiveMode)['RequiresProfileGates']
        try:
            LoggingService.LogFunctionEntry("AddJobToQueue", "QueueManagementBusinessService", MediaFileId, Priority)

            # Get media file
            mediaFile = self.DatabaseManager.GetMediaFileById(MediaFileId)
            if not mediaFile:
                errorMsg = f"Media file with ID {MediaFileId} not found"
                LoggingService.LogError(errorMsg, "QueueManagementBusinessService", "AddJobToQueue")
                return {"Success": False, "ErrorMessage": errorMsg}

            # Targeted per-MediaFileId dedup; returns AlreadyQueued=True with existing row ID so callers can be idempotent.
            ExistingRows = self.DatabaseManager.DatabaseService.ExecuteQuery(
                "SELECT Id FROM TranscodeQueue WHERE MediaFileId = %s AND Status = 'Pending' LIMIT 1",
                (int(MediaFileId),),
            )
            if ExistingRows:
                ExistingId = int(ExistingRows[0]['id'])
                LoggingService.LogWarning(f"File {mediaFile.FileName} already pending (row {ExistingId})", "QueueManagementBusinessService", "AddJobToQueue")
                return {"Success": True, "AlreadyQueued": True, "ItemId": ExistingId, "FileName": mediaFile.FileName}

            # Handle profile assignment if ProfileId is provided (user selected a profile)
            if ProfileId is not None:
                # Get the profile and update the media file's assigned profile
                profile = self.ProfileRepository.GetProfileById(ProfileId)
                if not profile:
                    errorMsg = f"Profile with ID {ProfileId} not found"
                    LoggingService.LogError(errorMsg, "QueueManagementBusinessService", "AddJobToQueue")
                    return {"Success": False, "ErrorMessage": errorMsg}

                # Update media file's assigned profile
                mediaFile.AssignedProfile = profile.ProfileName
                self.DatabaseManager.SaveMediaFile(mediaFile)
                LoggingService.LogInfo(f"Updated media file {mediaFile.FileName} to use profile {profile.ProfileName}", "QueueManagementBusinessService", "AddJobToQueue")

            # Check if file has a profile (either existing or just assigned)
            if IsTranscodeMode and (not mediaFile.AssignedProfile or mediaFile.AssignedProfile.strip() == ''):
                errorMsg = f"File {mediaFile.FileName} has no profile assigned. Please select a profile first."
                LoggingService.LogWarning(errorMsg, "QueueManagementBusinessService", "AddJobToQueue")
                return {"Success": False, "ErrorMessage": errorMsg}

            if IsTranscodeMode:
                # directive: transcode-flow-canonical | # see transcode.ST2 -- AdequacyGate refuses compact-source admissions (C13).
                if not ForceAdd:
                    from Features.TranscodeQueue.AdequacyGate import AdequacyGate
                    AdequacyResult = AdequacyGate(self.DatabaseManager.DatabaseService).Evaluate(mediaFile)
                    if AdequacyResult.Excluded:
                        Reason = (f"AdequacyGate excluded: {AdequacyResult.Reason} "
                                f"(source={AdequacyResult.SourceKbps}kbps <= Tier1Target={AdequacyResult.Tier1TargetKbps}kbps)")
                        LoggingService.LogInfo(f"AdequacyGate excluded {mediaFile.FileName}: {Reason}", "QueueManagementBusinessService", "AddJobToQueue")
                        return {"Success": False, "ErrorMessage": Reason, "CanOverride": True, "AdequacyDecision": AdequacyResult.Reason}
                # Marginal-savings gate; ForceAdd bypasses so operator can pin same-resolution re-encodes.
                if not ForceAdd:
                    shouldSkip, skipReason = self.EvaluateQueueAdmissionForProfile(mediaFile, mediaFile.AssignedProfile)
                    if shouldSkip:
                        errorMsg = f"Cannot add {mediaFile.FileName} to queue: {skipReason}"
                        LoggingService.LogInfo(errorMsg, "QueueManagementBusinessService", "AddJobToQueue")
                        return {"Success": False, "ErrorMessage": errorMsg, "CanOverride": True}
                else:
                    LoggingService.LogWarning(f"Force adding {mediaFile.FileName} to queue (admission gate overridden)", "QueueManagementBusinessService", "AddJobToQueue")

                # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C10
                from Features.QualityTesting.Disposition.RetranscodeDecider import RetranscodeDecider
                from Features.TranscodeJob.Adjustments.AdjustmentRegistry import AdjustmentRegistry
                retranscodeDecider = RetranscodeDecider(AttemptRepository=self.DatabaseManager)
                adjustmentRegistry = AdjustmentRegistry()
                shouldRetranscode, previousAttempt = retranscodeDecider.Decide(mediaFile.Id)

                if not shouldRetranscode:
                    if not ForceAdd:
                        skipMsg = f"Quality already acceptable (VMAF >= 80), skipping retranscode for {mediaFile.FileName}"
                        LoggingService.LogInfo(skipMsg, "QueueManagementBusinessService", "AddJobToQueue")
                        return {"Success": True, "Skipped": True, "Message": "Quality already acceptable, skipping retranscode", "FileName": mediaFile.FileName}
                    LoggingService.LogWarning(f"Force adding {mediaFile.FileName} despite VMAF>=80 on latest attempt (VMAF gate overridden)", "QueueManagementBusinessService", "AddJobToQueue")

                if previousAttempt:
                    previousCRF = previousAttempt.get('Quality')
                    vmafScore = previousAttempt.get('VMAF')

                    if previousCRF and vmafScore is not None and vmafScore < 80:
                        adjustedCRF = adjustmentRegistry.Get('cq').Calculate(
                            PreviousAttempt={'Quality': previousCRF, 'VMAF': vmafScore},
                            ProfileSettings={}, GateThreshold=80.0,
                        ).CRF

                        minCRF = 15
                        if adjustedCRF < minCRF:
                            errorMsg = f"Cannot adjust CRF further for {mediaFile.FileName}: Previous CRF={previousCRF}, VMAF={vmafScore:.2f}, Adjusted CRF={adjustedCRF} would be below minimum {minCRF}"
                            directory = ntpath.dirname(mediaFile.FilePath)  # canonical display
                            problemFileId = self.Repository.AddProblemFile(
                                mediaFile.FilePath,
                                "CRF_Adjustment_Failed",
                                f"CRF adjustment failed: Previous CRF={previousCRF}, VMAF={vmafScore:.2f}, Calculated CRF={adjustedCRF} is below minimum threshold (15). Quality threshold unreachable."
                            )
                            if problemFileId:
                                LoggingService.LogError(f"Logged CRF adjustment failure to ProblemFiles (ID: {problemFileId}): {errorMsg}", "QueueManagementBusinessService", "AddJobToQueue")
                            return {"Success": False, "ErrorMessage": errorMsg}

            if mediaFile.AssignedProfile:
                queueItem = self.CreateQueueItemFromMediaFileWithProfile(mediaFile)
            else:
                queueItem = self.CreateQueueItemFromMediaFileSimple(mediaFile)
            if not queueItem:
                errorMsg = f"Failed to create queue item for {mediaFile.FileName}"
                LoggingService.LogError(errorMsg, "QueueManagementBusinessService", "AddJobToQueue")
                return {"Success": False, "ErrorMessage": errorMsg}

            # Stamp the bucket ProcessingMode (Remux, AudioFix, etc.) onto the row. # directive: transcode-worker-unification
            queueItem.ProcessingMode = EffectiveMode

            # Priority: operator-explicit overrides; otherwise +15 manual bonus capped at 194 (195-200 reserved; see queue-priority.feature.md).
            if Priority is not None:
                queueItem.Priority = Priority
            else:
                queueItem.Priority = min(194, queueItem.Priority + 15)
                LoggingService.LogInfo(f"Added manual addition bonus (+15, capped at 194) to priority for {mediaFile.FileName}. New priority: {queueItem.Priority}", "QueueManagementBusinessService", "AddJobToQueue")

            # Save to database
            itemId = self.Repository.SaveTranscodeQueueItem(queueItem)

            # T29: fire AudioPolicyAdmissionGate synchronously at insert time. # directive: transcode-worker-unification | # see work-bucket.C4, work-bucket.C5
            try:
                from Features.AudioNormalization.AudioPolicyAdmissionGate import AudioPolicyAdmissionGate
                Gate = AudioPolicyAdmissionGate()
                Decision = Gate.AdmitOrDefer(mediaFile, IntendedProcessingMode=EffectiveMode)
                Gate.SnapshotPolicyOnQueueRow(MediaFileId, Decision.PolicyJson)
            except Exception as AudioEx:
                LoggingService.LogWarning(f"Audio policy snapshot failed for MediaFileId={MediaFileId}: {AudioEx}", "QueueManagementBusinessService", "AddJobToQueue")

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

            # ActiveJobs orphan sweep on delete -- catches non-Running residue.
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
            from Features.ServiceControl.ActiveJobRepository import ActiveJobRepository as _AJR
            _ajrepo = _AJR(self.Repository.DatabaseService)
            activeJobs = _ajrepo.GetActiveJobsByService(_AJR.BuildActiveJobsQuery("TranscodeService"))
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
            if not FilePath or not LocalExists(FilePath):
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

    # directive: path-schema-migration | # see path.S8
    def PopulateQueueForSubtitleFix(self, FileIds: list = None) -> Dict[str, Any]:
        """Queue specific or all eligible files for subtitle fix processing; typed pair is canonical identity."""
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

            # Get existing queue items to avoid duplicates (by typed-pair identity)
            existingQueueItems = self.Repository.GetAllTranscodeQueueItems()
            existingPairs = {(item.StorageRootId, item.RelativePath or '') for item in existingQueueItems}

            itemsAdded = 0
            itemsSkipped = 0

            for mediaFile in mediaFiles:
                if (mediaFile.StorageRootId, mediaFile.RelativePath or '') in existingPairs:
                    itemsSkipped += 1
                    continue

                _DirCanonical = ntpath.dirname(mediaFile.FilePath or "") if mediaFile.FilePath else ''
                queueItem = TranscodeQueueModel(
                    StorageRootId=mediaFile.StorageRootId,
                    RelativePath=mediaFile.RelativePath or '',
                    FileName=mediaFile.FileName,
                    Directory=_DirCanonical,
                    SizeBytes=int((mediaFile.SizeMB or 0) * 1024 * 1024),
                    SizeMB=mediaFile.SizeMB or 0.0,
                    Priority=0,
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
