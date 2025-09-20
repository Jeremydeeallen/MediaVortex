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
- [ ] T001 Create database schema extensions for TranscodeQueue, TranscodeAttempts, TranscodeFiles, and Profiles tables
- [ ] T002 Initialize HandBrake CLI integration with subprocess module and error handling
- [ ] T003 [P] Configure temporary directory structure at c:\HandBrakeTemp\Source and c:\HandBrakeTemp\Output

## Phase 3.2: Tests First (TDD) - MUST COMPLETE BEFORE 3.3
**CRITICAL: These tests MUST be written and MUST FAIL before ANY implementation**
- [ ] T004 [P] Contract test POST /api/transcode/start in tests/contract/TestTranscodeStart.py
- [ ] T005 [P] Contract test GET /api/transcode/status/{JobId} in tests/contract/TestTranscodeStatus.py
- [ ] T006 [P] Contract test POST /api/transcode/queue/prioritize in tests/contract/TestQueuePrioritize.py
- [ ] T007 [P] Integration test transcoding workflow in tests/integration/TestTranscodingWorkflow.py
- [ ] T008 [P] Integration test queue prioritization in tests/integration/TestQueuePrioritization.py
- [ ] T009 [P] Integration test error handling in tests/integration/TestErrorHandling.py

## Phase 3.3: Core Implementation (ONLY after tests are failing)
- [ ] T010 [P] TranscodeQueueItem model in Models/TranscodeQueueModel.py
- [ ] T011 [P] TranscodingJob model in Models/TranscodeAttemptModel.py
- [ ] T012 [P] TranscodingResult model in Models/TranscodeFileModel.py
- [ ] T013 [P] TranscodingProfile model in Models/TranscodeProfileModel.py
- [ ] T014 [P] TranscodingQueueProcessor service in Services/TranscodingQueueProcessor.py
- [ ] T015 [P] HandBrakeTranscodingService in Services/HandBrakeTranscodingService.py
- [ ] T016 [P] FileManagerService for copy/delete operations in Services/FileManagerService.py
- [ ] T017 POST /api/transcode/start endpoint in Controllers/TranscodeQueueController.py
- [ ] T018 GET /api/transcode/status/{jobId} endpoint in Controllers/TranscodeQueueController.py
- [ ] T019 POST /api/transcode/queue/prioritize endpoint in Controllers/TranscodeQueueController.py
- [ ] T020 Input validation for transcoding requests
- [ ] T021 Error handling and logging for transcoding operations

## Phase 3.4: Integration
- [ ] T022 Connect TranscodingQueueProcessor to database with transaction management
- [ ] T023 Integrate HandBrake CLI execution with progress tracking
- [ ] T024 File system operations with UTF-8 compatibility
- [ ] T025 Database logging for all transcoding operations
- [ ] T026 Queue prioritization by file size (SizeMB DESC, DateAdded ASC)

## Phase 3.5: Polish
- [ ] T027 [P] Unit tests for TranscodingQueueProcessor in tests/unit/TestTranscodingQueueProcessor.py
- [ ] T028 [P] Unit tests for HandBrakeTranscodingService in tests/unit/TestHandBrakeService.py
- [ ] T029 [P] Unit tests for FileManagerService in tests/unit/TestFileManager.py
- [ ] T030 Performance tests for large file processing
- [ ] T031 [P] Update documentation in Docs/TranscodingFeature.md
- [ ] T032 Remove code duplication and optimize database queries
- [ ] T033 Run quickstart.md validation scenarios

## Dependencies
- Tests (T004-T009) before implementation (T010-T021)
- T010-T013 (models) block T014-T016 (services)
- T014-T016 (services) block T017-T019 (endpoints)
- T022-T026 (integration) depend on T010-T021 (core implementation)
- Implementation before polish (T027-T033)

## Parallel Example
```
# Launch T004-T009 together:
Task: "Contract test POST /api/transcode/start in tests/contract/TestTranscodeStart.py"
Task: "Contract test GET /api/transcode/status/{JobId} in tests/contract/TestTranscodeStatus.py"
Task: "Contract test POST /api/transcode/queue/prioritize in tests/contract/TestQueuePrioritize.py"
Task: "Integration test transcoding workflow in tests/integration/TestTranscodingWorkflow.py"
Task: "Integration test queue prioritization in tests/integration/TestQueuePrioritization.py"
Task: "Integration test error handling in tests/integration/TestErrorHandling.py"
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
   - TranscodeStartContract.json → T004 contract test [P]
   - TranscodeStatusContract.json → T005 contract test [P]
   - TranscodeQueuePrioritizeContract.json → T006 contract test [P]
   - Each endpoint → implementation task

2. **From Data Model**:
   - TranscodeQueueItem → T010 model creation [P]
   - TranscodingJob → T011 model creation [P]
   - TranscodingResult → T012 model creation [P]
   - TranscodingProfile → T013 model creation [P]
   - Relationships → service layer tasks

3. **From User Stories**:
   - Transcoding workflow → T007 integration test [P]
   - Queue prioritization → T008 integration test [P]
   - Error handling → T009 integration test [P]
   - Quickstart scenarios → validation tasks

4. **Ordering**:
   - Setup → Tests → Models → Services → Endpoints → Polish
   - Dependencies block parallel execution

## Validation Checklist
*GATE: Checked by main() before returning*

- [x] All contracts have corresponding tests (T004-T006)
- [x] All entities have model tasks (T010-T013)
- [x] All tests come before implementation (T004-T009 before T010-T021)
- [x] Parallel tasks truly independent
- [x] Each task specifies exact file path
- [x] No task modifies same file as another [P] task
