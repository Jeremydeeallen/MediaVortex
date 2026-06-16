import json

from flask import Blueprint, request, jsonify, render_template

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
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
    "KeepCommentaryTracks, EnableSpeechLanguageDetection, AudioDelayMs, LastUpdated"
    ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s, %s, %s, NOW()) "
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
    "LastUpdated = NOW()"
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

        # directive: perfect-audio-vertical | # see perfect-audio-vertical.C6
        @self.Blueprint.route('/api/AudioNormalization/Review', methods=['GET'])
        def review_queue():
            """Return MediaFiles currently held for operator review."""
            try:
                Rows = self.Review.ListReviewQueue()
                return jsonify({'Success': True, 'Message': 'OK',
                                'Data': {'Count': len(Rows), 'Rows': Rows}})
            except Exception as Ex:
                LoggingService.LogException("Failed review queue", Ex,
                                            "AudioNormalizationController", "review_queue")
                return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 500

        # directive: perfect-audio-vertical | # see perfect-audio-vertical.C6
        @self.Blueprint.route('/api/AudioNormalization/Review/<int:media_file_id>/Resolve', methods=['POST'])
        def resolve_review(media_file_id):
            """Clear AdmissionDeferReason for a held-for-review MediaFile."""
            try:
                self.Review.ResolveReview(media_file_id)
                return jsonify({'Success': True, 'Message': 'Resolved', 'Data': {}})
            except Exception as Ex:
                LoggingService.LogException("Failed resolving review", Ex,
                                            "AudioNormalizationController", "resolve_review")
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


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C10
def BuildBlueprint():
    """Module-level factory returning a registered Flask Blueprint for WebService.Main."""
    return AudioNormalizationController().Blueprint
