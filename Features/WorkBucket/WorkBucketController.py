from flask import Blueprint, jsonify, render_template, request

from Core.Logging.LoggingService import LoggingService
from Core.Querying import PagedQuery
from Features.WorkBucket.Domain.BucketKey import BucketKey
from Features.WorkBucket.Domain.FilterSpec import FilterSpec
from Features.WorkBucket.Domain.ProfileName import InvalidProfileError
from Features.WorkBucket.Domain.SeriesIdentity import SeriesIdentity
from Features.WorkBucket.Domain.SortSpec import SortSpec
from Features.WorkBucket.Repositories.FilesInSeriesRepository import FilesInSeriesRepository
from Features.WorkBucket.Repositories.SeriesQueryRepository import SeriesQueryRepository
from Features.WorkBucket.Services.QueueAdmissionAppService import QueueAdmissionAppService
from Features.WorkBucket.Services.SeriesProfileService import SeriesProfileService


# directive: work-transcode-unified | # see work-bucket.C1
class WorkBucketController:
    """Flask blueprint serving /Work/<bucket> + /api/Work/<bucket>/*. HTTP-only -- no SQL, no business logic."""

    # directive: work-transcode-unified | # see work-bucket.C1
    def __init__(self):
        self.Blueprint = Blueprint('work_bucket', __name__)
        self.SeriesRepo = SeriesQueryRepository()
        self.FilesRepo = FilesInSeriesRepository()
        self.ProfileService = SeriesProfileService()
        self.QueueService = QueueAdmissionAppService()
        self._RegisterRoutes()

    # directive: work-transcode-unified | # see work-bucket.C1
    def _RegisterRoutes(self):
        @self.Blueprint.route('/Work/<url_key>', methods=['GET'])
        # directive: work-transcode-unified | # see work-bucket.C1
        def render_page(url_key):
            Bucket = BucketKey.FromUrlKey(url_key)
            if Bucket is None:
                return render_template('Error.html', ErrorCode=404, ErrorMessage=f"Unknown work bucket: {url_key}"), 404
            return render_template('WorkBucket.html', UrlKey=url_key, Bucket=Bucket)

        @self.Blueprint.route('/api/Work/<url_key>', methods=['GET'])
        # directive: work-transcode-unified | # see work-bucket.C1
        def list_series(url_key):
            try:
                Bucket = BucketKey.FromUrlKey(url_key)
                if Bucket is None:
                    return jsonify({'Success': False, 'Message': f"Unknown bucket: {url_key}", 'Data': {}}), 404
                Page = max(1, int(request.args.get('page', 1) or 1))
                PageSize = max(1, min(200, int(request.args.get('pageSize', 25) or 25)))
                Sort = SortSpec.FromString(request.args.get('sort', ''))
                Drives = tuple(
                    int(D) for D in request.args.getlist('drive') if D.strip().isdigit()
                )
                Filter = FilterSpec(StorageRootIds=Drives, SearchTerm=request.args.get('search', '') or '')
                Result = self.SeriesRepo.ListSeriesByBucket(
                    Bucket=Bucket,
                    Query=PagedQuery(Page=Page, PageSize=PageSize),
                    Sort=Sort,
                    Filter=Filter,
                )
                return jsonify({
                    'Success': True, 'Message': 'OK',
                    'Data': {
                        'Bucket': Bucket.BucketName,
                        'Total': Result.TotalCount,
                        'Page': Result.Page,
                        'PageSize': Result.PageSize,
                        'Series': [S.ToJson() for S in Result.Rows],
                    },
                })
            except Exception as Ex:
                LoggingService.LogException(f"list_series failed for {url_key}", Ex, "WorkBucketController", "list_series")
                return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 500

        @self.Blueprint.route('/api/Work/<url_key>/Series/<path:sid>', methods=['GET'])
        # directive: work-transcode-unified | # see work-bucket.C2
        def list_files_in_series(url_key, sid):
            try:
                Bucket = BucketKey.FromUrlKey(url_key)
                if Bucket is None:
                    return jsonify({'Success': False, 'Message': f"Unknown bucket: {url_key}", 'Data': {}}), 404
                Identity = SeriesIdentity.FromCompositeKey(sid)
                Files = self.FilesRepo.ListFilesInSeries(Identity, Bucket)
                return jsonify({
                    'Success': True, 'Message': 'OK',
                    'Data': {
                        'Bucket': Bucket.BucketName,
                        'Series': Identity.ToCompositeKey(),
                        'Files': [F.ToJson() for F in Files],
                    },
                })
            except ValueError as Ex:
                return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 400
            except Exception as Ex:
                LoggingService.LogException(f"list_files_in_series failed for {url_key}/{sid}", Ex, "WorkBucketController", "list_files_in_series")
                return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 500

        @self.Blueprint.route('/api/Work/<url_key>/Series/<path:sid>/Profile', methods=['POST'])
        # directive: work-transcode-unified | # see work-bucket.C3
        def set_series_profile(url_key, sid):
            try:
                Bucket = BucketKey.FromUrlKey(url_key)
                if Bucket is None:
                    return jsonify({'Success': False, 'Message': f"Unknown bucket: {url_key}", 'Data': {}}), 404
                Identity = SeriesIdentity.FromCompositeKey(sid)
                Body = request.get_json(force=True, silent=True) or {}
                RawName = Body.get('ProfileName', '')
                Affected = self.ProfileService.SetProfile(Identity, RawName)
                return jsonify({
                    'Success': True, 'Message': f"Applied profile to {Affected} files",
                    'Data': {'FilesAffected': Affected, 'ProfileName': RawName},
                })
            except InvalidProfileError as Ex:
                return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 400
            except ValueError as Ex:
                return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 400
            except Exception as Ex:
                LoggingService.LogException(f"set_series_profile failed for {url_key}/{sid}", Ex, "WorkBucketController", "set_series_profile")
                return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 500

        @self.Blueprint.route('/api/Work/<url_key>/Series/<path:sid>/Profile', methods=['DELETE'])
        # directive: work-transcode-unified | # see work-bucket.C3
        def clear_series_profile(url_key, sid):
            try:
                Bucket = BucketKey.FromUrlKey(url_key)
                if Bucket is None:
                    return jsonify({'Success': False, 'Message': f"Unknown bucket: {url_key}", 'Data': {}}), 404
                Identity = SeriesIdentity.FromCompositeKey(sid)
                self.ProfileService.ClearProfile(Identity)
                return jsonify({'Success': True, 'Message': 'Profile cleared', 'Data': {}})
            except ValueError as Ex:
                return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 400
            except Exception as Ex:
                LoggingService.LogException(f"clear_series_profile failed for {url_key}/{sid}", Ex, "WorkBucketController", "clear_series_profile")
                return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 500

        @self.Blueprint.route('/api/Work/<url_key>/Series/<path:sid>/Queue', methods=['POST'])
        # directive: work-transcode-unified | # see work-bucket.C4
        def queue_series(url_key, sid):
            try:
                Bucket = BucketKey.FromUrlKey(url_key)
                if Bucket is None:
                    return jsonify({'Success': False, 'Message': f"Unknown bucket: {url_key}", 'Data': {}}), 404
                Identity = SeriesIdentity.FromCompositeKey(sid)
                Result = self.QueueService.AdmitSeries(Identity, Bucket)
                return jsonify({
                    'Success': True,
                    'Message': f"Queued {Result.Inserted}",
                    'Data': {'Inserted': Result.Inserted, 'AlreadyQueued': Result.AlreadyQueued, 'Total': Result.Total},
                })
            except ValueError as Ex:
                return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 400
            except Exception as Ex:
                LoggingService.LogException(f"queue_series failed for {url_key}/{sid}", Ex, "WorkBucketController", "queue_series")
                return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 500

        @self.Blueprint.route('/api/Work/<url_key>/Queue/<int:media_file_id>', methods=['POST'])
        # directive: work-transcode-unified | # see work-bucket.C5
        def queue_one(url_key, media_file_id):
            try:
                Bucket = BucketKey.FromUrlKey(url_key)
                if Bucket is None:
                    return jsonify({'Success': False, 'Message': f"Unknown bucket: {url_key}", 'Data': {}}), 404
                Status, QueueId = self.QueueService.AdmitOne(media_file_id, Bucket)
                return jsonify({
                    'Success': True,
                    'Message': 'Queued' if Status == 'queued' else 'Already queued',
                    'Data': {'Status': Status, 'QueueId': QueueId, 'ProcessingMode': Bucket.ProcessingMode},
                })
            except Exception as Ex:
                LoggingService.LogException(f"queue_one failed for {url_key}/{media_file_id}", Ex, "WorkBucketController", "queue_one")
                return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 500
