from flask import Blueprint, jsonify, render_template, request

from Core.Logging.LoggingService import LoggingService
from Features.WorkBucket.WorkBucketRepository import (
    WorkBucketRepository,
    BUCKET_TO_PROCESSING_MODE,
    BUCKET_TO_URL_KEY,
)


URL_LABELS = {
    'Transcode': {
        'Title': 'Transcode',
        'Subtitle': 'Files needing full transcode -- video + audio + container.',
        'Bucket': 'Transcode',
        'Icon': 'fas fa-film',
    },
    'Remux': {
        'Title': 'Remux',
        'Subtitle': 'Files needing container fix (audio is also normalized through the same emitter).',
        'Bucket': 'Remux',
        'Icon': 'fas fa-box',
    },
    'Audio': {
        'Title': 'Audio',
        'Subtitle': 'Files where audio is the only blocker; container + video stream-copy through.',
        'Bucket': 'AudioFixOnly',
        'Icon': 'fas fa-volume-up',
    },
}


# directive: work-bucket-landing-pages | # see directive.md C1
class WorkBucketController:
    """Flask blueprint serving /Work/<bucket> pages + paginated JSON + single-row queue endpoint."""

    # directive: work-bucket-landing-pages | # see directive.md C1
    def __init__(self):
        """Construct repository + register routes."""
        self.Repository = WorkBucketRepository()
        self.Blueprint = Blueprint('work_bucket', __name__)
        self._RegisterRoutes()

    # directive: work-bucket-landing-pages | # see directive.md C1
    def _RegisterRoutes(self):
        """Wire /Work/<bucket> render + /api/Work/<bucket> list + /api/Work/<bucket>/Queue/<id>."""

        # directive: work-bucket-landing-pages | # see directive.md C1
        @self.Blueprint.route('/Work/<url_key>', methods=['GET'])
        def render_page(url_key):
            """Render the shared landing template parameterized by URL key."""
            Labels = URL_LABELS.get(url_key)
            if Labels is None:
                return render_template('Error.html', ErrorCode=404, ErrorMessage=f"Unknown work bucket: {url_key}"), 404
            return render_template('WorkBucket.html', UrlKey=url_key, Labels=Labels)

        # directive: work-bucket-landing-pages | # see directive.md C1
        @self.Blueprint.route('/api/Work/<url_key>', methods=['GET'])
        def list_files(url_key):
            """Return paginated list of MediaFiles in the bucket + total + already-queued count."""
            try:
                Labels = URL_LABELS.get(url_key)
                if Labels is None:
                    return jsonify({'Success': False, 'Message': f"Unknown bucket: {url_key}", 'Data': {}}), 404
                Bucket = Labels['Bucket']
                Offset = int(request.args.get('offset', 0) or 0)
                Limit = int(request.args.get('limit', 50) or 50)
                Counts = self.Repository.CountByBucket(Bucket)
                Rows = self.Repository.ListByBucket(Bucket, Offset=Offset, Limit=Limit)
                return jsonify({
                    'Success': True, 'Message': 'OK',
                    'Data': {
                        'Bucket': Bucket,
                        'Total': Counts['Total'],
                        'AlreadyQueued': Counts['AlreadyQueued'],
                        'Offset': Offset,
                        'Limit': Limit,
                        'Rows': Rows,
                    },
                })
            except Exception as Ex:
                LoggingService.LogException(f"WorkBucket list failed for {url_key}", Ex, "WorkBucketController", "list_files")
                return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 500

        # directive: h1-operator-control | # see directive.md H1G3
        @self.Blueprint.route('/api/Work/<url_key>/QueueNext', methods=['POST'])
        def queue_next(url_key):
            """Bulk-queue up to {limit} idle MediaFiles in the bucket. Body: {Limit: int up to 1000}."""
            try:
                Labels = URL_LABELS.get(url_key)
                if Labels is None:
                    return jsonify({'Success': False, 'Message': f"Unknown bucket: {url_key}", 'Data': {}}), 404
                Body = request.get_json(force=True, silent=True) or {}
                Limit = int(Body.get('Limit', 200) or 200)
                Mode = BUCKET_TO_PROCESSING_MODE[Labels['Bucket']]
                Result = self.Repository.QueueNext(Labels['Bucket'], Mode, Limit=Limit)
                return jsonify({
                    'Success': True,
                    'Message': f"Queued {Result['Inserted']}",
                    'Data': Result,
                })
            except Exception as Ex:
                LoggingService.LogException(f"WorkBucket QueueNext failed for {url_key}", Ex, "WorkBucketController", "queue_next")
                return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 500

        # directive: work-bucket-landing-pages | # see directive.md C2
        @self.Blueprint.route('/api/Work/<url_key>/Queue/<int:media_file_id>', methods=['POST'])
        def queue_one(url_key, media_file_id):
            """Idempotently queue one MediaFile with the bucket's ProcessingMode."""
            try:
                Labels = URL_LABELS.get(url_key)
                if Labels is None:
                    return jsonify({'Success': False, 'Message': f"Unknown bucket: {url_key}", 'Data': {}}), 404
                Mode = BUCKET_TO_PROCESSING_MODE[Labels['Bucket']]
                Status, QueueId = self.Repository.QueueOne(media_file_id, Mode)
                return jsonify({
                    'Success': True,
                    'Message': 'Queued' if Status == 'queued' else 'Already queued',
                    'Data': {'Status': Status, 'QueueId': QueueId, 'ProcessingMode': Mode},
                })
            except Exception as Ex:
                LoggingService.LogException(f"WorkBucket queue failed for {url_key}/{media_file_id}", Ex, "WorkBucketController", "queue_one")
                return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 500
