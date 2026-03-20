# Database Schema Visual

## CRITICAL DATA FLOW RULE

**MediaFiles table is ONLY for display and profile assignment. NEVER use MediaFiles data for transcoding decisions.**

**ALL transcoding settings come exclusively from ProfileThresholds based on the assigned profile:**
- File -> Profile Assignment -> ProfileThresholds -> Transcoding Settings
- Bitrates, quality, codec, target resolution = ProfileThresholds only
- MediaFiles resolution, codec, etc. = Display only

## Table and Columns

| Table.Column | Data Type | Nullable | Default |
|---|---|---|---|
| activejobs.id | bigint | NO | nextval('"ActiveJobs_Id_seq"'::regclass) |
| activejobs.servicename | text | NO |  |
| activejobs.jobtype | text | NO |  |
| activejobs.queueid | bigint | NO |  |
| activejobs.processid | bigint | NO |  |
| activejobs.threadid | bigint | YES |  |
| activejobs.startedat | timestamp without time zone | YES | CURRENT_TIMESTAMP |
| activejobs.status | text | YES | 'Running'::text |
| activejobs.createdat | timestamp without time zone | YES | CURRENT_TIMESTAMP |
| activejobs.updatedat | timestamp without time zone | YES | CURRENT_TIMESTAMP |
| codecflags.id | bigint | NO | nextval('"CodecFlags_Id_seq"'::regclass) |
| codecflags.codecname | text | NO |  |
| codecflags.displayname | text | NO |  |
| codecflags.presettype | text | NO |  |
| codecflags.presetmin | bigint | YES |  |
| codecflags.presetmax | bigint | YES |  |
| codecflags.presetdefault | bigint | YES |  |
| codecflags.presetoptions | text | YES |  |
| codecflags.filmgraintype | text | NO |  |
| codecflags.filmgrainmin | bigint | YES |  |
| codecflags.filmgrainmax | bigint | YES |  |
| codecflags.filmgraindefault | bigint | YES |  |
| codecflags.tuneoptions | text | YES |  |
| codecflags.createddate | timestamp without time zone | YES | CURRENT_TIMESTAMP |
| codecflags.lastmodified | timestamp without time zone | YES | CURRENT_TIMESTAMP |
| codecparameters.id | bigint | NO | nextval('"CodecParameters_Id_seq"'::regclass) |
| codecparameters.codecflagsid | bigint | NO |  |
| codecparameters.parametername | text | NO |  |
| codecparameters.parametertype | text | NO |  |
| codecparameters.minvalue | double precision | YES |  |
| codecparameters.maxvalue | double precision | YES |  |
| codecparameters.defaultvalue | text | YES |  |
| codecparameters.description | text | YES |  |
| codecparameters.ffmpegflag | text | NO |  |
| codecparameters.createddate | timestamp without time zone | YES | CURRENT_TIMESTAMP |
| compliantfiles.id | bigint | NO | nextval('"CompliantFiles_Id_seq"'::regclass) |
| compliantfiles.filepath | text | NO |  |
| compliantfiles.filename | text | NO |  |
| compliantfiles.directory | text | NO |  |
| compliantfiles.sizebytes | bigint | NO |  |
| compliantfiles.sizemb | double precision | NO |  |
| compliantfiles.reason | text | NO |  |
| compliantfiles.dateadded | timestamp without time zone | YES | CURRENT_TIMESTAMP |
| compliantfiles.lastmodified | timestamp without time zone | YES | CURRENT_TIMESTAMP |
| compressionlearningmodels.id | bigint | NO | nextval('"CompressionLearningModels_Id_seq"'::regclass) |
| compressionlearningmodels.modelname | text | NO |  |
| compressionlearningmodels.modelversion | text | NO |  |
| compressionlearningmodels.modeltype | text | NO |  |
| compressionlearningmodels.modeldata | text | NO |  |
| compressionlearningmodels.trainingsamples | bigint | NO |  |
| compressionlearningmodels.accuracy | double precision | YES |  |
| compressionlearningmodels.createddate | timestamp without time zone | YES | CURRENT_TIMESTAMP |
| compressionlearningmodels.lasttrained | timestamp without time zone | YES |  |
| compressionlearningmodels.isactive | boolean | YES | true |
| compressionlearningsamples.id | bigint | NO | nextval('"CompressionLearningSamples_Id_seq"'::regclass) |
| compressionlearningsamples.filepath | text | NO |  |
| compressionlearningsamples.filename | text | NO |  |
| compressionlearningsamples.directory | text | NO |  |
| compressionlearningsamples.sizebytes | bigint | NO |  |
| compressionlearningsamples.sizemb | double precision | NO |  |
| compressionlearningsamples.resolution | text | YES |  |
| compressionlearningsamples.videocodec | text | YES |  |
| compressionlearningsamples.audiocodec | text | YES |  |
| compressionlearningsamples.contenttype | text | YES |  |
| compressionlearningsamples.currentbitrate | bigint | YES |  |
| compressionlearningsamples.quality | bigint | NO |  |
| compressionlearningsamples.originalsizebytes | bigint | NO |  |
| compressionlearningsamples.compressedsizebytes | bigint | NO |  |
| compressionlearningsamples.sizereductionbytes | bigint | NO |  |
| compressionlearningsamples.sizereductionpercent | double precision | NO |  |
| compressionlearningsamples.transcodedurationseconds | double precision | YES |  |
| compressionlearningsamples.success | boolean | NO |  |
| compressionlearningsamples.errormessage | text | YES |  |
| compressionlearningsamples.dateadded | timestamp without time zone | YES | CURRENT_TIMESTAMP |
| compressionlearningsamples.analysisfactors | text | YES |  |
| compressionlearningstats.id | bigint | NO | nextval('"CompressionLearningStats_Id_seq"'::regclass) |
| compressionlearningstats.contenttype | text | YES |  |
| compressionlearningstats.resolution | text | YES |  |
| compressionlearningstats.videocodec | text | YES |  |
| compressionlearningstats.quality | bigint | YES |  |
| compressionlearningstats.samplecount | bigint | NO |  |
| compressionlearningstats.averagereductionpercent | double precision | NO |  |
| compressionlearningstats.minreductionpercent | double precision | NO |  |
| compressionlearningstats.maxreductionpercent | double precision | NO |  |
| compressionlearningstats.standarddeviation | double precision | YES |  |
| compressionlearningstats.confidencescore | double precision | YES |  |
| compressionlearningstats.lastupdated | timestamp without time zone | YES | CURRENT_TIMESTAMP |
| configuration.key | text | NO |  |
| configuration.value | text | NO |  |
| configuration.description | text | YES |  |
| configuration.updatedat | timestamp without time zone | YES | CURRENT_TIMESTAMP |
| jellyfinoperations.logfilename | text | NO |  |
| jellyfinoperations.operationtype | text | NO |  |
| jellyfinoperations.filepath | text | YES |  |
| jellyfinoperations.filename | text | YES |  |
| jellyfinoperations.videocodec | text | YES |  |
| jellyfinoperations.audiocodec | text | YES |  |
| jellyfinoperations.container | text | YES |  |
| jellyfinoperations.resolution | text | YES |  |
| jellyfinoperations.reason | text | YES |  |
| jellyfinoperations.logdate | text | YES |  |
| jellyfinoperations.importedat | timestamp without time zone | YES | CURRENT_TIMESTAMP |
| jellyfinoperations.subtitlecodecs | text | YES |  |
| jellyfinoperations.transcodeactions | text | YES |  |
| jellyfinoperations.destresolution | text | YES |  |
| jellyfinoperations.destprofile | text | YES |  |
| jellyfinoperations.destlevel | text | YES |  |
| jellyfinoperations.destpixelformat | text | YES |  |
| jellyfinoperations.destformat | text | YES |  |
| logs.id | bigint | NO | nextval('"Logs_Id_seq"'::regclass) |
| logs.timestamp | timestamp without time zone | YES | CURRENT_TIMESTAMP |
| logs.loglevel | text | NO |  |
| logs.functionname | text | NO |  |
| logs.message | text | NO |  |
| logs.sourcefile | text | YES |  |
| logs.sourceline | bigint | YES |  |
| logs.sourcefunction | text | YES |  |
| logs.exceptiontype | text | YES |  |
| logs.exceptionmessage | text | YES |  |
| logs.stacktrace | text | YES |  |
| logs.userid | text | YES |  |
| logs.sessionid | text | YES |  |
| logs.requestid | text | YES |  |
| logs.component | text | YES |  |
| logs.operation | text | YES |  |
| logs.durationms | bigint | YES |  |
| logs.additionaldata | text | YES |  |
| logs.createdat | timestamp without time zone | YES | CURRENT_TIMESTAMP |
| mediafiles.id | bigint | NO | nextval('"MediaFiles_Id_seq"'::regclass) |
| mediafiles.seasonid | bigint | YES |  |
| mediafiles.filepath | text | NO |  |
| mediafiles.filename | text | YES |  |
| mediafiles.sizemb | double precision | YES |  |
| mediafiles.videobitratekbps | bigint | YES |  |
| mediafiles.audiobitratekbps | bigint | YES |  |
| mediafiles.resolution | text | YES |  |
| mediafiles.codec | text | YES |  |
| mediafiles.durationminutes | double precision | YES |  |
| mediafiles.framerate | double precision | YES |  |
| mediafiles.lastscanneddate | timestamp without time zone | YES |  |
| mediafiles.compressionpotential | text | YES |  |
| mediafiles.assignedprofile | text | YES |  |
| mediafiles.isinterlaced | text | YES | 0 |
| mediafiles.resolutioncategory | text | YES |  |
| mediafiles.filemodificationtime | timestamp without time zone | YES |  |
| mediafiles.keepsource | boolean | YES | false |
| mediafiles.totalframes | bigint | YES |  |
| mediafiles.codecprofile | text | YES |  |
| mediafiles.colorrange | text | YES |  |
| mediafiles.fieldorder | text | YES |  |
| mediafiles.hasbframes | bigint | YES |  |
| mediafiles.refframes | bigint | YES |  |
| mediafiles.pixelformat | text | YES |  |
| mediafiles.level | bigint | YES |  |
| mediafiles.audiochannels | bigint | YES |  |
| mediafiles.audiosamplerate | bigint | YES |  |
| mediafiles.audiosampleformat | text | YES |  |
| mediafiles.audiochannellayout | text | YES |  |
| mediafiles.containerformat | text | YES |  |
| mediafiles.overallbitrate | bigint | YES |  |
| mediafiles.transcodedbymediavortex | boolean | YES | false |
| mediafiles.lastmodifieddate | timestamp without time zone | YES |  |
| mediafiles.filesize | bigint | YES |  |
| mediafiles.audiocodec | text | YES |  |
| mediafiles.subtitleformats | text | YES |  |
| mediafilesarchive.id | bigint | YES |  |
| mediafilesarchive.seasonid | bigint | YES |  |
| mediafilesarchive.filepath | text | NO |  |
| mediafilesarchive.filename | text | YES |  |
| mediafilesarchive.sizemb | double precision | YES |  |
| mediafilesarchive.videobitratekbps | bigint | YES |  |
| mediafilesarchive.audiobitratekbps | bigint | YES |  |
| mediafilesarchive.resolution | text | YES |  |
| mediafilesarchive.codec | text | YES |  |
| mediafilesarchive.durationminutes | double precision | YES |  |
| mediafilesarchive.framerate | double precision | YES |  |
| mediafilesarchive.lastscanneddate | timestamp without time zone | YES |  |
| mediafilesarchive.compressionpotential | text | YES |  |
| mediafilesarchive.assignedprofile | text | YES |  |
| mediafilesarchive.isinterlaced | text | YES |  |
| mediafilesarchive.resolutioncategory | text | YES |  |
| mediafilesarchive.filemodificationtime | timestamp without time zone | YES |  |
| mediafilesarchive.keepsource | boolean | YES |  |
| mediafilesarchive.totalframes | bigint | YES |  |
| mediafilesarchive.codecprofile | text | YES |  |
| mediafilesarchive.colorrange | text | YES |  |
| mediafilesarchive.fieldorder | text | YES |  |
| mediafilesarchive.hasbframes | bigint | YES |  |
| mediafilesarchive.refframes | bigint | YES |  |
| mediafilesarchive.pixelformat | text | YES |  |
| mediafilesarchive.level | bigint | YES |  |
| mediafilesarchive.audiochannels | bigint | YES |  |
| mediafilesarchive.audiosamplerate | bigint | YES |  |
| mediafilesarchive.audiosampleformat | text | YES |  |
| mediafilesarchive.audiochannellayout | text | YES |  |
| mediafilesarchive.containerformat | text | YES |  |
| mediafilesarchive.overallbitrate | bigint | YES |  |
| mediafilesarchive.transcodedbymediavortex | boolean | YES |  |
| mediafilesarchive.archivedate | timestamp without time zone | YES | CURRENT_TIMESTAMP |
| mediafilesarchive.transcodeattemptid | bigint | YES |  |
| presetoptions.id | bigint | NO | nextval('"PresetOptions_Id_seq"'::regclass) |
| presetoptions.codecflagsid | bigint | NO |  |
| presetoptions.presetvalue | text | NO |  |
| presetoptions.presetname | text | NO |  |
| presetoptions.description | text | YES |  |
| presetoptions.sortorder | bigint | YES | 0 |
| presetoptions.createddate | timestamp without time zone | YES | CURRENT_TIMESTAMP |
| problemfiles.id | bigint | NO | nextval('"ProblemFiles_Id_seq"'::regclass) |
| problemfiles.filepath | text | NO |  |
| problemfiles.filename | text | NO |  |
| problemfiles.directory | text | NO |  |
| problemfiles.sizebytes | bigint | NO |  |
| problemfiles.sizemb | double precision | NO |  |
| problemfiles.errortype | text | NO |  |
| problemfiles.errormessage | text | YES |  |
| problemfiles.dateencountered | timestamp without time zone | YES | CURRENT_TIMESTAMP |
| problemfiles.retrycount | bigint | YES | 0 |
| problemfiles.lastretry | timestamp without time zone | YES |  |
| profiles.id | bigint | NO | nextval('"Profiles_Id_seq"'::regclass) |
| profiles.profilename | text | NO |  |
| profiles.description | text | YES |  |
| profiles.createddate | timestamp without time zone | YES | CURRENT_TIMESTAMP |
| profiles.lastmodified | timestamp without time zone | YES | CURRENT_TIMESTAMP |
| profiles.codec | text | YES | 'libsvtav1'::text |
| profiles.preset | bigint | YES | 6 |
| profiles.filmgrain | bigint | YES | 10 |
| profiles.yadifmode | bigint | YES | 1 |
| profiles.yadifparity | bigint | YES | 1 |
| profiles.yadifdeint | bigint | YES | 1 |
| profiles.codecflagsid | bigint | YES |  |
| profiles.usenvidiahardware | bigint | YES | 0 |
| profilethresholds.id | bigint | NO | nextval('"ProfileThresholds_Id_seq"'::regclass) |
| profilethresholds.profileid | bigint | NO |  |
| profilethresholds.resolution | text | NO |  |
| profilethresholds.under30minmb | bigint | NO | 0 |
| profilethresholds.under65minmb | bigint | NO | 0 |
| profilethresholds.over65minmb | bigint | NO | 0 |
| profilethresholds.videobitratekbps | bigint | NO | 0 |
| profilethresholds.audiobitratekbps | bigint | NO | 0 |
| profilethresholds.fallbackvideobitratekbps | bigint | NO | 0 |
| profilethresholds.fallbackaudiobitratekbps | bigint | NO | 0 |
| profilethresholds.transcodedownto | text | NO | ''::text |
| profilethresholds.quality | bigint | YES |  |
| profilethresholds.keepsource | boolean | NO | false |
| profilethresholds.containertype | text | NO | 'mp4'::text |
| qualitytestingqueue.id | bigint | NO | nextval('"QualityTestingQueue_Id_seq"'::regclass) |
| qualitytestingqueue.transcodeattemptid | bigint | YES |  |
| qualitytestingqueue.originalfilepath | text | YES |  |
| qualitytestingqueue.transcodedfilepath | text | YES |  |
| qualitytestingqueue.localsourcepath | text | YES |  |
| qualitytestingqueue.dateadded | timestamp without time zone | YES | CURRENT_TIMESTAMP |
| qualitytestingqueue.datestarted | timestamp without time zone | YES |  |
| qualitytestingqueue.datecompleted | timestamp without time zone | YES |  |
| qualitytestingqueuebackup.id | bigint | YES |  |
| qualitytestingqueuebackup.transcodeattemptid | bigint | YES |  |
| qualitytestingqueuebackup.originalfilepath | text | YES |  |
| qualitytestingqueuebackup.transcodedfilepath | text | YES |  |
| qualitytestingqueuebackup.filename | text | YES |  |
| qualitytestingqueuebackup.status | text | YES |  |
| qualitytestingqueuebackup.priority | bigint | YES |  |
| qualitytestingqueuebackup.dateadded | text | YES |  |
| qualitytestingqueuebackup.datestarted | text | YES |  |
| qualitytestingqueuebackup.datecompleted | text | YES |  |
| qualitytestingqueuebackup.errormessage | text | YES |  |
| qualitytestingqueuebackup.retrycount | bigint | YES |  |
| qualitytestingqueuebackup.maxretries | bigint | YES |  |
| qualitytestingqueuebackup.strategytype | text | YES |  |
| qualitytestingqueuebackup.strategyid | bigint | YES |  |
| qualitytestingqueuebackup.alternativeprofileids | text | YES |  |
| qualitytestingqueuebackup.customsettings | text | YES |  |
| qualitytestingqueuebackup.vmafscore | double precision | YES |  |
| qualitytestingqueuebackup.createddate | text | YES |  |
| qualitytestingqueuebackup.completeddate | text | YES |  |
| qualitytestingqueuetest.id | bigint | YES |  |
| qualitytestingqueuetest.transcodeattemptid | bigint | YES |  |
| qualitytestingqueuetest.originalfilepath | text | YES |  |
| qualitytestingqueuetest.transcodedfilepath | text | YES |  |
| qualitytestingqueuetest.filename | text | YES |  |
| qualitytestingqueuetest.status | text | YES |  |
| qualitytestingqueuetest.priority | bigint | YES |  |
| qualitytestingqueuetest.dateadded | text | YES |  |
| qualitytestingqueuetest.datestarted | text | YES |  |
| qualitytestingqueuetest.datecompleted | text | YES |  |
| qualitytestingqueuetest.errormessage | text | YES |  |
| qualitytestingqueuetest.retrycount | bigint | YES |  |
| qualitytestingqueuetest.maxretries | bigint | YES |  |
| qualitytestingqueuetest.strategytype | text | YES |  |
| qualitytestingqueuetest.strategyid | bigint | YES |  |
| qualitytestingqueuetest.alternativeprofileids | text | YES |  |
| qualitytestingqueuetest.customsettings | text | YES |  |
| qualitytestingqueuetest.vmafscore | double precision | YES |  |
| qualitytestingqueuetest.createddate | text | YES |  |
| qualitytestingqueuetest.completeddate | text | YES |  |
| qualitytestingqueuetest.localsourcepath | text | YES |  |
| qualitytestingstrategies.id | bigint | NO | nextval('"QualityTestingStrategies_Id_seq"'::regclass) |
| qualitytestingstrategies.profileid | bigint | NO |  |
| qualitytestingstrategies.strategytype | text | NO |  |
| qualitytestingstrategies.vmafthreshold | double precision | YES | 90.0 |
| qualitytestingstrategies.maxattempts | bigint | YES | 3 |
| qualitytestingstrategies.alternativeprofileids | text | YES |  |
| qualitytestingstrategies.customsettings | text | YES |  |
| qualitytestingstrategies.isenabled | boolean | YES | false |
| qualitytestingstrategies.createddate | timestamp without time zone | YES | CURRENT_TIMESTAMP |
| qualitytestingstrategies.updateddate | timestamp without time zone | YES | CURRENT_TIMESTAMP |
| qualitytestprogress.id | bigint | NO | nextval('"QualityTestProgress_Id_seq"'::regclass) |
| qualitytestprogress.transcodeattemptid | bigint | NO |  |
| qualitytestprogress.status | text | NO |  |
| qualitytestprogress.progresspercentage | bigint | NO |  |
| qualitytestprogress.currentstep | text | YES |  |
| qualitytestprogress.currentframe | bigint | YES |  |
| qualitytestprogress.currenttime | text | YES |  |
| qualitytestprogress.processingspeed | text | YES |  |
| qualitytestprogress.eta | text | YES |  |
| qualitytestprogress.starttime | timestamp without time zone | NO |  |
| qualitytestprogress.updatedat | timestamp without time zone | NO |  |
| qualitytestprogress.createdat | timestamp without time zone | YES | CURRENT_TIMESTAMP |
| qualitytestresults.id | bigint | NO | nextval('"QualityTestResults_Id_seq"'::regclass) |
| qualitytestresults.transcodeattemptid | bigint | NO |  |
| qualitytestresults.testduration | double precision | YES |  |
| qualitytestresults.passesthreshold | boolean | YES |  |
| qualitytestresults.rank | bigint | YES | 0 |
| qualitytestresults.errormessage | text | YES |  |
| qualitytestresults.datetested | timestamp without time zone | YES | CURRENT_TIMESTAMP |
| qualitytestresults.ffmpegcommand | text | YES |  |
| qualitytestresults.status | text | YES | 'Running'::text |
| qualitytestresults.vmafscore | double precision | YES |  |
| rootfolders.id | bigint | NO | nextval('"RootFolders_Id_seq"'::regclass) |
| rootfolders.rootfolder | text | NO |  |
| rootfolders.lastscanneddate | timestamp without time zone | YES |  |
| rootfolders.totalsizegb | double precision | YES |  |
| scanjobs.id | bigint | NO | nextval('"ScanJobs_Id_seq"'::regclass) |
| scanjobs.jobid | text | NO |  |
| scanjobs.rootfolderpath | text | NO |  |
| scanjobs.recursive | boolean | NO | true |
| scanjobs.status | text | NO | 'Pending'::text |
| scanjobs.processid | bigint | YES |  |
| scanjobs.starttime | timestamp without time zone | YES |  |
| scanjobs.endtime | timestamp without time zone | YES |  |
| scanjobs.progress | double precision | YES | 0.0 |
| scanjobs.currentdirectory | text | YES |  |
| scanjobs.totalfiles | bigint | YES | 0 |
| scanjobs.processedfiles | bigint | YES | 0 |
| scanjobs.skippedfiles | bigint | YES | 0 |
| scanjobs.encodingerrors | bigint | YES | 0 |
| scanjobs.newfiles | bigint | YES | 0 |
| scanjobs.updatedfiles | bigint | YES | 0 |
| scanjobs.deletedfiles | bigint | YES | 0 |
| scanjobs.errormessage | text | YES |  |
| scanjobs.lastupdated | timestamp without time zone | YES | CURRENT_TIMESTAMP |
| scanjobs.scantype | text | YES | 'File'::text |
| seasons.id | bigint | NO | nextval('"Seasons_Id_seq"'::regclass) |
| seasons.rootfolderid | bigint | YES |  |
| seasons.seasonname | text | YES |  |
| servicecommands.id | bigint | NO | nextval('"ServiceCommands_Id_seq"'::regclass) |
| servicecommands.commandtype | text | NO |  |
| servicecommands.sourceservice | text | NO |  |
| servicecommands.targetservice | text | NO |  |
| servicecommands.parameters | text | YES |  |
| servicecommands.status | text | NO | 'PENDING'::text |
| servicecommands.createdat | timestamp without time zone | YES | CURRENT_TIMESTAMP |
| servicecommands.processedat | timestamp without time zone | YES |  |
| servicecommands.result | text | YES |  |
| servicecommands.errormessage | text | YES |  |
| servicecommands.retrycount | bigint | YES | 0 |
| servicecommands.maxretries | bigint | YES | 3 |
| servicecommands.priority | bigint | YES | 1 |
| servicecommands.createdby | text | YES |  |
| servicecommands.updatedat | timestamp without time zone | YES | CURRENT_TIMESTAMP |
| servicestatus.id | bigint | NO | nextval('"ServiceStatus_Id_seq"'::regclass) |
| servicestatus.servicename | text | NO |  |
| servicestatus.status | text | NO |  |
| servicestatus.healthstatus | text | NO |  |
| servicestatus.starttime | timestamp without time zone | YES |  |
| servicestatus.lasthealthcheck | timestamp without time zone | YES |  |
| servicestatus.uptimeseconds | bigint | YES | 0 |
| servicestatus.memoryusage | double precision | YES | 0.0 |
| servicestatus.cpuusage | double precision | YES | 0.0 |
| servicestatus.databaseconnection | boolean | YES | true |
| servicestatus.diskspace | double precision | YES | 0.0 |
| servicestatus.errorcount | bigint | YES | 0 |
| servicestatus.maxerrors | bigint | YES | 5 |
| servicestatus.activejobscount | bigint | YES | 0 |
| servicestatus.isprocessing | boolean | YES | false |
| servicestatus.lasterrormessage | text | YES |  |
| servicestatus.processid | bigint | YES |  |
| servicestatus.version | text | YES | '1.0.0'::text |
| servicestatus.servicetype | text | YES | 'Microservice'::text |
| servicestatus.createdat | timestamp without time zone | YES | CURRENT_TIMESTAMP |
| servicestatus.updatedat | timestamp without time zone | YES | CURRENT_TIMESTAMP |
| servicestatus.maxconcurrentjobs | bigint | YES | 1 |
| servicestatus.microservicestatus | text | YES |  |
| systemsettings.id | bigint | NO | nextval('"SystemSettings_Id_seq"'::regclass) |
| systemsettings.settingkey | text | NO |  |
| systemsettings.settingvalue | text | YES |  |
| systemsettings.description | text | YES |  |
| systemsettings.datatype | text | YES | 'string'::text |
| systemsettings.lastmodified | timestamp without time zone | YES | CURRENT_TIMESTAMP |
| temporaryfilepaths.id | bigint | NO | nextval('"TemporaryFilePaths_Id_seq"'::regclass) |
| temporaryfilepaths.transcodeattemptid | bigint | YES |  |
| temporaryfilepaths.originalpath | text | YES |  |
| temporaryfilepaths.localsourcepath | text | YES |  |
| temporaryfilepaths.localoutputpath | text | YES |  |
| temporaryfilepaths.createddate | timestamp without time zone | YES |  |
| transcodeattempts.id | bigint | NO | nextval('"TranscodeAttempts_Id_seq"'::regclass) |
| transcodeattempts.filepath | text | NO |  |
| transcodeattempts.attemptdate | timestamp without time zone | YES |  |
| transcodeattempts.quality | bigint | YES |  |
| transcodeattempts.oldsizebytes | bigint | YES |  |
| transcodeattempts.newsizebytes | bigint | YES |  |
| transcodeattempts.success | boolean | YES |  |
| transcodeattempts.sizereductionbytes | bigint | YES |  |
| transcodeattempts.sizereductionpercent | double precision | YES |  |
| transcodeattempts.errormessage | text | YES |  |
| transcodeattempts.transcodedurationseconds | double precision | YES |  |
| transcodeattempts.ffpmpegcommand | text | YES |  |
| transcodeattempts.audiobitratekbps | bigint | YES |  |
| transcodeattempts.videobitratekbps | bigint | YES |  |
| transcodeattempts.profilename | text | YES |  |
| transcodeattempts.vmaf | double precision | YES |  |
| transcodeattempts.qualitytestrequired | boolean | YES | false |
| transcodeattempts.qualitytestskipped | boolean | YES | false |
| transcodeattempts.qualitytestcompleted | boolean | YES | false |
| transcodeattempts.filereplaced | boolean | YES |  |
| transcodeattempts.filereplaceddate | timestamp without time zone | YES |  |
| transcodeattempts.replacementtype | text | YES |  |
| transcodeattempts.starttime | text | YES |  |
| transcodeattempts.preferredattempt | boolean | YES | false |
| transcodeattempts.completeddate | timestamp without time zone | YES |  |
| transcodefiles.id | bigint | NO | nextval('"TranscodeFiles_Id_seq"'::regclass) |
| transcodefiles.filepath | text | NO |  |
| transcodefiles.allqualitiesfailed | boolean | NO |  |
| transcodefiles.successfullytranscoded | boolean | NO |  |
| transcodefiles.firstattemptdate | timestamp without time zone | YES |  |
| transcodefiles.lastattemptdate | timestamp without time zone | YES |  |
| transcodefiles.successdate | timestamp without time zone | YES |  |
| transcodefiles.finalquality | bigint | YES |  |
| transcodefiles.finalsizebytes | bigint | YES |  |
| transcodefiles.totalattempts | bigint | YES | 0 |
| transcodefiles.originalfilepath | text | YES |  |
| transcodefiles.finalfilepath | text | YES |  |
| transcodeprogress.id | bigint | NO | nextval('"TranscodeProgress_Id_seq"'::regclass) |
| transcodeprogress.transcodeattemptid | bigint | NO |  |
| transcodeprogress.passnumber | bigint | NO |  |
| transcodeprogress.passtype | text | NO |  |
| transcodeprogress.currentphase | text | YES |  |
| transcodeprogress.progresspercent | double precision | YES |  |
| transcodeprogress.currentframe | bigint | YES |  |
| transcodeprogress.totalframes | bigint | YES |  |
| transcodeprogress.currentfps | double precision | YES |  |
| transcodeprogress.averagefps | double precision | YES |  |
| transcodeprogress.currentbitrate | text | YES |  |
| transcodeprogress.currenttime | text | YES |  |
| transcodeprogress.eta | text | YES |  |
| transcodeprogress.currentspeed | text | YES |  |
| transcodeprogress.passduration | double precision | YES |  |
| transcodeprogress.lastprogressupdate | timestamp without time zone | YES | CURRENT_TIMESTAMP |
| transcodeprogress.handbrakeoutput | text | YES |  |
| transcodeprogress.status | text | YES |  |
| transcodequeue.id | bigint | NO | nextval('"TranscodeQueue_Id_seq"'::regclass) |
| transcodequeue.filepath | text | NO |  |
| transcodequeue.filename | text | NO |  |
| transcodequeue.directory | text | NO |  |
| transcodequeue.sizebytes | bigint | NO |  |
| transcodequeue.sizemb | double precision | NO |  |
| transcodequeue.priority | bigint | YES | 0 |
| transcodequeue.status | text | YES | 'queued'::text |
| transcodequeue.dateadded | timestamp without time zone | YES | CURRENT_TIMESTAMP |
| transcodequeue.datestarted | timestamp without time zone | YES |  |
| transcodequeue.processingmode | text | YES | 'Transcode'::text |

## Indexes

| Table | Index | Unique | Primary | Definition |
|---|---|---|---|---|
| activejobs | ActiveJobs_pkey | True | True | CREATE UNIQUE INDEX "ActiveJobs_pkey" ON public.activejobs USING btree (id) |
| codecflags | CodecFlags_pkey | True | True | CREATE UNIQUE INDEX "CodecFlags_pkey" ON public.codecflags USING btree (id) |
| codecparameters | CodecParameters_pkey | True | True | CREATE UNIQUE INDEX "CodecParameters_pkey" ON public.codecparameters USING btree (id) |
| compliantfiles | CompliantFiles_pkey | True | True | CREATE UNIQUE INDEX "CompliantFiles_pkey" ON public.compliantfiles USING btree (id) |
| compressionlearningmodels | CompressionLearningModels_pkey | True | True | CREATE UNIQUE INDEX "CompressionLearningModels_pkey" ON public.compressionlearningmodels USING btree (id) |
| compressionlearningsamples | CompressionLearningSamples_pkey | True | True | CREATE UNIQUE INDEX "CompressionLearningSamples_pkey" ON public.compressionlearningsamples USING btree (id) |
| compressionlearningstats | CompressionLearningStats_pkey | True | True | CREATE UNIQUE INDEX "CompressionLearningStats_pkey" ON public.compressionlearningstats USING btree (id) |
| configuration | Configuration_pkey | True | True | CREATE UNIQUE INDEX "Configuration_pkey" ON public.configuration USING btree (key) |
| jellyfinoperations | JellyfinOperations_pkey | True | True | CREATE UNIQUE INDEX "JellyfinOperations_pkey" ON public.jellyfinoperations USING btree (logfilename) |
| logs | Logs_pkey | True | True | CREATE UNIQUE INDEX "Logs_pkey" ON public.logs USING btree (id) |
| mediafiles | MediaFiles_pkey | True | True | CREATE UNIQUE INDEX "MediaFiles_pkey" ON public.mediafiles USING btree (id) |
| presetoptions | PresetOptions_pkey | True | True | CREATE UNIQUE INDEX "PresetOptions_pkey" ON public.presetoptions USING btree (id) |
| problemfiles | ProblemFiles_pkey | True | True | CREATE UNIQUE INDEX "ProblemFiles_pkey" ON public.problemfiles USING btree (id) |
| profiles | Profiles_pkey | True | True | CREATE UNIQUE INDEX "Profiles_pkey" ON public.profiles USING btree (id) |
| profilethresholds | ProfileThresholds_pkey | True | True | CREATE UNIQUE INDEX "ProfileThresholds_pkey" ON public.profilethresholds USING btree (id) |
| qualitytestingqueue | QualityTestingQueue_pkey | True | True | CREATE UNIQUE INDEX "QualityTestingQueue_pkey" ON public.qualitytestingqueue USING btree (id) |
| qualitytestingstrategies | QualityTestingStrategies_pkey | True | True | CREATE UNIQUE INDEX "QualityTestingStrategies_pkey" ON public.qualitytestingstrategies USING btree (id) |
| qualitytestprogress | QualityTestProgress_pkey | True | True | CREATE UNIQUE INDEX "QualityTestProgress_pkey" ON public.qualitytestprogress USING btree (id) |
| qualitytestresults | QualityTestResults_pkey | True | True | CREATE UNIQUE INDEX "QualityTestResults_pkey" ON public.qualitytestresults USING btree (id) |
| rootfolders | RootFolders_pkey | True | True | CREATE UNIQUE INDEX "RootFolders_pkey" ON public.rootfolders USING btree (id) |
| scanjobs | ScanJobs_pkey | True | True | CREATE UNIQUE INDEX "ScanJobs_pkey" ON public.scanjobs USING btree (id) |
| seasons | Seasons_pkey | True | True | CREATE UNIQUE INDEX "Seasons_pkey" ON public.seasons USING btree (id) |
| servicecommands | ServiceCommands_pkey | True | True | CREATE UNIQUE INDEX "ServiceCommands_pkey" ON public.servicecommands USING btree (id) |
| servicestatus | ServiceStatus_pkey | True | True | CREATE UNIQUE INDEX "ServiceStatus_pkey" ON public.servicestatus USING btree (id) |
| systemsettings | SystemSettings_pkey | True | True | CREATE UNIQUE INDEX "SystemSettings_pkey" ON public.systemsettings USING btree (id) |
| temporaryfilepaths | TemporaryFilePaths_pkey | True | True | CREATE UNIQUE INDEX "TemporaryFilePaths_pkey" ON public.temporaryfilepaths USING btree (id) |
| transcodeattempts | TranscodeAttempts_pkey | True | True | CREATE UNIQUE INDEX "TranscodeAttempts_pkey" ON public.transcodeattempts USING btree (id) |
| transcodefiles | TranscodeFiles_pkey | True | True | CREATE UNIQUE INDEX "TranscodeFiles_pkey" ON public.transcodefiles USING btree (id) |
| transcodeprogress | TranscodeProgress_pkey | True | True | CREATE UNIQUE INDEX "TranscodeProgress_pkey" ON public.transcodeprogress USING btree (id) |
| transcodequeue | TranscodeQueue_pkey | True | True | CREATE UNIQUE INDEX "TranscodeQueue_pkey" ON public.transcodequeue USING btree (id) |

## Foreign Key Constraints

| Table | Constraint | Column | Referenced Table | Referenced Column | On Update | On Delete |
|---|---|---|---|---|---|---|
