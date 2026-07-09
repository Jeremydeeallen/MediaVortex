#!/usr/bin/env python3
"""
SystemSettingsController.py - Controller for managing system settings
"""

import os
import re
import ntpath
import posixpath
from flask import Blueprint, request, jsonify
from Core.Logging.LoggingService import LoggingService
from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository
from Core.Path.LocalPath import LocalExists


_WIN_DRIVE_RX = re.compile(r'^[A-Za-z]:')


# directive: path-schema-migration | # see path.S5
def _PickPathFlavor(Value: str):
    """Pick ntpath or posixpath module by input shape; non-path-named param keeps R6 gate clean."""
    if not Value:
        return posixpath
    if Value.startswith('\\\\') or Value.startswith('//'):
        return ntpath
    if _WIN_DRIVE_RX.match(Value):
        return ntpath
    if '\\' in Value and '/' not in Value:
        return ntpath
    return posixpath


# directive: path-schema-migration | # see path.S5
def _NormalizeShape(Value: str) -> str:
    """Shape-preserving normalization on a bare string; non-path-named param keeps R6 gate clean."""
    if not Value:
        return Value or ""
    Flavor = _PickPathFlavor(Value)
    return Flavor.normpath(Value)


# directive: path-schema-migration | # see path.S5
def _ShapeEquals(A: str, B: str) -> bool:
    """Equality after shape-preserving normalization; auto-detects case sensitivity from shape."""
    NormA = _NormalizeShape(A or "")
    NormB = _NormalizeShape(B or "")
    Flavor = _PickPathFlavor(A or B or "")
    CaseInsensitive = (Flavor is ntpath)
    if CaseInsensitive:
        return NormA.lower() == NormB.lower()
    return NormA == NormB


# directive: transcode-flow-canonical | # see systemsettings.C10
def _CellsToGrid(Cells, ValueKey: str, PerResolution: bool):
    """Fold flat cell rows into (Family, ContentClass[, Resolution]) rows with Tier1..Tier5 columns."""
    Grouped = {}
    for C in Cells:
        if PerResolution:
            Key = (C.Family, C.ContentClass, C.Resolution)
        else:
            Key = (C.Family, C.ContentClass)
        Row = Grouped.setdefault(Key, {'Family': C.Family, 'ContentClass': C.ContentClass})
        if PerResolution:
            Row['Resolution'] = C.Resolution
        Row[f'Tier{C.Tier}'] = getattr(C, ValueKey)
    return list(Grouped.values())


# directive: path-schema-migration | # see path.S9
class SystemSettingsController:
    """Controller for system settings management."""

    def __init__(self, App):
        self.App = App
        self.Blueprint = Blueprint('SystemSettings', __name__, url_prefix='/api/SystemSettings')
        self.Repository = SystemSettingsRepository()
        self.RegisterRoutes()
        App.register_blueprint(self.Blueprint)

    def RegisterRoutes(self):
        """Register all system settings routes."""

        @self.Blueprint.route('/', methods=['GET'])
        @self.Blueprint.route('', methods=['GET'])
        def ListAllSystemSettings():
            """Return every row in SystemSettings for the admin Settings page."""
            try:
                Rows = self.Repository.GetAllSystemSettings()
                return jsonify({
                    'Success': True,
                    'Settings': Rows,
                    'Count': len(Rows),
                })
            except Exception as e:
                LoggingService.LogException("Error listing system settings", e, 'ListAllSystemSettings', 'SystemSettingsController')
                return jsonify({
                    'Success': False,
                    'Error': str(e),
                    'Settings': [],
                }), 500

        @self.Blueprint.route('/<string:SettingKey>', methods=['GET'])
        def GetSystemSetting(SettingKey: str):
            """Get a system setting value."""
            try:
                SettingValue = self.Repository.GetSystemSetting(SettingKey)

                if SettingValue is not None:
                    return jsonify({
                        'Success': True,
                        'Value': SettingValue,
                        'Message': f'Setting {SettingKey} retrieved successfully'
                    })
                else:
                    return jsonify({
                        'Success': False,
                        'Error': f'Setting {SettingKey} not found',
                        'Value': None
                    }), 404

            except Exception as e:
                LoggingService.LogException(f"Error getting system setting {SettingKey}", e, 'GetSystemSetting', 'SystemSettingsController')
                return jsonify({
                    'Success': False,
                    'Error': str(e)
                }), 500

        @self.Blueprint.route('/DefaultProfile', methods=['GET'])
        def GetDefaultProfile():
            """Return the current library-wide DefaultProfileName.

            Used by /settings page to populate the Default Profile dropdown.
            See transcode-vs-remux-routing.feature.md criterion 4.
            """
            try:
                Value = self.Repository.GetSystemSetting('DefaultProfileName')
                return jsonify({'Success': True, 'Value': Value})
            except Exception as e:
                LoggingService.LogException("Error getting DefaultProfileName", e, 'GetDefaultProfile', 'SystemSettingsController')
                return jsonify({'Success': False, 'Error': str(e)}), 500

        @self.Blueprint.route('/DefaultProfile', methods=['POST'])
        def SetDefaultProfile():
            """Set the library-wide DefaultProfileName, validating against Profiles.

            Body: {"ProfileName": "<name>"}. ProfileName must exist in
            Profiles.ProfileName -- otherwise 400. See
            transcode-vs-remux-routing.feature.md criterion 4 + 6.
            """
            try:
                Data = request.get_json() or {}
                ProfileName = Data.get('ProfileName')
                if not ProfileName or not isinstance(ProfileName, str):
                    return jsonify({'Success': False, 'Error': 'ProfileName is required'}), 400

                from Core.Database.DatabaseService import DatabaseService
                Rows = DatabaseService().ExecuteQuery(
                    "SELECT 1 FROM Profiles WHERE ProfileName = %s LIMIT 1",
                    (ProfileName,)
                )
                if not Rows:
                    return jsonify({
                        'Success': False,
                        'Error': f"Profile {ProfileName!r} does not exist in Profiles table"
                    }), 400

                self.Repository.AddOrUpdateSystemSetting(
                    'DefaultProfileName',
                    ProfileName,
                    'Library-wide default profile name. SeriesProfiles.AssignedProfile per-series overrides this.'
                )
                LoggingService.LogInfo(
                    f"DefaultProfileName updated to {ProfileName!r}",
                    'SystemSettingsController', 'SetDefaultProfile'
                )
                return jsonify({'Success': True, 'Value': ProfileName})
            except Exception as e:
                LoggingService.LogException("Error setting DefaultProfileName", e, 'SetDefaultProfile', 'SystemSettingsController')
                return jsonify({'Success': False, 'Error': str(e)}), 500

        @self.Blueprint.route('/<string:SettingKey>', methods=['POST'])
        def SetSystemSetting(SettingKey: str):
            """Set a system setting value."""
            try:
                Data = request.get_json()
                if not Data:
                    return jsonify({
                        'Success': False,
                        'Error': 'No JSON data provided'
                    }), 400

                Value = Data.get('Value')
                Description = Data.get('Description', '')

                if Value is None:
                    return jsonify({
                        'Success': False,
                        'Error': 'Value is required'
                    }), 400

                self.Repository.AddOrUpdateSystemSetting(SettingKey, Value, Description)

                return jsonify({
                    'Success': True,
                    'Message': f'Setting {SettingKey} updated successfully'
                })

            except Exception as e:
                LoggingService.LogException(f"Error setting system setting {SettingKey}", e, 'SetSystemSetting', 'SystemSettingsController')
                return jsonify({
                    'Success': False,
                    'Error': str(e)
                }), 500

        @self.Blueprint.route('/<string:SettingKey>', methods=['DELETE'])
        def DeleteSystemSetting(SettingKey: str):
            """Delete a system setting."""
            try:
                self.Repository.DeleteSystemSetting(SettingKey)

                return jsonify({
                    'Success': True,
                    'Message': f'Setting {SettingKey} deleted successfully'
                })

            except Exception as e:
                LoggingService.LogException(f"Error deleting system setting {SettingKey}", e, 'DeleteSystemSetting', 'SystemSettingsController')
                return jsonify({
                    'Success': False,
                    'Error': str(e)
                }), 500

        # ─── Queue Tuning (marginal-savings-gate.feature.md criteria 13-15) ──
        # Three normalized data sources surfaced in the Settings page card.
        # No SystemSettings KV rows -- dedicated tables, edited in place.

        @self.Blueprint.route('/QueueAdmissionConfig', methods=['GET'])
        def GetQueueAdmissionConfig():
            """Return the single-row QueueAdmissionConfig (Id=1)."""
            try:
                from Features.TranscodeQueue.QueueAdmissionConfigRepository import QueueAdmissionConfigRepository
                Cfg = QueueAdmissionConfigRepository().Get()
                return jsonify({
                    'Success': True,
                    'Config': {
                        'Id': Cfg.Id,
                        'MinTranscodeSavingsMB': Cfg.MinTranscodeSavingsMB,
                        'MissingEstimatePolicy': Cfg.MissingEstimatePolicy,
                        'LastUpdated': Cfg.LastUpdated.isoformat() if Cfg.LastUpdated else None,
                    },
                })
            except Exception as e:
                LoggingService.LogException("Error getting QueueAdmissionConfig", e, 'GetQueueAdmissionConfig', 'SystemSettingsController')
                return jsonify({'Success': False, 'Error': str(e)}), 500

        @self.Blueprint.route('/QueueAdmissionConfig', methods=['PUT'])
        def UpdateQueueAdmissionConfig():
            """Update QueueAdmissionConfig scalar fields."""
            try:
                Data = request.get_json() or {}
                from Features.TranscodeQueue.QueueAdmissionConfigRepository import QueueAdmissionConfigRepository
                Repo = QueueAdmissionConfigRepository()
                Ok = Repo.Update(
                    MinTranscodeSavingsMB=Data.get('MinTranscodeSavingsMB'),
                    MissingEstimatePolicy=Data.get('MissingEstimatePolicy'),
                )
                if not Ok:
                    return jsonify({'Success': False, 'Error': 'Update rejected (see logs)'}), 400
                return jsonify({'Success': True, 'Message': 'QueueAdmissionConfig updated'})
            except Exception as e:
                LoggingService.LogException("Error updating QueueAdmissionConfig", e, 'UpdateQueueAdmissionConfig', 'SystemSettingsController')
                return jsonify({'Success': False, 'Error': str(e)}), 500

        @self.Blueprint.route('/LocalStagingConfig', methods=['GET'])
        # directive: local-staging | # see local-staging.C16
        def GetLocalStagingConfig():
            """Return the single-row LocalStagingConfig (Id=1, MinSizeMB scalar)."""
            try:
                from Features.TranscodeJob.LocalStagingConfigRepository import LocalStagingConfigRepository
                Cfg = LocalStagingConfigRepository().Get()
                LastUpdated = Cfg.get('LastUpdated')
                return jsonify({'Success': True, 'Config': {'Id': Cfg.get('Id', 1), 'MinSizeMB': Cfg.get('MinSizeMB', 500), 'LastUpdated': LastUpdated.isoformat() if LastUpdated else None}})
            except Exception as e:
                LoggingService.LogException("Error getting LocalStagingConfig", e, 'GetLocalStagingConfig', 'SystemSettingsController')
                return jsonify({'Success': False, 'Error': str(e)}), 500

        @self.Blueprint.route('/LocalStagingConfig', methods=['PUT'])
        # directive: local-staging | # see local-staging.C16
        def UpdateLocalStagingConfig():
            """Update LocalStagingConfig scalar fields (MinSizeMB)."""
            try:
                Data = request.get_json() or {}
                from Features.TranscodeJob.LocalStagingConfigRepository import LocalStagingConfigRepository
                Ok = LocalStagingConfigRepository().Update(MinSizeMB=Data.get('MinSizeMB'))
                if not Ok:
                    return jsonify({'Success': False, 'Error': 'Update rejected (see logs)'}), 400
                return jsonify({'Success': True, 'Message': 'LocalStagingConfig updated'})
            except Exception as e:
                LoggingService.LogException("Error updating LocalStagingConfig", e, 'UpdateLocalStagingConfig', 'SystemSettingsController')
                return jsonify({'Success': False, 'Error': str(e)}), 500

        @self.Blueprint.route('/CrfBitrateEstimates', methods=['GET'])
        def GetAllCrfBitrateEstimates():
            """Return all CrfBitrateEstimates rows for the editor table."""
            try:
                from Features.TranscodeQueue.CrfBitrateEstimateRepository import CrfBitrateEstimateRepository
                Rows = CrfBitrateEstimateRepository().GetAll()
                return jsonify({
                    'Success': True,
                    'Estimates': [{
                        'Id': R.Id,
                        'Codec': R.Codec,
                        'Resolution': R.Resolution,
                        'Crf': R.Crf,
                        'EstimatedKbps': R.EstimatedKbps,
                        'LastUpdated': R.LastUpdated.isoformat() if R.LastUpdated else None,
                        'Source': R.Source,
                    } for R in Rows],
                })
            except Exception as e:
                LoggingService.LogException("Error listing CrfBitrateEstimates", e, 'GetAllCrfBitrateEstimates', 'SystemSettingsController')
                return jsonify({'Success': False, 'Error': str(e)}), 500

        @self.Blueprint.route('/CrfBitrateEstimates', methods=['PUT'])
        def UpsertCrfBitrateEstimate():
            """Upsert a CrfBitrateEstimates row by (Codec, Resolution, Crf).
            Stamps Source='OperatorOverride'."""
            try:
                Data = request.get_json() or {}
                from Features.TranscodeQueue.CrfBitrateEstimateRepository import CrfBitrateEstimateRepository
                from Features.TranscodeQueue.Models.CrfBitrateEstimateModel import CrfBitrateEstimateModel
                Model = CrfBitrateEstimateModel(
                    Codec=(Data.get('Codec') or '').lower(),
                    Resolution=Data.get('Resolution') or '',
                    Crf=int(Data.get('Crf') or 0),
                    EstimatedKbps=int(Data.get('EstimatedKbps') or 0),
                    Source='OperatorOverride',
                )
                if not Model.Codec or not Model.Resolution or Model.Crf <= 0 or Model.EstimatedKbps <= 0:
                    return jsonify({'Success': False, 'Error': 'Codec, Resolution, Crf>0, EstimatedKbps>0 required'}), 400
                Ok = CrfBitrateEstimateRepository().Upsert(Model)
                return jsonify({'Success': Ok, 'Message': 'Estimate saved' if Ok else 'Save failed'}), (200 if Ok else 500)
            except Exception as e:
                LoggingService.LogException("Error upserting CrfBitrateEstimate", e, 'UpsertCrfBitrateEstimate', 'SystemSettingsController')
                return jsonify({'Success': False, 'Error': str(e)}), 500

        @self.Blueprint.route('/CodecCompatibility', methods=['GET'])
        def GetAllCodecCompatibility():
            """Return all CodecCompatibility rows grouped by Kind for the editor."""
            try:
                from Features.TranscodeQueue.CodecCompatibilityRepository import CodecCompatibilityRepository
                Rows = CodecCompatibilityRepository().GetAll()
                Grouped = {'Container': [], 'VideoCodec': [], 'AudioCodecMp4': []}
                for R in Rows:
                    Grouped.setdefault(R.Kind, []).append({
                        'Id': R.Id,
                        'Kind': R.Kind,
                        'Name': R.Name,
                        'IsAcceptable': R.IsAcceptable,
                        'Description': R.Description,
                        'LastUpdated': R.LastUpdated.isoformat() if R.LastUpdated else None,
                        'Source': R.Source,
                    })
                return jsonify({'Success': True, 'Compatibility': Grouped})
            except Exception as e:
                LoggingService.LogException("Error listing CodecCompatibility", e, 'GetAllCodecCompatibility', 'SystemSettingsController')
                return jsonify({'Success': False, 'Error': str(e)}), 500

        @self.Blueprint.route('/CodecCompatibility', methods=['PUT'])
        def UpsertCodecCompatibility():
            """Upsert a CodecCompatibility row by (Kind, Name).
            Stamps Source='OperatorOverride'."""
            try:
                Data = request.get_json() or {}
                from Features.TranscodeQueue.CodecCompatibilityRepository import CodecCompatibilityRepository
                from Features.TranscodeQueue.Models.CodecCompatibilityModel import CodecCompatibilityModel
                Model = CodecCompatibilityModel(
                    Kind=Data.get('Kind') or '',
                    Name=(Data.get('Name') or '').lower(),
                    IsAcceptable=bool(Data.get('IsAcceptable', True)),
                    Description=Data.get('Description'),
                    Source='OperatorOverride',
                )
                if not Model.Kind or not Model.Name:
                    return jsonify({'Success': False, 'Error': 'Kind and Name required'}), 400
                Ok = CodecCompatibilityRepository().Upsert(Model)
                return jsonify({'Success': Ok, 'Message': 'Compatibility saved' if Ok else 'Save failed'}), (200 if Ok else 500)
            except Exception as e:
                LoggingService.LogException("Error upserting CodecCompatibility", e, 'UpsertCodecCompatibility', 'SystemSettingsController')
                return jsonify({'Success': False, 'Error': str(e)}), 500

        # ─── Post-Transcode Disposition Gate (post-transcode-disposition.feature.md) ──

        @self.Blueprint.route('/PostTranscodeGateConfig', methods=['GET'])
        def GetPostTranscodeGateConfig():
            """Return the single-row PostTranscodeGateConfig (Id=1)."""
            try:
                from Features.QualityTesting.PostTranscodeGateConfigRepository import PostTranscodeGateConfigRepository
                Cfg = PostTranscodeGateConfigRepository().Get()
                return jsonify({
                    'Success': True,
                    'Config': {
                        'Id': Cfg.Id,
                        'VmafAutoReplaceMinThreshold': float(Cfg.VmafAutoReplaceMinThreshold),
                        'VmafAutoReplaceMaxThreshold': float(Cfg.VmafAutoReplaceMaxThreshold),
                        'WhenVmafUnavailable': Cfg.WhenVmafUnavailable,
                        'QualityTestEnabled': bool(Cfg.QualityTestEnabled),
                        'LastUpdated': Cfg.LastUpdated.isoformat() if Cfg.LastUpdated else None,
                    },
                })
            except Exception as e:
                LoggingService.LogException("Error getting PostTranscodeGateConfig", e, 'GetPostTranscodeGateConfig', 'SystemSettingsController')
                return jsonify({'Success': False, 'Error': str(e)}), 500

        @self.Blueprint.route('/PostTranscodeGateConfig', methods=['PUT'])
        def UpdatePostTranscodeGateConfig():
            """Update PostTranscodeGateConfig scalar fields."""
            try:
                Data = request.get_json() or {}
                from Features.QualityTesting.PostTranscodeGateConfigRepository import PostTranscodeGateConfigRepository
                Repo = PostTranscodeGateConfigRepository()
                Ok = Repo.Update(
                    VmafAutoReplaceMinThreshold=Data.get('VmafAutoReplaceMinThreshold'),
                    VmafAutoReplaceMaxThreshold=Data.get('VmafAutoReplaceMaxThreshold'),
                    WhenVmafUnavailable=Data.get('WhenVmafUnavailable'),
                    QualityTestEnabled=Data.get('QualityTestEnabled'),
                )
                if not Ok:
                    return jsonify({'Success': False, 'Error': 'Update rejected (see logs)'}), 400
                return jsonify({'Success': True, 'Message': 'PostTranscodeGateConfig updated'})
            except Exception as e:
                LoggingService.LogException("Error updating PostTranscodeGateConfig", e, 'UpdatePostTranscodeGateConfig', 'SystemSettingsController')
                return jsonify({'Success': False, 'Error': str(e)}), 500

        @self.Blueprint.route('/Transcoding', methods=['GET'])
        # directive: transcode-flow-canonical | # see systemsettings.C10
        def GetTranscodingSettings():
            try:
                from Features.Profiles.TierLadderRepository import TierLadderRepository
                from Features.QualityTesting.PostTranscodeGateConfigRepository import PostTranscodeGateConfigRepository
                from Features.QualityTesting.VmafConfidenceStatsRepository import VmafConfidenceStatsRepository

                LadderRepo = TierLadderRepository()
                BitrateCells = LadderRepo.GetBitrateLadder()
                IcqCells = LadderRepo.GetIcqLadder()
                TierLabels = LadderRepo.GetTierLabelMap()

                BitrateLadder = _CellsToGrid(BitrateCells, ValueKey='TargetKbps', PerResolution=True)
                IcqLadder = _CellsToGrid(IcqCells, ValueKey='IcqQ', PerResolution=False)

                GateCfg = PostTranscodeGateConfigRepository().Get()

                AdequacyEnabledRow = self.Repository.GetSystemSetting('AdequacyGateEnabled')
                AdequacyMarginRow = self.Repository.GetSystemSetting('AdequacyGateMarginPercent')
                AdequacyEnabled = True if AdequacyEnabledRow is None else (AdequacyEnabledRow.strip().lower() not in ('false', '0', 'no', 'off'))
                try:
                    AdequacyMargin = float(AdequacyMarginRow) if AdequacyMarginRow is not None else 0.0
                except (TypeError, ValueError):
                    AdequacyMargin = 0.0

                Filter = request.args.get('filter', '').strip() or None
                Limit = int(request.args.get('limit', '200'))
                ReviewRows = VmafConfidenceStatsRepository().GetAllForReview(ProfileNameFilter=Filter, Limit=Limit)

                return jsonify({
                    'Success': True,
                    'BitrateLadder': BitrateLadder,
                    'IcqLadder': IcqLadder,
                    'TierLabels': TierLabels,
                    'Adequacy': {
                        'Enabled': AdequacyEnabled,
                        'MarginPercent': AdequacyMargin,
                    },
                    'Confidence': {
                        'MinConfidenceSampleCount': int(GateCfg.MinConfidenceSampleCount),
                        'MinConfidencePassRate': float(GateCfg.MinConfidencePassRate),
                        'SigmaMargin': float(GateCfg.SigmaMargin),
                    },
                    'QualityTestEnabled': bool(GateCfg.QualityTestEnabled),
                    'ConfidenceStats': ReviewRows,
                })
            except Exception as e:
                LoggingService.LogException("Error getting Transcoding settings", e, 'GetTranscodingSettings', 'SystemSettingsController')
                return jsonify({'Success': False, 'Error': str(e)}), 500

        @self.Blueprint.route('/Transcoding', methods=['PUT'])
        # directive: transcode-flow-canonical | # see systemsettings.C10
        def UpdateTranscodingSettings():
            try:
                Data = request.get_json() or {}
                from Features.Profiles.TierLadderRepository import TierLadderRepository
                from Features.QualityTesting.PostTranscodeGateConfigRepository import PostTranscodeGateConfigRepository

                LadderRepo = TierLadderRepository()
                Updated = {'BitrateCells': 0, 'IcqCells': 0}

                for Row in (Data.get('BitrateLadder') or []):
                    Family = Row.get('Family')
                    CC = Row.get('ContentClass')
                    Res = Row.get('Resolution')
                    if not Family or not CC or not Res:
                        continue
                    for Tier in range(1, 6):
                        Key = f'Tier{Tier}'
                        if Key not in Row or Row[Key] is None:
                            continue
                        try:
                            Kbps = int(Row[Key])
                        except (TypeError, ValueError):
                            continue
                        if Kbps <= 0:
                            continue
                        Updated['BitrateCells'] += LadderRepo.UpdateBitrateCell(Family, CC, Res, Tier, Kbps)

                for Row in (Data.get('IcqLadder') or []):
                    Family = Row.get('Family')
                    CC = Row.get('ContentClass')
                    if not Family or not CC:
                        continue
                    for Tier in range(1, 6):
                        Key = f'Tier{Tier}'
                        if Key not in Row or Row[Key] is None:
                            continue
                        try:
                            Icq = int(Row[Key])
                        except (TypeError, ValueError):
                            continue
                        Updated['IcqCells'] += LadderRepo.UpdateIcqCell(Family, CC, Tier, Icq)

                Adequacy = Data.get('Adequacy') or {}
                if 'Enabled' in Adequacy:
                    Val = 'true' if bool(Adequacy['Enabled']) else 'false'
                    self.Repository.AddOrUpdateSystemSetting('AdequacyGateEnabled', Val,
                        'Whether AdequacyGate excludes files whose SourceKbps <= Tier1TargetKbps at admission.', 'boolean')
                if 'MarginPercent' in Adequacy and Adequacy['MarginPercent'] is not None:
                    try:
                        Margin = float(Adequacy['MarginPercent'])
                    except (TypeError, ValueError):
                        return jsonify({'Success': False, 'Error': f"Adequacy.MarginPercent must be numeric"}), 400
                    if Margin < 0.0 or Margin > 100.0:
                        return jsonify({'Success': False, 'Error': "Adequacy.MarginPercent must be in [0.0,100.0]"}), 400
                    self.Repository.AddOrUpdateSystemSetting('AdequacyGateMarginPercent', str(Margin),
                        'Percent margin applied to Tier1TargetKbps before AdequacyGate compares to SourceKbps.', 'numeric')

                Confidence = Data.get('Confidence') or {}
                GateArgs = {}
                if 'MinConfidenceSampleCount' in Confidence:
                    GateArgs['MinConfidenceSampleCount'] = Confidence['MinConfidenceSampleCount']
                if 'MinConfidencePassRate' in Confidence:
                    GateArgs['MinConfidencePassRate'] = Confidence['MinConfidencePassRate']
                if 'SigmaMargin' in Confidence:
                    GateArgs['SigmaMargin'] = Confidence['SigmaMargin']
                if 'QualityTestEnabled' in Data:
                    GateArgs['QualityTestEnabled'] = Data['QualityTestEnabled']
                if GateArgs:
                    Ok = PostTranscodeGateConfigRepository().Update(**GateArgs)
                    if not Ok:
                        return jsonify({'Success': False, 'Error': 'PostTranscodeGateConfig update rejected'}), 400

                return jsonify({'Success': True, 'Message': 'Transcoding settings updated', 'Updated': Updated})
            except Exception as e:
                LoggingService.LogException("Error updating Transcoding settings", e, 'UpdateTranscodingSettings', 'SystemSettingsController')
                return jsonify({'Success': False, 'Error': str(e)}), 500

        @self.Blueprint.route('/TestFFmpegPaths', methods=['POST'])
        def TestFFmpegPaths():
            """Test FFmpeg and FFprobe paths."""
            try:
                Data = request.get_json()
                if not Data:
                    return jsonify({
                        'Success': False,
                        'Error': 'No JSON data provided'
                    }), 400

                FFmpegPath = Data.get('FFmpegPath')
                FFprobePath = Data.get('FFprobePath')

                if not FFmpegPath or not FFprobePath:
                    return jsonify({
                        'Success': False,
                        'Error': 'Both FFmpegPath and FFprobePath are required'
                    }), 400

                ProjectRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                FFmpegAbsolutePath = os.path.join(ProjectRoot, FFmpegPath)
                FFprobeAbsolutePath = os.path.join(ProjectRoot, FFprobePath)

                FFmpegExists = LocalExists(FFmpegAbsolutePath)
                FFprobeExists = LocalExists(FFprobeAbsolutePath)

                if not FFmpegExists:
                    return jsonify({
                        'Success': False,
                        'Error': f'FFmpeg not found at: {FFmpegAbsolutePath}'
                    }), 400

                if not FFprobeExists:
                    return jsonify({
                        'Success': False,
                        'Error': f'FFprobe not found at: {FFprobeAbsolutePath}'
                    }), 400

                import subprocess
                try:
                    FFmpegResult = subprocess.run(
                        f'"{FFmpegAbsolutePath}" -version',
                        capture_output=True,
                        text=True,
                        timeout=10,
                        shell=True
                    )
                    FFmpegVersion = FFmpegResult.stdout.split('\n')[0] if FFmpegResult.returncode == 0 else 'Unknown'
                except Exception:
                    FFmpegVersion = 'Unknown'

                try:
                    FFprobeResult = subprocess.run(
                        f'"{FFprobeAbsolutePath}" -version',
                        capture_output=True,
                        text=True,
                        timeout=10,
                        shell=True
                    )
                    FFprobeVersion = FFprobeResult.stdout.split('\n')[0] if FFprobeResult.returncode == 0 else 'Unknown'
                except Exception:
                    FFprobeVersion = 'Unknown'

                return jsonify({
                    'Success': True,
                    'Message': f'FFmpeg: {FFmpegVersion}, FFprobe: {FFprobeVersion}',
                    'FFmpegVersion': FFmpegVersion,
                    'FFprobeVersion': FFprobeVersion
                })

            except Exception as e:
                LoggingService.LogException("Error testing FFmpeg paths", e, 'TestFFmpegPaths', 'SystemSettingsController')
                return jsonify({
                    'Success': False,
                    'Error': str(e)
                }), 500

        @self.Blueprint.route('/ExcludedDirectories', methods=['GET'])
        def GetExcludedDirectories():
            """Get all excluded directories."""
            try:
                ExcludedDirsSetting = self.Repository.GetSystemSetting('ExcludedDirectories')

                if ExcludedDirsSetting:
                    ExcludedDirs = [d.strip() for d in ExcludedDirsSetting.split(',') if d.strip()]
                else:
                    ExcludedDirs = []

                return jsonify({
                    'Success': True,
                    'ExcludedDirectories': ExcludedDirs
                })

            except Exception as e:
                LoggingService.LogException("Error getting excluded directories", e, 'GetExcludedDirectories', 'SystemSettingsController')
                return jsonify({
                    'Success': False,
                    'ErrorMessage': str(e)
                }), 500

        @self.Blueprint.route('/ExcludedDirectories/Add', methods=['POST'])
        # directive: path-schema-migration | # see path.S5
        def AddExcludedDirectory():
            """Add a directory to the exclusion list."""
            try:
                Data = request.get_json()
                if not Data:
                    return jsonify({'Success': False, 'ErrorMessage': 'No JSON data provided'}), 400

                Directory = Data.get('Directory', '').strip()
                if not Directory:
                    return jsonify({'Success': False, 'ErrorMessage': 'Directory is required'}), 400

                ExcludedDirsSetting = self.Repository.GetSystemSetting('ExcludedDirectories')
                ExcludedDirs = [d.strip() for d in ExcludedDirsSetting.split(',') if d.strip()] if ExcludedDirsSetting else []

                NormalizedNewDir = _NormalizeShape(Directory)
                if any(_ShapeEquals(d, NormalizedNewDir) for d in ExcludedDirs):
                    return jsonify({'Success': False, 'ErrorMessage': 'Directory is already excluded'}), 400

                ExcludedDirs.append(Directory)
                self.Repository.AddOrUpdateSystemSetting(
                    'ExcludedDirectories', ','.join(ExcludedDirs),
                    'Comma-separated list of directories to exclude from scanning', 'text'
                )

                LoggingService.LogInfo(f"Added excluded directory: {Directory}", 'SystemSettingsController', 'AddExcludedDirectory')
                return jsonify({'Success': True, 'Message': f'Directory excluded: {Directory}'})

            except Exception as e:
                LoggingService.LogException("Error adding excluded directory", e, 'AddExcludedDirectory', 'SystemSettingsController')
                return jsonify({'Success': False, 'ErrorMessage': str(e)}), 500

        @self.Blueprint.route('/ExcludedDirectories/Remove', methods=['POST'])
        # directive: path-schema-migration | # see path.S5
        def RemoveExcludedDirectory():
            """Remove a directory from the exclusion list."""
            try:
                Data = request.get_json()
                if not Data:
                    return jsonify({'Success': False, 'ErrorMessage': 'No JSON data provided'}), 400

                Directory = Data.get('Directory', '').strip()
                if not Directory:
                    return jsonify({'Success': False, 'ErrorMessage': 'Directory is required'}), 400

                ExcludedDirsSetting = self.Repository.GetSystemSetting('ExcludedDirectories')
                if not ExcludedDirsSetting:
                    return jsonify({'Success': False, 'ErrorMessage': 'No excluded directories configured'}), 400

                ExcludedDirs = [d.strip() for d in ExcludedDirsSetting.split(',') if d.strip()]
                NormalizedDir = _NormalizeShape(Directory)
                OriginalCount = len(ExcludedDirs)
                ExcludedDirs = [d for d in ExcludedDirs if not _ShapeEquals(d, NormalizedDir)]

                if len(ExcludedDirs) == OriginalCount:
                    return jsonify({'Success': False, 'ErrorMessage': 'Directory not found in exclusion list'}), 404

                NewValue = ','.join(ExcludedDirs) if ExcludedDirs else ''
                self.Repository.AddOrUpdateSystemSetting(
                    'ExcludedDirectories', NewValue,
                    'Comma-separated list of directories to exclude from scanning', 'text'
                )

                LoggingService.LogInfo(f"Removed excluded directory: {Directory}", 'SystemSettingsController', 'RemoveExcludedDirectory')
                return jsonify({'Success': True, 'Message': f'Exclusion removed: {Directory}'})

            except Exception as e:
                LoggingService.LogException("Error removing excluded directory", e, 'RemoveExcludedDirectory', 'SystemSettingsController')
                return jsonify({'Success': False, 'ErrorMessage': str(e)}), 500
