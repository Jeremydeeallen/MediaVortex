# Tasks: Video Queue Transcoding

**Input**: Design documents from `/specs/002-add-a-feature/`
**Prerequisites**: plan.md (required), research.md, data-model.md, contracts/

## Execution Flow (main)
```
1. Load plan.md from feature directory
   → If not found: ERROR "No implementation plan found"
   → Extract: tech stack, libraries, structure
2. Load optional design documents:
   → data-model.md: Extract entities → model tasks
   → contracts/: Each file → contract test task
   → research.md: Extract decisions → setup tasks
3. Generate tasks by category:
   → Setup: project init, dependencies, linting
   → Tests: contract tests, integration tests
   → Core: models, services, CLI commands
   → Integration: DB, middleware, logging
   → Polish: unit tests, performance, docs
4. Apply task rules:
   → Different files = mark [P] for parallel
   → Same file = sequential (no [P])
   → Tests before implementation (TDD)
5. Number tasks sequentially (T001, T002...)
6. Generate dependency graph
7. Create parallel execution examples
8. Validate task completeness:
   → All contracts have tests?
   → All entities have models?
   → All endpoints implemented?
9. Return: SUCCESS (tasks ready for execution)
```

## Format: `[ID] [P?] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- Include exact file paths in descriptions

## Path Conventions
- **Single project**: `src/`, `tests/` at repository root
- **Web app**: `backend/src/`, `frontend/src/`
- **Mobile**: `api/src/`, `ios/src/` or `android/src/`
- Paths shown below assume single project - adjust based on plan.md structure

## Phase 3.1: Setup
- [x] T001 Create database schema extensions for TranscodeQueue, TranscodeAttempts, TranscodeFiles, and Profiles tables
- [x] T002 Initialize FFmpeg integration for transcoding and quality scoring with VMAF analysis
- [x] T003 [P] Configure temporary directory structure at c:\MediaVortex\Source and c:\MediaVortex\<filename>
- [x] T004 [P] Setup filename resolution logic for resolution-based naming (1080p/2160p to 720p replacement)
- [x] T005 [P] Setup FFmpeg transcoding service with quality settings from MediaFiles table

## Phase 3.2: Tests First (TDD) - MUST COMPLETE BEFORE 3.3
**CRITICAL: These tests MUST be written and MUST FAIL before ANY implementation**
- [x] T006 [P] Contract test POST /api/transcode/start in Tests/Contract/TestTranscodeStart.py
- [x] T007 [P] Contract test GET /api/transcode/status/{JobId} in Tests/Contract/TestTranscodeStatus.py
- [x] T008 [P] Contract test GET /api/transcode/queue in Tests/Contract/TestQueueGet.py
- [x] T009 [P] Integration test transcoding workflow with quality scoring in Tests/Integration/TestTranscodingWorkflow.py
- [x] T010 [P] Integration test filename resolution logic in Tests/Integration/TestFilenameResolution.py
- [x] T011 [P] Integration test quality scoring and file replacement logic in Tests/Integration/TestQualityScoring.py

## Phase 3.3: Core Implementation (ONLY after tests are failing)
- [x] T012 [P] TranscodeQueueItem model in Models/TranscodeQueueModel.py
- [x] T013 [P] TranscodingJob model in Models/TranscodeAttemptModel.py
- [x] T014 [P] TranscodingResult model in Models/TranscodeFileModel.py
- [x] T015 [P] TranscodingProfile model in Models/TranscodeProfileModel.py
- [x] T016 [P] TranscodingQueueProcessor service in Services/TranscodingQueueProcessor.py
- [x] T017 [P] FFmpegTranscodingService with aspect ratio preservation in Services/FFmpegTranscodingService.py
- [x] T018 [P] FileManagerService for copy/delete operations in Services/FileManagerService.py
- [x] T019 [P] QualityScoringService with FFmpeg VMAF analysis in Services/QualityScoringService.py
- [x] T020 [P] FilenameResolutionService for resolution-based naming in Services/FilenameResolutionService.py
- [x] T021 POST /api/transcode/start endpoint in Controllers/TranscodeQueueController.py
- [x] T022 GET /api/transcode/status/{jobId} endpoint in Controllers/TranscodeQueueController.py
- [x] T023 GET /api/transcode/queue endpoint in Controllers/TranscodeQueueController.py
- [x] T024 Input validation for transcoding requests
- [x] T025 Error handling and logging for transcoding operations

## Phase 3.4: Integration
- [x] T026 Connect TranscodingQueueProcessor to database with transaction management
- [x] T027 Integrate complete transcoding workflow: copy to c:\MediaVortex\Source, transcode with FFmpeg and aspect ratio preservation
- [x] T028 Integrate quality scoring workflow: FFmpeg VMAF analysis with >90 threshold validation
- [x] T029 Integrate file replacement logic: delete original and copy transcoded file only on quality pass
- [x] T030 Integrate filename resolution: replace 1080p/2160p with target resolution in output filename
- [x] T031 File system operations with UTF-8 compatibility
- [x] T032 Database logging for all transcoding operations in TranscodeAttempts table
- [x] T033 Queue retrieval with proper ordering (top item processing)
- [x] T034 Error handling: log failures in TranscodeAttempts, skip file cleanup on quality failure

## Phase 3.5: FFmpeg Progress Optimization
- [ ] T035 Optimize FFmpeg progress storage: Use single record per transcode with UPDATE instead of INSERT in Repositories/DatabaseManager.py
- [ ] T036 Add ETA calculation logic: Calculate remaining time from current speed and progress in Services/TranscodingBusinessService.py
- [ ] T037 Add ProgressPercent calculation: Calculate percentage from current time / total duration in Services/TranscodingBusinessService.py
- [ ] T038 Fix FFmpeg progress parsing: Handle out_time field and get input file duration in Services/FFmpegService.py
- [ ] T039 Update TranscodeProgress GUI: Modify Templates/TranscodeProgress.html to pull all progress data from database instead of real-time parsing
- [ ] T040 Update ActivityViewModel: Modify ViewModels/ActivityViewModel.py to use optimized single-record database queries
- [ ] T041 Test optimized progress display: Verify real-time updates in frontend with minimal database records and clean GUI display

## Phase 3.6: VMAF System Fixes
- [x] T051 Fix VMAF API endpoint indentation error in Controllers/VMAFJobController.py line 71
- [x] T052 Verify VMAF FFmpeg syntax compatibility with new FFmpegMaster version in Services/FFmpegComparisonService.py
- [ ] T053 Test VMAF functionality with corrected API endpoint and verify quality analysis works

## Phase 3.7: Resolution Scaling Implementation
- [ ] T054 Add resolution scaling logic to FFmpegTranscodingService.BuildFFmpegCommand() method
- [ ] T055 Implement TranscodeDownTo field processing in FFmpeg command generation
- [ ] T056 Add -vf scale=WIDTH:HEIGHT filter to FFmpeg commands when TranscodeDownTo is set
- [ ] T057 Test resolution scaling with 4K to 720p transcoding to verify proper scaling

## Phase 3.8: Polish
- [ ] T042 [P] Unit tests for TranscodingQueueProcessor in tests/unit/TestTranscodingQueueProcessor.py
- [ ] T043 [P] Unit tests for FFmpegTranscodingService in tests/unit/TestFFmpegTranscodingService.py
- [ ] T044 [P] Unit tests for FileManagerService in tests/unit/TestFileManager.py
- [ ] T045 [P] Unit tests for QualityScoringService in tests/unit/TestQualityScoringService.py
- [ ] T046 [P] Unit tests for FilenameResolutionService in tests/unit/TestFilenameResolutionService.py
- [ ] T047 Performance tests for large file processing
- [ ] T048 [P] Update documentation in Docs/TranscodingFeature.md
- [ ] T049 Remove code duplication and optimize database queries
- [ ] T050 Run quickstart.md validation scenarios

## Dependencies
- Tests (T006-T011) before implementation (T012-T025)
- T012-T015 (models) block T016-T020 (services)
- T016-T020 (services) block T021-T023 (endpoints)
- T026-T034 (integration) depend on T012-T025 (core implementation)
- T035-T041 (FFmpeg progress optimization) depend on T026-T034 (integration)
- T039-T040 (GUI updates) depend on T035-T038 (database optimization)
- Implementation before polish (T042-T050)

## Parallel Examples
```
# Launch T006-T011 together (Tests):
Task: "Contract test POST /api/transcode/start in tests/contract/TestTranscodeStart.py"
Task: "Contract test GET /api/transcode/status/{JobId} in tests/contract/TestTranscodeStatus.py"
Task: "Contract test GET /api/transcode/queue in tests/contract/TestQueueGet.py"
Task: "Integration test transcoding workflow with quality scoring in tests/integration/TestTranscodingWorkflow.py"
Task: "Integration test filename resolution logic in tests/integration/TestFilenameResolution.py"
Task: "Integration test quality scoring and file replacement logic in tests/integration/TestQualityScoring.py"

# Launch T042-T046 together (Unit Tests):
Task: "Unit tests for TranscodingQueueProcessor in tests/unit/TestTranscodingQueueProcessor.py"
Task: "Unit tests for FFmpegTranscodingService in tests/unit/TestFFmpegTranscodingService.py"
Task: "Unit tests for FileManagerService in tests/unit/TestFileManager.py"
Task: "Unit tests for QualityScoringService in tests/unit/TestQualityScoringService.py"
Task: "Unit tests for FilenameResolutionService in tests/unit/TestFilenameResolutionService.py"
```

## Notes
- [P] tasks = different files, no dependencies
- Verify tests fail before implementing
- Commit after each task
- Avoid: vague tasks, same file conflicts
- Follow PascalCase naming convention for all new code
- Use centralized logging through LoggingService
- Ensure UTF-8 compatibility for all file operations

## Task Generation Rules
*Applied during main() execution*

1. **From Contracts**:
   - TranscodeStartContract.json → T006 contract test [P]
   - TranscodeStatusContract.json → T007 contract test [P]
   - TranscodeQueueGetContract.json → T008 contract test [P]
   - Each endpoint → implementation task

2. **From Data Model**:
   - TranscodeQueueItem → T012 model creation [P]
   - TranscodingJob → T013 model creation [P]
   - TranscodingResult → T014 model creation [P]
   - TranscodingProfile → T015 model creation [P]
   - MediaFiles quality settings → FFmpeg transcoding service tasks
   - Relationships → service layer tasks

3. **From User Stories**:
   - Transcoding workflow with quality scoring → T009 integration test [P]
   - Filename resolution logic → T010 integration test [P]
   - Quality scoring and file replacement → T011 integration test [P]
   - Quickstart scenarios → validation tasks

4. **Ordering**:
   - Setup → Tests → Models → Services → Endpoints → Integration → Polish
   - Dependencies block parallel execution

## Validation Checklist
*GATE: Checked by main() before returning*

- [x] All contracts have corresponding tests (T006-T008)
- [x] All entities have model tasks (T012-T015)
- [x] All tests come before implementation (T006-T011 before T012-T025)
- [x] Quality scoring workflow included (T009, T011, T019, T028)
- [x] Filename resolution logic included (T010, T020, T030)
- [x] Complete transcoding workflow with file replacement (T027-T034)
- [x] Parallel tasks truly independent
- [x] Each task specifies exact file path
- [x] No task modifies same file as another [P] task
