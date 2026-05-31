# directive: ceo-mode-enforcement
# PreToolUse hook: enforces phase gates + 15 content rules per .claude/standards/index.md
# Invoked by Claude Code on Write|Edit|MultiEdit tool calls. Reads JSON from stdin, emits JSON to stdout.
# PowerShell 5.1 compatible.

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$RepoRoot = (Get-Location).Path
$StateFile = Join-Path $RepoRoot ".claude\.session-state.json"
$OverrideLog = Join-Path $RepoRoot ".claude\.standards-overrides.log"
$DirectiveFile = Join-Path $RepoRoot ".claude\directive.md"
$RulesDir = Join-Path $RepoRoot ".claude\rules"
$StandardsIndex = Join-Path $RepoRoot ".claude\standards\index.md"

function Read-StdinJson {
    $Raw = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($Raw)) { return $null }
    return $Raw | ConvertFrom-Json
}

function Emit-Deny {
    param([string]$Reason)
    $Out = @{
        hookSpecificOutput = @{
            hookEventName = "PreToolUse"
            permissionDecision = "deny"
            permissionDecisionReason = $Reason
        }
        continue = $true
    } | ConvertTo-Json -Depth 6 -Compress
    [Console]::Out.Write($Out)
    exit 0
}

function Emit-Ask {
    param([string]$Reason)
    $Out = @{
        hookSpecificOutput = @{
            hookEventName = "PreToolUse"
            permissionDecision = "ask"
            permissionDecisionReason = $Reason
        }
        continue = $true
    } | ConvertTo-Json -Depth 6 -Compress
    [Console]::Out.Write($Out)
    exit 0
}

function Emit-Allow { exit 0 }

function Get-SessionState {
    if (Test-Path $StateFile) {
        try { return Get-Content $StateFile -Raw | ConvertFrom-Json } catch { }
    }
    $Slug = Get-DirectiveSlug
    $Phase = Get-DirectivePhase
    if ($Slug -and $Phase) {
        return [PSCustomObject]@{ directive_slug = $Slug; phase = $Phase }
    }
    return $null
}

function Get-DirectiveSlug {
    if (-not (Test-Path $DirectiveFile)) { return $null }
    $Text = Get-Content $DirectiveFile -Raw
    $M = [regex]::Match($Text, '\*\*Slug:\*\*\s*(\S+)')
    if ($M.Success -and $M.Groups[1].Value -ne '<previous-slug>') { return $M.Groups[1].Value }
    return $null
}

function Get-DirectivePhase {
    if (-not (Test-Path $DirectiveFile)) { return $null }
    $Text = Get-Content $DirectiveFile -Raw
    $M = [regex]::Match($Text, '\*\*Status:\*\*\s*Active\s*--\s*phase:\s*([A-Z_]+)')
    if ($M.Success) { return $M.Groups[1].Value }
    return $null
}

function Get-DirectiveFiles {
    if (-not (Test-Path $DirectiveFile)) { return @() }
    $Text = Get-Content $DirectiveFile -Raw
    $M = [regex]::Match($Text, '(?ms)### Files\s*```\s*(.*?)```')
    if (-not $M.Success) { return @() }
    $Block = $M.Groups[1].Value
    $Files = @()
    foreach ($Line in ($Block -split "`n")) {
        $Trimmed = $Line.Trim()
        if ($Trimmed -and -not $Trimmed.StartsWith('#') -and -not $Trimmed.StartsWith('--')) {
            $PathPart = ($Trimmed -split '\s+')[0]
            if ($PathPart) { $Files += $PathPart }
        }
    }
    return $Files
}

function Get-ReadFilesFromTranscript {
    param([string]$TranscriptPath)
    if (-not $TranscriptPath -or -not (Test-Path $TranscriptPath)) { return @() }
    $Files = @{}
    foreach ($Line in (Get-Content $TranscriptPath)) {
        $Matches = [regex]::Matches($Line, '"name"\s*:\s*"Read"[^}]*?"file_path"\s*:\s*"([^"]+)"')
        foreach ($M in $Matches) {
            $P = $M.Groups[1].Value -replace '\\\\', '\'
            $Files[$P.ToLower()] = $true
        }
    }
    return @($Files.Keys)
}

function Synthesize-PostEditContent {
    param($ToolName, $ToolInput)
    if ($ToolName -eq 'Write') { return $ToolInput.content }
    $FilePath = $ToolInput.file_path
    $Current = ''
    if (Test-Path $FilePath) { $Current = Get-Content $FilePath -Raw }
    if (-not $Current) { $Current = '' }
    if ($ToolName -eq 'Edit') {
        $Old = $ToolInput.old_string
        $New = $ToolInput.new_string
        if ($ToolInput.replace_all) {
            return $Current.Replace($Old, $New)
        } else {
            $Idx = $Current.IndexOf($Old)
            if ($Idx -lt 0) { return $Current }
            return $Current.Substring(0, $Idx) + $New + $Current.Substring($Idx + $Old.Length)
        }
    }
    if ($ToolName -eq 'MultiEdit') {
        $Buf = $Current
        foreach ($E in $ToolInput.edits) {
            if ($E.replace_all) { $Buf = $Buf.Replace($E.old_string, $E.new_string) }
            else {
                $Idx = $Buf.IndexOf($E.old_string)
                if ($Idx -ge 0) { $Buf = $Buf.Substring(0, $Idx) + $E.new_string + $Buf.Substring($Idx + $E.old_string.Length) }
            }
        }
        return $Buf
    }
    return $Current
}

function Get-AddedLines {
    param($ToolName, $ToolInput)
    if ($ToolName -eq 'Write') { return ($ToolInput.content -split "`n") }
    if ($ToolName -eq 'Edit') { return ($ToolInput.new_string -split "`n") }
    if ($ToolName -eq 'MultiEdit') {
        $Lines = @()
        foreach ($E in $ToolInput.edits) { $Lines += ($E.new_string -split "`n") }
        return $Lines
    }
    return @()
}

function Test-AllowOverride {
    param([string]$Content, [int]$LineNumber, [string]$RuleId, [string]$FilePath)
    $Lines = $Content -split "`n"
    $Start = [Math]::Max(0, $LineNumber - 3)
    $End = [Math]::Min($Lines.Length - 1, $LineNumber + 3)
    for ($I = $Start; $I -le $End; $I++) {
        $M = [regex]::Match($Lines[$I], '#\s*allow:\s*(.+)$')
        if ($M.Success) {
            $Reason = $M.Groups[1].Value.Trim()
            if ($Reason) {
                $Entry = @{
                    ts = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ")
                    rule = $RuleId
                    file = $FilePath
                    line = $LineNumber + 1
                    reason = $Reason
                } | ConvertTo-Json -Compress
                Add-Content -Path $OverrideLog -Value $Entry -Encoding UTF8
                return $true
            }
        }
    }
    return $false
}

# ============ Phase gate ============
function Test-PhaseGate {
    param($State, $ToolName, $ToolInput)
    if (-not $State) { return $null }
    $Phase = $State.phase
    $FilePath = $ToolInput.file_path
    $IsDirectiveDoc = $FilePath -and ((Resolve-Path $FilePath -ErrorAction SilentlyContinue).Path -eq (Resolve-Path $DirectiveFile -ErrorAction SilentlyContinue).Path)
    switch ($Phase) {
        'NEEDS_STANDARDS_REVIEW' {
            return "Phase NEEDS_STANDARDS_REVIEW: Read every file under .claude/rules/ and .claude/standards/index.md before any Write/Edit. Then advance the directive doc Status line to 'phase: NEEDS_PLAN'. See .claude/rules/ceo-mode.md#phase-state-machine. Path forward: read every file under .claude/rules/ and .claude/standards/index.md, then advance the directive doc Status line to 'phase: NEEDS_PLAN'."
        }
        'NEEDS_PLAN' {
            if (-not $IsDirectiveDoc) { return "Phase NEEDS_PLAN: only the directive doc ($DirectiveFile) may be edited until the plan is committed and phase advances to NEEDS_DOC_PREREAD. See .claude/rules/ceo-mode.md#phase-state-machine. Path forward: finish drafting acceptance criteria + Files list in the directive doc, then advance Status to 'phase: NEEDS_DOC_PREREAD'." }
            return $null
        }
        'NEEDS_DOC_PREREAD' {
            if (-not $IsDirectiveDoc) { return "Phase NEEDS_DOC_PREREAD: Read every *.feature.md and *.flow.md ancestor of files in the directive's ## Files section before Edit/Write to code. Only the directive doc may be Edited until phase advances to IMPLEMENTING. See .claude/rules/ceo-mode.md#phase-state-machine. Path forward: Read every *.feature.md and *.flow.md ancestor of files in the directive ## Files section, then advance Status to 'phase: IMPLEMENTING'." }
            return $null
        }
        'VERIFYING' {
            if (-not $IsDirectiveDoc) { return "Phase VERIFYING: only the directive doc may be edited. Record per-criterion evidence; do not edit code unless re-entering IMPLEMENTING. See .claude/rules/ceo-mode.md#phase-state-machine. Path forward: record per-criterion evidence in the directive Verification section; if more code work is needed, drop Status back to 'phase: IMPLEMENTING' first." }
            return $null
        }
        default { return $null }
    }
}

# ============ Content rules ============

function Test-R1-DocPreread {
    param($PostContent, $FilePath, $ReadFiles, $AllContent)
    if ($FilePath -notmatch '\.(py|js|html|sql)$') { return $null }
    $FileDir = Split-Path $FilePath -Parent
    if (-not $FileDir -or -not (Test-Path $FileDir)) { return $null }
    $Docs = @()
    $Docs += Get-ChildItem -Path $FileDir -Filter '*.feature.md' -File -ErrorAction SilentlyContinue
    $Docs += Get-ChildItem -Path $FileDir -Filter '*.flow.md' -File -ErrorAction SilentlyContinue
    foreach ($D in $Docs) {
        if ($ReadFiles -notcontains $D.FullName.ToLower()) {
            return "R1 Doc preread: $FilePath has colocated doc $($D.FullName) which has not been Read this session. Read it before Edit/Write. See .claude/rules/ceo-mode.md#documents-first-read-plan-then-update. Path forward: Read the named colocated *.feature.md / *.flow.md file before editing the code -- it owns the contract this code implements."
        }
    }
    return $null
}

function Test-R2-SeedEvidence {
    param($PostContent, $FilePath, $AllContent)
    if ($FilePath -notmatch '[\\/]Scripts[\\/]SQLScripts[\\/]Add[^\\/]+\.py$') { return $null }
    $Lines = $PostContent -split "`n"
    for ($I = 0; $I -lt $Lines.Length; $I++) {
        $Line = $Lines[$I]
        if ($Line -notmatch '(?i)INSERT\s+INTO|VALUES\s*\(') { continue }
        $NumMatches = [regex]::Matches($Line, '(?<![A-Za-z_])(\d{2,})(?![A-Za-z_])')
        foreach ($NM in $NumMatches) {
            $Literal = $NM.Groups[1].Value
            $Citation = $false
            $Cited = $null
            for ($J = [Math]::Max(0,$I-2); $J -le [Math]::Min($Lines.Length-1,$I+2); $J++) {
                $CM = [regex]::Match($Lines[$J], '#\s*from:\s*([^\s:]+)(?::(\d+))?')
                if ($CM.Success) {
                    $Citation = $true
                    $Cited = $CM.Groups[1].Value
                    break
                }
            }
            if (-not $Citation) {
                if (Test-AllowOverride $PostContent $I 'R2' $FilePath) { continue }
                return "R2 Seed evidence: $FilePath line $($I+1) inserts literal '$Literal' with no '# from: <path>' citation nearby. Cite the shootout sidecar, canary command file, or other operator-validated source. See .claude/standards/index.md R2 row + .claude/rules/db-is-authority.md. Path forward: add a '# from: <path>' citation within 2 lines of the INSERT literal, pointing at the operator-validated source (shootout sidecar, canary command file, or feature doc) that contains the literal value."
            }
            $CitedPath = Join-Path $RepoRoot $Cited
            if (-not (Test-Path $CitedPath)) {
                if (Test-AllowOverride $PostContent $I 'R2' $FilePath) { continue }
                return "R2 Seed evidence: $FilePath line $($I+1) cites '$Cited' but that path does not exist. See .claude/standards/index.md R2 row + .claude/rules/db-is-authority.md. Path forward: add a '# from: <path>' citation within 2 lines of the INSERT literal, pointing at the operator-validated source (shootout sidecar, canary command file, or feature doc) that contains the literal value."
            }
            $CitedContent = Get-Content $CitedPath -Raw
            if ($CitedContent -notmatch [regex]::Escape($Literal)) {
                if (Test-AllowOverride $PostContent $I 'R2' $FilePath) { continue }
                return "R2 Seed evidence: $FilePath line $($I+1) cites '$Cited' but literal '$Literal' does not appear in that file. See .claude/standards/index.md R2 row + .claude/rules/db-is-authority.md. Path forward: add a '# from: <path>' citation within 2 lines of the INSERT literal, pointing at the operator-validated source (shootout sidecar, canary command file, or feature doc) that contains the literal value."
            }
        }
    }
    return $null
}

function Test-R3-NoCachedSettings {
    param($PostContent, $FilePath, $AllContent)
    if ($FilePath -notmatch '(?i)(Services|Repositories)[\\/].*\.py$|Features[\\/].*Service\.py$') { return $null }
    $InInit = $false
    $Lines = $PostContent -split "`n"
    for ($I = 0; $I -lt $Lines.Length; $I++) {
        if ($Lines[$I] -match 'def\s+__init__\s*\(') { $InInit = $true; continue }
        if ($InInit -and $Lines[$I] -match '^\s*def\s+\w+') { $InInit = $false }
        if (-not $InInit) { continue }
        if ($Lines[$I] -match 'self\._(cached_\w+|\w+_settings|config_snapshot)\s*=') {
            if (Test-AllowOverride $PostContent $I 'R3' $FilePath) { continue }
            return "R3 No cached settings: $FilePath __init__ assigns to '$($Matches[0])'. Read settings fresh per call; do not cache DB-backed config on long-lived instances. See .claude/rules/db-is-authority.md#the-invariant. Path forward: move the read out of __init__ and into a fresh-per-call method; long-lived services read config on every decision so mid-flight operator changes take effect immediately."
        }
    }
    return $null
}

function Test-R4-NoEnvVars {
    param($PostContent, $FilePath, $AllContent)
    if ($FilePath -notmatch '\.py$') { return $null }
    $Bootstrap = @('Core/Database/DatabaseService.py','StartMediaVortex.py','StopMediaVortex.py','WebService/Main.py')
    $Norm = $FilePath -replace '\\','/'
    foreach ($B in $Bootstrap) { if ($Norm -like "*$B") { return $null } }
    if ($Norm -match '/WorkerService/Main\.py$') { return $null }
    $Lines = $PostContent -split "`n"
    for ($I = 0; $I -lt $Lines.Length; $I++) {
        if ($Lines[$I] -match 'os\.environ\.get\s*\(|os\.getenv\s*\(') {
            if (Test-AllowOverride $PostContent $I 'R4' $FilePath) { continue }
            return "R4 No env vars outside bootstrap: $FilePath line $($I+1) uses os.environ/os.getenv. New runtime config goes in SystemSettings, not env vars. See .claude/rules/db-is-authority.md. Path forward: add the setting to SystemSettings (DB-backed runtime config) and read it via SystemSettingsRepository.GetSystemSetting. Bootstrap files (DatabaseService, StartMediaVortex, Main.py) are the only place env vars are allowed."
        }
    }
    return $null
}

function Test-R5-ExecuteQueryMisuse {
    param($PostContent, $FilePath, $AllContent)
    if ($FilePath -notmatch '\.py$') { return $null }
    $Matches = [regex]::Matches($PostContent, 'ExecuteQuery\s*\(\s*["'']\s*(INSERT|UPDATE|DELETE)\b', 'IgnoreCase')
    if ($Matches.Count -gt 0) {
        $Line = ($PostContent.Substring(0,$Matches[0].Index) -split "`n").Length - 1
        if (Test-AllowOverride $PostContent $Line 'R5' $FilePath) { return $null }
        return "R5 ExecuteQuery misuse: $FilePath uses ExecuteQuery() on a write statement. Use ExecuteNonQuery() for INSERT/UPDATE/DELETE; ExecuteQuery() does not commit. See CLAUDE.md (Database operations section). Path forward: switch to ExecuteNonQuery for the INSERT/UPDATE/DELETE (it auto-commits). If you need the inserted row back, ExecuteNonQuery the write, then ExecuteQuery a SELECT."
    }
    return $null
}

function Test-R6-PathShape {
    param($PostContent, $FilePath, $AllContent)
    if ($FilePath -notmatch '\.py$') { return $null }
    $Lines = $PostContent -split "`n"
    for ($I = 0; $I -lt $Lines.Length; $I++) {
        if ($Lines[$I] -match '(?i)\b(\w*(?:path|filepath)\w*)\s*\.\s*replace\s*\([^)]*\)\s*\.\s*split\s*\(') {
            if (Test-AllowOverride $PostContent $I 'R6' $FilePath) { continue }
            return "R6 Path shape: $FilePath line $($I+1) does .replace().split() on a path-named variable. FilePath is a mix of UNC, drive-letter, and POSIX shapes; use shape-explicit path libs. See .claude/rules/ceo-mode.md#handling-preexisting-comment--doc-violations-encountered-mid-directive. Path forward: for new code, use PathTranslationService for canonical<->local translation, or ntpath / PurePosixPath for shape-explicit string ops. For preexisting code outside this directive's surface, open a new directive (e.g. 'path-shape-migration-<file>') and do the migration there; do not expand the current directive's blast radius."
        }
        if ($Lines[$I] -match '(?i)os\.path\.(dirname|basename|join|split)\s*\(\s*\w*(?:path|filepath)\w*') {
            if (Test-AllowOverride $PostContent $I 'R6' $FilePath) { continue }
            return "R6 Path shape: $FilePath line $($I+1) uses os.path on a path-named variable. os.path is platform-relative; MediaFiles.FilePath shapes are not. See .claude/rules/ceo-mode.md#handling-preexisting-comment--doc-violations-encountered-mid-directive. Path forward: for new code, use PathTranslationService for canonical<->local translation, or ntpath / PurePosixPath for shape-explicit string ops. For preexisting code outside this directive's surface, open a new directive (e.g. 'path-shape-migration-<file>') and do the migration there; do not expand the current directive's blast radius."
        }
    }
    return $null
}

function Test-R7-PolymorphicCascade {
    param($PostContent, $FilePath, $AllContent)
    if ($FilePath -notmatch '[\\/]Scripts[\\/]SQLScripts[\\/].*\.py$') { return $null }
    if ($PostContent -match '(?is)(ALTER|CREATE)\s+TABLE[^;]*?(QueueId|JobId|EntityId|TargetId)[^;]*?ON\s+DELETE\s+CASCADE') {
        $Line = ($PostContent.Substring(0,$Matches[0].Index) -split "`n").Length - 1
        if (Test-AllowOverride $PostContent $Line 'R7' $FilePath) { return $null }
        return "R7 Polymorphic CASCADE: $FilePath has ON DELETE CASCADE on a polymorphic FK column. Use root-cause caller fix + recurring sweep instead. See .claude/rules/data-integrity.md and memory/feedback_polymorphic_fk_no_cascade.md. Path forward: drop the CASCADE; fix the caller that creates orphaned rows; add a recurring sweep job that WARN-logs each removal."
    }
    return $null
}

function Test-R8-TestPlacement {
    param($PostContent, $FilePath, $AllContent, $IsNew)
    if (-not $IsNew) { return $null }
    $Name = Split-Path $FilePath -Leaf
    if ($Name -notmatch '^(test_.*|Test.*)\.py$') { return $null }
    $Norm = $FilePath -replace '\\','/'
    if ($Norm -match '/Tests/(Contract|Unit)/') { return $null }
    return "R8 Test placement: new test file $FilePath must live under Tests/Contract/ or Tests/Unit/. See .claude/rules/test-placement.md. Path forward: move the new test file to Tests/Contract/ (live-DB integration) or Tests/Unit/ (no I/O); test fixtures duplicate across suites rather than import across them."
}

function Test-R9-LikeEscape {
    param($PostContent, $FilePath, $AllContent)
    if ($FilePath -notmatch '\.py$') { return $null }
    $FuncMatches = [regex]::Matches($PostContent, '(?ms)^\s*def\s+(\w+)\s*\([^)]*\)\s*:\s*\n(.*?)(?=\n\S|\Z)')
    foreach ($FM in $FuncMatches) {
        $Body = $FM.Groups[2].Value
        if ($Body -match '(?i)\bLIKE\s+(\%s|\?|''%)') {
            if ($Body -notmatch 'EscapeLikePattern\s*\(') {
                $Line = ($PostContent.Substring(0,$FM.Index) -split "`n").Length - 1
                if (Test-AllowOverride $PostContent $Line 'R9' $FilePath) { continue }
                return "R9 LIKE without escape: $FilePath function '$($FM.Groups[1].Value)' uses LIKE without calling EscapeLikePattern(). Paths contain %, _, ! which break LIKE matching."
            }
        }
    }
    return $null
}

function Test-R10-ClaimPredicate {
    param($PostContent, $FilePath, $AllContent)
    if ($FilePath -notmatch '[\\/]Repositories[\\/].*\.py$') { return $null }
    $FuncMatches = [regex]::Matches($PostContent, '(?ms)^\s*def\s+(Claim\w*)\s*\([^)]*\)\s*:\s*\n(.*?)(?=\n\s*def\s|\Z)')
    $HasImport = $PostContent -match 'BuildClaimPredicate'
    foreach ($FM in $FuncMatches) {
        $Body = $FM.Groups[2].Value
        if ($Body -match '(?i)EXISTS\s*\(\s*SELECT\s+1\s+FROM\s+Workers') {
            if (-not $HasImport -or $Body -notmatch 'BuildClaimPredicate') {
                $Line = ($PostContent.Substring(0,$FM.Index) -split "`n").Length - 1
                if (Test-AllowOverride $PostContent $Line 'R10' $FilePath) { continue }
                return "R10 Claim bypass: $FilePath function '$($FM.Groups[1].Value)' rolls its own Workers EXISTS clause. Call Core.Database.WorkerCapabilityPredicate.BuildClaimPredicate."
            }
        }
    }
    return $null
}

function Test-R11-MigrationIdempotency {
    param($PostContent, $FilePath, $AllContent)
    if ($FilePath -notmatch '[\\/]Scripts[\\/]SQLScripts[\\/].*\.py$') { return $null }
    $Patterns = @(
        @{ Rx = '(?i)CREATE\s+TABLE\s+(?!IF\s+NOT\s+EXISTS)'; Msg = "CREATE TABLE without IF NOT EXISTS" },
        @{ Rx = '(?i)CREATE\s+(UNIQUE\s+)?INDEX\s+(?!IF\s+NOT\s+EXISTS)'; Msg = "CREATE INDEX without IF NOT EXISTS" },
        @{ Rx = '(?i)INSERT\s+INTO\s+\w+[^;]*VALUES[^;]*(?<!ON\s+CONFLICT[^;]*)(?=;|$)'; Msg = "INSERT without ON CONFLICT" }
    )
    foreach ($P in $Patterns) {
        if ($PostContent -match $P.Rx) {
            $Idx = ([regex]$P.Rx).Match($PostContent).Index
            $Line = ($PostContent.Substring(0,$Idx) -split "`n").Length - 1
            if (Test-AllowOverride $PostContent $Line 'R11' $FilePath) { continue }
            return "R11 Migration idempotency: $FilePath has $($P.Msg). Migrations must be safe to re-run. See .claude/rules/data-integrity.md (idempotent migrations). Path forward: add IF NOT EXISTS to CREATE TABLE / CREATE INDEX, and ON CONFLICT DO NOTHING (or DO UPDATE) to INSERT INTO. If no unique constraint exists, use a pre-check SELECT + conditional INSERT and override this rule with a documented reason."
        }
    }
    return $null
}

function Test-R12-CommentVolume {
    param($PostContent, $FilePath, $AllContent)
    if ($FilePath -notmatch '\.py$') { return $null }
    $Lines = $PostContent -split "`n"
    $BlockStart = -1
    for ($I = 0; $I -lt $Lines.Length; $I++) {
        if ($Lines[$I] -match '^\s*#') {
            if ($BlockStart -lt 0) { $BlockStart = $I }
            elseif (($I - $BlockStart) -ge 1) {
                if (Test-AllowOverride $PostContent $I 'R12' $FilePath) { $BlockStart = -1; continue }
                return "R12 Comment volume: $FilePath line $($BlockStart+1)-$($I+1) is a multi-line # comment block. One-line max; rationale belongs in the directive doc. See .claude/rules/ceo-mode.md#handling-preexisting-comment--doc-violations-encountered-mid-directive. Path forward: classify the block first -- (a) pure WHAT-redundancy: delete entirely; (b) permanent-invariant WHY (BUG-NNNN, hard-won constraint): MOVE the content to KNOWN-ISSUES.md or the appropriate *.feature.md, leave a single-line anchor in code ('# BUG-0005' or '# see worker-lifecycle.feature.md C6'); (c) active-directive WHY: put the content in the current directive doc, leave a '# directive: <slug>' anchor; (d) surprising WHY that fits nowhere: collapse to a single in-place comment line. If the scope is large (many blocks across many files), open a new directive ('<file>-comment-promotion') and do the classification there."
            }
        } else { $BlockStart = -1 }
    }
    $DocMatches = [regex]::Matches($PostContent, '(?ms)"""(.*?)"""')
    foreach ($DM in $DocMatches) {
        $Body = $DM.Groups[1].Value
        if (($Body -split "`n").Length -gt 1) {
            $Line = ($PostContent.Substring(0,$DM.Index) -split "`n").Length - 1
            if (Test-AllowOverride $PostContent $Line 'R12' $FilePath) { continue }
            return "R12 Comment volume: $FilePath line $($Line+1) has a multi-line docstring. Single-line max; rationale belongs in the directive doc. See .claude/rules/ceo-mode.md#handling-preexisting-comment--doc-violations-encountered-mid-directive. Path forward: classify the block first -- (a) pure WHAT-redundancy: delete entirely; (b) permanent-invariant WHY (BUG-NNNN, hard-won constraint): MOVE the content to KNOWN-ISSUES.md or the appropriate *.feature.md, leave a single-line anchor in code ('# BUG-0005' or '# see worker-lifecycle.feature.md C6'); (c) active-directive WHY: put the content in the current directive doc, leave a '# directive: <slug>' anchor; (d) surprising WHY that fits nowhere: collapse to a single in-place comment line. If the scope is large (many blocks across many files), open a new directive ('<file>-comment-promotion') and do the classification there."
        }
    }
    if ($PostContent -match '^\s*"""') {
        if (-not (Test-AllowOverride $PostContent 0 'R12' $FilePath)) {
            return "R12 Comment volume: $FilePath has a module-level docstring. Documentation lives in the directive doc only. See .claude/rules/ceo-mode.md#handling-preexisting-comment--doc-violations-encountered-mid-directive. Path forward: classify the block first -- (a) pure WHAT-redundancy: delete entirely; (b) permanent-invariant WHY (BUG-NNNN, hard-won constraint): MOVE the content to KNOWN-ISSUES.md or the appropriate *.feature.md, leave a single-line anchor in code ('# BUG-0005' or '# see worker-lifecycle.feature.md C6'); (c) active-directive WHY: put the content in the current directive doc, leave a '# directive: <slug>' anchor; (d) surprising WHY that fits nowhere: collapse to a single in-place comment line. If the scope is large (many blocks across many files), open a new directive ('<file>-comment-promotion') and do the classification there."
        }
    }
    return $null
}

function Test-R13-NoNewFeatureDocs {
    param($PostContent, $FilePath, $AllContent, $IsNew)
    if (-not $IsNew) { return $null }
    if ($FilePath -match '\.(feature|flow)\.md$') {
        return "R13 New feature/flow doc: $FilePath is a new *.feature.md / *.flow.md file. Documentation lives in the directive doc only -- update .claude/directive.md instead. See .claude/rules/ceo-mode.md#documents-first-read-plan-then-update. Path forward: put the new documentation in the active directive doc (.claude/directive.md). On directive close, content that became a permanent invariant gets promoted to the appropriate existing *.feature.md / *.flow.md; transient operational notes archive with the directive in .claude/directives/closed/."
    }
    return $null
}

function Test-R14-AnnotationDrift {
    param($PostContent, $FilePath, $ToolName, $ToolInput, $AllContent)
    if ($FilePath -notmatch '\.(feature|flow)\.md$') { return $null }
    $Added = Get-AddedLines $ToolName $ToolInput
    foreach ($Line in $Added) {
        if ($Line -match '(?i)(removed\s+\d{4}-\d{2}-\d{2}|deprecated|no longer used|previously\s+|formerly\s+)') {
            if (Test-AllowOverride $PostContent 0 'R14' $FilePath) { continue }
            return "R14 Annotation drift: $FilePath edit adds an annotation line ('$($Line.Trim())'). Delete the obsolete section instead of annotating it. See .claude/rules/ceo-mode.md#documents-first-read-plan-then-update step 2. Path forward: delete the obsolete section from the feature/flow doc entirely; the directive doc carries the reason for removal in its Status block, so the obsolete section in the feature doc has no remaining job."
        }
    }
    return $null
}

function Test-R15-DirectiveAnchor {
    param($PostContent, $FilePath, $DirectiveFiles)
    if ($FilePath -notmatch '\.py$') { return $null }
    $Slug = Get-DirectiveSlug
    if (-not $Slug) { return $null }
    $Norm = $FilePath -replace '\\','/'
    $InScope = $false
    foreach ($DF in $DirectiveFiles) {
        $DFNorm = $DF -replace '\\','/'
        if ($Norm -like "*$DFNorm" -or $Norm -like "*/$DFNorm") { $InScope = $true; break }
    }
    if (-not $InScope) { return $null }
    $Lines = $PostContent -split "`n"
    for ($I = 0; $I -lt $Lines.Length; $I++) {
        if ($Lines[$I] -match '^\s*(def|class)\s+\w+') {
            $Prev = if ($I -gt 0) { $Lines[$I-1] } else { '' }
            if ($Prev -notmatch "#\s*directive:\s*$([regex]::Escape($Slug))") {
                if (Test-AllowOverride $PostContent $I 'R15' $FilePath) { continue }
                return "R15 Directive anchor: $FilePath line $($I+1) defines a function/class without '# directive: $Slug' on the line above. This file is in the active directive's scope. See .claude/standards/index.md R15 row. Path forward: add '# directive: <active-slug>' on the line immediately above the def/class. This is the grep anchor that lets future readers find the directive that explains why this function exists in its current shape."
            }
        }
    }
    return $null
}

# ============ Main ============

$HookInput = Read-StdinJson
if (-not $HookInput) { Emit-Allow }

$ToolName = $HookInput.tool_name
$ToolInput = $HookInput.tool_input
$TranscriptPath = $HookInput.transcript_path

if ($ToolName -notin @('Write','Edit','MultiEdit')) { Emit-Allow }
if (-not $ToolInput.file_path) { Emit-Allow }

$FilePath = $ToolInput.file_path

# Skip enforcement for hook scripts themselves and directive maintenance
$NormFP = $FilePath -replace '\\','/'
if ($NormFP -match '/\.claude/(hooks|standards|directive\.md|directives/|rules/|plans/)') {
    # Hook + standards files are exempt from R1-R15 (they ARE the standards layer).
    # Phase gate still applies.
    $State = Get-SessionState
    $PhaseRefusal = Test-PhaseGate $State $ToolName $ToolInput
    if ($PhaseRefusal) { Emit-Deny $PhaseRefusal }
    Emit-Allow
}

$State = Get-SessionState
$PhaseRefusal = Test-PhaseGate $State $ToolName $ToolInput
if ($PhaseRefusal) { Emit-Deny $PhaseRefusal }

$IsNew = -not (Test-Path $FilePath)
$PostContent = Synthesize-PostEditContent $ToolName $ToolInput
$ReadFiles = Get-ReadFilesFromTranscript $TranscriptPath
$DirectiveFiles = Get-DirectiveFiles

$Rules = @(
    { Test-R1-DocPreread $PostContent $FilePath $ReadFiles $PostContent },
    { Test-R2-SeedEvidence $PostContent $FilePath $PostContent },
    { Test-R3-NoCachedSettings $PostContent $FilePath $PostContent },
    { Test-R4-NoEnvVars $PostContent $FilePath $PostContent },
    { Test-R5-ExecuteQueryMisuse $PostContent $FilePath $PostContent },
    { Test-R6-PathShape $PostContent $FilePath $PostContent },
    { Test-R7-PolymorphicCascade $PostContent $FilePath $PostContent },
    { Test-R8-TestPlacement $PostContent $FilePath $PostContent $IsNew },
    { Test-R9-LikeEscape $PostContent $FilePath $PostContent },
    { Test-R10-ClaimPredicate $PostContent $FilePath $PostContent },
    { Test-R11-MigrationIdempotency $PostContent $FilePath $PostContent },
    { Test-R12-CommentVolume $PostContent $FilePath $PostContent },
    { Test-R13-NoNewFeatureDocs $PostContent $FilePath $PostContent $IsNew },
    { Test-R14-AnnotationDrift $PostContent $FilePath $ToolName $ToolInput $PostContent },
    { Test-R15-DirectiveAnchor $PostContent $FilePath $DirectiveFiles }
)

try {
    foreach ($R in $Rules) {
        $Refusal = & $R
        if ($Refusal) { Emit-Deny $Refusal }
    }
} catch {
    Emit-Ask "Standards hook errored: $($_.Exception.Message). Asking for human review."
}

Emit-Allow
