from flask import Blueprint, request, jsonify
from Core.Logging.LoggingService import LoggingService
from Features.ShowSettings.ShowSettingsRepository import ShowSettingsRepository
from Features.ShowSettings.Models.ShowSettingModel import ShowSettingModel


ShowSettingsBlueprint = Blueprint('ShowSettings', __name__, url_prefix='/api/ShowSettings')

Repository = ShowSettingsRepository()


@ShowSettingsBlueprint.route('/Shows', methods=['GET'])
def GetShows():
    """Get all shows with stats and current settings."""
    try:
        Drive = request.args.get('Drive', None)
        Shows = Repository.GetShowsWithStats(Drive)
        return jsonify({'Success': True, 'Data': Shows})
    except Exception as Ex:
        LoggingService.LogException("Exception getting shows", Ex, "ShowSettingsController", "GetShows")
        return jsonify({'Success': False, 'Message': str(Ex)}), 500


@ShowSettingsBlueprint.route('/Settings', methods=['GET'])
def GetAllSettings():
    """Get all show settings."""
    try:
        Settings = Repository.GetAllShowSettings()
        SettingsList = [{'Id': S.Id, 'ShowFolder': S.ShowFolder, 'TargetResolution': S.TargetResolution} for S in Settings]
        return jsonify({'Success': True, 'Data': SettingsList})
    except Exception as Ex:
        LoggingService.LogException("Exception getting settings", Ex, "ShowSettingsController", "GetAllSettings")
        return jsonify({'Success': False, 'Message': str(Ex)}), 500


@ShowSettingsBlueprint.route('/Save', methods=['POST'])
def SaveShowSetting():
    """Save a show setting (single show)."""
    try:
        Data = request.get_json()
        if not Data:
            return jsonify({'Success': False, 'Message': 'No data provided'}), 400

        ShowFolder = Data.get('ShowFolder', '').strip()
        TargetResolution = Data.get('TargetResolution', '').strip()

        if not ShowFolder:
            return jsonify({'Success': False, 'Message': 'ShowFolder is required'}), 400

        ValidResolutions = ['480p', '720p', '1080p', '2160p', '']
        if TargetResolution not in ValidResolutions:
            return jsonify({'Success': False, 'Message': f'Invalid TargetResolution. Must be one of: {ValidResolutions}'}), 400

        Setting = ShowSettingModel(ShowFolder=ShowFolder, TargetResolution=TargetResolution)
        ResultId = Repository.SaveShowSetting(Setting)

        if ResultId:
            return jsonify({'Success': True, 'Message': f'Setting saved for {ShowFolder}', 'Id': ResultId})
        else:
            return jsonify({'Success': False, 'Message': 'Failed to save setting'}), 500
    except Exception as Ex:
        LoggingService.LogException("Exception saving show setting", Ex, "ShowSettingsController", "SaveShowSetting")
        return jsonify({'Success': False, 'Message': str(Ex)}), 500


@ShowSettingsBlueprint.route('/BulkUpdate', methods=['POST'])
def BulkUpdateShowSettings():
    """Update target resolution for multiple shows at once."""
    try:
        Data = request.get_json()
        if not Data:
            return jsonify({'Success': False, 'Message': 'No data provided'}), 400

        ShowFolders = Data.get('ShowFolders', [])
        TargetResolution = Data.get('TargetResolution', '').strip()

        if not ShowFolders:
            return jsonify({'Success': False, 'Message': 'ShowFolders list is required'}), 400

        ValidResolutions = ['480p', '720p', '1080p', '2160p', '']
        if TargetResolution not in ValidResolutions:
            return jsonify({'Success': False, 'Message': f'Invalid TargetResolution. Must be one of: {ValidResolutions}'}), 400

        Updated = Repository.BulkUpdateTargetResolution(ShowFolders, TargetResolution)
        return jsonify({'Success': True, 'Message': f'Updated {Updated} shows to {TargetResolution or "profile default"}', 'UpdatedCount': Updated})
    except Exception as Ex:
        LoggingService.LogException("Exception bulk updating", Ex, "ShowSettingsController", "BulkUpdateShowSettings")
        return jsonify({'Success': False, 'Message': str(Ex)}), 500


@ShowSettingsBlueprint.route('/SetSeriesProfile', methods=['POST'])
def SetSeriesProfile():
    """Set or clear the per-show profile override.

    Body: {"ShowFolder": "<full path e.g. T:\\Survivor>", "ProfileName": "<name or empty string to clear>"}.
    Empty/missing ProfileName clears the override -- show then inherits SystemSettings.DefaultProfileName.
    Non-empty ProfileName must exist in Profiles.ProfileName -- otherwise 400.

    Owns: transcode-vs-remux-routing.feature.md criteria 5, 6.
    """
    try:
        Data = request.get_json() or {}
        ShowFolder = (Data.get('ShowFolder') or '').strip()
        ProfileName = (Data.get('ProfileName') or '').strip()

        if not ShowFolder:
            return jsonify({'Success': False, 'Message': 'ShowFolder is required'}), 400

        if ProfileName:
            from Core.Database.DatabaseService import DatabaseService
            Rows = DatabaseService().ExecuteQuery(
                "SELECT 1 FROM Profiles WHERE ProfileName = %s LIMIT 1",
                (ProfileName,)
            )
            if not Rows:
                return jsonify({
                    'Success': False,
                    'Message': f"Profile '{ProfileName}' does not exist in Profiles table"
                }), 400

        # ProfileName == '' clears the override (writes NULL).
        Repository.SetSeriesAssignedProfile(ShowFolder, ProfileName or None)
        DescVal = repr(ProfileName) if ProfileName else 'NULL (inherit default)'
        LoggingService.LogInfo(
            f"ShowSettings.AssignedProfile for '{ShowFolder}' set to {DescVal}",
            "ShowSettingsController", "SetSeriesProfile"
        )
        return jsonify({'Success': True, 'ShowFolder': ShowFolder, 'AssignedProfile': ProfileName or None})
    except Exception as Ex:
        LoggingService.LogException("Exception in SetSeriesProfile", Ex, "ShowSettingsController", "SetSeriesProfile")
        return jsonify({'Success': False, 'Message': str(Ex)}), 500


@ShowSettingsBlueprint.route('/Delete', methods=['POST'])
def DeleteShowSetting():
    """Delete a show setting (reverts to default)."""
    try:
        Data = request.get_json()
        if not Data:
            return jsonify({'Success': False, 'Message': 'No data provided'}), 400

        ShowFolder = Data.get('ShowFolder', '').strip()
        if not ShowFolder:
            return jsonify({'Success': False, 'Message': 'ShowFolder is required'}), 400

        Result = Repository.DeleteShowSetting(ShowFolder)
        if Result:
            return jsonify({'Success': True, 'Message': f'Setting removed for {ShowFolder}'})
        else:
            return jsonify({'Success': False, 'Message': 'Setting not found'}), 404
    except Exception as Ex:
        LoggingService.LogException("Exception deleting setting", Ex, "ShowSettingsController", "DeleteShowSetting")
        return jsonify({'Success': False, 'Message': str(Ex)}), 500


@ShowSettingsBlueprint.route('/SmartPopulate', methods=['POST'])
def SmartPopulateQueue():
    """Generate suggested queue items ranked by MediaFiles.PriorityScore.

    Body params (all optional):
      Drive   -- drive-letter prefix filter (e.g. 'T:')
      Limit   -- page size, 1-500 (default 100); the business service coerces.
      Offset  -- pagination offset (default 0)
      Search  -- substring match on FileName or show-folder segment, case-insensitive,
                 max 100 chars. Empty/whitespace = no filter.
      Mode    -- 'Transcode' | 'Remux'. Filters by MediaFiles.RecommendedMode so
                 Card 1 ('Transcode') and Card 1.5 ('Remux') get scoped result sets.
                 See remux-populate-card.feature.md criterion 4. Invalid value is
                 silently ignored (returns the unscoped set, backward-compat).

    Service is the source of truth for sort order (PriorityScore DESC NULLS LAST,
    SizeMB DESC). See smart-populate.flow.md for the user journey.
    """
    try:
        Data = request.get_json() or {}
        Limit = Data.get('Limit', 100)
        Offset = Data.get('Offset', 0)
        Drive = Data.get('Drive', '')
        Search = Data.get('Search', '') or ''
        Mode = Data.get('Mode')
        Focus = Data.get('Focus')  # 'Audio' | 'Container' | 'Mixed' (Quick Fix tab)
        if isinstance(Search, str) and len(Search) > 100:
            Search = Search[:100]

        from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
        Service = QueueManagementBusinessService()
        Result = Service.SmartPopulateQueue(Limit=Limit, Offset=Offset, Drive=Drive, Search=Search, Mode=Mode, Focus=Focus)

        return jsonify(Result)
    except Exception as Ex:
        LoggingService.LogException("Exception in smart populate", Ex, "ShowSettingsController", "SmartPopulateQueue")
        return jsonify({'Success': False, 'Message': str(Ex)}), 500


@ShowSettingsBlueprint.route('/NextTranscodeBatch', methods=['POST'])
def NextTranscodeBatch():
    """Largest non-compliant transcode candidates -- WHERE NeedsTranscode ORDER BY SizeMB DESC."""
    try:
        Data = request.get_json() or {}
        Limit = Data.get('Limit', 100)
        Offset = Data.get('Offset', 0)
        Drive = Data.get('Drive', '')
        Search = Data.get('Search', '') or ''
        if isinstance(Search, str) and len(Search) > 100:
            Search = Search[:100]

        from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
        Service = QueueManagementBusinessService()
        Result = Service.NextTranscodeBatch(Limit=Limit, Offset=Offset, Drive=Drive, Search=Search)
        return jsonify(Result)
    except Exception as Ex:
        LoggingService.LogException("Exception in NextTranscodeBatch", Ex, "ShowSettingsController", "NextTranscodeBatch")
        return jsonify({'Success': False, 'Message': str(Ex)}), 500


@ShowSettingsBlueprint.route('/QueueByFolder', methods=['POST'])
def QueueByFolder():
    """Queue all untranscoded files for specified show/media folders.
    Applies the same safety guards as PopulateQueueFromMediaFiles:
    - Skips files with HasExplicitEnglishAudio = false
    - Skips files already successfully transcoded with VMAF >= 80
    - Skips files already in the transcode queue
    """
    try:
        Data = request.get_json()
        if not Data:
            return jsonify({'Success': False, 'Message': 'No data provided'}), 400

        ShowFolders = Data.get('ShowFolders', [])
        ProfileId = Data.get('ProfileId')

        if not ShowFolders:
            return jsonify({'Success': False, 'Message': 'ShowFolders list is required'}), 400
        if not ProfileId:
            return jsonify({'Success': False, 'Message': 'ProfileId is required'}), 400

        ProfileId = int(ProfileId)

        # directive: path-schema-migration | # see path.S8
        from Core.Database.DatabaseService import DatabaseService, EscapeLikePattern
        from Core.Path.Path import Path as _PathSS, PathError as _PESS
        from Core.Path.PathStorageRoots import GetStorageRoots as _GSRSS

        FolderConditions = []
        Params = []
        for Folder in ShowFolders:
            try:
                _P = _PathSS.FromLegacyString(Folder, _GSRSS())
            except _PESS:
                continue
            FolderConditions.append("(m.StorageRootId = %s AND m.RelativePath LIKE %s ESCAPE '!')")
            Params.append(_P.StorageRootId)
            Params.append(EscapeLikePattern(_P.RelativePath) + '%')

        if not FolderConditions:
            # directive: path-class-perfection | # see path.C22
            from Core.Path.PathStorageRoots import GetPrefixMap as _GPMSS
            _Available = list(_GPMSS().values())
            return jsonify({'Success': False, 'Message': f'None of the provided ShowFolders matched a StorageRoot prefix. Inputs: {ShowFolders!r}. AvailableRoots: {_Available}'}), 400

        FolderWhere = ' OR '.join(FolderConditions)

        Sql = (
            "SELECT m.Id "
            "FROM MediaFiles m "
            "WHERE (m.TranscodedByMediaVortex IS NULL OR m.TranscodedByMediaVortex = false) "
            "  AND m.Id NOT IN (SELECT MediaFileId FROM TranscodeQueue WHERE MediaFileId IS NOT NULL) "
            "  AND m.SizeMB > 0 "
            "  AND (m.HasExplicitEnglishAudio IS NULL OR m.HasExplicitEnglishAudio = true) "
            "  AND m.Resolution IS NOT NULL "
            f"  AND ({FolderWhere}) "
            "ORDER BY m.SizeMB DESC"
        )

        Rows = DatabaseService().ExecuteQuery(Sql, tuple(Params))

        if not Rows:
            return jsonify({'Success': True, 'Message': 'No eligible files found in the selected folders', 'ItemsAdded': 0, 'ItemsSkipped': 0})

        MediaFileIds = [Row.get('Id') for Row in Rows if Row.get('Id') is not None]

        from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
        Service = QueueManagementBusinessService()
        Result = Service.AddSuggestionsToQueue(MediaFileIds=MediaFileIds, ProfileId=ProfileId, Mode='Transcode')

        return jsonify(Result)
    except Exception as Ex:
        LoggingService.LogException("Exception queuing by folder", Ex, "ShowSettingsController", "QueueByFolder")
        return jsonify({'Success': False, 'Message': str(Ex)}), 500


@ShowSettingsBlueprint.route('/QueueAllMatching', methods=['POST'])
def QueueAllMatching():
    """Queue every cascade-classified candidate matching optional Search/Drive
    in a single INSERT...SELECT. For Card 1.5's "Queue All" affordance.

    Body:
      Mode    -- required: 'Transcode' | 'Quick' | 'Remux'/'AudioFix' (legacy aliases).
      Search  -- optional substring; matches FileName or show-folder segment.
      Drive   -- optional drive prefix, e.g. 'T:'.
    """
    try:
        Data = request.get_json() or {}
        Mode = Data.get('Mode')
        _VALID_MODES = ('Transcode', 'Quick', 'Remux', 'AudioFix')
        if Mode not in _VALID_MODES:
            return jsonify({'Success': False, 'Message': f'Mode must be one of {_VALID_MODES} (got {Mode!r})'}), 400

        Search = Data.get('Search', '') or ''
        if isinstance(Search, str) and len(Search) > 100:
            Search = Search[:100]
        Drive = Data.get('Drive', '') or ''

        from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
        Service = QueueManagementBusinessService()
        Result = Service.QueueAllMatching(Mode=Mode, Search=Search, Drive=Drive)
        return jsonify(Result)
    except Exception as Ex:
        LoggingService.LogException("Exception in QueueAllMatching route", Ex, "ShowSettingsController", "QueueAllMatching")
        return jsonify({'Success': False, 'Message': str(Ex)}), 500


@ShowSettingsBlueprint.route('/AddToQueue', methods=['POST'])
def AddSuggestionsToQueue():
    """Add user-approved suggestions to the queue.

    Body:
      MediaFileIds -- list of ints. Preferred payload shape (slim).
      Items        -- legacy: list of dicts with MediaFileId. Only the
                      MediaFileId field is read; all other fields are
                      ignored (file metadata comes from MediaFiles).
      ProfileId    -- integer Profiles.Id, required for Mode='Transcode'.
                      Must be null/missing for Mode='Quick'/'Remux'/'AudioFix' --
                      the cascade has already decided "container/audio fix only"
                      so no profile choice is needed.
      Mode         -- 'Transcode' (default) | 'Quick' (post-2026-05-17 Remux+AudioFix
                      collapse) | 'Remux' / 'AudioFix' (legacy aliases, still
                      accepted for in-flight backward compat).
    """
    try:
        Data = request.get_json()
        if not Data:
            return jsonify({'Success': False, 'Message': 'No data provided'}), 400

        MediaFileIds = Data.get('MediaFileIds')
        Items = Data.get('Items')
        if not MediaFileIds and not Items:
            return jsonify({'Success': False, 'Message': 'No MediaFileIds or Items provided'}), 400

        Mode = Data.get('Mode', 'Transcode') or 'Transcode'
        _VALID_MODES = ('Transcode', 'Quick', 'Remux', 'AudioFix')
        if Mode not in _VALID_MODES:
            return jsonify({'Success': False, 'Message': f'Invalid Mode: {Mode!r}. Must be one of {_VALID_MODES}.'}), 400

        ProfileId = Data.get('ProfileId')
        if ProfileId is not None:
            try:
                ProfileId = int(ProfileId)
            except (TypeError, ValueError):
                return jsonify({'Success': False, 'Message': 'ProfileId must be an integer or null'}), 400

        from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
        Service = QueueManagementBusinessService()
        Result = Service.AddSuggestionsToQueue(
            MediaFileIds=MediaFileIds,
            Items=Items,
            ProfileId=ProfileId,
            Mode=Mode,
        )

        return jsonify(Result)
    except Exception as Ex:
        LoggingService.LogException("Exception adding suggestions to queue", Ex, "ShowSettingsController", "AddSuggestionsToQueue")
        return jsonify({'Success': False, 'Message': str(Ex)}), 500
