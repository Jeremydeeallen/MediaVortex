# directive: dialog-boost-emission-integrity | # see .claude/directive.md C2
from typing import List


# directive: dialog-boost-emission-integrity | # see .claude/directive.md C2
class PriorBoostSourceError(RuntimeError):
    pass


_PRIOR_BOOST_HANDLER_PREFIX = 'Dialog Boost'
_PRIOR_BOOST_TITLE = 'Dialog Boost'


# directive: dialog-boost-emission-integrity | # see .claude/directive.md C2
def IsMediaVortexBoostTrack(Stream: dict) -> bool:
    Tags = (Stream.get('tags') if Stream else None) or {}
    Handler = str(Tags.get('handler_name') or '')
    Title = str(Tags.get('title') or '')
    return Handler.startswith(_PRIOR_BOOST_HANDLER_PREFIX) or Title == _PRIOR_BOOST_TITLE


# directive: dialog-boost-emission-integrity | # see .claude/directive.md C2
def SelectTrueSourceStreams(Streams: List[dict]) -> List[dict]:
    if not Streams:
        return []
    Filtered = [S for S in Streams if not IsMediaVortexBoostTrack(S)]
    if not Filtered:
        raise PriorBoostSourceError(
            f"source has {len(Streams)} audio streams, all are prior MediaVortex Dialog Boost tracks; "
            f"no true source audio to encode"
        )
    return Filtered
