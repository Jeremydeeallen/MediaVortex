import ast
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
AUDIO_FILTER_EMITTER = os.path.join(REPO_ROOT, 'Features', 'AudioNormalization', 'AudioFilterEmitter.py')
TRANSCODE_SHAPE = os.path.join(REPO_ROOT, 'Features', 'TranscodeJob', 'Emit', 'TranscodeShape.py')


# directive: audio-pipeline-fail-loud
def _ReadSource(Path):
    with open(Path, 'r', encoding='utf-8') as F:
        return F.read()


# directive: audio-pipeline-fail-loud
def _LiteralStringsAdjacent(Source, A, B, MaxGap=8):
    Pattern = re.compile(r"['\"]" + re.escape(A) + r"['\"]\s*,\s*['\"]" + re.escape(B) + r"['\"]")
    return Pattern.search(Source) is not None


# directive: audio-pipeline-fail-loud
class TestAudioPipelineNoSilentFallback(unittest.TestCase):

    def test_audio_filter_emitter_has_no_strategy_review_silent_skip(self):
        Source = _ReadSource(AUDIO_FILTER_EMITTER)
        BadPattern = re.compile(
            r"if\s+Strategy\.Strategy\s*==\s*STRATEGY_REVIEW\s*:\s*\n\s*continue\b",
            re.MULTILINE,
        )
        self.assertIsNone(
            BadPattern.search(Source),
            "AudioFilterEmitter must not 'continue' silently on STRATEGY_REVIEW; route through DispositionResolver instead.",
        )

    def test_audio_filter_emitter_routes_review_through_disposition_resolver(self):
        Source = _ReadSource(AUDIO_FILTER_EMITTER)
        self.assertIn(
            '_BuildReviewFallbackBlock',
            Source,
            "AudioFilterEmitter must call _BuildReviewFallbackBlock for STRATEGY_REVIEW paths.",
        )
        self.assertIn(
            'DispositionResolver.ResolveForTrack',
            Source,
            "_BuildReviewFallbackBlock must delegate to DispositionResolver.ResolveForTrack.",
        )

    def test_pick_default_language_delegates_to_policy(self):
        Source = _ReadSource(AUDIO_FILTER_EMITTER)
        self.assertIn(
            'DispositionResolver.PickDefaultLanguage',
            Source,
            "_PickDefaultLanguage must consult AudioDispositionResolver.PickDefaultLanguage; no implicit chain.",
        )

    def test_transcode_shape_has_no_literal_c_a_copy_extend(self):
        Source = _ReadSource(TRANSCODE_SHAPE)
        BadPattern = re.compile(
            r"CommandParts\.extend\(\[[^\]]*['\"]-c:a['\"]\s*,\s*['\"]copy['\"]",
        )
        self.assertIsNone(
            BadPattern.search(Source),
            "TranscodeShape must not extend CommandParts with a literal ['-c:a', 'copy'] pair; codec must come from AudioCodecPolicy.",
        )

    def test_transcode_shape_consumes_codec_policy(self):
        Source = _ReadSource(TRANSCODE_SHAPE)
        self.assertIn(
            'self.CodecPolicy.Decide',
            Source,
            "TranscodeShape must consult self.CodecPolicy.Decide for the empty-Blocks branch.",
        )

    def test_audio_filter_emitter_emit_tracks_returns_typed_blocks_or_raises(self):
        Source = _ReadSource(AUDIO_FILTER_EMITTER)
        Tree = ast.parse(Source)
        Found = False
        for Node in ast.walk(Tree):
            if isinstance(Node, ast.FunctionDef) and Node.name == 'EmitTracks':
                Found = True
                for Sub in ast.walk(Node):
                    if isinstance(Sub, ast.Return):
                        Val = Sub.value
                        IsBlocks = isinstance(Val, ast.Name) and Val.id == 'Blocks'
                        IsConstantNone = isinstance(Val, ast.Constant) and Val.value is None
                        self.assertTrue(
                            IsBlocks or IsConstantNone,
                            f"EmitTracks must return only the typed Blocks list (or None); got AST {ast.dump(Val)}",
                        )
        self.assertTrue(Found, "EmitTracks must exist on AudioFilterEmitter.")


if __name__ == '__main__':
    unittest.main()
