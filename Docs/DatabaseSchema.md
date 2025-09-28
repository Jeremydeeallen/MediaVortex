# Database Schema Visual

## CRITICAL DATA FLOW RULE

**MediaFiles table is ONLY for display and profile assignment. NEVER use MediaFiles data for transcoding decisions.**

**ALL transcoding settings come exclusively from ProfileThresholds based on the assigned profile:**
- File → Profile Assignment → ProfileThresholds → Transcoding Settings
- Bitrates, quality, codec, target resolution = ProfileThresholds only
- MediaFiles resolution, codec, etc. = Display only

## Queries Used

### Table and Columns
```sql
SELECT 
    m.name || '.' || p.name AS TableColumn,
    p.type AS DataType
FROM sqlite_master m
CROSS JOIN pragma_table_info(m.name) p
WHERE m.type = 'table' 
    AND m.name NOT LIKE 'sqlite_%'
ORDER BY m.name, p.cid;
```

### Indexes
```sql
SELECT 
    m.name AS TableName,
    i.name AS IndexName,
    i."unique" AS IsUnique,
    i."origin" AS Origin,
    i."partial" AS IsPartial
FROM sqlite_master m
CROSS JOIN pragma_index_list(m.name) i
WHERE m.type = 'table' 
    AND m.name NOT LIKE 'sqlite_%'
ORDER BY m.name, i.seq;
```

### Index Columns
```sql
SELECT 
    m.name AS TableName,
    i.name AS IndexName,
    ic.name AS ColumnName,
    ic.seqno AS ColumnSequence
FROM sqlite_master m
CROSS JOIN pragma_index_list(m.name) i
CROSS JOIN pragma_index_info(i.name) ic
WHERE m.type = 'table' 
    AND m.name NOT LIKE 'sqlite_%'
ORDER BY m.name, i.seq, ic.seqno;
```

## Results

### Table and Columns

CodecFlags.Id	INTEGER
CodecFlags.CodecName	TEXT
CodecFlags.DisplayName	TEXT
CodecFlags.PresetType	TEXT
CodecFlags.PresetMin	INTEGER
CodecFlags.PresetMax	INTEGER
CodecFlags.PresetDefault	INTEGER
CodecFlags.PresetOptions	TEXT
CodecFlags.FilmGrainType	TEXT
CodecFlags.FilmGrainMin	INTEGER
CodecFlags.FilmGrainMax	INTEGER
CodecFlags.FilmGrainDefault	INTEGER
CodecFlags.TuneOptions	TEXT
CodecFlags.CreatedDate	DATETIME
CodecFlags.LastModified	DATETIME
CodecParameters.Id	INTEGER
CodecParameters.CodecFlagsId	INTEGER
CodecParameters.ParameterName	TEXT
CodecParameters.ParameterType	TEXT
CodecParameters.MinValue	REAL
CodecParameters.MaxValue	REAL
CodecParameters.DefaultValue	TEXT
CodecParameters.Description	TEXT
CodecParameters.FFmpegFlag	TEXT
CodecParameters.CreatedDate	DATETIME
CompliantFiles.Id	INTEGER
CompliantFiles.FilePath	TEXT
CompliantFiles.FileName	TEXT
CompliantFiles.Directory	TEXT
CompliantFiles.SizeBytes	INTEGER
CompliantFiles.SizeMB	REAL
CompliantFiles.Reason	TEXT
CompliantFiles.DateAdded	TIMESTAMP
CompliantFiles.LastModified	TIMESTAMP
CompressionLearningModels.Id	INTEGER
CompressionLearningModels.ModelName	TEXT
CompressionLearningModels.ModelVersion	TEXT
CompressionLearningModels.ModelType	TEXT
CompressionLearningModels.ModelData	TEXT
CompressionLearningModels.TrainingSamples	INTEGER
CompressionLearningModels.Accuracy	REAL
CompressionLearningModels.CreatedDate	TIMESTAMP
CompressionLearningModels.LastTrained	TIMESTAMP
CompressionLearningModels.IsActive	BOOLEAN
CompressionLearningSamples.Id	INTEGER
CompressionLearningSamples.FilePath	TEXT
CompressionLearningSamples.FileName	TEXT
CompressionLearningSamples.Directory	TEXT
CompressionLearningSamples.SizeBytes	INTEGER
CompressionLearningSamples.SizeMB	REAL
CompressionLearningSamples.Resolution	TEXT
CompressionLearningSamples.VideoCodec	TEXT
CompressionLearningSamples.AudioCodec	TEXT
CompressionLearningSamples.ContentType	TEXT
CompressionLearningSamples.CurrentBitrate	INTEGER
CompressionLearningSamples.Quality	INTEGER
CompressionLearningSamples.OriginalSizeBytes	INTEGER
CompressionLearningSamples.CompressedSizeBytes	INTEGER
CompressionLearningSamples.SizeReductionBytes	INTEGER
CompressionLearningSamples.SizeReductionPercent	REAL
CompressionLearningSamples.TranscodeDurationSeconds	REAL
CompressionLearningSamples.Success	BOOLEAN
CompressionLearningSamples.ErrorMessage	TEXT
CompressionLearningSamples.DateAdded	TIMESTAMP
CompressionLearningSamples.AnalysisFactors	TEXT
CompressionLearningStats.Id	INTEGER
CompressionLearningStats.ContentType	TEXT
CompressionLearningStats.Resolution	TEXT
CompressionLearningStats.VideoCodec	TEXT
CompressionLearningStats.Quality	INTEGER
CompressionLearningStats.SampleCount	INTEGER
CompressionLearningStats.AverageReductionPercent	REAL
CompressionLearningStats.MinReductionPercent	REAL
CompressionLearningStats.MaxReductionPercent	REAL
CompressionLearningStats.StandardDeviation	REAL
CompressionLearningStats.ConfidenceScore	REAL
CompressionLearningStats.LastUpdated	TIMESTAMP
Configuration.Key	TEXT
Configuration.Value	TEXT
Configuration.Description	TEXT
Configuration.UpdatedAt	DATETIME
Logs.Id	INTEGER
Logs.Timestamp	DATETIME
Logs.LogLevel	TEXT
Logs.FunctionName	TEXT
Logs.Message	TEXT
Logs.SourceFile	TEXT
Logs.SourceLine	INTEGER
Logs.SourceFunction	TEXT
Logs.ExceptionType	TEXT
Logs.ExceptionMessage	TEXT
Logs.StackTrace	TEXT
Logs.UserId	TEXT
Logs.SessionId	TEXT
Logs.RequestId	TEXT
Logs.Component	TEXT
Logs.Operation	TEXT
Logs.DurationMs	INTEGER
Logs.AdditionalData	TEXT
Logs.CreatedAt	DATETIME
MediaFiles.Id	INTEGER
MediaFiles.SeasonId	INTEGER
MediaFiles.FilePath	TEXT
MediaFiles.FileName	TEXT
MediaFiles.SizeMB	REAL
MediaFiles.VideoBitrateKbps	INTEGER
MediaFiles.AudioBitrateKbps	INTEGER
MediaFiles.Resolution	TEXT
MediaFiles.Codec	TEXT
MediaFiles.DurationMinutes	REAL
MediaFiles.FrameRate	REAL
MediaFiles.LastScannedDate	TIMESTAMP
MediaFiles.CompressionPotential	TEXT
MediaFiles.AssignedProfile	TEXT
MediaFiles.IsInterlaced	BIT
MediaFiles.ResolutionCategory	TEXT
MediaFiles.FileModificationTime	DATETIME
MediaFiles.KeepSource	BOOLEAN
PresetOptions.Id	INTEGER
PresetOptions.CodecFlagsId	INTEGER
PresetOptions.PresetValue	TEXT
PresetOptions.PresetName	TEXT
PresetOptions.Description	TEXT
PresetOptions.SortOrder	INTEGER
PresetOptions.CreatedDate	DATETIME
ProblemFiles.Id	INTEGER
ProblemFiles.FilePath	TEXT
ProblemFiles.FileName	TEXT
ProblemFiles.Directory	TEXT
ProblemFiles.SizeBytes	INTEGER
ProblemFiles.SizeMB	REAL
ProblemFiles.ErrorType	TEXT
ProblemFiles.ErrorMessage	TEXT
ProblemFiles.DateEncountered	TIMESTAMP
ProblemFiles.RetryCount	INTEGER
ProblemFiles.LastRetry	TIMESTAMP
ProfileThresholds.Id	INTEGER
ProfileThresholds.ProfileId	INTEGER
ProfileThresholds.Resolution	TEXT
ProfileThresholds.Under30MinMB	INTEGER
ProfileThresholds.Under65MinMB	INTEGER
ProfileThresholds.Over65MinMB	INTEGER
ProfileThresholds.VideoBitrateKbps	INTEGER
ProfileThresholds.AudioBitrateKbps	INTEGER
ProfileThresholds.FallbackVideoBitrateKbps	INTEGER
ProfileThresholds.FallbackAudioBitrateKbps	INTEGER
ProfileThresholds.TranscodeDownTo	TEXT
ProfileThresholds.Quality	INTEGER
ProfileThresholds.KeepSource	BOOLEAN
ProfileThresholds.ContainerType	TEXT
Profiles.Id	INTEGER
Profiles.ProfileName	TEXT
Profiles.Description	TEXT
Profiles.CreatedDate	TIMESTAMP
Profiles.LastModified	TIMESTAMP
Profiles.Codec	TEXT
Profiles.Preset	INTEGER
Profiles.FilmGrain	INTEGER
Profiles.YadifMode	INTEGER
Profiles.YadifParity	INTEGER
Profiles.YadifDeint	INTEGER
Profiles.CodecFlagsId	INTEGER
Profiles.TenBitEncoding	BOOLEAN
RootFolders.Id	INTEGER
RootFolders.RootFolder	TEXT
RootFolders.LastScannedDate	TIMESTAMP
RootFolders.TotalSizeGB	REAL
ScanJobs.Id	INTEGER
ScanJobs.JobId	TEXT
ScanJobs.RootFolderPath	TEXT
ScanJobs.Recursive	BOOLEAN
ScanJobs.Status	TEXT
ScanJobs.ProcessId	INTEGER
ScanJobs.StartTime	TIMESTAMP
ScanJobs.EndTime	TIMESTAMP
ScanJobs.Progress	REAL
ScanJobs.CurrentDirectory	TEXT
ScanJobs.TotalFiles	INTEGER
ScanJobs.ProcessedFiles	INTEGER
ScanJobs.SkippedFiles	INTEGER
ScanJobs.EncodingErrors	INTEGER
ScanJobs.NewFiles	INTEGER
ScanJobs.UpdatedFiles	INTEGER
ScanJobs.DeletedFiles	INTEGER
ScanJobs.ErrorMessage	TEXT
ScanJobs.LastUpdated	TIMESTAMP
ScanJobs.ScanType	TEXT
Seasons.Id	INTEGER
Seasons.RootFolderId	INTEGER
Seasons.SeasonName	TEXT
ServiceStatus.Id	INTEGER
ServiceStatus.ServiceName	TEXT
ServiceStatus.Status	TEXT
ServiceStatus.HealthStatus	TEXT
ServiceStatus.StartTime	TIMESTAMP
ServiceStatus.LastHealthCheck	TIMESTAMP
ServiceStatus.UptimeSeconds	INTEGER
ServiceStatus.MemoryUsage	REAL
ServiceStatus.CPUUsage	REAL
ServiceStatus.DatabaseConnection	BOOLEAN
ServiceStatus.DiskSpace	REAL
ServiceStatus.ErrorCount	INTEGER
ServiceStatus.MaxErrors	INTEGER
ServiceStatus.ActiveJobsCount	INTEGER
ServiceStatus.IsProcessing	BOOLEAN
ServiceStatus.LastErrorMessage	TEXT
ServiceStatus.ProcessId	INTEGER
ServiceStatus.Version	TEXT
ServiceStatus.ServiceType	TEXT
ServiceStatus.CreatedAt	TIMESTAMP
ServiceStatus.UpdatedAt	TIMESTAMP
SystemSettings.Id	INTEGER
SystemSettings.SettingKey	TEXT
SystemSettings.SettingValue	TEXT
SystemSettings.Description	TEXT
SystemSettings.DataType	TEXT
SystemSettings.LastModified	TIMESTAMP
TranscodeAttempts.Id	INTEGER
TranscodeAttempts.FilePath	TEXT
TranscodeAttempts.AttemptDate	TIMESTAMP
TranscodeAttempts.Quality	INTEGER
TranscodeAttempts.OldSizeBytes	INTEGER
TranscodeAttempts.NewSizeBytes	INTEGER
TranscodeAttempts.Success	BOOLEAN
TranscodeAttempts.SizeReductionBytes	INTEGER
TranscodeAttempts.SizeReductionPercent	REAL
TranscodeAttempts.ErrorMessage	TEXT
TranscodeAttempts.TranscodeDurationSeconds	REAL
TranscodeAttempts.FfpmpegCommand	TEXT
TranscodeAttempts.AudioBitrateKbps	INTEGER
TranscodeAttempts.VideoBitrateKbps	INTEGER
TranscodeAttempts.ProfileName	TEXT
TranscodeAttempts.VMAF	REAL
TranscodeFiles.Id	INTEGER
TranscodeFiles.FilePath	TEXT
TranscodeFiles.AllQualitiesFailed	BOOLEAN
TranscodeFiles.SuccessfullyTranscoded	BOOLEAN
TranscodeFiles.FirstAttemptDate	TIMESTAMP
TranscodeFiles.LastAttemptDate	TIMESTAMP
TranscodeFiles.SuccessDate	TIMESTAMP
TranscodeFiles.FinalQuality	INTEGER
TranscodeFiles.FinalSizeBytes	INTEGER
TranscodeFiles.TotalAttempts	INTEGER
TranscodeFiles.OriginalFilePath	TEXT
TranscodeFiles.FinalFilePath	TEXT
TranscodeProgress.Id	INTEGER
TranscodeProgress.TranscodeAttemptId	INTEGER
TranscodeProgress.PassNumber	INTEGER
TranscodeProgress.PassType	TEXT
TranscodeProgress.CurrentPhase	TEXT
TranscodeProgress.ProgressPercent	REAL
TranscodeProgress.CurrentFrame	INTEGER
TranscodeProgress.TotalFrames	INTEGER
TranscodeProgress.CurrentFPS	REAL
TranscodeProgress.AverageFPS	REAL
TranscodeProgress.CurrentBitrate	TEXT
TranscodeProgress.CurrentTime	TEXT
TranscodeProgress.ETA	TEXT
TranscodeProgress.CurrentSpeed	TEXT
TranscodeProgress.PassDuration	REAL
TranscodeProgress.LastProgressUpdate	TIMESTAMP
TranscodeProgress.HandBrakeOutput	TEXT
TranscodeProgress.Status	TEXT
TranscodeQueue.Id	INTEGER
TranscodeQueue.FilePath	TEXT
TranscodeQueue.FileName	TEXT
TranscodeQueue.Directory	TEXT
TranscodeQueue.SizeBytes	INTEGER
TranscodeQueue.SizeMB	REAL
TranscodeQueue.Priority	INTEGER
TranscodeQueue.Status	TEXT
TranscodeQueue.DateAdded	TIMESTAMP
TranscodeQueue.DateStarted	TIMESTAMP
VMAFProgress.Id	INTEGER
VMAFProgress.VMAFQueueId	INTEGER
VMAFProgress.TranscodeAttemptId	INTEGER
VMAFProgress.Status	TEXT
VMAFProgress.ProgressPercentage	INTEGER
VMAFProgress.CurrentStep	TEXT
VMAFProgress.StartTime	DATETIME
VMAFProgress.EndTime	DATETIME
VMAFProgress.ErrorMessage	TEXT
VMAFProgress.CreatedAt	DATETIME
VMAFProgress.UpdatedAt	DATETIME
VMAFProgress.ETA	TEXT
VMAFQueue.Id	INTEGER
VMAFQueue.TranscodeAttemptId	INTEGER
VMAFQueue.OriginalFilePath	TEXT
VMAFQueue.TranscodedFilePath	TEXT
VMAFQueue.FileName	TEXT
VMAFQueue.Status	TEXT
VMAFQueue.Priority	INTEGER
VMAFQueue.DateAdded	DATETIME
VMAFQueue.DateStarted	DATETIME
VMAFQueue.DateCompleted	DATETIME
VMAFQueue.VMAFScore	REAL
VMAFQueue.QualityThreshold	REAL
VMAFQueue.ErrorMessage	TEXT
VMAFQueue.RetryCount	INTEGER
VMAFQueue.MaxRetries	INTEGER

### Indexes

CodecFlags	sqlite_autoindex_CodecFlags_1	1	u	0
CodecParameters	sqlite_autoindex_CodecParameters_1	1	u	0
CompliantFiles	idx_CompliantFiles_FileName	0	c	0
CompliantFiles	idx_CompliantFiles_Directory	0	c	0
CompliantFiles	idx_CompliantFiles_Reason	0	c	0
CompliantFiles	idx_CompliantFiles_SizeBytes	0	c	0
CompliantFiles	idx_CompliantFiles_FilePath	0	c	0
CompliantFiles	sqlite_autoindex_CompliantFiles_1	1	u	0
CompressionLearningModels	idx_CompressionLearningModels_IsActive	0	c	0
CompressionLearningModels	idx_CompressionLearningModels_ModelName	0	c	0
CompressionLearningModels	sqlite_autoindex_CompressionLearningModels_1	1	u	0
CompressionLearningSamples	idx_CompressionLearningSamples_DateAdded	0	c	0
CompressionLearningSamples	idx_CompressionLearningSamples_Quality	0	c	0
CompressionLearningSamples	idx_CompressionLearningSamples_ContentType	0	c	0
CompressionLearningSamples	idx_CompressionLearningSamples_FilePath	0	c	0
CompressionLearningStats	idx_CompressionLearningStats_Quality	0	c	0
CompressionLearningStats	idx_CompressionLearningStats_ContentType	0	c	0
Configuration	sqlite_autoindex_Configuration_1	1	pk	0
Logs	IdxLogsTimestampLevel	0	c	0
Logs	IdxLogsUserSession	0	c	0
Logs	IdxLogsOperation	0	c	0
Logs	IdxLogsComponent	0	c	0
Logs	IdxLogsLogger	0	c	0
Logs	IdxLogsLevel	0	c	0
Logs	IdxLogsTimestamp	0	c	0
PresetOptions	sqlite_autoindex_PresetOptions_1	1	u	0
ProblemFiles	idx_ProblemFiles_Directory	0	c	0
ProblemFiles	idx_ProblemFiles_ErrorType	0	c	0
ProblemFiles	idx_ProblemFiles_FilePath	0	c	0
ProfileThresholds	sqlite_autoindex_ProfileThresholds_1	1	u	0
Profiles	sqlite_autoindex_Profiles_1	1	u	0
RootFolders	sqlite_autoindex_RootFolders_1	1	u	0
ScanJobs	sqlite_autoindex_ScanJobs_1	1	u	0
ServiceStatus	sqlite_autoindex_ServiceStatus_1	1	u	0
SystemSettings	idx_SystemSettings_SettingKey	0	c	0
SystemSettings	sqlite_autoindex_SystemSettings_1	1	u	0
TranscodeAttempts	idx_TranscodeAttempts_FilePath	0	c	0
TranscodeAttempts	idx_TranscodeAttempts_AttemptDate	0	c	0
TranscodeAttempts	idx_TranscodeAttempts_Success	0	c	0
TranscodeFiles	idx_TranscodeFiles_SuccessfullyTranscoded	0	c	0
TranscodeFiles	idx_TranscodeFiles_FilePath	0	c	0
TranscodeFiles	sqlite_autoindex_TranscodeFiles_1	1	u	0
TranscodeProgress	idx_TranscodeProgress_AttemptId	0	c	0
TranscodeQueue	idx_TranscodeQueue_FileName	0	c	0
TranscodeQueue	idx_TranscodeQueue_Directory	0	c	0
TranscodeQueue	idx_TranscodeQueue_Priority	0	c	0
TranscodeQueue	idx_TranscodeQueue_Status	0	c	0
TranscodeQueue	idx_TranscodeQueue_FilePath	0	c	0
TranscodeQueue	sqlite_autoindex_TranscodeQueue_1	1	u	0
VMAFProgress	idx_VMAFProgress_StartTime	0	c	0
VMAFProgress	idx_VMAFProgress_Status	0	c	0
VMAFProgress	idx_VMAFProgress_TranscodeAttemptId	0	c	0
VMAFProgress	idx_VMAFProgress_VMAFQueueId	0	c	0

### Index Columns

CodecFlags	sqlite_autoindex_CodecFlags_1	CodecName	0
CodecParameters	sqlite_autoindex_CodecParameters_1	CodecFlagsId	0
CodecParameters	sqlite_autoindex_CodecParameters_1	ParameterName	1
CompliantFiles	idx_CompliantFiles_FileName	FileName	0
CompliantFiles	idx_CompliantFiles_Directory	Directory	0
CompliantFiles	idx_CompliantFiles_Reason	Reason	0
CompliantFiles	idx_CompliantFiles_SizeBytes	SizeBytes	0
CompliantFiles	idx_CompliantFiles_FilePath	FilePath	0
CompliantFiles	sqlite_autoindex_CompliantFiles_1	FilePath	0
CompressionLearningModels	idx_CompressionLearningModels_IsActive	IsActive	0
CompressionLearningModels	idx_CompressionLearningModels_ModelName	ModelName	0
CompressionLearningModels	sqlite_autoindex_CompressionLearningModels_1	ModelName	0
CompressionLearningSamples	idx_CompressionLearningSamples_DateAdded	DateAdded	0
CompressionLearningSamples	idx_CompressionLearningSamples_Quality	Quality	0
CompressionLearningSamples	idx_CompressionLearningSamples_ContentType	ContentType	0
CompressionLearningSamples	idx_CompressionLearningSamples_FilePath	FilePath	0
CompressionLearningStats	idx_CompressionLearningStats_Quality	Quality	0
CompressionLearningStats	idx_CompressionLearningStats_ContentType	ContentType	0
Configuration	sqlite_autoindex_Configuration_1	Key	0
Logs	IdxLogsTimestampLevel	Timestamp	0
Logs	IdxLogsTimestampLevel	LogLevel	1
Logs	IdxLogsUserSession	UserId	0
Logs	IdxLogsUserSession	SessionId	1
Logs	IdxLogsOperation	Operation	0
Logs	IdxLogsComponent	Component	0
Logs	IdxLogsLogger	FunctionName	0
Logs	IdxLogsLevel	LogLevel	0
Logs	IdxLogsTimestamp	Timestamp	0
PresetOptions	sqlite_autoindex_PresetOptions_1	CodecFlagsId	0
PresetOptions	sqlite_autoindex_PresetOptions_1	PresetValue	1
ProblemFiles	idx_ProblemFiles_Directory	Directory	0
ProblemFiles	idx_ProblemFiles_ErrorType	ErrorType	0
ProblemFiles	idx_ProblemFiles_FilePath	FilePath	0
ProfileThresholds	sqlite_autoindex_ProfileThresholds_1	ProfileId	0
ProfileThresholds	sqlite_autoindex_ProfileThresholds_1	Resolution	1
Profiles	sqlite_autoindex_Profiles_1	ProfileName	0
RootFolders	sqlite_autoindex_RootFolders_1	RootFolder	0
ScanJobs	sqlite_autoindex_ScanJobs_1	JobId	0
ServiceStatus	sqlite_autoindex_ServiceStatus_1	ServiceName	0
SystemSettings	idx_SystemSettings_SettingKey	SettingKey	0
SystemSettings	sqlite_autoindex_SystemSettings_1	SettingKey	0
TranscodeAttempts	idx_TranscodeAttempts_FilePath	FilePath	0
TranscodeAttempts	idx_TranscodeAttempts_AttemptDate	AttemptDate	0
TranscodeAttempts	idx_TranscodeAttempts_Success	Success	0
TranscodeFiles	idx_TranscodeFiles_SuccessfullyTranscoded	SuccessfullyTranscoded	0
TranscodeFiles	idx_TranscodeFiles_FilePath	FilePath	0
TranscodeFiles	sqlite_autoindex_TranscodeFiles_1	FilePath	0
TranscodeProgress	idx_TranscodeProgress_AttemptId	TranscodeAttemptId	0
TranscodeQueue	idx_TranscodeQueue_FileName	FileName	0
TranscodeQueue	idx_TranscodeQueue_Directory	Directory	0
TranscodeQueue	idx_TranscodeQueue_Priority	Priority	0
TranscodeQueue	idx_TranscodeQueue_Status	Status	0
TranscodeQueue	idx_TranscodeQueue_FilePath	FilePath	0
TranscodeQueue	sqlite_autoindex_TranscodeQueue_1	FilePath	0
VMAFProgress	idx_VMAFProgress_StartTime	StartTime	0
VMAFProgress	idx_VMAFProgress_Status	Status	0
VMAFProgress	idx_VMAFProgress_TranscodeAttemptId	TranscodeAttemptId	0
VMAFProgress	idx_VMAFProgress_VMAFQueueId	VMAFQueueId	0
