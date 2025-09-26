# Quality Testing Architecture Overhaul

This document outlines the complete architectural redesign of the quality testing system to support flexible, configurable quality assessment strategies following MVVM principles.

## Overview

The current quality testing system has a rigid flow: Transcode → Auto-add to VMAF → Process VMAF. This overhaul introduces flexible quality testing strategies that can be configured per profile and file, supporting multiple testing scenarios.

## Quality Testing Scenarios

### 1. **Skip Quality Testing**
- **Use Case**: User is confident in transcoding quality
- **Flow**: Transcode → Complete → Skip VMAF → File Management
- **Configuration**: Profile-based or file-specific override

### 2. **Single Quality Test**
- **Use Case**: Standard quality assessment
- **Flow**: Transcode → Complete → Single VMAF → File Management
- **Configuration**: Default behavior with configurable threshold

### 3. **Multi Quality Test**
- **Use Case**: Compare multiple transcoding options
- **Flow**: Transcode → Complete → Multi VMAF → Select Best → File Management
- **Configuration**: Multiple profile testing with result comparison

### 4. **Custom Quality Test**
- **Use Case**: Specialized quality assessment
- **Flow**: Transcode → Complete → Custom VMAF Strategy → File Management
- **Configuration**: Custom settings and thresholds

## MVVM Architecture Design

### **Models (Data Layer)**

#### 1. **QualityTestingStrategyModel**
```python
class QualityTestingStrategyModel:
    """Model for quality testing strategy configuration."""
    
    def __init__(self):
        self.Id: Optional[int] = None
        self.ProfileId: int = 0
        self.StrategyType: str = "Single"  # "Skip", "Single", "Multi", "Custom"
        self.VMAFThreshold: float = 90.0
        self.MaxAttempts: int = 3
        self.AlternativeProfileIds: List[int] = []  # For multi-testing
        self.CustomSettings: Dict[str, Any] = {}
        self.IsEnabled: bool = True
        self.CreatedDate: Optional[datetime] = None
        self.UpdatedDate: Optional[datetime] = None
```

#### 2. **QualityTestResultModel**
```python
class QualityTestResultModel:
    """Model for individual quality test results."""
    
    def __init__(self):
        self.Id: Optional[int] = None
        self.TranscodeAttemptId: int = 0
        self.VMAFScore: float = 0.0
        self.ProfileId: int = 0
        self.ProfileName: str = ""
        self.FileSize: int = 0
        self.TestDuration: float = 0.0
        self.PassesThreshold: bool = False
        self.Rank: int = 0  # For multi-testing ranking
        self.ErrorMessage: Optional[str] = None
        self.DateTested: Optional[datetime] = None
```

#### 3. **QualityTestingQueueModel**
```python
class QualityTestingQueueModel:
    """Model for quality testing queue management."""
    
    def __init__(self):
        self.Id: Optional[int] = None
        self.TranscodeAttemptId: int = 0
        self.StrategyId: int = 0
        self.Status: str = "Pending"  # "Pending", "Testing", "Completed", "Skipped", "Failed"
        self.Results: List[QualityTestResultModel] = []
        self.SelectedResultId: Optional[int] = None
        self.DateCreated: Optional[datetime] = None
        self.DateCompleted: Optional[datetime] = None
        self.ErrorMessage: Optional[str] = None
```

#### 4. **FileQualityOverrideModel**
```python
class FileQualityOverrideModel:
    """Model for file-specific quality testing overrides."""
    
    def __init__(self):
        self.Id: Optional[int] = None
        self.FilePath: str = ""
        self.OverrideStrategy: str = "None"  # "None", "Skip", "Single", "Multi", "Custom"
        self.CustomThreshold: Optional[float] = None
        self.SkipQualityTesting: bool = False
        self.CustomSettings: Dict[str, Any] = {}
        self.CreatedDate: Optional[datetime] = None
```

### **ViewModels (Business Logic Layer)**

#### 1. **QualityTestingViewModel**
```python
class QualityTestingViewModel:
    """ViewModel for quality testing business logic."""
    
    def __init__(self, DatabaseManagerInstance: DatabaseManager = None):
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
        self.StrategyService = QualityTestingStrategyService(self.DatabaseManager)
        self.MultiTestingService = MultiQualityTestingService(self.DatabaseManager)
        self.OrchestratorService = QualityTestingOrchestratorService(self.DatabaseManager)
    
    def DetermineTestingStrategy(self, MediaFile: MediaFileModel, Profile: ProfileModel) -> QualityTestingStrategyModel:
        """Determine quality testing strategy based on file and profile settings."""
        try:
            # Check for file-specific overrides first
            fileOverride = self.DatabaseManager.GetFileQualityOverride(MediaFile.FilePath)
            if fileOverride and fileOverride.OverrideStrategy != "None":
                return self._CreateStrategyFromOverride(fileOverride)
            
            # Get profile-based strategy
            profileStrategy = self.StrategyService.GetStrategyForProfile(Profile.Id)
            if profileStrategy:
                return profileStrategy
            
            # Default strategy
            return self._CreateDefaultStrategy(Profile.Id)
            
        except Exception as e:
            LoggingService.LogException("Exception determining testing strategy", e, "QualityTestingViewModel", "DetermineTestingStrategy")
            return self._CreateDefaultStrategy(Profile.Id)
    
    def CreateQualityTest(self, TranscodeAttemptId: int, Strategy: QualityTestingStrategyModel) -> QualityTestingQueueModel:
        """Create quality test based on strategy."""
        try:
            qualityTest = QualityTestingQueueModel()
            qualityTest.TranscodeAttemptId = TranscodeAttemptId
            qualityTest.StrategyId = Strategy.Id
            qualityTest.Status = "Pending"
            qualityTest.DateCreated = datetime.now()
            
            # Save to database
            qualityTestId = self.DatabaseManager.SaveQualityTestingQueue(qualityTest)
            qualityTest.Id = qualityTestId
            
            return qualityTest
            
        except Exception as e:
            LoggingService.LogException("Exception creating quality test", e, "QualityTestingViewModel", "CreateQualityTest")
            return None
    
    def ProcessQualityTest(self, QualityTest: QualityTestingQueueModel) -> Dict[str, Any]:
        """Process quality test according to strategy."""
        try:
            # Get strategy details
            strategy = self.DatabaseManager.GetQualityTestingStrategy(QualityTest.StrategyId)
            if not strategy:
                return {"Success": False, "ErrorMessage": "Strategy not found"}
            
            # Route to appropriate handler
            if strategy.StrategyType == "Skip":
                return self.OrchestratorService.HandleSkipStrategy(QualityTest.TranscodeAttemptId)
            elif strategy.StrategyType == "Single":
                return self.OrchestratorService.HandleSingleStrategy(QualityTest.TranscodeAttemptId)
            elif strategy.StrategyType == "Multi":
                return self.OrchestratorService.HandleMultiStrategy(QualityTest.TranscodeAttemptId, strategy.AlternativeProfileIds)
            elif strategy.StrategyType == "Custom":
                return self.OrchestratorService.HandleCustomStrategy(QualityTest.TranscodeAttemptId, strategy.CustomSettings)
            else:
                return {"Success": False, "ErrorMessage": f"Unknown strategy type: {strategy.StrategyType}"}
                
        except Exception as e:
            LoggingService.LogException("Exception processing quality test", e, "QualityTestingViewModel", "ProcessQualityTest")
            return {"Success": False, "ErrorMessage": str(e)}
    
    def SelectBestResult(self, Results: List[QualityTestResultModel]) -> QualityTestResultModel:
        """Select best result from multiple tests."""
        try:
            if not Results:
                return None
            
            # Filter results that pass threshold
            passingResults = [r for r in Results if r.PassesThreshold]
            if not passingResults:
                # If no results pass threshold, return the highest VMAF score
                return max(Results, key=lambda x: x.VMAFScore)
            
            # Among passing results, select the best VMAF score
            return max(passingResults, key=lambda x: x.VMAFScore)
            
        except Exception as e:
            LoggingService.LogException("Exception selecting best result", e, "QualityTestingViewModel", "SelectBestResult")
            return Results[0] if Results else None
```

#### 2. **TranscodingViewModel** (Enhanced)
```python
class TranscodingViewModel:
    """Enhanced ViewModel for transcoding with quality testing integration."""
    
    def __init__(self, DatabaseManagerInstance: DatabaseManager = None):
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
        self.QualityTestingViewModel = QualityTestingViewModel(self.DatabaseManager)
        self.FileManager = TranscodingFileManagerService()
    
    def CompleteTranscoding(self, TranscodeAttemptId: int, OutputFilePath: str) -> Dict[str, Any]:
        """Complete transcoding and determine next step based on quality testing strategy."""
        try:
            # Get transcode attempt details
            transcodeAttempt = self.DatabaseManager.GetTranscodeAttemptById(TranscodeAttemptId)
            if not transcodeAttempt:
                return {"Success": False, "ErrorMessage": "Transcode attempt not found"}
            
            # Get media file and profile
            mediaFile = self.DatabaseManager.GetMediaFileByPath(transcodeAttempt.OriginalFilePath)
            profile = self.DatabaseManager.GetProfileById(transcodeAttempt.ProfileId)
            
            if not mediaFile or not profile:
                return {"Success": False, "ErrorMessage": "Media file or profile not found"}
            
            # Determine quality testing strategy
            strategy = self.QualityTestingViewModel.DetermineTestingStrategy(mediaFile, profile)
            
            # Create quality test
            qualityTest = self.QualityTestingViewModel.CreateQualityTest(TranscodeAttemptId, strategy)
            if not qualityTest:
                return {"Success": False, "ErrorMessage": "Failed to create quality test"}
            
            # Process quality test
            result = self.QualityTestingViewModel.ProcessQualityTest(qualityTest)
            
            return {
                "Success": True,
                "QualityTestId": qualityTest.Id,
                "Strategy": strategy.StrategyType,
                "Result": result
            }
            
        except Exception as e:
            LoggingService.LogException("Exception completing transcoding", e, "TranscodingViewModel", "CompleteTranscoding")
            return {"Success": False, "ErrorMessage": str(e)}
```

### **Services (Business Logic Implementation)**

#### 1. **QualityTestingStrategyService**
```python
class QualityTestingStrategyService:
    """Service for managing quality testing strategies."""
    
    def __init__(self, DatabaseManagerInstance: DatabaseManager = None):
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
    
    def GetStrategyForProfile(self, ProfileId: int) -> Optional[QualityTestingStrategyModel]:
        """Get quality testing strategy for a profile."""
        try:
            return self.DatabaseManager.GetQualityTestingStrategyByProfileId(ProfileId)
        except Exception as e:
            LoggingService.LogException("Exception getting strategy for profile", e, "QualityTestingStrategyService", "GetStrategyForProfile")
            return None
    
    def GetStrategyForFile(self, MediaFile: MediaFileModel) -> Optional[QualityTestingStrategyModel]:
        """Get quality testing strategy for a specific file."""
        try:
            # Check for file-specific overrides
            fileOverride = self.DatabaseManager.GetFileQualityOverride(MediaFile.FilePath)
            if fileOverride and fileOverride.OverrideStrategy != "None":
                return self._CreateStrategyFromOverride(fileOverride)
            
            # Get profile-based strategy
            return self.GetStrategyForProfile(MediaFile.AssignedProfile)
            
        except Exception as e:
            LoggingService.LogException("Exception getting strategy for file", e, "QualityTestingStrategyService", "GetStrategyForFile")
            return None
    
    def ShouldSkipQualityTesting(self, Profile: ProfileModel, MediaFile: MediaFileModel) -> bool:
        """Determine if quality testing should be skipped."""
        try:
            # Check file-specific override
            fileOverride = self.DatabaseManager.GetFileQualityOverride(MediaFile.FilePath)
            if fileOverride:
                return fileOverride.SkipQualityTesting
            
            # Check profile strategy
            strategy = self.GetStrategyForProfile(Profile.Id)
            if strategy:
                return strategy.StrategyType == "Skip"
            
            return False
            
        except Exception as e:
            LoggingService.LogException("Exception checking skip quality testing", e, "QualityTestingStrategyService", "ShouldSkipQualityTesting")
            return False
```

#### 2. **MultiQualityTestingService**
```python
class MultiQualityTestingService:
    """Service for handling multiple quality testing scenarios."""
    
    def __init__(self, DatabaseManagerInstance: DatabaseManager = None):
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
        self.VMAFService = VMAFQueueBusinessService(self.DatabaseManager)
    
    def CreateMultipleTranscodes(self, OriginalFile: str, ProfileIds: List[int]) -> List[TranscodeAttemptModel]:
        """Create multiple transcoding attempts with different profiles."""
        try:
            transcodes = []
            
            for profileId in ProfileIds:
                # Create transcode attempt for each profile
                transcodeAttempt = TranscodeAttemptModel()
                transcodeAttempt.OriginalFilePath = OriginalFile
                transcodeAttempt.ProfileId = profileId
                transcodeAttempt.Status = "Pending"
                transcodeAttempt.DateCreated = datetime.now()
                
                # Save to database
                attemptId = self.DatabaseManager.SaveTranscodeAttempt(transcodeAttempt)
                transcodeAttempt.Id = attemptId
                
                transcodes.append(transcodeAttempt)
            
            return transcodes
            
        except Exception as e:
            LoggingService.LogException("Exception creating multiple transcodes", e, "MultiQualityTestingService", "CreateMultipleTranscodes")
            return []
    
    def RunQualityComparison(self, TranscodeAttempts: List[TranscodeAttemptModel]) -> List[QualityTestResultModel]:
        """Run VMAF comparison on multiple transcoded files."""
        try:
            results = []
            
            for attempt in TranscodeAttempts:
                # Get transcoded file path
                outputPath = self._GetTranscodedFilePath(attempt)
                if not outputPath or not os.path.exists(outputPath):
                    continue
                
                # Run VMAF analysis
                vmafResult = self.VMAFService.ProcessVMAFJob(attempt.OriginalFilePath, outputPath)
                
                if vmafResult.Success:
                    # Create quality test result
                    result = QualityTestResultModel()
                    result.TranscodeAttemptId = attempt.Id
                    result.VMAFScore = vmafResult.VMAFScore
                    result.ProfileId = attempt.ProfileId
                    result.FileSize = os.path.getsize(outputPath)
                    result.PassesThreshold = vmafResult.VMAFScore >= 90.0
                    result.DateTested = datetime.now()
                    
                    results.append(result)
            
            return results
            
        except Exception as e:
            LoggingService.LogException("Exception running quality comparison", e, "MultiQualityTestingService", "RunQualityComparison")
            return []
    
    def SelectBestTranscode(self, Results: List[QualityTestResultModel]) -> QualityTestResultModel:
        """Select the best transcoding result."""
        try:
            if not Results:
                return None
            
            # Filter results that pass threshold
            passingResults = [r for r in Results if r.PassesThreshold]
            if not passingResults:
                # If no results pass threshold, return the highest VMAF score
                return max(Results, key=lambda x: x.VMAFScore)
            
            # Among passing results, select the best VMAF score
            return max(passingResults, key=lambda x: x.VMAFScore)
            
        except Exception as e:
            LoggingService.LogException("Exception selecting best transcode", e, "MultiQualityTestingService", "SelectBestTranscode")
            return Results[0] if Results else None
```

#### 3. **QualityTestingOrchestratorService**
```python
class QualityTestingOrchestratorService:
    """Service for orchestrating quality testing workflows."""
    
    def __init__(self, DatabaseManagerInstance: DatabaseManager = None):
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
        self.MultiTestingService = MultiQualityTestingService(self.DatabaseManager)
        self.VMAFService = VMAFQueueBusinessService(self.DatabaseManager)
    
    def ProcessQualityTestingRequest(self, QualityTest: QualityTestingQueueModel) -> Dict[str, Any]:
        """Orchestrate quality testing based on strategy."""
        try:
            # Get strategy details
            strategy = self.DatabaseManager.GetQualityTestingStrategy(QualityTest.StrategyId)
            if not strategy:
                return {"Success": False, "ErrorMessage": "Strategy not found"}
            
            # Route to appropriate handler
            if strategy.StrategyType == "Skip":
                return self.HandleSkipStrategy(QualityTest.TranscodeAttemptId)
            elif strategy.StrategyType == "Single":
                return self.HandleSingleStrategy(QualityTest.TranscodeAttemptId)
            elif strategy.StrategyType == "Multi":
                return self.HandleMultiStrategy(QualityTest.TranscodeAttemptId, strategy.AlternativeProfileIds)
            elif strategy.StrategyType == "Custom":
                return self.HandleCustomStrategy(QualityTest.TranscodeAttemptId, strategy.CustomSettings)
            else:
                return {"Success": False, "ErrorMessage": f"Unknown strategy type: {strategy.StrategyType}"}
                
        except Exception as e:
            LoggingService.LogException("Exception processing quality testing request", e, "QualityTestingOrchestratorService", "ProcessQualityTestingRequest")
            return {"Success": False, "ErrorMessage": str(e)}
    
    def HandleSkipStrategy(self, TranscodeAttemptId: int) -> Dict[str, Any]:
        """Handle skipping quality testing."""
        try:
            # Update transcode attempt
            self.DatabaseManager.UpdateTranscodeAttempt(TranscodeAttemptId, {
                'VMAF': None,
                'QualityTested': False
            })
            
            # Proceed with file management
            return {
                "Success": True,
                "Strategy": "Skip",
                "Message": "Quality testing skipped"
            }
            
        except Exception as e:
            LoggingService.LogException("Exception handling skip strategy", e, "QualityTestingOrchestratorService", "HandleSkipStrategy")
            return {"Success": False, "ErrorMessage": str(e)}
    
    def HandleSingleStrategy(self, TranscodeAttemptId: int) -> Dict[str, Any]:
        """Handle single quality test."""
        try:
            # Get transcode attempt
            attempt = self.DatabaseManager.GetTranscodeAttemptById(TranscodeAttemptId)
            if not attempt:
                return {"Success": False, "ErrorMessage": "Transcode attempt not found"}
            
            # Get output file path
            outputPath = self._GetTranscodedFilePath(attempt)
            if not outputPath or not os.path.exists(outputPath):
                return {"Success": False, "ErrorMessage": "Transcoded file not found"}
            
            # Run VMAF analysis
            vmafResult = self.VMAFService.ProcessVMAFJob(attempt.OriginalFilePath, outputPath)
            
            if vmafResult.Success:
                # Update transcode attempt with VMAF score
                self.DatabaseManager.UpdateTranscodeAttempt(TranscodeAttemptId, {
                    'VMAF': vmafResult.VMAFScore,
                    'QualityTested': True
                })
                
                return {
                    "Success": True,
                    "Strategy": "Single",
                    "VMAFScore": vmafResult.VMAFScore,
                    "PassesThreshold": vmafResult.VMAFScore >= 90.0
                }
            else:
                return {"Success": False, "ErrorMessage": vmafResult.ErrorMessage}
                
        except Exception as e:
            LoggingService.LogException("Exception handling single strategy", e, "QualityTestingOrchestratorService", "HandleSingleStrategy")
            return {"Success": False, "ErrorMessage": str(e)}
    
    def HandleMultiStrategy(self, TranscodeAttemptId: int, ProfileIds: List[int]) -> Dict[str, Any]:
        """Handle multiple quality tests."""
        try:
            # Get original transcode attempt
            originalAttempt = self.DatabaseManager.GetTranscodeAttemptById(TranscodeAttemptId)
            if not originalAttempt:
                return {"Success": False, "ErrorMessage": "Original transcode attempt not found"}
            
            # Create multiple transcodes
            transcodes = self.MultiTestingService.CreateMultipleTranscodes(originalAttempt.OriginalFilePath, ProfileIds)
            
            # Run quality comparison
            results = self.MultiTestingService.RunQualityComparison(transcodes)
            
            # Select best result
            bestResult = self.MultiTestingService.SelectBestTranscode(results)
            
            if bestResult:
                # Update original transcode attempt with best result
                self.DatabaseManager.UpdateTranscodeAttempt(TranscodeAttemptId, {
                    'VMAF': bestResult.VMAFScore,
                    'QualityTested': True,
                    'BestProfileId': bestResult.ProfileId
                })
                
                return {
                    "Success": True,
                    "Strategy": "Multi",
                    "VMAFScore": bestResult.VMAFScore,
                    "BestProfileId": bestResult.ProfileId,
                    "TotalTests": len(results),
                    "PassingTests": len([r for r in results if r.PassesThreshold])
                }
            else:
                return {"Success": False, "ErrorMessage": "No valid results from multi-testing"}
                
        except Exception as e:
            LoggingService.LogException("Exception handling multi strategy", e, "QualityTestingOrchestratorService", "HandleMultiStrategy")
            return {"Success": False, "ErrorMessage": str(e)}
    
    def HandleCustomStrategy(self, TranscodeAttemptId: int, CustomSettings: Dict[str, Any]) -> Dict[str, Any]:
        """Handle custom quality testing strategy."""
        try:
            # Implement custom strategy logic based on settings
            # This is a placeholder for future custom implementations
            
            return {
                "Success": True,
                "Strategy": "Custom",
                "Message": "Custom strategy implemented"
            }
            
        except Exception as e:
            LoggingService.LogException("Exception handling custom strategy", e, "QualityTestingOrchestratorService", "HandleCustomStrategy")
            return {"Success": False, "ErrorMessage": str(e)}
```

### **Views (UI Layer)**

#### 1. **QualityTestingSettingsView**
- Profile-based quality testing settings
- File-specific overrides
- Strategy selection (Skip/Single/Multi/Custom)
- Threshold configuration
- Alternative profile selection for multi-testing

#### 2. **QualityTestingQueueView**
- Current quality testing status
- Multi-test progress tracking
- Result comparison interface
- Strategy selection and modification

#### 3. **QualityTestingResultsView**
- VMAF score comparison
- File size comparison
- Quality vs. size trade-offs
- Best result selection
- Historical quality testing data

## Database Schema Extensions

### **QualityTestingStrategies Table**
```sql
CREATE TABLE QualityTestingStrategies (
    Id INTEGER PRIMARY KEY,
    ProfileId INTEGER NOT NULL,
    StrategyType TEXT NOT NULL,  -- "Skip", "Single", "Multi", "Custom"
    VMAFThreshold REAL DEFAULT 90.0,
    MaxAttempts INTEGER DEFAULT 3,
    AlternativeProfileIds TEXT,  -- JSON array for multi-testing
    CustomSettings TEXT,  -- JSON for custom strategies
    IsEnabled BOOLEAN DEFAULT TRUE,
    CreatedDate DATETIME DEFAULT CURRENT_TIMESTAMP,
    UpdatedDate DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ProfileId) REFERENCES Profiles(Id)
);
```

### **QualityTestingQueue Table**
```sql
CREATE TABLE QualityTestingQueue (
    Id INTEGER PRIMARY KEY,
    TranscodeAttemptId INTEGER NOT NULL,
    StrategyId INTEGER NOT NULL,
    Status TEXT DEFAULT 'Pending',  -- "Pending", "Testing", "Completed", "Skipped", "Failed"
    Results TEXT,  -- JSON array of QualityTestResultModel
    SelectedResultId INTEGER,
    DateCreated DATETIME DEFAULT CURRENT_TIMESTAMP,
    DateCompleted DATETIME,
    ErrorMessage TEXT,
    FOREIGN KEY (TranscodeAttemptId) REFERENCES TranscodeAttempts(Id),
    FOREIGN KEY (StrategyId) REFERENCES QualityTestingStrategies(Id)
);
```

### **FileQualityOverrides Table**
```sql
CREATE TABLE FileQualityOverrides (
    Id INTEGER PRIMARY KEY,
    FilePath TEXT NOT NULL UNIQUE,
    OverrideStrategy TEXT DEFAULT 'None',  -- "None", "Skip", "Single", "Multi", "Custom"
    CustomThreshold REAL,
    SkipQualityTesting BOOLEAN DEFAULT FALSE,
    CustomSettings TEXT,  -- JSON for custom overrides
    CreatedDate DATETIME DEFAULT CURRENT_TIMESTAMP,
    UpdatedDate DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### **QualityTestResults Table**
```sql
CREATE TABLE QualityTestResults (
    Id INTEGER PRIMARY KEY,
    TranscodeAttemptId INTEGER NOT NULL,
    VMAFScore REAL NOT NULL,
    ProfileId INTEGER NOT NULL,
    ProfileName TEXT NOT NULL,
    FileSize INTEGER NOT NULL,
    TestDuration REAL NOT NULL,
    PassesThreshold BOOLEAN NOT NULL,
    Rank INTEGER DEFAULT 0,
    ErrorMessage TEXT,
    DateTested DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (TranscodeAttemptId) REFERENCES TranscodeAttempts(Id),
    FOREIGN KEY (ProfileId) REFERENCES Profiles(Id)
);
```

## Implementation Phases

### **Phase 1: Core Architecture (Weeks 1-2)**
1. Create base models and interfaces
2. Implement QualityTestingStrategyService
3. Add database schema extensions
4. Create basic ViewModels

### **Phase 2: Strategy Implementation (Weeks 3-4)**
1. Implement SkipStrategy
2. Implement SingleStrategy
3. Implement MultiStrategy
4. Create QualityTestingOrchestratorService

### **Phase 3: Multi-Testing Support (Weeks 5-6)**
1. Create MultiQualityTestingService
2. Implement quality comparison logic
3. Add result selection algorithms
4. Create progress tracking

### **Phase 4: UI Integration (Weeks 7-8)**
1. Add quality testing settings to profile management
2. Create quality testing queue interface
3. Add result comparison views
4. Implement file-specific overrides

### **Phase 5: Testing and Optimization (Weeks 9-10)**
1. Comprehensive testing of all strategies
2. Performance optimization
3. Error handling improvements
4. Documentation and training

## Key Benefits

### **Flexibility**
- Multiple quality testing strategies
- Profile and file-specific configuration
- Easy addition of new strategies

### **Configurability**
- Granular control over quality testing
- Override capabilities for special cases
- Custom strategy support

### **Scalability**
- Modular architecture
- Easy to extend with new features
- Performance-optimized for large datasets

### **Maintainability**
- Clear separation of concerns
- MVVM architecture compliance
- Comprehensive logging and error handling

### **User Experience**
- Intuitive configuration interface
- Real-time progress tracking
- Comprehensive result comparison

## Migration Strategy

### **Backward Compatibility**
- Existing VMAF queue continues to work
- Gradual migration to new system
- Fallback to old system if needed

### **Data Migration**
- Migrate existing VMAF queue items
- Create default strategies for existing profiles
- Preserve historical quality testing data

### **Rollout Plan**
1. Deploy new architecture alongside existing system
2. Migrate profiles one by one to new system
3. Gradually phase out old VMAF queue system
4. Full migration to new architecture

This architecture provides a comprehensive, flexible, and maintainable solution for quality testing that can adapt to various user needs and scenarios while maintaining clean MVVM principles.
