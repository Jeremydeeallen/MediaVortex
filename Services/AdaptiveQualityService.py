#!/usr/bin/env python3
"""
Adaptive Quality Service
Service for adjusting CRF values based on previous transcode attempt VMAF scores.
Implements MVVM pattern using MVVM architecture
"""

from typing import Optional, Dict, Any, Tuple
from Services.LoggingService import LoggingService


class AdaptiveQualityService:
    """Service for adaptive CRF adjustment based on previous VMAF results."""
    
    def __init__(self, DatabaseManagerInstance=None):
        """Initialize the service with database manager."""
        self.DatabaseManager = DatabaseManagerInstance
    
    def GetLatestTranscodeAttemptWithVMAF(self, FilePath: str) -> Optional[Dict[str, Any]]:
        """
        Get the most recent transcode attempt with VMAF score for a file.
        
        Args:
            FilePath: Path to the file to check
            
        Returns:
            Dict with Quality (CRF), VMAF, ProfileName, AttemptDate, Success, or None if no attempts
        """
        try:
            LoggingService.LogFunctionEntry("GetLatestTranscodeAttemptWithVMAF", "AdaptiveQualityService", FilePath)
            
            if not self.DatabaseManager:
                LoggingService.LogError("DatabaseManager not initialized", "AdaptiveQualityService", "GetLatestTranscodeAttemptWithVMAF")
                return None
            
            attempt = self.DatabaseManager.GetLatestTranscodeAttemptWithVMAF(FilePath)
            
            if attempt:
                LoggingService.LogDebug(f"Found previous attempt for {FilePath}: CRF={attempt.get('Quality')}, VMAF={attempt.get('VMAF')}", 
                                      "AdaptiveQualityService", "GetLatestTranscodeAttemptWithVMAF")
            else:
                LoggingService.LogDebug(f"No previous attempt found for {FilePath}", 
                                      "AdaptiveQualityService", "GetLatestTranscodeAttemptWithVMAF")
            
            return attempt
            
        except Exception as e:
            LoggingService.LogException("Exception getting latest transcode attempt with VMAF", e, "AdaptiveQualityService", "GetLatestTranscodeAttemptWithVMAF")
            return None
    
    def CalculateAdjustedCRF(self, PreviousCRF: int, VMAFScore: float) -> int:
        """
        Calculate new CRF based on VMAF score.
        
        Rules:
        - VMAF < 50: Decrease CRF by 4
        - VMAF 50-60: Decrease CRF by 3
        - VMAF 61-70: Decrease CRF by 2
        - VMAF 71-79: Decrease CRF by 1
        - VMAF 80+: Should not be called (skip retranscode)
        
        Args:
            PreviousCRF: CRF value used in previous attempt
            VMAFScore: VMAF score from previous attempt
            
        Returns:
            New CRF value (lower = higher quality)
        """
        try:
            LoggingService.LogFunctionEntry("CalculateAdjustedCRF", "AdaptiveQualityService", PreviousCRF, VMAFScore)
            
            if VMAFScore < 50:
                adjustment = 4
                reason = "VMAF < 50"
            elif VMAFScore < 61:
                adjustment = 3
                reason = "VMAF 50-60"
            elif VMAFScore < 71:
                adjustment = 2
                reason = "VMAF 61-70"
            elif VMAFScore < 80:
                adjustment = 1
                reason = "VMAF 71-79"
            else:
                # VMAF >= 80 should not retranscode, but if called, use 1 as safety
                adjustment = 1
                reason = "VMAF >= 80 (should not retranscode)"
                LoggingService.LogWarning(f"CalculateAdjustedCRF called with VMAF >= 80 ({VMAFScore}). Should skip retranscode.", 
                                        "AdaptiveQualityService", "CalculateAdjustedCRF")
            
            newCRF = PreviousCRF - adjustment
            
            # Enforce minimum CRF (industry standard minimum is 15)
            minCRF = 15
            if newCRF < minCRF:
                LoggingService.LogWarning(f"Calculated CRF {newCRF} is below minimum {minCRF}, enforcing minimum", 
                                        "AdaptiveQualityService", "CalculateAdjustedCRF")
                newCRF = minCRF
            
            LoggingService.LogInfo(f"CRF adjustment: {PreviousCRF} -> {newCRF} (adjustment: -{adjustment}, reason: {reason}, VMAF: {VMAFScore:.2f})", 
                                 "AdaptiveQualityService", "CalculateAdjustedCRF")
            
            return newCRF
            
        except Exception as e:
            LoggingService.LogException("Exception calculating adjusted CRF", e, "AdaptiveQualityService", "CalculateAdjustedCRF")
            return PreviousCRF  # Return previous CRF on error
    
    def ValidateCRFAdjustment(self, AdjustedCRF: int, CurrentCRF: int, MinCRF: int = 15) -> bool:
        """
        Check if CRF adjustment is valid.
        
        Args:
            AdjustedCRF: The calculated adjusted CRF value
            CurrentCRF: The current CRF value from profile
            MinCRF: Minimum allowed CRF value (default 15)
            
        Returns:
            True if adjustment is valid, False otherwise
        """
        try:
            LoggingService.LogFunctionEntry("ValidateCRFAdjustment", "AdaptiveQualityService", AdjustedCRF, CurrentCRF, MinCRF)
            
            # Check if adjusted CRF is below minimum
            if AdjustedCRF < MinCRF:
                LoggingService.LogWarning(f"Adjusted CRF {AdjustedCRF} is below minimum {MinCRF}", 
                                        "AdaptiveQualityService", "ValidateCRFAdjustment")
                return False
            
            # Check if adjusted CRF is same as current (no improvement possible)
            if AdjustedCRF == CurrentCRF:
                LoggingService.LogInfo(f"Adjusted CRF {AdjustedCRF} is same as current CRF {CurrentCRF}, no adjustment needed", 
                                     "AdaptiveQualityService", "ValidateCRFAdjustment")
                return False
            
            # Adjustment is valid
            LoggingService.LogDebug(f"CRF adjustment validated: {CurrentCRF} -> {AdjustedCRF}", 
                                  "AdaptiveQualityService", "ValidateCRFAdjustment")
            return True
            
        except Exception as e:
            LoggingService.LogException("Exception validating CRF adjustment", e, "AdaptiveQualityService", "ValidateCRFAdjustment")
            return False
    
    def ShouldRetranscode(self, FilePath: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Check if file should be retranscoded based on previous attempt VMAF.
        Skips retranscoding if a preferred attempt exists.
        
        Returns:
            Tuple of (should_retranscode: bool, previous_attempt: Dict or None)
        """
        try:
            LoggingService.LogFunctionEntry("ShouldRetranscode", "AdaptiveQualityService", FilePath)
            
            previousAttempt = self.GetLatestTranscodeAttemptWithVMAF(FilePath)
            
            if not previousAttempt:
                # No previous attempt - should transcode (first attempt)
                LoggingService.LogDebug(f"No previous attempt for {FilePath}, should transcode", 
                                      "AdaptiveQualityService", "ShouldRetranscode")
                return True, None
            
            # Check if this is a preferred attempt - if so, skip retranscoding
            isPreferred = previousAttempt.get('PreferredAttempt', False)
            if isPreferred:
                LoggingService.LogInfo(f"Previous attempt for {FilePath} is marked as preferred, skipping retranscode", 
                                     "AdaptiveQualityService", "ShouldRetranscode")
                return False, previousAttempt
            
            vmaf = previousAttempt.get('VMAF')
            if vmaf is None:
                # Previous attempt has no VMAF - should transcode (may not have been quality tested)
                LoggingService.LogDebug(f"Previous attempt for {FilePath} has no VMAF, should transcode", 
                                      "AdaptiveQualityService", "ShouldRetranscode")
                return True, previousAttempt
            
            # Check if VMAF is acceptable (>= 80 means no retranscode needed)
            if vmaf >= 80:
                LoggingService.LogInfo(f"Previous attempt for {FilePath} has acceptable VMAF {vmaf:.2f} (>= 80), skipping retranscode", 
                                     "AdaptiveQualityService", "ShouldRetranscode")
                return False, previousAttempt
            
            # VMAF < 80 - should retranscode with adjusted CRF
            LoggingService.LogDebug(f"Previous attempt for {FilePath} has VMAF {vmaf:.2f} (< 80), should retranscode", 
                                  "AdaptiveQualityService", "ShouldRetranscode")
            return True, previousAttempt
            
        except Exception as e:
            LoggingService.LogException("Exception checking if should retranscode", e, "AdaptiveQualityService", "ShouldRetranscode")
            # On error, default to retranscoding (safer)
            return True, None

