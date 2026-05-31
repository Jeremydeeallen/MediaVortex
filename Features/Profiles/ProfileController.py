from flask import Blueprint, request, jsonify
from Features.Profiles.ProfileManagementViewModel import ProfileManagementViewModel
from Features.Profiles.Models.TranscodeProfileModel import TranscodeProfileModel
from Features.Profiles.Models.ProfileThresholdModel import ProfileThresholdModel
from Core.Logging.LoggingService import LoggingService
from datetime import datetime


# directive: unify-profile-editor
class ProfileController:
    """API controller for profile management endpoints."""

    # directive: unify-profile-editor
    def __init__(self, view_model: ProfileManagementViewModel = None):
        self.ViewModel = view_model or ProfileManagementViewModel()
        self.Blueprint = Blueprint('profiles', __name__, url_prefix='/api')
        self._register_routes()

    # directive: unify-profile-editor
    def _register_routes(self):
        """Register all profile-related routes."""

        @self.Blueprint.route('/profiles', methods=['GET'])
        # directive: unify-profile-editor
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
                LoggingService.LogException("Failed to load profiles", e, "ProfileController", "get_all_profiles")
                return jsonify({
                    'success': False,
                    'error': f'Failed to load profiles: {str(e)}'
                }), 500

        @self.Blueprint.route('/profiles/<int:profile_id>', methods=['GET'])
        # directive: unify-profile-editor
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
                LoggingService.LogException("Failed to load profile", e, "ProfileController", "get_profile")
                return jsonify({
                    'success': False,
                    'error': f'Failed to load profile: {str(e)}'
                }), 500

        @self.Blueprint.route('/profiles', methods=['POST'])
        # directive: unify-profile-editor
        def create_profile():
            """Create a new profile with thresholds."""
            try:
                LoggingService.LogFunctionEntry("create_profile")
                data = request.get_json()
                LoggingService.LogInfo(f"Received data: {data}", "create_profile", "ProfileController")

                if not data or 'ProfileName' not in data:
                    LoggingService.LogInfo("Missing ProfileName", "create_profile", "ProfileController")
                    return jsonify({
                        'success': False,
                        'error': 'ProfileName is required'
                    }), 400

                profile_name = data['ProfileName'].strip()
                description = data.get('Description', '').strip()
                thresholds = data.get('Thresholds', [])

                codec = data.get('Codec', 'libsvtav1')
                preset = data.get('Preset', 6)
                film_grain = data.get('FilmGrain', 10)
                yadif_mode = data.get('YadifMode', 1)
                yadif_parity = data.get('YadifParity', 1)
                yadif_deint = data.get('YadifDeint', 1)
                use_nvidia_hardware = data.get('UseNvidiaHardware', 0)

                LoggingService.LogInfo(f"Profile name: {profile_name}, Description: {description}, Thresholds count: {len(thresholds)}, Codec: {codec}, Preset: {preset}", "create_profile", "ProfileController")

                success = self.ViewModel.CreateProfileWithThresholds(profile_name, description, thresholds,
                                                                    codec, preset, film_grain, yadif_mode, yadif_parity, yadif_deint, use_nvidia_hardware)
                LoggingService.LogInfo(f"CreateProfileWithThresholds result: {success}", "create_profile", "ProfileController")

                if success:
                    LoggingService.LogInfo(f"Success message: {self.ViewModel.SuccessMessage}", "create_profile", "ProfileController")
                    return jsonify({
                        'success': True,
                        'message': self.ViewModel.SuccessMessage
                    }), 201
                else:
                    LoggingService.LogInfo(f"Error message: {self.ViewModel.ErrorMessage}", "create_profile", "ProfileController")
                    return jsonify({
                        'success': False,
                        'error': self.ViewModel.ErrorMessage
                    }), 400
            except Exception as e:
                LoggingService.LogException("Exception in create_profile", e, "create_profile", "ProfileController")
                return jsonify({
                    'success': False,
                    'error': f'Failed to create profile: {str(e)}'
                }), 500

        @self.Blueprint.route('/profiles/<int:profile_id>', methods=['PUT'])
        # directive: unify-profile-editor
        def UpdateProfile(profile_id):
            """Update an existing profile with thresholds."""
            try:
                LoggingService.LogFunctionEntry("UpdateProfile", profile_id)
                data = request.get_json()
                LoggingService.LogInfo(f"Received data: {data}", "UpdateProfile", "ProfileController")

                if not data:
                    LoggingService.LogInfo("No data received", "UpdateProfile", "ProfileController")
                    return jsonify({
                        'success': False,
                        'error': 'Profile data is required'
                    }), 400

                profile_name = data.get('ProfileName', '').strip()
                description = data.get('Description', '').strip()
                thresholds = data.get('Thresholds', [])

                codec = data.get('Codec', 'libsvtav1')
                preset = data.get('Preset', 6)
                film_grain = data.get('FilmGrain', 10)
                yadif_mode = data.get('YadifMode', 1)
                yadif_parity = data.get('YadifParity', 1)
                yadif_deint = data.get('YadifDeint', 1)
                use_nvidia_hardware = data.get('UseNvidiaHardware', 0)

                LoggingService.LogInfo(f"Profile name: {profile_name}, Description: {description}, Thresholds count: {len(thresholds)}, Codec: {codec}, Preset: {preset}", "UpdateProfile", "ProfileController")

                success = self.ViewModel.UpdateProfileWithThresholds(profile_id, profile_name, description, thresholds,
                                                                    codec, preset, film_grain, yadif_mode, yadif_parity, yadif_deint, use_nvidia_hardware)
                LoggingService.LogInfo(f"UpdateProfileWithThresholds result: {success}", "UpdateProfile", "ProfileController")

                if success:
                    LoggingService.LogInfo(f"Success message: {self.ViewModel.SuccessMessage}", "UpdateProfile", "ProfileController")
                    return jsonify({
                        'success': True,
                        'message': self.ViewModel.SuccessMessage
                    })
                else:
                    LoggingService.LogInfo(f"Error message: {self.ViewModel.ErrorMessage}", "UpdateProfile", "ProfileController")
                    return jsonify({
                        'success': False,
                        'error': self.ViewModel.ErrorMessage
                    }), 400
            except Exception as e:
                LoggingService.LogException("Exception in UpdateProfile", e, "UpdateProfile", "ProfileController")
                return jsonify({
                    'success': False,
                    'error': f'Failed to update profile: {str(e)}'
                }), 500

        @self.Blueprint.route('/profiles/<int:profile_id>/knobs', methods=['PATCH'])
        # directive: unify-profile-editor
        def patch_profile_knobs(profile_id):
            """Update lifted knob columns on Profiles + ProfileThresholds. Column names whitelisted."""
            try:
                Payload = request.get_json() or {}
                PROFILE_COLS = {
                    'ProfileName', 'Description',
                    'Codec', 'Preset', 'FilmGrain',
                    'YadifMode', 'YadifParity', 'YadifDeint', 'UseNvidiaHardware',
                    'Tune', 'Multipass', 'PixelFormat',
                    'AudioCodec', 'AudioBitrateKbps', 'AudioChannels', 'AudioFilter',
                    'Container', 'FastStart', 'RateControlMode', 'AqStrength',
                }
                THRESHOLD_COLS = {
                    'Resolution', 'TranscodeDownTo', 'Quality', 'ContainerType',
                    'Under30MinMB', 'Under65MinMB', 'Over65MinMB',
                    'VideoBitrateKbps', 'AudioBitrateKbps',
                    'FallbackVideoBitrateKbps', 'FallbackAudioBitrateKbps',
                    'RcLookahead', 'BFrames', 'BRefMode',
                    'ScaleHeight', 'MaxBitrateMultiplier',
                    'SourceBitratePercent', 'MinBitrateKbps', 'MaxBitrateKbps', 'Gop',
                }
                from Core.Database.DatabaseService import DatabaseService
                Db = DatabaseService()

                ProfileUpdates = {k: v for k, v in (Payload.get('Profile') or {}).items() if k in PROFILE_COLS}
                if ProfileUpdates:
                    Sets = ', '.join(f'{k} = %s' for k in ProfileUpdates.keys())
                    Db.ExecuteNonQuery(f'UPDATE Profiles SET {Sets} WHERE Id = %s',
                                       tuple(ProfileUpdates.values()) + (profile_id,))

                ThresholdRows = Payload.get('Thresholds') or []
                ThresholdsUpdated = 0
                for Row in ThresholdRows:
                    Tid = Row.get('Id')
                    if not Tid:
                        continue
                    Updates = {k: v for k, v in Row.items() if k in THRESHOLD_COLS}
                    if not Updates:
                        continue
                    Sets = ', '.join(f'{k} = %s' for k in Updates.keys())
                    Db.ExecuteNonQuery(
                        f'UPDATE ProfileThresholds SET {Sets} WHERE Id = %s AND ProfileId = %s',
                        tuple(Updates.values()) + (Tid, profile_id),
                    )
                    ThresholdsUpdated += 1

                return jsonify({
                    'success': True,
                    'message': f'Updated {len(ProfileUpdates)} profile field(s) and {ThresholdsUpdated} threshold row(s).',
                    'profile_updates': len(ProfileUpdates),
                    'threshold_updates': ThresholdsUpdated,
                })
            except Exception as e:
                LoggingService.LogException("Failed to patch profile knobs", e, "ProfileController", "patch_profile_knobs")
                return jsonify({'success': False, 'error': str(e)}), 500

        @self.Blueprint.route('/profiles/<int:profile_id>', methods=['DELETE'])
        # directive: unify-profile-editor
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
                LoggingService.LogException("Failed to delete profile", e, "ProfileController", "delete_profile")
                return jsonify({
                    'success': False,
                    'error': f'Failed to delete profile: {str(e)}'
                }), 500

        @self.Blueprint.route('/profiles/<int:profile_id>/copy', methods=['POST'])
        def copy_profile(profile_id):
            """Duplicate a profile + thresholds under a new name."""
            try:
                data = request.get_json() or {}
                new_name = (data.get('NewName') or '').strip()
                if not new_name:
                    return jsonify({'success': False, 'error': 'NewName is required'}), 400
                result = self.ViewModel.CopyProfile(profile_id, new_name)
                status = 200 if result.get('success') else 400
                return jsonify(result), status
            except Exception as e:
                LoggingService.LogException("Failed to copy profile", e, "ProfileController", "copy_profile")
                return jsonify({'success': False, 'error': f'Failed to copy profile: {str(e)}'}), 500

        @self.Blueprint.route('/profiles/reorder', methods=['POST'])
        # directive: unify-profile-editor
        def reorder_profiles():
            """Update the display order of profiles."""
            try:
                Data = request.get_json()
                OrderedIds = Data.get('OrderedIds', [])
                if not OrderedIds:
                    return jsonify({'success': False, 'error': 'OrderedIds is required'}), 400

                from Features.Profiles.ProfileRepository import ProfileRepository
                Repo = ProfileRepository()
                Success = Repo.UpdateProfileOrder(OrderedIds)
                if Success:
                    return jsonify({'success': True, 'message': 'Profile order updated'})
                else:
                    return jsonify({'success': False, 'error': 'Failed to update order'}), 500
            except Exception as e:
                LoggingService.LogException("Failed to reorder profiles", e, "ProfileController", "reorder_profiles")
                return jsonify({'success': False, 'error': str(e)}), 500

        @self.Blueprint.route('/profiles/<int:profile_id>/thresholds', methods=['POST'])
        # directive: unify-profile-editor
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
                    data['TranscodeDownTo'].strip(),
                    data.get('Quality')
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
                LoggingService.LogException("Failed to add threshold", e, "ProfileController", "add_threshold")
                return jsonify({
                    'success': False,
                    'error': f'Failed to add threshold: {str(e)}'
                }), 500

        @self.Blueprint.route('/profiles/<int:profile_id>/thresholds/<int:threshold_id>', methods=['PUT'])
        # directive: unify-profile-editor
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
                    TranscodeDownTo=data.get('TranscodeDownTo', '').strip(),
                    Quality=data.get('Quality')
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
                LoggingService.LogException("Failed to update threshold", e, "ProfileController", "update_threshold")
                return jsonify({
                    'success': False,
                    'error': f'Failed to update threshold: {str(e)}'
                }), 500

        @self.Blueprint.route('/profiles/<int:profile_id>/thresholds/<int:threshold_id>', methods=['DELETE'])
        # directive: unify-profile-editor
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
                LoggingService.LogException("Failed to delete threshold", e, "ProfileController", "delete_threshold")
                return jsonify({
                    'success': False,
                    'error': f'Failed to delete threshold: {str(e)}'
                }), 500

        @self.Blueprint.route('/profiles/assign-to-root-folder', methods=['POST'])
        # directive: unify-profile-editor
        def assign_profile_to_root_folder():
            """Assign a profile to all media files in a specific root folder."""
            try:
                LoggingService.LogFunctionEntry("assign_profile_to_root_folder", "ProfileController")

                data = request.get_json()
                if not data:
                    return jsonify({
                        'success': False,
                        'error': 'Request body is required'
                    }), 400

                root_folder_path = data.get('RootFolderPath')
                profile_id = data.get('ProfileId')

                if not root_folder_path:
                    return jsonify({
                        'success': False,
                        'error': 'RootFolderPath is required'
                    }), 400

                if not profile_id:
                    return jsonify({
                        'success': False,
                        'error': 'ProfileId is required'
                    }), 400

                if not isinstance(profile_id, int) or profile_id < 1:
                    return jsonify({
                        'success': False,
                        'error': 'ProfileId must be a positive integer'
                    }), 400

                result = self.ViewModel.AssignProfileToRootFolder(root_folder_path, profile_id)

                if result.get('Success', False):
                    LoggingService.LogInfo(f"Profile assignment successful: {result.get('Message', '')}", "assign_profile_to_root_folder", "ProfileController")
                    return jsonify({
                        'success': True,
                        'message': result.get('Message', 'Profile assigned successfully'),
                        'filesUpdated': result.get('FilesUpdated', 0),
                        'profileName': result.get('ProfileName', ''),
                        'rootFolderPath': result.get('RootFolderPath', '')
                    })
                else:
                    LoggingService.LogError(f"Profile assignment failed: {result.get('ErrorMessage', '')}", "ProfileController", "assign_profile_to_root_folder")
                    return jsonify({
                        'success': False,
                        'error': result.get('ErrorMessage', 'Failed to assign profile')
                    }), 400

            except Exception as e:
                errorMsg = f'Failed to assign profile to root folder: {str(e)}'
                LoggingService.LogException(errorMsg, e, "ProfileController", "assign_profile_to_root_folder")
                return jsonify({
                    'success': False,
                    'error': errorMsg
                }), 500
