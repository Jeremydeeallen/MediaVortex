from typing import FrozenSet, Optional


# directive: transcode-flow-canonical -- C34
AUDIO_ONLY_CONTAINERS: FrozenSet[str] = frozenset({
    'mp3',
    'flac',
    'ogg',
    'wav',
    'aac',
    'opus',
    'dsf',
    'dff',
    'ape',
    'wma',
})


# directive: transcode-flow-canonical -- C34
def IsAudioOnlyContainer(Mf) -> bool:
    Raw = _ReadContainerFormat(Mf)
    if not Raw:
        return False
    Parts = {Tok.strip().lower() for Tok in str(Raw).split(',') if Tok.strip()}
    return bool(Parts & AUDIO_ONLY_CONTAINERS)


def _ReadContainerFormat(Mf) -> Optional[str]:
    if hasattr(Mf, 'get'):
        return Mf.get('ContainerFormat')
    return getattr(Mf, 'ContainerFormat', None)
