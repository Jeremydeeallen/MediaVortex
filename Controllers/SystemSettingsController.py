#!/usr/bin/env python3
"""
SystemSettingsController.py - Controller for managing system settings
"""

from flask import Blueprint, request, jsonify
from Services.LoggingService import LoggingService
from Repositories.DatabaseManager import DatabaseManager


class SystemSettingsController:
    """Controller for system settings management."""
    
    def __init__(self, App):
        self.App = App
        self.Blueprint = Blueprint('SystemSettings', __name__, url_prefix='/api/SystemSettings')
        self.DatabaseManager = DatabaseManager()
        self.RegisterRoutes()
        App.register_blueprint(self.Blueprint)
    
    def RegisterRoutes(self):
        """Register all system settings routes."""
        
        @self.Blueprint.route('/<string:SettingKey>', methods=['GET'])
        def GetSystemSetting(SettingKey: str):
            """Get a system setting value."""
            try:
                SettingValue = self.DatabaseManager.GetSystemSetting(SettingKey)
                
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
                
                self.DatabaseManager.AddOrUpdateSystemSetting(SettingKey, Value, Description)
                
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
                self.DatabaseManager.DeleteSystemSetting(SettingKey)
                
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
                
                # Convert relative paths to absolute paths
                ProjectRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                FFmpegAbsolutePath = os.path.join(ProjectRoot, FFmpegPath)
                FFprobeAbsolutePath = os.path.join(ProjectRoot, FFprobePath)
                
                # Test if files exist
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
                
                # Test FFmpeg version
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
                
                # Test FFprobe version
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
