"""
Core Topology Service
Detects CPU core topology (P-cores vs E-cores) on Intel hybrid architectures.
Uses Windows GetSystemCpuSetInformation API to determine EfficiencyClass per logical processor.
"""

import ctypes
import ctypes.wintypes
import platform
from typing import List, Dict, Any, Optional
from Core.Logging.LoggingService import LoggingService


class CoreTopologyService:
    """Detects and exposes P-core vs E-core logical processor IDs for Intel hybrid CPUs."""

    _Instance = None

    def __init__(self):
        self.PCoreLogicalIds: List[int] = []
        self.ECoreLogicalIds: List[int] = []
        self.AllLogicalIds: List[int] = []
        self.IsHybrid: bool = False
        self.DetectionMethod: str = "none"
        self._Detect()

    @classmethod
    def GetInstance(cls):
        """Get singleton instance."""
        if cls._Instance is None:
            cls._Instance = cls()
        return cls._Instance

    def _Detect(self):
        """Detect core topology. Try Windows API first, then fallback heuristic."""
        if platform.system() != "Windows":
            LoggingService.LogInfo("CoreTopologyService using all-cores fallback (Windows-only API not available on this platform)", "CoreTopologyService", "_Detect")
            self._FallbackAllCores()
            return

        try:
            Success = self._DetectViaGetSystemCpuSetInformation()
            if Success:
                self.DetectionMethod = "GetSystemCpuSetInformation"
                return
        except Exception as Ex:
            LoggingService.LogWarning(f"GetSystemCpuSetInformation failed: {Ex}", "CoreTopologyService", "_Detect")

        try:
            Success = self._DetectViaCpuSets()
            if Success:
                self.DetectionMethod = "SYSTEM_CPU_SET_INFORMATION"
                return
        except Exception as Ex:
            LoggingService.LogWarning(f"CpuSets fallback failed: {Ex}", "CoreTopologyService", "_Detect")

        self._FallbackAllCores()

    def _DetectViaGetSystemCpuSetInformation(self) -> bool:
        """Use GetSystemCpuSetInformation to read EfficiencyClass per logical processor.

        The SYSTEM_CPU_SET_INFORMATION structure contains an EfficiencyClass field:
        - 0 = Efficiency core (E-core)
        - 1 = Performance core (P-core)
        """
        try:
            Kernel32 = ctypes.windll.kernel32

            # First call: get required buffer size
            BufferLength = ctypes.c_ulong(0)
            Kernel32.GetSystemCpuSetInformation(None, 0, ctypes.byref(BufferLength), None, 0)

            if BufferLength.value == 0:
                return False

            # Allocate buffer and call again
            Buffer = (ctypes.c_byte * BufferLength.value)()
            Result = Kernel32.GetSystemCpuSetInformation(
                ctypes.byref(Buffer), BufferLength.value, ctypes.byref(BufferLength), None, 0
            )

            if not Result:
                ErrorCode = ctypes.get_last_error()
                LoggingService.LogWarning(f"GetSystemCpuSetInformation returned False, error={ErrorCode}",
                                         "CoreTopologyService", "_DetectViaGetSystemCpuSetInformation")
                return False

            # Parse the variable-length records
            # SYSTEM_CPU_SET_INFORMATION structure layout (simplified):
            #   DWORD Size                (offset 0, 4 bytes)
            #   CPU_SET_INFORMATION_TYPE  (offset 4, 4 bytes) — 0 = CpuSetInformation
            #   DWORD Id                  (offset 8, 4 bytes)
            #   WORD  Group               (offset 12, 2 bytes)
            #   BYTE  LogicalProcessorIndex (offset 14, 1 byte)
            #   BYTE  CoreIndex           (offset 15, 1 byte)
            #   BYTE  LastLevelCacheIndex  (offset 16, 1 byte)
            #   BYTE  NumaNodeIndex       (offset 17, 1 byte)
            #   BYTE  EfficiencyClass     (offset 18, 1 byte)
            #   ...remaining fields

            PCores = []
            ECores = []
            Offset = 0

            while Offset < BufferLength.value:
                # Read Size (first 4 bytes of each record)
                RecordSize = int.from_bytes(Buffer[Offset:Offset + 4], byteorder='little')
                if RecordSize == 0:
                    break

                # Read LogicalProcessorIndex (offset 14 within record)
                LogicalIndex = Buffer[Offset + 14]
                # Read EfficiencyClass (offset 18 within record)
                EfficiencyClass = Buffer[Offset + 18]

                if EfficiencyClass == 0:
                    ECores.append(LogicalIndex)
                else:
                    PCores.append(LogicalIndex)

                Offset += RecordSize

            if not PCores and not ECores:
                return False

            self.PCoreLogicalIds = sorted(PCores)
            self.ECoreLogicalIds = sorted(ECores)
            self.AllLogicalIds = sorted(PCores + ECores)
            self.IsHybrid = len(PCores) > 0 and len(ECores) > 0

            LoggingService.LogInfo(
                f"Detected topology: {len(PCores)} P-core logical IDs {self.PCoreLogicalIds}, "
                f"{len(ECores)} E-core logical IDs {self.ECoreLogicalIds}, Hybrid={self.IsHybrid}",
                "CoreTopologyService", "_DetectViaGetSystemCpuSetInformation")

            return True

        except Exception as Ex:
            LoggingService.LogException("Error in GetSystemCpuSetInformation detection", Ex,
                                       "CoreTopologyService", "_DetectViaGetSystemCpuSetInformation")
            return False

    def _DetectViaCpuSets(self) -> bool:
        """Fallback: use PowerShell to query CPU set information."""
        try:
            import subprocess
            import json

            PsCommand = (
                "Get-CimInstance -ClassName Win32_Processor | "
                "Select-Object NumberOfCores, NumberOfLogicalProcessors, NumberOfEnabledCore | "
                "ConvertTo-Json"
            )

            Result = subprocess.run(
                ['powershell', '-NoProfile', '-Command', PsCommand],
                capture_output=True, text=True, timeout=10,
                creationflags=0x08000000  # CREATE_NO_WINDOW
            )

            if Result.returncode != 0 or not Result.stdout.strip():
                return False

            CpuInfo = json.loads(Result.stdout)
            if isinstance(CpuInfo, list):
                CpuInfo = CpuInfo[0]

            TotalCores = CpuInfo.get('NumberOfCores', 0)
            TotalLogical = CpuInfo.get('NumberOfLogicalProcessors', 0)

            if TotalCores == 0 or TotalLogical == 0:
                return False

            # Heuristic for Intel hybrid: if logical > cores * 2, not all cores have HT
            # i9-14900KF: 24 cores, 32 logical → 8 P-cores with HT (16 logical) + 16 E-cores (16 logical)
            # P-cores have HT, E-cores don't
            if TotalLogical > TotalCores:
                HtThreads = TotalLogical - TotalCores  # Number of HT threads
                PCoreCount = HtThreads  # Each P-core adds 1 HT thread
                ECoreCount = TotalCores - PCoreCount

                if PCoreCount > 0 and ECoreCount > 0:
                    # P-cores get first PCoreCount*2 logical IDs (physical + HT pairs)
                    PCoreLogical = list(range(0, PCoreCount * 2))
                    # E-cores get remaining logical IDs
                    ECoreLogical = list(range(PCoreCount * 2, TotalLogical))

                    self.PCoreLogicalIds = PCoreLogical
                    self.ECoreLogicalIds = ECoreLogical
                    self.AllLogicalIds = sorted(PCoreLogical + ECoreLogical)
                    self.IsHybrid = True

                    LoggingService.LogInfo(
                        f"Heuristic topology: {len(PCoreLogical)} P-core logical IDs, "
                        f"{len(ECoreLogical)} E-core logical IDs (from {TotalCores} cores, {TotalLogical} logical)",
                        "CoreTopologyService", "_DetectViaCpuSets")
                    return True

            return False

        except Exception as Ex:
            LoggingService.LogException("Error in CpuSets fallback detection", Ex,
                                       "CoreTopologyService", "_DetectViaCpuSets")
            return False

    def _FallbackAllCores(self):
        """Fallback: treat all cores as equal (non-hybrid or detection failed)."""
        import psutil
        TotalLogical = psutil.cpu_count(logical=True) or 1
        self.AllLogicalIds = list(range(TotalLogical))
        self.PCoreLogicalIds = list(range(TotalLogical))
        self.ECoreLogicalIds = list(range(TotalLogical))
        self.IsHybrid = False
        self.DetectionMethod = "fallback"
        LoggingService.LogInfo(f"Using fallback topology: {TotalLogical} logical processors, all treated equally",
                               "CoreTopologyService", "_FallbackAllCores")

    def GetPCorePhysicalIds(self) -> List[int]:
        """Get logical IDs of P-core physical threads only (even-numbered P-core IDs, excluding HT siblings).

        On i9-14900KF: returns [0, 2, 4, 6, 8, 10, 12, 14] (8 physical P-cores).
        On non-hybrid: returns all logical IDs.
        """
        if not self.IsHybrid:
            return list(self.AllLogicalIds)

        # P-cores with HT have paired logical IDs (e.g., 0/1, 2/3, 4/5...)
        # Even-numbered IDs are the physical cores
        return [Id for Id in self.PCoreLogicalIds if Id % 2 == 0]

    def GetAllPCoreIds(self) -> List[int]:
        """Get all P-core logical IDs including HT siblings."""
        return list(self.PCoreLogicalIds)

    def GetECoreIds(self) -> List[int]:
        """Get all E-core logical IDs."""
        return list(self.ECoreLogicalIds)

    def GetCoresForTier(self, Tier: str, MaxCount: int = 0) -> List[int]:
        """Get core IDs for a given tier, limited to MaxCount.

        Args:
            Tier: "performance" (P-cores physical only), "performance-all" (P-cores + HT),
                  "efficiency" (E-cores), or "all"
            MaxCount: Maximum cores to return (0 = all available in tier)

        Returns:
            List of logical processor IDs
        """
        if Tier == "performance":
            Cores = self.GetPCorePhysicalIds()
        elif Tier == "performance-all":
            Cores = self.GetAllPCoreIds()
        elif Tier == "efficiency":
            Cores = self.GetECoreIds()
        else:
            Cores = list(self.AllLogicalIds)

        if MaxCount > 0 and len(Cores) > MaxCount:
            Cores = Cores[:MaxCount]

        return Cores

    def GetTopologySummary(self) -> Dict[str, Any]:
        """Get a summary of the detected topology for diagnostics/UI."""
        return {
            "IsHybrid": self.IsHybrid,
            "DetectionMethod": self.DetectionMethod,
            "PCoreLogicalIds": self.PCoreLogicalIds,
            "ECoreLogicalIds": self.ECoreLogicalIds,
            "PCoreCount": len(self.PCoreLogicalIds),
            "ECoreCount": len(self.ECoreLogicalIds),
            "TotalLogical": len(self.AllLogicalIds),
            "PCorePhysicalIds": self.GetPCorePhysicalIds()
        }
