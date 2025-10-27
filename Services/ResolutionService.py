from typing import Tuple, Optional, List
from Services.LoggingService import LoggingService


class ResolutionService:
    """Business service for resolution standardization and matching logic."""
    
    def __init__(self):
        """Initialize the ResolutionService."""
        self.StandardResolutions = ['480p', '720p', '1080p', '2160p']
        self.StandardHeights = [480, 720, 1080, 2160]
        # Cache for standardized resolutions to avoid repeated processing
        self.ResolutionCache = {}
    
    def StandardizeResolution(self, Resolution: str) -> str:
        """
        Main entry point for resolution standardization.
        
        Args:
            Resolution: Resolution string in any format (e.g., '1920x1080', '1080p')
            
        Returns:
            Standardized resolution string (e.g., '1080p', '720p', '480p')
        """
        try:
            # Check cache first to avoid repeated processing
            if Resolution in self.ResolutionCache:
                return self.ResolutionCache[Resolution]
            
            # Only log function entry for non-standard resolutions to reduce log flooding
            if not self.IsExactMatch(Resolution):
                LoggingService.LogFunctionEntry("StandardizeResolution", "ResolutionService", Resolution)
            
            if not Resolution or Resolution.strip() == '':
                LoggingService.LogWarning("Empty resolution provided, defaulting to 480p", "ResolutionService", "StandardizeResolution")
                result = "480p"
                self.ResolutionCache[Resolution] = result
                return result
            
            # Check if already in standard format
            if self.IsExactMatch(Resolution):
                # Remove INFO log for standard resolutions to reduce flooding
                self.ResolutionCache[Resolution] = Resolution
                return Resolution
            
            # Parse pixel dimensions
            Width, Height = self.ParseResolution(Resolution)
            if Width is None or Height is None:
                LoggingService.LogWarning(f"Could not parse resolution {Resolution}, defaulting to 480p", "ResolutionService", "StandardizeResolution")
                result = "480p"
                self.ResolutionCache[Resolution] = result
                return result
            
            # Check if ultra-wide or VR (skip these)
            if self.IsUltraWideOrVR(Width, Height):
                LoggingService.LogInfo(f"Resolution {Resolution} ({Width}x{Height}) is ultra-wide/VR, skipping standardization", "ResolutionService", "StandardizeResolution")
                result = "SKIP"
                self.ResolutionCache[Resolution] = result
                return result
            
            # Get standard height (round down)
            StandardHeight = self.GetStandardHeight(Height)
            
            # Calculate standard width maintaining aspect ratio
            StandardWidth = self.CalculateStandardWidth(Width, Height, StandardHeight)
            
            # Map to standard resolution name
            StandardResolution = self.MapToStandardResolution(StandardWidth, StandardHeight)
            
            LoggingService.LogInfo(f"Standardized {Resolution} ({Width}x{Height}) to {StandardResolution} ({StandardWidth}x{StandardHeight})", 
                                 "ResolutionService", "StandardizeResolution")
            
            # Cache the result
            self.ResolutionCache[Resolution] = StandardResolution
            return StandardResolution
            
        except Exception as e:
            LoggingService.LogException("Error standardizing resolution", e, "ResolutionService", "StandardizeResolution")
            return "480p"  # Safe fallback
    
    def IsExactMatch(self, Resolution: str) -> bool:
        """
        Check if resolution is already in standard format.
        
        Args:
            Resolution: Resolution string to check
            
        Returns:
            True if resolution is already standard (480p, 720p, 1080p, 2160p)
        """
        return Resolution in self.StandardResolutions
    
    def ParseResolution(self, Resolution: str) -> Tuple[Optional[int], Optional[int]]:
        """
        Extract width and height from resolution string.
        
        Args:
            Resolution: Resolution string (e.g., '1920x1080', '1280x720')
            
        Returns:
            Tuple of (Width, Height) or (None, None) if parsing fails
        """
        try:
            Resolution = Resolution.strip().lower()
            
            # Handle pixel format (e.g., '1920x1080')
            if 'x' in Resolution:
                parts = Resolution.split('x')
                if len(parts) == 2:
                    Width = int(parts[0])
                    Height = int(parts[1])
                    return Width, Height
            
            # Handle standard format (e.g., '1080p')
            if Resolution.endswith('p'):
                height_str = Resolution[:-1]
                if height_str.isdigit():
                    Height = int(height_str)
                    # Estimate width based on common aspect ratios
                    if Height == 2160:
                        Width = 3840  # 4K
                    elif Height == 1080:
                        Width = 1920  # Full HD
                    elif Height == 720:
                        Width = 1280  # HD
                    elif Height == 480:
                        Width = 854   # SD
                    else:
                        Width = int(Height * 16 / 9)  # Default 16:9
                    return Width, Height
            
            return None, None
            
        except Exception as e:
            LoggingService.LogException("Error parsing resolution", e, "ResolutionService", "ParseResolution")
            return None, None
    
    def IsUltraWideOrVR(self, Width: int, Height: int) -> bool:
        """
        Detect ultra-wide or VR formats that should be skipped.
        
        Args:
            Width: Video width in pixels
            Height: Video height in pixels
            
        Returns:
            True if resolution should be skipped (ultra-wide or VR)
        """
        try:
            AspectRatio = Width / Height
            
            # Ultra-wide formats (21:9, 32:9, etc.)
            if AspectRatio > 2.0:
                LoggingService.LogInfo(f"Detected ultra-wide format: {Width}x{Height} (aspect ratio: {AspectRatio:.2f})", 
                                     "ResolutionService", "IsUltraWideOrVR")
                return True
            
            # VR formats (square or near-square with high resolution)
            if 0.8 <= AspectRatio <= 1.2 and (Width > 2000 or Height > 2000):
                LoggingService.LogInfo(f"Detected VR format: {Width}x{Height} (aspect ratio: {AspectRatio:.2f})", 
                                     "ResolutionService", "IsUltraWideOrVR")
                return True
            
            return False
            
        except Exception as e:
            LoggingService.LogException("Error detecting ultra-wide/VR format", e, "ResolutionService", "IsUltraWideOrVR")
            return False
    
    def GetStandardHeight(self, SourceHeight: int) -> int:
        """
        Round down to nearest standard height.
        
        Args:
            SourceHeight: Source video height in pixels
            
        Returns:
            Standard height (2160, 1080, 720, or 480)
        """
        try:
            if SourceHeight >= 2160:
                return 2160  # 4K
            elif SourceHeight >= 1080:
                return 1080  # Full HD
            elif SourceHeight >= 720:
                return 720   # HD
            elif SourceHeight >= 480:
                return 480   # SD
            else:
                return 480   # Default to SD for very low resolutions
                
        except Exception as e:
            LoggingService.LogException("Error getting standard height", e, "ResolutionService", "GetStandardHeight")
            return 480
    
    def CalculateStandardWidth(self, SourceWidth: int, SourceHeight: int, TargetHeight: int) -> int:
        """
        Calculate width to maintain aspect ratio.
        
        Args:
            SourceWidth: Source video width in pixels
            SourceHeight: Source video height in pixels
            TargetHeight: Target standard height in pixels
            
        Returns:
            Calculated width maintaining aspect ratio
        """
        try:
            AspectRatio = SourceWidth / SourceHeight
            TargetWidth = int(TargetHeight * AspectRatio)
            
            # Ensure width is even (required for most codecs)
            if TargetWidth % 2 != 0:
                TargetWidth += 1
            
            return TargetWidth
            
        except Exception as e:
            LoggingService.LogException("Error calculating standard width", e, "ResolutionService", "CalculateStandardWidth")
            return TargetHeight * 16 // 9  # Default 16:9 aspect ratio
    
    def MapToStandardResolution(self, Width: int, Height: int) -> str:
        """
        Map pixel dimensions to standard resolution name.
        
        Args:
            Width: Video width in pixels
            Height: Video height in pixels
            
        Returns:
            Standard resolution name (2160p, 1080p, 720p, or 480p)
        """
        try:
            if Height == 2160:
                return "2160p"
            elif Height == 1080:
                return "1080p"
            elif Height == 720:
                return "720p"
            elif Height == 480:
                return "480p"
            else:
                return "480p"  # Default fallback
                
        except Exception as e:
            LoggingService.LogException("Error mapping to standard resolution", e, "ResolutionService", "MapToStandardResolution")
            return "480p"
    
    def FindMatchingThreshold(self, FileResolution: str, ProfileThresholds: List) -> Optional:
        """
        Find matching profile threshold using standardized resolution.
        
        Args:
            FileResolution: File resolution string
            ProfileThresholds: List of ProfileThresholdModel objects
            
        Returns:
            Matching ProfileThresholdModel or None
        """
        try:
            LoggingService.LogFunctionEntry("FindMatchingThreshold", "ResolutionService", FileResolution)
            
            # Standardize the file resolution
            StandardizedResolution = self.StandardizeResolution(FileResolution)
            
            if StandardizedResolution == "SKIP":
                LoggingService.LogInfo(f"File resolution {FileResolution} should be skipped (ultra-wide/VR)", 
                                     "ResolutionService", "FindMatchingThreshold")
                return None
            
            # Find matching threshold using standardized resolution
            MatchingThresholds = []
            for Threshold in ProfileThresholds:
                # Use cached result if available, otherwise standardize
                ThresholdResolution = Threshold.Resolution or ""
                if ThresholdResolution in self.ResolutionCache:
                    ThresholdResolutionStandard = self.ResolutionCache[ThresholdResolution]
                else:
                    ThresholdResolutionStandard = self.StandardizeResolution(ThresholdResolution)
                
                if ThresholdResolutionStandard == StandardizedResolution:
                    MatchingThresholds.append(Threshold)
                    LoggingService.LogInfo(f"Found resolution match: {Threshold.Resolution} -> {ThresholdResolutionStandard}", 
                                         "ResolutionService", "FindMatchingThreshold")
            
            if MatchingThresholds:
                # Use the first matching threshold
                Threshold = MatchingThresholds[0]
                LoggingService.LogInfo(f"Using profile threshold {Threshold.ProfileId} for {FileResolution}", 
                                     "ResolutionService", "FindMatchingThreshold")
                return Threshold
            
            LoggingService.LogWarning(f"No profile threshold found for resolution {FileResolution} (standardized: {StandardizedResolution})", 
                                    "ResolutionService", "FindMatchingThreshold")
            return None
            
        except Exception as e:
            LoggingService.LogException("Error finding matching threshold", e, "ResolutionService", "FindMatchingThreshold")
            return None
    
    def CompareResolutions(self, SourceResolution: str, TargetResolution: str) -> int:
        """
        Compare two resolutions by height.
        
        Args:
            SourceResolution: Source file resolution string
            TargetResolution: Target resolution string
            
        Returns:
            -1 if source < target, 0 if equal, 1 if source > target
        """
        try:
            LoggingService.LogFunctionEntry("CompareResolutions", "ResolutionService", SourceResolution, TargetResolution)
            
            # Parse both resolutions
            SourceWidth, SourceHeight = self.ParseResolution(SourceResolution or "")
            TargetWidth, TargetHeight = self.ParseResolution(TargetResolution or "")
            
            # Handle missing or invalid resolutions
            if SourceHeight is None or TargetHeight is None:
                LoggingService.LogWarning(f"Could not parse resolutions: source={SourceResolution}, target={TargetResolution}", 
                                        "ResolutionService", "CompareResolutions")
                return 0  # Treat as equal to avoid blocking
            
            # Compare heights
            if SourceHeight < TargetHeight:
                result = -1
            elif SourceHeight == TargetHeight:
                result = 0
            else:
                result = 1
            
            LoggingService.LogDebug(f"Resolution comparison: {SourceResolution} ({SourceHeight}) vs {TargetResolution} ({TargetHeight}) = {result}", 
                                    "ResolutionService", "CompareResolutions")
            return result
            
        except Exception as e:
            LoggingService.LogException("Error comparing resolutions", e, "ResolutionService", "CompareResolutions")
            return 0  # Treat as equal to avoid blocking

    def ValidateResolutionMapping(self, ProfileThresholds: List) -> dict:
        """
        Validate all resolutions have proper mappings.
        
        Args:
            ProfileThresholds: List of ProfileThresholdModel objects
            
        Returns:
            Dictionary with validation results
        """
        try:
            LoggingService.LogFunctionEntry("ValidateResolutionMapping", "ResolutionService")
            
            Results = {
                "TotalThresholds": len(ProfileThresholds),
                "StandardResolutions": {},
                "NonStandardResolutions": [],
                "MissingMappings": [],
                "ValidMappings": 0
            }
            
            for Threshold in ProfileThresholds:
                Resolution = Threshold.Resolution or ""
                Standardized = self.StandardizeResolution(Resolution)
                
                if Standardized in self.StandardResolutions:
                    if Standardized not in Results["StandardResolutions"]:
                        Results["StandardResolutions"][Standardized] = 0
                    Results["StandardResolutions"][Standardized] += 1
                    Results["ValidMappings"] += 1
                elif Standardized == "SKIP":
                    Results["NonStandardResolutions"].append(Resolution)
                else:
                    Results["MissingMappings"].append(Resolution)
            
            LoggingService.LogInfo(f"Resolution mapping validation complete: {Results['ValidMappings']} valid mappings", 
                                 "ResolutionService", "ValidateResolutionMapping")
            
            return Results
            
        except Exception as e:
            LoggingService.LogException("Error validating resolution mapping", e, "ResolutionService", "ValidateResolutionMapping")
            return {"Error": str(e)}
