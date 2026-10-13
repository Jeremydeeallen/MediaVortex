import json
import urllib.request
from typing import Dict, List


_HTTP_TIMEOUT_SEC = 60


# directive: movies-video-rule | # see ingest.ST3
class RadarrError(Exception):
    pass


# directive: movies-video-rule | # see ingest.ST3
class RadarrClient:

    # directive: movies-video-rule | # see ingest.ST3
    def __init__(self, Url: str, ApiKey: str):
        if not Url or not ApiKey:
            raise RadarrError("Radarr URL and API key are required; set RadarrUrl and RadarrApiKey on /settings")
        self.Url = Url.strip().rstrip('/')
        self.ApiKey = ApiKey.strip()

    # directive: movies-video-rule | # see ingest.ST3
    def ListMovies(self) -> List[dict]:
        Req = urllib.request.Request(f"{self.Url}/api/v3/movie", headers={'X-Api-Key': self.ApiKey})
        with urllib.request.urlopen(Req, timeout=_HTTP_TIMEOUT_SEC) as R:
            if R.status != 200:
                raise RadarrError(f"GET {self.Url}/api/v3/movie rc={R.status}")
            return json.loads(R.read().decode('utf-8'))

    @staticmethod
    # directive: movies-video-rule | # see ingest.ST3
    def FolderIndex(Movies: List[dict]) -> Dict[str, dict]:
        Index: Dict[str, dict] = {}
        for M in Movies:
            Stripped = (M.get('path') or '').rstrip('/').rstrip('\\')
            Cut = max(Stripped.rfind('/'), Stripped.rfind('\\'))
            Index.setdefault(Stripped if Cut == -1 else Stripped[Cut + 1:], M)
        return Index
