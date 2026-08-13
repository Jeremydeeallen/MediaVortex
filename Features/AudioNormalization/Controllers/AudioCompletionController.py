from flask import Blueprint


# directive: audio-vertical-dialog-boost-enforcement
AudioCompletionBlueprint = Blueprint(
    'AudioCompletion', __name__, url_prefix='/api/AudioCompletion'
)
