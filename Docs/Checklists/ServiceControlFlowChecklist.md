# Service Control Flow Checklist

## Current Status Analysis

### ✅ Working Components
- [x] **SystemOrchestratorService** - Entry point, starts MediaVortex automatically
- [x] **MediaVortex Web Interface** - Status.html template with start button
- [x] **ServiceControlController API** - Directly starts services (FIXED)
- [x] **Database Updates** - ServiceControlController updates ServiceStatus table

### ❌ Critical Fixes Needed Before Quality Scan Works
- [ ] **QualityCompareService Process Startup** - ServiceControlController must start process correctly
- [ ] **Quality Testing Loop** - Not implemented (starts processes gradually)
- [ ] **MaxConcurrentJobs Database Setting** - Must be configured in database
- [ ] **FFmpeg VMAF Execution** - Not running quality tests

## Critical Fixes Required

### 1. ServiceControlController Direct Process Startup (FIXED)
- [x] **Fixed** ServiceControlController now directly starts services
- [x] **Fixed** No more orchestrator dependency for service startup
- [x] **Fixed** Direct subprocess.Popen() calls to start services

### 2. QualityCompareService Process Startup (NEEDS TESTING)
- [ ] **Test** ServiceControlController starts QualityCompareService process
- [ ] **Verify** Process starts with correct Python executable path
- [ ] **Verify** ProcessId is set in database
- [ ] **Test** Service updates ServiceStatus to "Running"

### 3. Quality Testing Loop Implementation (CRITICAL)
- [ ] **Write** PrivateQualityTestingLoop() method in QualityCompareService
- [ ] **Implement** Gradual process startup (1 → wait → 1 more → repeat)
- [ ] **Add** MaxConcurrentJobs database checking
- [ ] **Test** Loop starts processes up to MaxConcurrentJobs limit

### 4. Database Configuration (CRITICAL)
- [ ] **Verify** MaxConcurrentJobs setting exists in database
- [ ] **Set** MaxConcurrentJobs to appropriate value (e.g., 3)
- [ ] **Verify** QualityTestingQueue has test files to process

## Implementation Checklist

### Phase 1: Test Direct Service Startup (IMMEDIATE)
- [ ] **Test** Click "Start" button → ServiceControlController starts QualityCompareService
- [ ] **Verify** Process starts and ProcessId is set in database
- [ ] **Verify** ServiceStatus updates to "Running"
- [ ] **Fix** Any process startup issues (Python path, permissions, etc.)

### Phase 2: Database Configuration (CRITICAL)
- [ ] **Verify** MaxConcurrentJobs setting exists in database
- [ ] **Set** MaxConcurrentJobs to appropriate value (e.g., 3)
- [ ] **Verify** QualityTestingQueue has test files to process
- [ ] **Test** Database queries return correct values

### Phase 3: Implement Quality Testing Loop (CRITICAL)
- [ ] **Write** PrivateQualityTestingLoop() method in QualityCompareService
- [ ] **Implement** Gradual process startup (1 → wait → 1 more → repeat)
- [ ] **Add** MaxConcurrentJobs database checking
- [ ] **Test** Loop starts processes up to MaxConcurrentJobs limit
- [ ] **Verify** FFmpeg VMAF tests execute and store results

### Phase 4: End-to-End Testing (FINAL)
- [ ] **Test** Complete flow: User clicks "Start" button
- [ ] **Verify** ServiceControlController directly starts QualityCompareService process
- [ ] **Verify** QualityCompareService starts quality testing loop
- [ ] **Verify** Quality tests run gradually up to MaxConcurrentJobs
- [ ] **Verify** FFmpeg VMAF tests execute and store results
- [ ] **Verify** All database updates work correctly

## Success Criteria

### Code Quality (COMPLETED)
- [x] Simple, direct flow without complex routing (FIXED)
- [x] One responsibility per component (FIXED)
- [x] KISS principle followed (FIXED)
- [x] MVVM pattern maintained (FIXED)
