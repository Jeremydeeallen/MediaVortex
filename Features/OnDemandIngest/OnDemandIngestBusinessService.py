# directive: probe-worker-decoupled -- path validation + queue insertion for on-demand scan / probe.
from typing import Dict, Any
from Core.Path import Path, PathError
from Core.Path.PathStorageRoots import GetStorageRoots
from Core.Logging.LoggingService import LoggingService
from Features.OnDemandIngest.OnDemandIngestRepository import OnDemandIngestRepository


class OnDemandIngestBusinessService:

    def __init__(self, Repo: OnDemandIngestRepository = None):
        self.Repo = Repo or OnDemandIngestRepository()

    def _ParseCanonical(self, CanonicalPath: str) -> Dict[str, Any]:
        if not CanonicalPath or not CanonicalPath.strip():
            return {'Success': False, 'Message': 'CanonicalPath is required'}
        try:
            P = Path.FromLegacyString(CanonicalPath.strip(), GetStorageRoots())
        except PathError as Ex:
            return {'Success': False, 'Message': f'Unknown or unresolvable canonical path: {Ex}'}
        return {'Success': True, 'StorageRootId': P.StorageRootId, 'RelativePath': P.RelativePath}

    def SubmitScan(self, CanonicalPath: str) -> Dict[str, Any]:
        Parsed = self._ParseCanonical(CanonicalPath)
        if not Parsed['Success']:
            return Parsed
        try:
            Rid = self.Repo.InsertScanRequest(Parsed['StorageRootId'], Parsed['RelativePath'])
            LoggingService.LogInfo(
                f"OnDemand scan queued: RequestId={Rid} sid={Parsed['StorageRootId']} rel={Parsed['RelativePath']!r}",
                'OnDemandIngestBusinessService', 'SubmitScan',
            )
            return {'Success': True, 'RequestId': Rid, 'Message': 'Queued'}
        except Exception as Ex:
            LoggingService.LogException('SubmitScan failed', Ex, 'OnDemandIngestBusinessService', 'SubmitScan')
            return {'Success': False, 'Message': f'Insert failed: {Ex}'}

    def SubmitProbe(self, CanonicalPath: str) -> Dict[str, Any]:
        Parsed = self._ParseCanonical(CanonicalPath)
        if not Parsed['Success']:
            return Parsed
        try:
            Rid = self.Repo.InsertProbeRequest(Parsed['StorageRootId'], Parsed['RelativePath'])
            LoggingService.LogInfo(
                f"OnDemand probe queued: RequestId={Rid} sid={Parsed['StorageRootId']} rel={Parsed['RelativePath']!r}",
                'OnDemandIngestBusinessService', 'SubmitProbe',
            )
            return {'Success': True, 'RequestId': Rid, 'Message': 'Queued'}
        except Exception as Ex:
            LoggingService.LogException('SubmitProbe failed', Ex, 'OnDemandIngestBusinessService', 'SubmitProbe')
            return {'Success': False, 'Message': f'Insert failed: {Ex}'}

    def RecentScans(self, Limit: int = 20) -> Dict[str, Any]:
        return {'Success': True, 'Rows': self.Repo.RecentScanRequests(Limit)}

    def RecentProbes(self, Limit: int = 20) -> Dict[str, Any]:
        return {'Success': True, 'Rows': self.Repo.RecentProbeRequests(Limit)}
