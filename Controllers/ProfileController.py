from flask import Blueprint, request, jsonify
from ViewModels.ProfileManagementViewModel import ProfileManagementViewModel
from Models.TranscodeProfileModel import TranscodeProfileModel
from Models.ProfileThresholdModel import ProfileThresholdModel
from Services.LoggingService import LoggingService
from datetime import datetime


class ProfileController:
    """API controller for profile management endpoints."""
    
    def __init__(self, view_model: ProfileManagementViewModel = None):
        self.ViewModel = view_model or ProfileManagementViewModel()
        self.Blueprint = Blueprint('profiles', __name__)
        self._register_routes()
    
    def _register_routes(self):
        """Register all profile-related routes."""
        
        @self.Blueprint.route('/profiles', methods=['GET'])
        def get_all_profiles():
            """Get all profiles."""
            try:
                success = self.ViewModel.LoadProfiles()
                if success:
                    return jsonify({
                        'success': True,
                        'profiles': self.ViewModel.GetProfilesAsDict(),
                        'message': 'Profiles loaded successfully'
                    })
                else:
                    return jsonify({
                        'success': False,
                        'error': self.ViewModel.ErrorMessage
                    }), 500
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': f'Failed to load profiles: {str(e)}'
                }), 500
        
        @self.Blueprint.route('/profiles/<int:profile_id>', methods=['GET'])
        def get_profile(profile_id):
            """Get a specific profile with its thresholds."""
            try:
                success = self.ViewModel.SelectProfile(profile_id)
                if success:
                    return jsonify({
                        'success': True,
                        'profile': self.ViewModel.GetSelectedProfileAsDict(),
                        'message': 'Profile loaded successfully'
                    })
                else:
                    return jsonify({
                        'success': False,
                        'error': self.ViewModel.ErrorMessage
                    }), 404
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': f'Failed to load profile: {str(e)}'
                }), 500
        
        @self.Blueprint.route('/profiles', methods=['POST'])
        def create_profile():
            """Create a new profile with thresholds."""
            try:
                LoggingService.LogFunctionEntry("create_profile")
                data = request.get_json()
                LoggingService.LogInfo("Received data", data)
                
                if not data or 'ProfileName' not in data:
                    LoggingService.LogInfo("Missing ProfileName")
                    return jsonify({
                        'success': False,
                        'error': 'ProfileName is required'
                    }), 400
                
                profile_name = data['ProfileName'].strip()
                description = data.get('Description', '').strip()
                thresholds = data.get('Thresholds', [])
                
                LoggingService.LogInfo("Profile name: {}, Description: {}, Thresholds count: {}", 
                               profile_name, description, len(thresholds))
                
                success = self.ViewModel.CreateProfileWithThresholds(profile_name, description, thresholds)
                LoggingService.LogInfo("CreateProfileWithThresholds result: {}", success)
                
                if success:
                    LoggingService.LogInfo("Success message: {}", self.ViewModel.SuccessMessage)
                    return jsonify({
                        'success': True,
                        'message': self.ViewModel.SuccessMessage
                    }), 201
                else:
                    LoggingService.LogInfo("Error message: {}", self.ViewModel.ErrorMessage)
                    return jsonify({
                        'success': False,
                        'error': self.ViewModel.ErrorMessage
                    }), 400
            except Exception as e:
                LoggingService.LogInfoException("Exception in create_profile", e)
                return jsonify({
                    'success': False,
                    'error': f'Failed to create profile: {str(e)}'
                }), 500
        
        @self.Blueprint.route('/profiles/<int:profile_id>', methods=['PUT'])
        def update_profile(profile_id):
            """Update an existing profile with thresholds."""
            try:
                LoggingService.LogFunctionEntry("update_profile", profile_id)
                data = request.get_json()
                LoggingService.LogInfo("Received data", data)
                
                if not data:
                    LoggingService.LogInfo("No data received")
                    return jsonify({
                        'success': False,
                        'error': 'Profile data is required'
                    }), 400
                
                profile_name = data.get('ProfileName', '').strip()
                description = data.get('Description', '').strip()
                thresholds = data.get('Thresholds', [])
                
                LoggingService.LogInfo("Profile name: {}, Description: {}, Thresholds count: {}", 
                               profile_name, description, len(thresholds))
                
                success = self.ViewModel.UpdateProfileWithThresholds(profile_id, profile_name, description, thresholds)
                LoggingService.LogInfo("UpdateProfileWithThresholds result: {}", success)
                
                if success:
                    LoggingService.LogInfo("Success message: {}", self.ViewModel.SuccessMessage)
                    return jsonify({
                        'success': True,
                        'message': self.ViewModel.SuccessMessage
                    })
                else:
                    LoggingService.LogInfo("Error message: {}", self.ViewModel.ErrorMessage)
                    return jsonify({
                        'success': False,
                        'error': self.ViewModel.ErrorMessage
                    }), 400
            except Exception as e:
                LoggingService.LogInfoException("Exception in update_profile", e)
                return jsonify({
                    'success': False,
                    'error': f'Failed to update profile: {str(e)}'
                }), 500
        
        @self.Blueprint.route('/profiles/<int:profile_id>', methods=['DELETE'])
        def delete_profile(profile_id):
            """Delete a profile."""
            try:
                success = self.ViewModel.DeleteProfile(profile_id)
                if success:
                    return jsonify({
                        'success': True,
                        'message': self.ViewModel.SuccessMessage
                    })
                else:
                    return jsonify({
                        'success': False,
                        'error': self.ViewModel.ErrorMessage
                    }), 400
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': f'Failed to delete profile: {str(e)}'
                }), 500
        
        @self.Blueprint.route('/profiles/<int:profile_id>/thresholds', methods=['POST'])
        def add_threshold(profile_id):
            """Add a threshold to a profile."""
            try:
                data = request.get_json()
                if not data:
                    return jsonify({
                        'success': False,
                        'error': 'Threshold data is required'
                    }), 400
                
                required_fields = ['Resolution', 'Under30MinMB', 'Under65MinMB', 'Over65MinMB',
                                 'VideoBitrateKbps', 'AudioBitrateKbps', 'FallbackVideoBitrateKbps',
                                 'FallbackAudioBitrateKbps', 'TranscodeDownTo']
                
                for field in required_fields:
                    if field not in data:
                        return jsonify({
                            'success': False,
                            'error': f'{field} is required'
                        }), 400
                
                success = self.ViewModel.AddThreshold(
                    profile_id,
                    data['Resolution'].strip(),
                    int(data['Under30MinMB']),
                    int(data['Under65MinMB']),
                    int(data['Over65MinMB']),
                    int(data['VideoBitrateKbps']),
                    int(data['AudioBitrateKbps']),
                    int(data['FallbackVideoBitrateKbps']),
                    int(data['FallbackAudioBitrateKbps']),
                    data['TranscodeDownTo'].strip()
                )
                
                if success:
                    return jsonify({
                        'success': True,
                        'message': self.ViewModel.SuccessMessage
                    }), 201
                else:
                    return jsonify({
                        'success': False,
                        'error': self.ViewModel.ErrorMessage
                    }), 400
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': f'Failed to add threshold: {str(e)}'
                }), 500
        
        @self.Blueprint.route('/profiles/<int:profile_id>/thresholds/<int:threshold_id>', methods=['PUT'])
        def update_threshold(profile_id, threshold_id):
            """Update a threshold."""
            try:
                data = request.get_json()
                if not data:
                    return jsonify({
                        'success': False,
                        'error': 'Threshold data is required'
                    }), 400
                
                threshold = ProfileThresholdModel(
                    Id=threshold_id,
                    ProfileId=profile_id,
                    Resolution=data.get('Resolution', '').strip(),
                    Under30MinMB=int(data.get('Under30MinMB', 0)),
                    Under65MinMB=int(data.get('Under65MinMB', 0)),
                    Over65MinMB=int(data.get('Over65MinMB', 0)),
                    VideoBitrateKbps=int(data.get('VideoBitrateKbps', 0)),
                    AudioBitrateKbps=int(data.get('AudioBitrateKbps', 0)),
                    FallbackVideoBitrateKbps=int(data.get('FallbackVideoBitrateKbps', 0)),
                    FallbackAudioBitrateKbps=int(data.get('FallbackAudioBitrateKbps', 0)),
                    TranscodeDownTo=data.get('TranscodeDownTo', '').strip()
                )
                
                success = self.ViewModel.UpdateThreshold(threshold)
                if success:
                    return jsonify({
                        'success': True,
                        'message': self.ViewModel.SuccessMessage
                    })
                else:
                    return jsonify({
                        'success': False,
                        'error': self.ViewModel.ErrorMessage
                    }), 400
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': f'Failed to update threshold: {str(e)}'
                }), 500
        
        @self.Blueprint.route('/profiles/<int:profile_id>/thresholds/<int:threshold_id>', methods=['DELETE'])
        def delete_threshold(profile_id, threshold_id):
            """Delete a threshold."""
            try:
                success = self.ViewModel.DeleteThreshold(threshold_id)
                if success:
                    return jsonify({
                        'success': True,
                        'message': self.ViewModel.SuccessMessage
                    })
                else:
                    return jsonify({
                        'success': False,
                        'error': self.ViewModel.ErrorMessage
                    }), 400
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': f'Failed to delete threshold: {str(e)}'
                }), 500
