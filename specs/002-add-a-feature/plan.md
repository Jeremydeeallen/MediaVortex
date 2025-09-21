# Implementation Plan: Video Queue Transcoding

**Branch**: `002-add-a-feature` | **Date**: 2025-09-19 | **Spec**: specs/002-add-a-feature/spec.md
**Input**: Feature specification from `/specs/002-add-a-feature/spec.md`

## Execution Flow (/plan command scope)
```
1. Load feature spec from Input path
   → If not found: ERROR "No feature spec at {path}"
2. Fill Technical Context (scan for NEEDS CLARIFICATION)
   → Detect Project Type from context (web=frontend+backend, mobile=app+api)
   → Set Structure Decision based on project type
3. Fill the Constitution Check section based on the content of the constitution document.
4. Evaluate Constitution Check section below
   → If violations exist: Document in Complexity Tracking
   → If no justification possible: ERROR "Simplify approach first"
   → Update Progress Tracking: Initial Constitution Check
5. Execute Phase 0 → research.md
   → If NEEDS CLARIFICATION remain: ERROR "Resolve unknowns"
6. Execute Phase 1 → contracts, data-model.md, quickstart.md, agent-specific template file (e.g., `CLAUDE.md` for Claude Code, `.github/copilot-instructions.md` for GitHub Copilot, `GEMINI.md` for Gemini CLI, `QWEN.md` for Qwen Code or `AGENTS.md` for opencode).
7. Re-evaluate Constitution Check section
   → If new violations: Refactor design, return to Phase 1
   → Update Progress Tracking: Post-Design Constitution Check
8. Plan Phase 2 → Describe task generation approach (DO NOT create tasks.md)
9. STOP - Ready for /tasks command
```

**IMPORTANT**: The /plan command STOPS at step 7. Phases 2-4 are executed by other commands:
- Phase 2: /tasks command creates tasks.md
- Phase 3-4: Implementation execution (manual or via tools)

## Summary
Video queue transcoding feature that processes videos from the TranscodeQueue table using FFmpeg with quality settings from the MediaFiles table. The system copies the top queue item to c:\MediaVortex\Source, transcodes it with FFmpeg using quality settings and audio bitrate while maintaining aspect ratio, outputs to c:\MediaVortex\<filename> with resolution-adjusted naming, performs quality scoring (>90 threshold), and replaces original files only on successful transcoding with proper database logging in TranscodeAttempts table.

## Technical Context
**Language/Version**: Python 3.11  
**Primary Dependencies**: SQLite3, FFmpeg for transcoding and quality scoring, Python file operations  
**Storage**: SQLite database (MediaVortex.db) with existing schema  
**Testing**: pytest for unit tests, integration tests for FFmpeg operations  
**Target Platform**: Windows (FFmpeg path specific)  
**Project Type**: single (existing MediaVortex application)  
**Performance Goals**: Process queue items sequentially with quality validation  
**Constraints**: Must preserve original files during transcoding, UTF-8 compatibility required, quality score >90 threshold  
**Scale/Scope**: Single transcoding operation at a time, database-driven queue management  
**File Paths**: Source files from scan directory, temp processing at c:\MediaVortex\Source, output to c:\MediaVortex\<filename>  
**Quality Validation**: FFmpeg-based quality scoring with 90+ threshold for file replacement  
**Transcoding Engine**: FFmpeg with quality settings from MediaFiles table  

## Constitution Check
*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### MVVM Architecture Compliance
- Models: TranscodeQueueItem, TranscodingProfile, TranscodingJob, TranscodingResult
- ViewModels: TranscodeQueueViewModel (existing)
- Views: TranscodeQueue.html (existing)
- Controllers: TranscodeQueueController (existing)
- Services: TranscodingBusinessService (existing), FFmpegService (existing)

### PascalCase Naming Convention
- All new classes, methods, variables must use PascalCase
- Database table names already follow PascalCase (TranscodeQueue, TranscodeAttempts, etc.)
- File names must use PascalCase (e.g., TranscodeQueueProcessor.py)

### Centralized Logging
- All operations must be logged through LoggingService
- Database storage required for all log entries
- Function names and components must be tracked

### File Operations in Python
- File copying, moving, deleting must use Python
- Cross-platform compatibility required
- FileManager class should handle all file operations

### UTF-8 Compatibility
- All text processing must support UTF-8 encoding
- File paths and names must handle Unicode characters

### No Emojis
- Professional text-only communication required
- No emojis in code, documentation, or output

### Actual Date and Time
- Current date/time must be retrieved before use in documentation
- No placeholder dates or hardcoded timestamps

## Project Structure

### Documentation (this feature)
```
specs/002-add-a-feature/
├── plan.md              # This file (/plan command output)
├── research.md          # Phase 0 output (/plan command)
├── data-model.md        # Phase 1 output (/plan command)
├── quickstart.md        # Phase 1 output (/plan command)
├── contracts/           # Phase 1 output (/plan command)
└── tasks.md             # Phase 2 output (/tasks command - NOT created by /plan)
```

### Source Code (repository root)
```
# Option 1: Single project (DEFAULT)
MediaVortex/
├── Models/
│   ├── TranscodeQueueModel.py (existing)
│   ├── TranscodeAttemptModel.py (existing)
│   └── TranscodeFileModel.py (existing)
├── Services/
│   ├── TranscodingBusinessService.py (existing)
│   ├── FFmpegService.py (existing)
│   └── DatabaseService.py (existing)
├── Controllers/
│   └── TranscodeQueueController.py (existing)
├── ViewModels/
│   └── TranscodeQueueViewModel.py (existing)
└── Views/
    └── TranscodeQueue.html (existing)

tests/
├── contract/
├── integration/
└── unit/
```

**Structure Decision**: Option 1 - Single project (existing MediaVortex application)

## Phase 0: Outline & Research
1. **Extract unknowns from Technical Context** above:
   - HandBrake CLI integration patterns
   - File size-based queue prioritization
   - Database transaction management for transcoding operations
   - Error handling and recovery patterns

2. **Generate and dispatch research agents**:
   ```
   Task: "Research HandBrake CLI integration patterns for Python applications"
   Task: "Find best practices for file size-based queue prioritization"
   Task: "Research database transaction patterns for long-running operations"
   Task: "Find error handling patterns for external process execution"
   ```

3. **Consolidate findings** in `research.md` using format:
   - Decision: [what was chosen]
   - Rationale: [why chosen]
   - Alternatives considered: [what else evaluated]

**Output**: research.md with all NEEDS CLARIFICATION resolved

## Phase 1: Design & Contracts
*Prerequisites: research.md complete*

1. **Extract entities from feature spec** → `data-model.md`:
   - TranscodeQueueItem: FilePath, FileName, SizeMB, Priority, Status, AssignedProfile
   - TranscodingJob: JobId, FilePath, ProfileSettings, StartTime, EndTime, Status
   - TranscodingResult: Success, OutputFilePath, SizeReduction, ErrorMessage

2. **Generate API contracts** from functional requirements:
   - POST /api/transcode/start - Start transcoding next item in queue
   - GET /api/transcode/status/{jobId} - Get transcoding job status
   - POST /api/transcode/queue/prioritize - Reorder queue by file size

3. **Generate contract tests** from contracts:
   - One test file per endpoint
   - Assert request/response schemas
   - Tests must fail (no implementation yet)

4. **Extract test scenarios** from user stories:
   - Each story → integration test scenario
   - Quickstart test = story validation steps

5. **Update agent file incrementally** (O(1) operation):
   - Run `.specify/scripts/powershell/update-agent-context.ps1 -AgentType cursor` for your AI assistant
   - If exists: Add only NEW tech from current plan
   - Preserve manual additions between markers
   - Update recent changes (keep last 3)
   - Keep under 150 lines for token efficiency
   - Output to repository root

**Output**: data-model.md, /contracts/*, failing tests, quickstart.md, agent-specific file

## Phase 2: Task Planning Approach
*This section describes what the /tasks command will do - DO NOT execute during /plan*

**Task Generation Strategy**:
- Load `.specify/templates/tasks-template.md` as base
- Generate tasks from Phase 1 design docs (contracts, data model, quickstart)
- Each contract → contract test task [P]
- Each entity → model creation task [P] 
- Each user story → integration test task
- Implementation tasks to make tests pass

**Ordering Strategy**:
- TDD order: Tests before implementation 
- Dependency order: Models before services before UI
- Mark [P] for parallel execution (independent files)

**Estimated Output**: 25-30 numbered, ordered tasks in tasks.md

**IMPORTANT**: This phase is executed by the /tasks command, NOT by /plan

## Phase 3+: Future Implementation
*These phases are beyond the scope of the /plan command*

**Phase 3**: Task execution (/tasks command creates tasks.md)  
**Phase 4**: Implementation (execute tasks.md following constitutional principles)  
**Phase 5**: Validation (run tests, execute quickstart.md, performance validation)

## Complexity Tracking
*Fill ONLY if Constitution Check has violations that must be justified*

No violations identified - all constitutional requirements can be met with existing architecture.

## Progress Tracking
*This checklist is updated during execution flow*

**Phase Status**:
- [x] Phase 0: Research complete (/plan command)
- [x] Phase 1: Design complete (/plan command)
- [x] Phase 2: Task planning complete (/plan command - describe approach only)
- [x] Phase 3: Tasks generated (/tasks command)
- [ ] Phase 4: Implementation complete
- [ ] Phase 5: Validation passed

**Gate Status**:
- [x] Initial Constitution Check: PASS
- [x] Post-Design Constitution Check: PASS
- [x] All NEEDS CLARIFICATION resolved
- [x] Complexity deviations documented

---
*Based on Constitution v1.1.0 - See `/memory/constitution.md`*
