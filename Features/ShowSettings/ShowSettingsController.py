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
        Default = Repository.GetDefaultTargetResolution()
        return jsonify({'Success': True, 'Data': Shows, 'DefaultTargetResolution': Default or ''})
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


@ShowSettingsBlueprint.route('/Default', methods=['GET'])
def GetDefaultSetting():
    """Get the default target resolution."""
    try:
        Default = Repository.GetDefaultTargetResolution()
        return jsonify({'Success': True, 'DefaultTargetResolution': Default or ''})
    except Exception as Ex:
        LoggingService.LogException("Exception getting default", Ex, "ShowSettingsController", "GetDefaultSetting")
        return jsonify({'Success': False, 'Message': str(Ex)}), 500


@ShowSettingsBlueprint.route('/Default', methods=['POST'])
def SetDefaultSetting():
    """Set the default target resolution (applies to shows without specific settings)."""
    try:
        Data = request.get_json()
        if not Data:
            return jsonify({'Success': False, 'Message': 'No data provided'}), 400

        TargetResolution = Data.get('TargetResolution', '').strip()

        ValidResolutions = ['480p', '720p', '1080p', '2160p', '']
        if TargetResolution not in ValidResolutions:
            return jsonify({'Success': False, 'Message': f'Invalid TargetResolution. Must be one of: {ValidResolutions}'}), 400

        Setting = ShowSettingModel(ShowFolder='*', TargetResolution=TargetResolution)
        Repository.SaveShowSetting(Setting)
        return jsonify({'Success': True, 'Message': f'Default target resolution set to {TargetResolution or "profile default"}'})
    except Exception as Ex:
        LoggingService.LogException("Exception setting default", Ex, "ShowSettingsController", "SetDefaultSetting")
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
        if isinstance(Search, str) and len(Search) > 100:
            Search = Search[:100]

        from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
        Service = QueueManagementBusinessService()
        Result = Service.SmartPopulateQueue(Limit=Limit, Offset=Offset, Drive=Drive, Search=Search, Mode=Mode)

        return jsonify(Result)
    except Exception as Ex:
        LoggingService.LogException("Exception in smart populate", Ex, "ShowSettingsController", "SmartPopulateQueue")
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

        from Core.Database.DatabaseService import DatabaseService, EscapeLikePattern

        FolderConditions = []
        Params = []
        for Folder in ShowFolders:
            FolderConditions.append("m.FilePath LIKE %s ESCAPE '!'")
            Params.append(EscapeLikePattern(Folder) + '%')

        FolderWhere = ' OR '.join(FolderConditions)

        Sql = f"""
            SELECT m.Id, m.FilePath, m.FileName, m.SizeMB, m.VideoBitrateKbps,
                   m.Codec, m.Resolution, m.ResolutionCategory,
                   m.HasExplicitEnglishAudio, m.AudioLanguages
            FROM MediaFiles m
            WHERE (m.TranscodedByMediaVortex IS NULL OR m.TranscodedByMediaVortex = false)
              AND m.Id NOT IN (SELECT MediaFileId FROM TranscodeQueue WHERE MediaFileId IS NOT NULL)
              AND m.SizeMB > 0
              AND (m.HasExplicitEnglishAudio IS NULL OR m.HasExplicitEnglishAudio = true)
              AND m.Resolution IS NOT NULL
              AND ({FolderWhere})
            ORDER BY m.SizeMB DESC
        """

        Rows = DatabaseService().ExecuteQuery(Sql, tuple(Params))

        if not Rows:
            return jsonify({'Success': True, 'Message': 'No eligible files found in the selected folders', 'ItemsAdded': 0, 'ItemsSkipped': 0})

        Items = []
        for Row in Rows:
            Items.append({
                'MediaFileId': Row.get('Id'),
                'FilePath': Row.get('FilePath', ''),
                'SizeMB': float(Row.get('SizeMB', 0) or 0),
                'Mode': 'Transcode',
                'Priority': int(float(Row.get('SizeMB', 0) or 0)),
            })

        from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
        Service = QueueManagementBusinessService()
        Result = Service.AddSuggestionsToQueue(Items, ProfileId=ProfileId)

        return jsonify(Result)
    except Exception as Ex:
        LoggingService.LogException("Exception queuing by folder", Ex, "ShowSettingsController", "QueueByFolder")
        return jsonify({'Success': False, 'Message': str(Ex)}), 500


@ShowSettingsBlueprint.route('/AddToQueue', methods=['POST'])
def AddSuggestionsToQueue():
    """Add user-approved suggestions to the queue.

    Body:
      Items     -- list of {MediaFileId, FilePath, FileName, SizeMB, ...}
      ProfileId -- (optional) integer Profiles.Id. Required when Mode='Transcode'.
                   For Mode='Remux' must be null/missing -- the cascade has
                   already decided "container/audio fix only" so no profile
                   choice is needed. See remux-populate-card.feature.md
                   criterion 5.
      Mode      -- 'Transcode' (default) or 'Remux'. Validated against this
                   tuple; other values return HTTP 400 (criterion 6).
    """
    try:
        Data = request.get_json()
        if not Data:
            return jsonify({'Success': False, 'Message': 'No data provided'}), 400

        Items = Data.get('Items', [])
        if not Items:
            return jsonify({'Success': False, 'Message': 'No items provided'}), 400

        Mode = Data.get('Mode', 'Transcode') or 'Transcode'
        if Mode not in ('Transcode', 'Remux'):
            return jsonify({'Success': False, 'Message': f'Invalid Mode: {Mode!r}. Must be "Transcode" or "Remux".'}), 400

        ProfileId = Data.get('ProfileId')
        if ProfileId is not None:
            try:
                ProfileId = int(ProfileId)
            except (TypeError, ValueError):
                return jsonify({'Success': False, 'Message': 'ProfileId must be an integer or null'}), 400

        from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
        Service = QueueManagementBusinessService()
        Result = Service.AddSuggestionsToQueue(Items, ProfileId=ProfileId, Mode=Mode)

        return jsonify(Result)
    except Exception as Ex:
        LoggingService.LogException("Exception adding suggestions to queue", Ex, "ShowSettingsController", "AddSuggestionsToQueue")
        return jsonify({'Success': False, 'Message': str(Ex)}), 500
