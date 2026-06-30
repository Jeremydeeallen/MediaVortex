import json
import time

from flask import Blueprint, request, jsonify, render_template

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService

# directive: worker-runtime-state
_AudioBackfillStatus = {'Running': False, 'Total': 0, 'Completed': 0, 'StartedAt': None, 'FinishedAt': None, 'DurationSec': None, 'LastError': None}


# directive: worker-runtime-state
def _SpawnAudioBackfill():
    import threading
    def _Run():
        Status = _AudioBackfillStatus
        Status['Running'] = True
        Status['Completed'] = 0
        Status['StartedAt'] = time.strftime('%Y-%m-%dT%H:%M:%S')
        Status['FinishedAt'] = None
        Status['DurationSec'] = None
        Status['LastError'] = None
        StartedAt = time.time()
        try:
            Rows = DatabaseService().ExecuteQuery("SELECT Id FROM MediaFiles")
            Ids = [int(R['Id'] if 'Id' in R else R['id']) for R in (Rows or [])]
            Status['Total'] = len(Ids)
            from Features.AudioNormalization.AudioVertical import AudioVertical
            Vertical = AudioVertical()
            ChunkSize = 500
            for I in range(0, len(Ids), ChunkSize):
                Vertical.RecomputeFor(Ids[I:I + ChunkSize])
                Status['Completed'] = min(I + ChunkSize, len(Ids))
            Status['FinishedAt'] = time.strftime('%Y-%m-%dT%H:%M:%S')
            Status['DurationSec'] = round(time.time() - StartedAt, 2)
            LoggingService.LogInfo(f"AudioVertical backfill complete for {len(Ids)} files in {Status['DurationSec']}s", 'AudioComplianceRulesUpdated', '_SpawnAudioBackfill')
        except Exception as Ex:
            Status['LastError'] = str(Ex)
            LoggingService.LogException("AudioVertical backfill failed", Ex, 'AudioComplianceRulesUpdated', '_SpawnAudioBackfill')
        finally:
            Status['Running'] = False
    threading.Thread(target=_Run, daemon=True, name='AudioBackfill').start()
from Features.AudioNormalization.AudioPolicyAdmissionGate import AudioPolicyAdmissionGate
from Features.AudioNormalization.Repositories.AudioNormalizationConfigRepository import (
    AudioNormalizationConfigRepository,
)
from Features.AudioNormalization.Services.AudioOperatorReviewService import (
    AudioOperatorReviewService,
)
from Features.AudioNormalization.Services.AudioRemeasurementService import (
    AudioRemeasurementService,
)


DASHBOARD_SUMMARY_SQL = (
    "SELECT LibraryId, UniformCount, AcceptableCount, DeviantCount, TotalCount "
    "FROM v_audio_consistency_summary ORDER BY LibraryId"
)


UPSERT_POLICY_SQL = (
    "INSERT INTO AudioNormalizationConfig ("
    "Scope, ScopeKey, Enabled, TargetIntegratedLufs, TargetTruePeakDbtp, TargetLra, "
    "LoudnessTolerance, EmitTracks, UngainablePolicy, LanguageKeepPolicy, "
    "KeepCommentaryTracks, EnableSpeechLanguageDetection, AudioDelayMs, "
    "PreVerticalReNormalizePolicy, MaxAudioChannels, LastUpdated"
    ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s, %s, %s, %s, %s, NOW()) "
    "ON CONFLICT (Scope, COALESCE(ScopeKey, '')) DO UPDATE SET "
    "Enabled = EXCLUDED.Enabled, "
    "TargetIntegratedLufs = EXCLUDED.TargetIntegratedLufs, "
    "TargetTruePeakDbtp = EXCLUDED.TargetTruePeakDbtp, "
    "TargetLra = EXCLUDED.TargetLra, "
    "LoudnessTolerance = EXCLUDED.LoudnessTolerance, "
    "EmitTracks = EXCLUDED.EmitTracks, "
    "UngainablePolicy = EXCLUDED.UngainablePolicy, "
    "LanguageKeepPolicy = EXCLUDED.LanguageKeepPolicy, "
    "KeepCommentaryTracks = EXCLUDED.KeepCommentaryTracks, "
    "EnableSpeechLanguageDetection = EXCLUDED.EnableSpeechLanguageDetection, "
    "AudioDelayMs = EXCLUDED.AudioDelayMs, "
    "PreVerticalReNormalizePolicy = EXCLUDED.PreVerticalReNormalizePolicy, "
    "MaxAudioChannels = EXCLUDED.MaxAudioChannels, "
    "LastUpdated = NOW()"
)


from Features.AudioNormalization.AudioNormalizationConfigValidator import (
    PRE_VERTICAL_POLICY_VALUES,
    ValidatePreVerticalPolicy,
)


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C10
class AudioNormalizationController:
    """Flask blueprint for /AudioNormalization GUI + API; envelope {Success, Message, Data} per error-ux."""

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C10
    def __init__(self):
        """Construct services + register routes."""
        self.Repository = AudioNormalizationConfigRepository()
        self.Review = AudioOperatorReviewService()
        self.Remeasurement = AudioRemeasurementService()
        self.Gate = AudioPolicyAdmissionGate()
        self.Blueprint = Blueprint('audio_normalization', __name__)
        self._RegisterRoutes()

    # directive: audio-review-queue-grouping | # see audio-normalization.C6
    def _TriggerRecompute(self, MediaFileIds):
        """Hand the cleared MediaFile ids to QueueManagementBusinessService.RecomputeForFiles so each lands in its correct WorkBucket."""
        if not MediaFileIds:
            return
        try:
            from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
            QueueManagementBusinessService().RecomputeForFiles(list(MediaFileIds))
        except Exception as Ex:
            LoggingService.LogException(
                "Recompute trigger post-review-resolve failed", Ex,
                "AudioNormalizationController", "_TriggerRecompute",
            )

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C10
    def _RegisterRoutes(self):
        """Wire GET /AudioNormalization, GET/POST API endpoints."""

        # directive: perfect-audio-vertical | # see perfect-audio-vertical.C10
        @self.Blueprint.route('/AudioNormalization', methods=['GET'])
        def render_page():
            """Render the Settings + Dashboard + Review tabbed page."""
            return render_template('AudioNormalization.html')

        # directive: perfect-audio-vertical | # see perfect-audio-vertical.C10
        @self.Blueprint.route('/api/AudioNormalization/Settings', methods=['GET'])
        def list_settings():
            """List every AudioNormalizationConfig row across all scopes."""
            try:
                Rows = []
                for Scope in ('global', 'library', 'folder', 'item'):
                    Rows.extend(self.Repository.ListByScope(Scope))
                return jsonify({'Success': True, 'Message': 'OK', 'Data': {'Rows': Rows}})
            except Exception as Ex:
                LoggingService.LogException("Failed listing audio policies", Ex,
                                            "AudioNormalizationController", "list_settings")
                return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 500

        # directive: perfect-audio-vertical | # see perfect-audio-vertical.C10
        @self.Blueprint.route('/api/AudioNormalization/Settings', methods=['POST'])
        def upsert_settings():
            """Insert or update a policy row at any scope."""
            try:
                Body = request.get_json(force=True, silent=True) or {}
                Args = (
                    Body.get('Scope', 'global'),
                    Body.get('ScopeKey'),
                    bool(Body.get('Enabled', True)),
                    float(Body.get('TargetIntegratedLufs', -23.0)),
                    float(Body.get('TargetTruePeakDbtp', -2.0)),
                    Body.get('TargetLra'),
                    float(Body.get('LoudnessTolerance', 4.0)),
                    json.dumps(Body.get('EmitTracks') or []),
                    Body.get('UngainablePolicy', 'adaptive'),
                    json.dumps(Body['LanguageKeepPolicy']) if Body.get('LanguageKeepPolicy') is not None else None,
                    bool(Body.get('KeepCommentaryTracks', True)),
                    bool(Body.get('EnableSpeechLanguageDetection', False)),
                    int(Body.get('AudioDelayMs', 0)),
                    ValidatePreVerticalPolicy(Body.get('PreVerticalReNormalizePolicy', 'lazy')),
                    int(Body.get('MaxAudioChannels', 2)),
                )
                DatabaseService().ExecuteNonQuery(UPSERT_POLICY_SQL, Args)
                return jsonify({'Success': True, 'Message': 'Saved', 'Data': {}})
            except Exception as Ex:
                LoggingService.LogException("Failed upserting audio policy", Ex,
                                            "AudioNormalizationController", "upsert_settings")
                return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 500

        # directive: perfect-audio-vertical | # see perfect-audio-vertical.C15
        @self.Blueprint.route('/api/AudioNormalization/Dashboard', methods=['GET'])
        def dashboard():
            """Return the v_audio_consistency_summary band breakdown per library."""
            try:
                Rows = DatabaseService().ExecuteQuery(DASHBOARD_SUMMARY_SQL)
                return jsonify({'Success': True, 'Message': 'OK', 'Data': {'Libraries': Rows}})
            except Exception as Ex:
                LoggingService.LogException("Failed dashboard query", Ex,
                                            "AudioNormalizationController", "dashboard")
                return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 500

        # directive: audio-review-queue-grouping | # see audio-normalization.C6
        @self.Blueprint.route('/api/AudioNormalization/Review', methods=['GET'])
        def review_queue():
            """Return grouped review queue: one group per AdmissionDeferReason with counts + samples."""
            try:
                Groups = self.Review.GroupedSummary()
                Total = sum(int(G.get('Total') or 0) for G in Groups)
                return jsonify({'Success': True, 'Message': 'OK',
                                'Data': {'Count': Total, 'Groups': Groups}})
            except Exception as Ex:
                LoggingService.LogException("Failed review queue", Ex,
                                            "AudioNormalizationController", "review_queue")
                return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 500

        # directive: perfect-audio-vertical | # see perfect-audio-vertical.C6
        @self.Blueprint.route('/api/AudioNormalization/Review/<int:media_file_id>/Resolve', methods=['POST'])
        def resolve_review(media_file_id):
            """Clear AdmissionDeferReason for a held-for-review MediaFile + trigger recompute."""
            try:
                self.Review.ResolveReview(media_file_id)
                self._TriggerRecompute([media_file_id])
                return jsonify({'Success': True, 'Message': 'Resolved', 'Data': {}})
            except Exception as Ex:
                LoggingService.LogException("Failed resolving review", Ex,
                                            "AudioNormalizationController", "resolve_review")
                return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 500

        # directive: audio-vertical-converge-to-zero | # see directive.md Z1
        @self.Blueprint.route('/api/AudioNormalization/Review/Resolve', methods=['POST'])
        def bulk_resolve_review():
            """Dispatch the correct bulk action per defer reason: clear / re-measure / re-enrich. Recompute fires when the file becomes admittable again."""
            try:
                Body = request.get_json(force=True, silent=True) or {}
                Reason = (Body.get('AdmissionDeferReason') or '').strip()
                Result = self.Review.BulkActionByReason(Reason)
                Ids = Result.get('Ids') or []
                ActionVerb = Result.get('ActionVerb')
                if ActionVerb == 'clear_and_recompute':
                    self._TriggerRecompute(Ids)
                Count = Result.get('Cleared') or Result.get('Marked') or 0
                return jsonify({'Success': True, 'Message': f"{ActionVerb}: {Count}", 'Data': Result})
            except ValueError as Ex:
                return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 400
            except Exception as Ex:
                LoggingService.LogException("Failed bulk resolve review", Ex,
                                            "AudioNormalizationController", "bulk_resolve_review")
                return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 500

        # directive: perfect-audio-vertical | # see perfect-audio-vertical.C19
        @self.Blueprint.route('/api/AudioNormalization/EnrichmentQueue/Status', methods=['GET'])
        def enrichment_status():
            """Return the count of pending speech-language enrichment jobs."""
            try:
                Rows = DatabaseService().ExecuteQuery(
                    "SELECT COUNT(*) AS Cnt FROM MediaFiles "
                    "WHERE AdmissionDeferReason = 'awaiting_speech_enrichment'"
                )
                Cnt = int(Rows[0]['cnt']) if Rows else 0
                return jsonify({'Success': True, 'Message': 'OK',
                                'Data': {'Pending': Cnt}})
            except Exception as Ex:
                LoggingService.LogException("Failed enrichment status", Ex,
                                            "AudioNormalizationController", "enrichment_status")
                return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 500

        # directive: perfect-audio-vertical | # see perfect-audio-vertical.C12
        @self.Blueprint.route('/api/AudioNormalization/SnapshotPolicies', methods=['POST'])
        def snapshot_policies():
            """Manually trigger the gate's BackfillRecentInserts to snapshot AudioPolicyJson on new queue rows."""
            try:
                self.Gate.BackfillRecentInserts()
                return jsonify({'Success': True, 'Message': 'Snapshot applied', 'Data': {}})
            except Exception as Ex:
                LoggingService.LogException("Failed snapshot trigger", Ex,
                                            "AudioNormalizationController", "snapshot_policies")
                return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 500

        @self.Blueprint.route('/api/AudioNormalization/Rules', methods=['GET'])
        # directive: audio-dialog-boost-real | # see audio-normalization.C8
        def get_audio_rules():
            Rows = DatabaseService().ExecuteQuery(
                "SELECT Id, TargetIntegratedLufs, TargetTruePeakDbtp, "
                "AcceptableAudioCodecsCsv, LastUpdated "
                "FROM AudioComplianceRules ORDER BY Id LIMIT 1"
            )
            if not Rows:
                return jsonify({'Success': False, 'Message': 'AudioComplianceRules has no rows -- migration not applied'}), 500
            return jsonify({'Success': True, 'Data': Rows[0]}), 200

        @self.Blueprint.route('/api/AudioNormalization/Rules', methods=['PUT'])
        # directive: audio-dialog-boost-real | # see audio-normalization.C8
        def update_audio_rules():
            Body = request.get_json(silent=True) or {}
            try:
                Lufs = float(Body.get('TargetIntegratedLufs'))
                TpDbtp = float(Body.get('TargetTruePeakDbtp'))
                Codecs = (Body.get('AcceptableAudioCodecsCsv') or '').strip()
            except (TypeError, ValueError):
                return jsonify({'Success': False, 'Message': 'Body field had wrong type'}), 400
            if not Codecs:
                return jsonify({'Success': False, 'Message': 'AcceptableAudioCodecsCsv is required'}), 400
            if TpDbtp > 0:
                return jsonify({'Success': False, 'Message': 'TargetTruePeakDbtp must be <= 0 dBTP'}), 400
            DatabaseService().ExecuteNonQuery(
                "UPDATE AudioComplianceRules SET "
                "TargetIntegratedLufs=%s, TargetTruePeakDbtp=%s, "
                "AcceptableAudioCodecsCsv=%s, LastUpdated=NOW() "
                "WHERE Id = 1",
                (Lufs, TpDbtp, Codecs),
            )
            LoggingService.LogInfo(
                f"AudioComplianceRules updated: Lufs={Lufs} TpDbtp={TpDbtp} codecs={Codecs!r}",
                'AudioNormalizationController', 'update_audio_rules',
            )
            _SpawnAudioBackfill()
            return jsonify({'Success': True, 'Message': 'Saved; library recompute kicked off in background.'}), 200

        # directive: worker-runtime-state
        @self.Blueprint.route('/api/AudioNormalization/Rules/BackfillStatus', methods=['GET'])
        def audio_rules_backfill_status():
            return jsonify({'Success': True, 'Data': dict(_AudioBackfillStatus)}), 200


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C10
def BuildBlueprint():
    """Module-level factory returning a registered Flask Blueprint for WebService.Main."""
    return AudioNormalizationController().Blueprint
