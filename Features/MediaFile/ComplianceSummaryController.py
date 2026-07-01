from flask import Blueprint, jsonify, render_template

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Repositories.DatabaseManager import DatabaseManager
from Features.Profiles.EffectiveProfileResolver import EffectiveProfileResolver
from Features.VideoEncoding.VideoVertical import VideoVertical
from Features.AudioNormalization.AudioVertical import AudioVertical
from Features.ContainerFormat.ContainerVertical import ContainerVertical


ComplianceSummaryBlueprint = Blueprint('compliance_summary', __name__, template_folder='templates')


# directive: compliance-symmetry
@ComplianceSummaryBlueprint.route('/api/MediaFile/<int:media_file_id>/ComplianceSummary', methods=['GET'])
def get_compliance_summary(media_file_id):
    try:
        Mgr = DatabaseManager()
        Db = DatabaseService()
        Mf = Mgr.GetMediaFileById(media_file_id)
        if Mf is None:
            return jsonify({'success': False, 'error': f'MediaFile {media_file_id} not found'}), 404

        Resolver = EffectiveProfileResolver()
        Profile = Resolver.Resolve(Mf)

        Vid = VideoVertical(Db=Db, RepoMgr=Mgr, ProfileResolver=Resolver).Evaluate(Mf)
        Aud = AudioVertical(Db=Db, RepoMgr=Mgr, ProfileResolver=Resolver).Evaluate(Mf)
        Con = ContainerVertical(Db=Db, RepoMgr=Mgr, ProfileResolver=Resolver).Evaluate(Mf)

        Bucket = _DeriveBucket(Vid[0], Con[0], Aud[0])
        PlannedOps = _PlannedOps(Bucket, Vid[0], Con[0], Aud[0])

        PolicyRow = _ResolveAudioPolicy(Db, Mf)

        Payload = {
            'success': True,
            'media_file_id': media_file_id,
            'file_name': getattr(Mf, 'FileName', None),
            'effective_profile': {
                'name': Profile.ProfileName if Profile else None,
                'stream_codec_name': Profile.StreamCodecName if Profile else None,
                'target_resolution_category': Profile.TargetResolutionCategory.Name if (Profile and Profile.TargetResolutionCategory) else None,
                'target_video_kbps': Profile.TargetVideoKbps if Profile else None,
                'allow_upscale': Profile.AllowUpscale if Profile else None,
                'audio_codec': Profile.AudioCodec if Profile else None,
                'target_audio_kbps': Profile.TargetAudioKbps if Profile else None,
                'container': Profile.Container if Profile else None,
            },
            'audio_policy': PolicyRow,
            'verdicts': {
                'video': {'compliant': Vid[0], 'reason': Vid[1]},
                'container': {'compliant': Con[0], 'reason': Con[1]},
                'audio': {'compliant': Aud[0], 'reason': Aud[1]},
            },
            'work_bucket': Bucket,
            'planned_operations': PlannedOps,
        }
        return jsonify(Payload)
    except Exception as Ex:
        LoggingService.LogException("Failed to render compliance summary", Ex, "ComplianceSummaryController", "get_compliance_summary")
        return jsonify({'success': False, 'error': str(Ex)}), 500


# directive: compliance-symmetry
@ComplianceSummaryBlueprint.route('/MediaFile/<int:media_file_id>/ComplianceSummary', methods=['GET'])
def render_compliance_summary(media_file_id):
    return render_template('ComplianceSummary.html', media_file_id=media_file_id)


# directive: compliance-symmetry
def _DeriveBucket(VideoCompliant, ContainerCompliant, AudioCompliant):
    if VideoCompliant is None or ContainerCompliant is None or AudioCompliant is None:
        return None
    if VideoCompliant is False:
        return 'Transcode'
    if ContainerCompliant is False:
        return 'Remux'
    if AudioCompliant is False:
        return 'AudioFix'
    return None


# directive: compliance-symmetry
def _PlannedOps(Bucket, VideoCompliant, ContainerCompliant, AudioCompliant):
    if Bucket is None:
        return []
    Ops = []
    if Bucket == 'Transcode':
        Ops.append('video_reencode')
        if ContainerCompliant is False:
            Ops.append('container_rewrite')
        if AudioCompliant is False:
            Ops.append('audio_reencode_loudnorm')
    elif Bucket == 'Remux':
        Ops.append('container_rewrite')
        if AudioCompliant is False:
            Ops.append('audio_reencode_loudnorm')
    elif Bucket == 'AudioFix':
        Ops.append('audio_reencode_loudnorm')
    return Ops


# directive: compliance-symmetry
def _ResolveAudioPolicy(Db, Mf):
    MediaFileId = getattr(Mf, 'Id', None)
    StorageRootId = getattr(Mf, 'StorageRootId', None)
    Rows = Db.ExecuteQuery(
        "SELECT Scope, ScopeKey, Enabled, TargetLra, MaxAudioChannels "
        "FROM AudioNormalizationConfig "
        "WHERE (Scope = 'item' AND ScopeKey = %s) "
        "   OR (Scope = 'library' AND ScopeKey = %s) "
        "   OR (Scope = 'global' AND ScopeKey IS NULL) "
        "ORDER BY CASE Scope WHEN 'item' THEN 1 WHEN 'folder' THEN 2 WHEN 'library' THEN 3 ELSE 4 END "
        "LIMIT 1",
        (str(MediaFileId) if MediaFileId is not None else '__none__',
         str(StorageRootId) if StorageRootId is not None else '__none__'),
    )
    return Rows[0] if Rows else None
