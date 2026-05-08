#!/usr/bin/env python3
"""
SystemSettingsController.py - Controller for managing system settings
"""

from flask import Blueprint, request, jsonify
from Core.Logging.LoggingService import LoggingService
from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository


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

                import os
                from pathlib import Path

                ProjectRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                FFmpegAbsolutePath = os.path.join(ProjectRoot, FFmpegPath)
                FFprobeAbsolutePath = os.path.join(ProjectRoot, FFprobePath)

                FFmpegExists = os.path.exists(FFmpegAbsolutePath)
                FFprobeExists = os.path.exists(FFprobeAbsolutePath)

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
        def AddExcludedDirectory():
            """Add a directory to the exclusion list."""
            try:
                import os
                Data = request.get_json()
                if not Data:
                    return jsonify({'Success': False, 'ErrorMessage': 'No JSON data provided'}), 400

                Directory = Data.get('Directory', '').strip()
                if not Directory:
                    return jsonify({'Success': False, 'ErrorMessage': 'Directory is required'}), 400

                ExcludedDirsSetting = self.Repository.GetSystemSetting('ExcludedDirectories')
                ExcludedDirs = [d.strip() for d in ExcludedDirsSetting.split(',') if d.strip()] if ExcludedDirsSetting else []

                NormalizedNewDir = os.path.normpath(Directory)
                if any(os.path.normpath(d) == NormalizedNewDir for d in ExcludedDirs):
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
        def RemoveExcludedDirectory():
            """Remove a directory from the exclusion list."""
            try:
                import os
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
                NormalizedDir = os.path.normpath(Directory)
                OriginalCount = len(ExcludedDirs)
                ExcludedDirs = [d for d in ExcludedDirs if os.path.normpath(d) != NormalizedDir]

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
