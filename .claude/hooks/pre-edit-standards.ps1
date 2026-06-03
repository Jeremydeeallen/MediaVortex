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
$RefusalStateFile = Join-Path $RepoRoot ".claude\.refusal-state.json"

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

function Get-CurrentSessionStamp {
    if (Test-Path $StateFile) {
        try {
            $S = Get-Content $StateFile -Raw | ConvertFrom-Json
            return $S.session_started_at
        } catch { }
    }
    return ""
}

function Increment-RefusalCount {
    param([string]$RuleId, [string]$FilePath)
    if (-not $RuleId -or -not $FilePath) { return 1 }
    $CurrentStamp = Get-CurrentSessionStamp
    $Counts = @{}
    if (Test-Path $RefusalStateFile) {
        try {
            $Loaded = Get-Content $RefusalStateFile -Raw | ConvertFrom-Json
            if ($Loaded.session_stamp -eq $CurrentStamp -and $Loaded.counts) {
                foreach ($Prop in $Loaded.counts.PSObject.Properties) {
                    $Counts[$Prop.Name] = [int]$Prop.Value
                }
            }
        } catch { }
    }
    $Key = "$RuleId|$($FilePath.ToLower())"
    if ($Counts.ContainsKey($Key)) { $Counts[$Key] = [int]$Counts[$Key] + 1 }
    else { $Counts[$Key] = 1 }
    $Out = @{ session_stamp = $CurrentStamp; counts = $Counts }
    $Json = $Out | ConvertTo-Json -Compress
    Set-Content -Path $RefusalStateFile -Value $Json -Encoding UTF8
    return $Counts[$Key]
}

function Emit-DenyWithRepeatDetection {
    param([string]$Reason, [string]$FilePath)
    # directive: hook-honesty-fence -- agent-stop header on every refusal.
    # Fires on the FIRST refusal too, not just on repeats. Prior design only
    # warned after token waste was already in flight.
    $StopHeader = @'
STOP. Do not search for a workaround. The Path forward below is the only acceptable answer.
Variants -- clever or otherwise -- will be refused. Iterating costs tokens and produces nothing.
If the Path forward is genuinely unworkable, ask the operator with a one-sentence reason instead of trying again.

'@
    $Reason = $StopHeader + $Reason
    $RuleMatch = [regex]::Match($Reason, '(?m)^(R\d+|Phase\s+\S+)')
    if ($RuleMatch.Success -and $FilePath) {
        $RuleId = $RuleMatch.Groups[1].Value
        $Count = Increment-RefusalCount $RuleId $FilePath
        if ($Count -ge 2) {
            $Ord = switch ($Count) { 1 {'1st'} 2 {'2nd'} 3 {'3rd'} default { "${Count}th" } }
            $StoppedPreamble = @"
STOPPED -- this is the $Ord refusal of $RuleId on this file in this session.

The 'Path forward:' in the prescribed text below is the answer. Further variants of the workaround you keep trying will continue to be refused; iterating costs tokens without progress.

Pivot to ONE of:
  (a) Do the prescribed Path forward LITERALLY (no creative reinterpretation, no clever variant).
  (b) Ask the operator to unblock with a one-sentence statement of why the prescribed path is unworkable.

Do NOT open a follow-up directive to escape -- we are working on the CURRENT directive; pivoting out is itself a workaround pattern. Fix it here, not later.

Original refusal follows:

"@
            $Reason = $StoppedPreamble + $Reason
        }
    }
    Emit-Deny $Reason
}

function Get-SessionState {
    # Directive doc is authoritative for slug + phase (session-state may be stale within a session
    # because SessionStart runs once at session boot and phase advances happen later via directive edits).
    $DirSlug = Get-DirectiveSlug
    $DirPhase = Get-DirectivePhase
    if (Test-Path $StateFile) {
        try {
            $S = Get-Content $StateFile -Raw | ConvertFrom-Json
            if ($DirPhase) { $S.phase = $DirPhase }
            if ($DirSlug) { $S.directive_slug = $DirSlug }
            return $S
        } catch { }
    }
    if ($DirSlug -and $DirPhase) {
        return [PSCustomObject]@{ directive_slug = $DirSlug; phase = $DirPhase }
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

function Get-R18Overrides {
    if (-not (Test-Path $DirectiveFile)) { return @() }
    $Text = Get-Content $DirectiveFile -Raw
    $M = [regex]::Match($Text, '(?ms)###\s*R18\s+overrides\s*\r?\n(.*?)(?=\r?\n###\s|\r?\n##\s|\r?\n---|\Z)')
    if (-not $M.Success) { return @() }
    $Out = @()
    foreach ($Line in ($M.Groups[1].Value -split "`n")) {
        $T = $Line.Trim().TrimStart('-','*',' ','`t')
        if (-not $T) { continue }
        $Cell = ($T -split '\s+--\s+|\s+#\s+|\s+:\s+',2)[0].Trim()
        if ($Cell) { $Out += ($Cell -replace '\\','/').ToLower() }
    }
    return $Out
}

function Test-R1FlowStubSatisfied {
    param($PostContent, $FilePath, $ReadFiles)
    # Returns $true when the code carries a `# see <flow-slug>.ST<N>` anchor,
    # the named *.flow.md exists somewhere in the repo, and a Read covers the ST<N> line.
    # In that case the colocated *.feature.md preread is waived (R1 criterion 6 extension).
    if (-not $ReadFiles -or -not ($ReadFiles -is [hashtable]) -or $ReadFiles.Count -eq 0) { return $false }
    $Anchors = @()
    foreach ($M in [regex]::Matches($PostContent, '#\s*see\s+([a-z0-9-]+)\.(ST\d+)')) {
        $Anchors += @{ slug = $M.Groups[1].Value.ToLower(); id = $M.Groups[2].Value }
    }
    if ($Anchors.Count -eq 0) { return $false }
    $FlowDocs = Get-ChildItem -Path $RepoRoot -Filter '*.flow.md' -Recurse -File -ErrorAction SilentlyContinue
    foreach ($A in $Anchors) {
        foreach ($FD in $FlowDocs) {
            $DocLower = $FD.FullName.ToLower()
            if (-not $ReadFiles.ContainsKey($DocLower)) { continue }
            $DocLines = $null
            try { $DocLines = Get-Content $FD.FullName -Encoding UTF8 } catch { continue }
            $Slug = $null
            for ($I = 0; $I -lt [Math]::Min(15, $DocLines.Length); $I++) {
                if ($DocLines[$I] -match '^\*\*Slug:\*\*\s*(\S+)') { $Slug = $Matches[1].ToLower(); break }
            }
            if ($Slug -ne $A.slug) { continue }
            $SectionLine = 0
            for ($I = 0; $I -lt $DocLines.Length; $I++) {
                if ($DocLines[$I] -match "\b$([regex]::Escape($A.id))\b") { $SectionLine = $I + 1; break }
            }
            if ($SectionLine -eq 0) { continue }
            foreach ($R in $ReadFiles[$DocLower]) {
                $Start = if ($R.offset -gt 0) { $R.offset } else { 1 }
                $End = if ($R.limit -gt 0) { $Start + $R.limit - 1 } else { $DocLines.Length }
                if ($SectionLine -ge $Start -and $SectionLine -le $End) { return $true }
            }
        }
    }
    return $false
}

function Get-ReadFilesFromTranscript {
    param([string]$TranscriptPath)
    # Returns hashtable: { path_lowercase => array of @{ offset = int; limit = int } }.
    # offset defaults to 1 (start), limit 0 means whole-file. Multiple Reads accumulate.
    if (-not $TranscriptPath -or -not (Test-Path $TranscriptPath)) { return @{} }
    $Files = @{}
    foreach ($Line in (Get-Content $TranscriptPath)) {
        foreach ($M in [regex]::Matches($Line, '"name"\s*:\s*"Read"[^}]*?"input"\s*:\s*\{([^}]*)\}')) {
            $Inner = $M.Groups[1].Value
            $PathM = [regex]::Match($Inner, '"file_path"\s*:\s*"([^"]+)"')
            if (-not $PathM.Success) { continue }
            $P = ($PathM.Groups[1].Value -replace '\\\\', '\').ToLower()
            $OffsetM = [regex]::Match($Inner, '"offset"\s*:\s*(\d+)')
            $LimitM = [regex]::Match($Inner, '"limit"\s*:\s*(\d+)')
            $Offset = if ($OffsetM.Success) { [int]$OffsetM.Groups[1].Value } else { 1 }
            $Limit = if ($LimitM.Success) { [int]$LimitM.Groups[1].Value } else { 0 }
            if (-not $Files.ContainsKey($P)) { $Files[$P] = @() }
            $Files[$P] += @{ offset = $Offset; limit = $Limit }
        }
    }
    return $Files
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
            $Result = $Current.Replace($Old, $New)
            if ($Result -ne $Current) { return $Result }
            return $Current.Replace($Old.Replace("`r`n","`n"), $New).Replace($Old.Replace("`n","`r`n"), $New)
        } else {
            $Idx = $Current.IndexOf($Old)
            if ($Idx -lt 0) {
                $CurNorm = $Current -replace "`r`n","`n"
                $OldNorm = $Old -replace "`r`n","`n"
                $Idx2 = $CurNorm.IndexOf($OldNorm)
                if ($Idx2 -lt 0) { return $Current }
                return $CurNorm.Substring(0, $Idx2) + $New + $CurNorm.Substring($Idx2 + $OldNorm.Length)
            }
            return $Current.Substring(0, $Idx) + $New + $Current.Substring($Idx + $Old.Length)
        }
    }
    if ($ToolName -eq 'MultiEdit') {
        $Buf = $Current
        foreach ($E in $ToolInput.edits) {
            if ($E.replace_all) { $Buf = $Buf.Replace($E.old_string, $E.new_string) }
            else {
                $Idx = $Buf.IndexOf($E.old_string)
                if ($Idx -lt 0) {
                    $BufNorm = $Buf -replace "`r`n","`n"
                    $OldNorm = $E.old_string -replace "`r`n","`n"
                    $Idx2 = $BufNorm.IndexOf($OldNorm)
                    if ($Idx2 -ge 0) { $Buf = $BufNorm.Substring(0, $Idx2) + $E.new_string + $BufNorm.Substring($Idx2 + $OldNorm.Length) }
                } else {
                    $Buf = $Buf.Substring(0, $Idx) + $E.new_string + $Buf.Substring($Idx + $E.old_string.Length)
                }
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

function Get-EditRegion {
    # Returns @{ Mode = 'WholeFile' | 'EditRegion' | 'NoRegion'; Regions = @(@{start;end}, ...) }
    # WholeFile: caller should treat all lines as in-region (Write tool, or defensive fallback).
    # EditRegion: caller filters violations to lines inside Regions (Edit/MultiEdit with non-empty new_string).
    # NoRegion: caller skips the check entirely (pure-deletion Edits author no new content).
    # Line numbers are 1-based and reference the POST-edit content (the synthesized result).
    param($ToolName, $ToolInput, $PostContent)
    $PostLineCount = ($PostContent -split "`n").Count
    if ($ToolName -eq 'Write') {
        return @{ Mode = 'WholeFile'; Regions = @(@{ start = 1; end = $PostLineCount }) }
    }
    $Edits = @()
    if ($ToolName -eq 'Edit') { $Edits = @($ToolInput) }
    elseif ($ToolName -eq 'MultiEdit') { $Edits = @($ToolInput.edits) }
    else {
        return @{ Mode = 'WholeFile'; Regions = @(@{ start = 1; end = $PostLineCount }) }
    }
    $AllNewEmpty = $true
    $Regions = @()
    foreach ($E in $Edits) {
        $New = if ($E.new_string) { [string]$E.new_string } else { '' }
        if ($New -ne '') { $AllNewEmpty = $false }
        if ($New -eq '') { continue }
        # Locate new_string in post-content. Try exact match, then CRLF/LF normalized.
        $Idx = $PostContent.IndexOf($New)
        if ($Idx -lt 0) {
            $PostNorm = $PostContent -replace "`r`n","`n"
            $NewNorm = $New -replace "`r`n","`n"
            $Idx2 = $PostNorm.IndexOf($NewNorm)
            if ($Idx2 -lt 0) { continue }
            $StartLine = ($PostNorm.Substring(0, $Idx2) -split "`n").Count
            $LineCount = ($NewNorm -split "`n").Count
        } else {
            $StartLine = ($PostContent.Substring(0, $Idx) -split "`n").Count
            $LineCount = ($New -split "`n").Count
        }
        $EndLine = $StartLine + $LineCount - 1
        $Regions += @{ start = $StartLine; end = $EndLine }
    }
    if ($AllNewEmpty) {
        return @{ Mode = 'NoRegion'; Regions = @() }
    }
    if ($Regions.Count -eq 0) {
        # Defensive: new_strings were non-empty but couldn't be located. Fall back to whole-file
        # rather than silently skipping checks.
        return @{ Mode = 'WholeFile'; Regions = @(@{ start = 1; end = $PostLineCount }) }
    }
    return @{ Mode = 'EditRegion'; Regions = $Regions }
}

function Test-LineInEditRegion {
    # 1-based line number; $EditRegion is the hashtable returned by Get-EditRegion.
    # WholeFile -> always true. NoRegion -> always false. EditRegion -> true iff line falls in any range.
    param([int]$LineNumber, $EditRegion)
    if (-not $EditRegion) { return $true }
    if ($EditRegion.Mode -eq 'WholeFile') { return $true }
    if ($EditRegion.Mode -eq 'NoRegion') { return $false }
    foreach ($R in $EditRegion.Regions) {
        if ($LineNumber -ge $R.start -and $LineNumber -le $R.end) { return $true }
    }
    return $false
}

function Test-RangeOverlapsEditRegion {
    # Returns true iff ANY line in [startLine, endLine] (1-based inclusive) is in the edit region.
    param([int]$StartLine, [int]$EndLine, $EditRegion)
    if (-not $EditRegion) { return $true }
    if ($EditRegion.Mode -eq 'WholeFile') { return $true }
    if ($EditRegion.Mode -eq 'NoRegion') { return $false }
    foreach ($R in $EditRegion.Regions) {
        if ($StartLine -le $R.end -and $EndLine -ge $R.start) { return $true }
    }
    return $false
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

# ============ Task-delegation opt-in gate ============
# directive: task-delegation-opt-in
function Test-TaskDelegationGate {
    param($State, $ToolName, $ToolInput)
    $FilePath = $ToolInput.file_path
    if (-not $FilePath) { return $null }
    $NormFP = ($FilePath -replace '\\','/').ToLower()
    $MarkerPath = Join-Path $RepoRoot ".claude\.task-delegation-on"
    $NormMarker = (($MarkerPath -replace '\\','/').ToLower())
    if ($NormFP -eq $NormMarker) {
        return "Operator-only file: .claude/.task-delegation-on is a manual opt-in toggle for task-delegation mode. The operator must create/delete this file directly (New-Item / Remove-Item). Claude cannot toggle task-delegation. See .claude/rules/ceo-mode.md (Task-delegation mode is operator opt-in)."
    }
    if ($State -and $State.phase) { return $null }
    if (Test-Path $MarkerPath) { return $null }
    if ($NormFP -match '/\.claude/directive\.md$') { return $null }
    return "No active directive AND .claude/.task-delegation-on marker absent. Two paths forward: (1) run /n <slug> to scaffold a directive, OR (2) ask the operator to create .claude/.task-delegation-on (e.g. 'New-Item .claude/.task-delegation-on -ItemType File') to enable task-delegation mode for this session. See .claude/rules/ceo-mode.md (Task-delegation mode is operator opt-in)."
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
            # Allow edits to the directive doc itself -- the operator needs to edit it to advance phase.
            if ($IsDirectiveDoc) { return $null }
            return "Phase NEEDS_STANDARDS_REVIEW: Read every file under .claude/rules/ and .claude/standards/index.md before any Write/Edit. Then advance the directive doc Status line to 'phase: NEEDS_PLAN'. See .claude/rules/ceo-mode.md (Phase state machine section). Path forward: read every file under .claude/rules/ and .claude/standards/index.md, then advance the directive doc Status line to 'phase: NEEDS_PLAN'."
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
        'IMPLEMENTING' {
            # Snapshot directive size at IMPLEMENTING -> DELIVERING transition.
            # Snapshot is later used by the DELIVERING -> Closed gate to enforce anti-drift (directive must not grow during DELIVERING).
            if ($IsDirectiveDoc) {
                $PostContent = Synthesize-PostEditContent $ToolName $ToolInput
                if ($PostContent -match '(?m)^\*\*Status:\*\*\s*Active\s*--\s*phase:\s*DELIVERING') {
                    $SnapshotFile = Join-Path $RepoRoot ".claude\.delivering-snapshot.json"
                    $Slug = Get-DirectiveSlug
                    if ($Slug) {
                        $Snap = @{
                            slug = $Slug
                            size_bytes = [Text.Encoding]::UTF8.GetByteCount($PostContent)
                            timestamp = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ")
                        } | ConvertTo-Json -Compress
                        Set-Content -Path $SnapshotFile -Value $Snap -Encoding UTF8
                    }
                }
            }
            return $null
        }
        'DELIVERING' {
            if (-not $IsDirectiveDoc) { return $null }
            # Gate the DELIVERING -> Closed transition: Promotions section must be non-empty;
            # directive must not have grown beyond snapshot * tolerance during DELIVERING.
            $PostContent = Synthesize-PostEditContent $ToolName $ToolInput
            $IsClosing = $PostContent -match '(?m)^\*\*Status:\*\*\s*Closed'
            if (-not $IsClosing) { return $null }
            # Gate (a): Promotions section present + non-empty (ignoring template placeholder lines).
            $PromoMatch = [regex]::Match($PostContent, '(?ms)###\s*Promotions\s*\r?\n(.*?)(?=\r?\n###\s|\r?\n##\s|\r?\n---|\Z)')
            $HasPromoContent = $false
            if ($PromoMatch.Success) {
                $PromoBody = $PromoMatch.Groups[1].Value
                foreach ($Line in ($PromoBody -split "`n")) {
                    $T = $Line.Trim()
                    if (-not $T) { continue }
                    if ($T.StartsWith('(') -or $T.StartsWith('|') -or $T.StartsWith('Required ') -or $T.StartsWith('Each row ') -or $T.StartsWith('If a ') -or $T.StartsWith('The hook only ')) { continue }
                    if ($T -match '^-\s' -or $T -match '^\*\s' -or $T -match '\S\s+\S') { $HasPromoContent = $true; break }
                }
                # Table rows with actual content (not the placeholder `<...>` row) also count.
                if (-not $HasPromoContent) {
                    foreach ($Line in ($PromoBody -split "`n")) {
                        if ($Line -match '^\s*\|' -and $Line -notmatch '\|---' -and $Line -notmatch '`<' -and $Line.Trim() -ne '|') {
                            $Cells = ($Line -split '\|') | Where-Object { $_.Trim() }
                            if ($Cells.Count -ge 2) { $HasPromoContent = $true; break }
                        }
                    }
                }
            }
            # directive: hook-honesty-fence -- tighten "no promotions" escape.
            # When the directive's ### Files block names a schema migration
            # (Scripts/SQLScripts/Add*.py), refuse a "no promotions" row. A
            # migration is always a contract change.
            if ($HasPromoContent) {
                $PromoLooksEmpty = $PromoMatch.Groups[1].Value -match '(?i)no\s+promotions\s*\|'
                if ($PromoLooksEmpty) {
                    $FilesMatch = [regex]::Match($PostContent, '(?ms)###\s*Files\s*\r?\n.*?```(.*?)```')
                    if ($FilesMatch.Success -and $FilesMatch.Groups[1].Value -match '(?i)Scripts[\\/]SQLScripts[\\/]Add[^\s]+\.py') {
                        return "Phase DELIVERING -> Closed: directive's ### Files block names a schema migration (Scripts/SQLScripts/Add*.py) but the Promotions table is 'no promotions'. A migration is always a contract change. Path forward: name the *.feature.md / *.flow.md that captures the new schema's contract, edit that doc in this directive's scope, and put a real row in Promotions pointing at it."
                    }
                }
            }
            if (-not $HasPromoContent) {
                return "Phase DELIVERING -> Closed: directive cannot close without a non-empty ### Promotions section. See .claude/rules/doc-layering.md (Lifecycle: directive -> features/flows) + .claude/directives/_template.md. Path forward: populate the ### Promotions table with one row per piece of durable content (source artifact -> target *.feature.md / *.flow.md file + commit SHA). If the directive has no durable content to promote (e.g. pure bugfix), add a single row 'no promotions | n/a | <reason>'. The hook only checks the section is non-empty."
            }
            # Gate (b): anti-drift size check against snapshot taken at IMPLEMENTING -> DELIVERING.
            $SnapshotFile = Join-Path $RepoRoot ".claude\.delivering-snapshot.json"
            if (Test-Path $SnapshotFile) {
                try {
                    $Snap = Get-Content $SnapshotFile -Raw | ConvertFrom-Json
                    $CurrentSlug = Get-DirectiveSlug
                    if ($Snap.slug -eq $CurrentSlug -and $Snap.size_bytes) {
                        $CurrentBytes = [Text.Encoding]::UTF8.GetByteCount($PostContent)
                        $MaxAllowed = [int]([double]$Snap.size_bytes * 1.10)
                        if ($CurrentBytes -gt $MaxAllowed) {
                            return "Phase DELIVERING -> Closed: directive grew from $($Snap.size_bytes) bytes (at IMPLEMENTING->DELIVERING) to $CurrentBytes bytes -- exceeds 10% tolerance ($MaxAllowed bytes max). Growth during DELIVERING means content was DUPLICATED into the directive rather than PROMOTED out to its permanent home. See .claude/rules/doc-layering.md. Path forward: move the new content INTO the target *.feature.md / *.flow.md listed in the Promotions table, then DELETE it from the directive doc. The directive's job at DELIVERING is to shrink as content moves to its permanent home, not grow."
                        }
                    }
                } catch { }
            }
            return $null
        }
        default { return $null }
    }
}

# ============ Content rules ============

function Test-R1-DocPreread {
    param($PostContent, $FilePath, $ReadFiles, $AllContent)
    # $ReadFiles is a hashtable from Get-ReadFilesFromTranscript: { path_lower => array of @{offset, limit} }.
    if ($FilePath -notmatch '\.(py|js|html|sql)$') { return $null }
    # Flow-stub satisfaction (R1 extension per flow-docs-as-hub criterion 6):
    # if the code carries `# see <flow-slug>.ST<N>` and the named *.flow.md has been Read
    # covering the ST<N> section, colocated *.feature.md preread is waived.
    if (Test-R1FlowStubSatisfied $PostContent $FilePath $ReadFiles) { return $null }
    $FileDir = Split-Path $FilePath -Parent
    if (-not $FileDir -or -not (Test-Path $FileDir)) { return $null }
    $Docs = @()
    $Docs += Get-ChildItem -Path $FileDir -Filter '*.feature.md' -File -ErrorAction SilentlyContinue
    $Docs += Get-ChildItem -Path $FileDir -Filter '*.flow.md' -File -ErrorAction SilentlyContinue
    if (-not $Docs) { return $null }
    # Extract anchors from code: # see <slug>.<W|S|C|ST><N>
    $AnchorRefs = @()
    foreach ($M in [regex]::Matches($PostContent, '#\s*see\s+([a-z0-9-]+)\.((?:W|S|C|ST)\d+)')) {
        $AnchorRefs += @{ slug = $M.Groups[1].Value.ToLower(); id = $M.Groups[2].Value }
    }
    $FileBaseName = Split-Path $FilePath -Leaf
    foreach ($D in $Docs) {
        $DocLower = $D.FullName.ToLower()
        $Reads = if ($ReadFiles -is [hashtable] -and $ReadFiles.ContainsKey($DocLower)) { $ReadFiles[$DocLower] } else { @() }
        # Full-file read (no offset, no limit) satisfies unconditionally.
        $HasFullRead = $false
        foreach ($R in $Reads) { if ($R.offset -le 1 -and $R.limit -eq 0) { $HasFullRead = $true; break } }
        if ($HasFullRead) { continue }
        # Parse doc once: lines + slug + relevance check.
        $DocLines = @()
        $DocSlug = $null
        $DocGovernsFile = $false
          $DocIsActive = $true
          try {
              $DocLines = Get-Content $D.FullName -Encoding UTF8
              for ($I = 0; $I -lt [Math]::Min(15, $DocLines.Length); $I++) {
                  if ($DocLines[$I] -match '^\*\*Slug:\*\*\s*(\S+)') { $DocSlug = $Matches[1].ToLower(); break }
              }
              # Relevance: doc must mention the file's basename. Colocated docs that don't reference
              # this file do not govern it.
              foreach ($Line in $DocLines) {
                  if ($Line -match [regex]::Escape($FileBaseName)) { $DocGovernsFile = $true; break }
              }
              # Status: docs marked NOT STARTED / PROPOSED / DRAFT / PAUSED describe planned work,
              # not current behavior. They name files they plan to modify but don't yet describe
              # what the code does today, so they should not gate edits.
              foreach ($Line in $DocLines) {
                  if ($Line -match '(?i)(^|\s)(NOT\s+STARTED|PROPOSED|DRAFT|PAUSED)(\s|$|\*|\.|--)') {
                      $DocIsActive = $false; break
                  }
              }
          } catch {}
          if (-not $DocGovernsFile) { continue }
          if (-not $DocIsActive) { continue }
        $MatchingAnchors = @($AnchorRefs | Where-Object { $_.slug -eq $DocSlug })
        if ($MatchingAnchors.Count -eq 0) {
            # No anchor refs to this doc.
            if (-not $Reads -or $Reads.Count -eq 0) {
                return "R1 Doc preread: $FilePath has colocated doc $($D.FullName) which has not been Read this session. Read it before Edit/Write. See .claude/rules/feature-docs.md / .claude/rules/doc-layering.md. Path forward: Read the named colocated *.feature.md / *.flow.md file -- full read, OR partial read covering the relevant section if you add a '# see $DocSlug.<S|W|C|ST><N>' anchor in the code (the hook will then validate the anchored section is in your Read window)."
            }
            # Partial read present, no anchor: today's lenient behavior. Continue.
            continue
        }
        # Anchored: each anchor's section line must fall in some Read window.
        $UncoveredAnchors = @()
        foreach ($A in $MatchingAnchors) {
            $SectionLine = 0
            for ($I = 0; $I -lt $DocLines.Length; $I++) {
                if ($DocLines[$I] -match "\b$([regex]::Escape($A.id))\b") { $SectionLine = $I + 1; break }
            }
            if ($SectionLine -eq 0) {
                $UncoveredAnchors += "$($A.slug).$($A.id) [section ID not found in $($D.Name)]"
                continue
            }
            $Covered = $false
            foreach ($R in $Reads) {
                $Start = if ($R.offset -gt 0) { $R.offset } else { 1 }
                $End = if ($R.limit -gt 0) { $Start + $R.limit - 1 } else { $DocLines.Length }
                if ($SectionLine -ge $Start -and $SectionLine -le $End) { $Covered = $true; break }
            }
            if (-not $Covered) { $UncoveredAnchors += "$($A.slug).$($A.id) at line $SectionLine" }
        }
        if ($UncoveredAnchors.Count -gt 0) {
            return "R1 Doc preread (anchored section not covered): code in $FilePath references doc $($D.FullName) but Read windows did not cover: $($UncoveredAnchors -join '; '). Path forward: Read $($D.Name) again with offset/limit covering the named section line(s). Or do a full Read if you need wider context."
        }
    }
    return $null
}

function Test-R18-DocReadBudget {
    param($ToolInput)
    # Refuse Read calls on *.feature.md without a small limit (forces partial reads; full reads burn cache).
    # Override: add a line under '### R18 overrides' in directive.md naming the path.
    $FilePath = $ToolInput.file_path
    if (-not $FilePath) { return $null }
    if ($FilePath -notmatch '(?i)\.feature\.md$') { return $null }
    $Limit = $null
    if ($ToolInput.PSObject.Properties['limit']) {
        try { $Limit = [int]$ToolInput.limit } catch { $Limit = $null }
    }
    if ($Limit -ne $null -and $Limit -gt 0 -and $Limit -le 50) { return $null }
    $NormFP = ($FilePath -replace '\\','/').ToLower()
    foreach ($O in (Get-R18Overrides)) {
        if ($NormFP.EndsWith($O) -or $O.EndsWith($NormFP) -or $NormFP -like "*$O*") {
            $Entry = @{
                ts = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ")
                rule = 'R18'
                file = $FilePath
                line = 0
                reason = "override matched directive R18 overrides line"
            } | ConvertTo-Json -Compress
            Add-Content -Path $OverrideLog -Value $Entry -Encoding UTF8
            return $null
        }
    }
    $LimitDisplay = if ($Limit -eq $null) { 'missing' } else { "$Limit" }
    return "R18 Doc read budget: Read($FilePath) has limit=$LimitDisplay (>50). Full reads of *.feature.md burn prompt cache. Path forward: use Read($FilePath, limit=50) (or smaller) and pass offset to walk the doc; navigate via colocated *.flow.md anchors when stage-scoped context is enough. Override: add a one-line entry under '### R18 overrides' in .claude/directive.md naming this path, then retry."
}

function Test-R16-FeatureSlug {
    param($PostContent, $FilePath, $AllContent)
    if ($FilePath -notmatch '\.(feature|flow)\.md$') { return $null }
    $Lines = $PostContent -split "`n"
    for ($I = 0; $I -lt [Math]::Min(15, $Lines.Length); $I++) {
        if ($Lines[$I] -match '^\*\*Slug:\*\*\s*\S') { return $null }
    }
    if (Test-AllowOverride $PostContent 0 'R16' $FilePath) { return $null }
    return "R16 Missing Slug: $FilePath has no '**Slug:**' field in the first 15 lines. Every *.feature.md / *.flow.md requires a top-level slug per .claude/rules/feature-docs.md (or flow-docs.md). Slug = lowercase filename without the .feature.md / .flow.md extension. Path forward: add '**Slug:** <slug>' on its own line directly under the H1 header. For bulk backfill of legacy docs, run: powershell -File Scripts/Maintenance/AddSlugsToFeatureDocs.ps1"
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
    # directive: db-monolith-steering-hook -- per-file R6 suppression on the monolith being migrated; see Core/Database/repository-split.feature.md#perfect-end-state. Running R6 on this file charges rent against preexisting os.path sites without producing forward progress. New methods get steered to per-aggregate repos by R19 where R6 still fires normally.
    $NormR6 = $FilePath -replace '\\','/'
    if ($NormR6 -match '/Repositories/DatabaseManager\.py$') { return $null }
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
    # $EditRegion may be $null (legacy callers) -> behaves as whole-file. WholeFile/EditRegion/NoRegion
    # modes documented on Get-EditRegion. Each refusal point checks Test-RangeOverlapsEditRegion or
    # Test-LineInEditRegion to filter preexisting violations outside the operator's edit scope
    # per directive r12-edited-region-only (2026-06-01).
    param($PostContent, $FilePath, $AllContent, $EditRegion)
    if ($FilePath -notmatch '\.py$') { return $null }
    $Lines = $PostContent -split "`n"
    $BlockStart = -1
    for ($I = 0; $I -lt $Lines.Length; $I++) {
        if ($Lines[$I] -match '^\s*#') {
            if ($BlockStart -lt 0) { $BlockStart = $I }
            elseif (($I - $BlockStart) -ge 1) {
                $BlockStartLine = $BlockStart + 1
                $BlockEndLine = $I + 1
                if (-not (Test-RangeOverlapsEditRegion $BlockStartLine $BlockEndLine $EditRegion)) { continue }
                if (Test-AllowOverride $PostContent $I 'R12' $FilePath) { $BlockStart = -1; continue }
                return "R12 Comment volume: $FilePath line $BlockStartLine-$BlockEndLine is a multi-line # comment block. One-line max; rationale belongs in the directive doc. See .claude/rules/ceo-mode.md#handling-preexisting-comment--doc-violations-encountered-mid-directive. Path forward: classify the block first -- (a) pure WHAT-redundancy: delete entirely; (b) permanent-invariant WHY (BUG-NNNN, hard-won constraint): MOVE the content to memory/KNOWN-ISSUES.md or the appropriate *.feature.md, leave a single-line anchor in code ('# BUG-0005' or '# see worker-lifecycle.feature.md C6'); (c) active-directive WHY: put the content in the current directive doc, leave a '# directive: <slug>' anchor; (d) surprising WHY that fits nowhere: collapse to a single in-place comment line. If the scope is large (many blocks across many files), open a new directive ('<file>-comment-promotion') and do the classification there."
            }
        } else { $BlockStart = -1 }
    }
    $DocMatches = [regex]::Matches($PostContent, '(?ms)"""(.*?)"""')
    foreach ($DM in $DocMatches) {
        $Body = $DM.Groups[1].Value
        $Line = ($PostContent.Substring(0,$DM.Index) -split "`n").Length - 1
        $DocStartLine = $Line + 1
        $DocEndLine = $DocStartLine + ($DM.Value -split "`n").Length - 1
        $IsSqlBlock = $Body -cmatch '\b(SELECT\s+[\*\w(]|INSERT\s+INTO\s+\w|UPDATE\s+\w+\s+SET|DELETE\s+FROM\s+\w|CREATE\s+(TABLE|INDEX|VIEW|UNIQUE)|DROP\s+(TABLE|INDEX|VIEW)|ALTER\s+TABLE\s+\w|WITH\s+\w+\s+AS\s*\()'
        if ($IsSqlBlock) {
            if (-not (Test-RangeOverlapsEditRegion $DocStartLine $DocEndLine $EditRegion)) { continue }
            if (Test-AllowOverride $PostContent $Line 'R12' $FilePath) { continue }
            $NormFP = $FilePath -replace '\\','/'
            $PlacementExempt = ($NormFP -match '/Scripts/SQLScripts/') -or ($NormFP -match '/Tests/') -or ($NormFP -match '/Scripts/QueryDatabase\.py$') -or ($NormFP -match '/Repositories/')
            $PlacementClause = if ($PlacementExempt) {
                "Placement: exempt for this path (Scripts/SQLScripts, Tests, QueryDatabase.py, Repositories/). Format rule still applies."
            } else {
                "Placement: business-logic SQL must move to a Repository method (Repositories/<X>Repository.py). Controllers/Services/ViewModels do not embed SQL."
            }
            return "R12 SQL string: $FilePath line $($Line+1) uses triple-quoted SQL. Two mandates, both required:`n(1) Format: convert to implicit string concatenation. Triple-quoted SQL is refused everywhere. Right shape:`n    Query = (`n        `"SELECT col1, col2 `"`n        `"FROM MediaFiles `"`n        `"WHERE Id = %s`"`n    )`n(2) $PlacementClause`nSee .claude/rules/sql-architecture.md."
        }
        if (($Body -split "`n").Length -gt 1) {
            if (-not (Test-RangeOverlapsEditRegion $DocStartLine $DocEndLine $EditRegion)) { continue }
            if (Test-AllowOverride $PostContent $Line 'R12' $FilePath) { continue }
            return "R12 Comment volume: $FilePath line $($Line+1) has a multi-line docstring. Single-line max; rationale belongs in the directive doc. See .claude/rules/ceo-mode.md#handling-preexisting-comment--doc-violations-encountered-mid-directive. Path forward: classify the block first -- (a) pure WHAT-redundancy: delete entirely; (b) permanent-invariant WHY (BUG-NNNN, hard-won constraint): MOVE the content to memory/KNOWN-ISSUES.md or the appropriate *.feature.md, leave a single-line anchor in code ('# BUG-0005' or '# see worker-lifecycle.feature.md C6'); (c) active-directive WHY: put the content in the current directive doc, leave a '# directive: <slug>' anchor; (d) surprising WHY that fits nowhere: collapse to a single in-place comment line. If the scope is large (many blocks across many files), open a new directive ('<file>-comment-promotion') and do the classification there."
        }
    }
    if ($PostContent -match '^\s*"""') {
        if (-not (Test-LineInEditRegion 1 $EditRegion)) { return $null }
        if (-not (Test-AllowOverride $PostContent 0 'R12' $FilePath)) {
            return "R12 Comment volume: $FilePath has a module-level docstring. Documentation lives in the directive doc only. See .claude/rules/ceo-mode.md#handling-preexisting-comment--doc-violations-encountered-mid-directive. Path forward: classify the block first -- (a) pure WHAT-redundancy: delete entirely; (b) permanent-invariant WHY (BUG-NNNN, hard-won constraint): MOVE the content to memory/KNOWN-ISSUES.md or the appropriate *.feature.md, leave a single-line anchor in code ('# BUG-0005' or '# see worker-lifecycle.feature.md C6'); (c) active-directive WHY: put the content in the current directive doc, leave a '# directive: <slug>' anchor; (d) surprising WHY that fits nowhere: collapse to a single in-place comment line. If the scope is large (many blocks across many files), open a new directive ('<file>-comment-promotion') and do the classification there."
        }
    }
    return $null
}

function Test-R13-NoNewFeatureDocs {
    param($PostContent, $FilePath, $AllContent, $IsNew)
    if (-not $IsNew) { return $null }
    if ($FilePath -notmatch '\.(feature|flow)\.md$') { return $null }
    # Phase-aware: creation is allowed at DELIVERING (when durable content gets promoted out of the directive doc into its permanent home).
    $CurrentState = Get-SessionState
    if ($CurrentState -and $CurrentState.phase -eq 'DELIVERING') { return $null }
    $PhaseName = if ($CurrentState -and $CurrentState.phase) { $CurrentState.phase } else { '<none>' }
    return "R13 Premature feature/flow doc: $FilePath is a new *.feature.md / *.flow.md file but current phase is $PhaseName -- creation is only allowed at DELIVERING (when durable content gets promoted out of the directive doc into its permanent home). See .claude/rules/doc-layering.md + .claude/standards/index.md R13. Path forward: keep the new documentation in the active directive doc (.claude/directive.md) until phase advances to DELIVERING. At DELIVERING, create the *.feature.md / *.flow.md as part of the Promotions step and record the source -> target row in the directive's ### Promotions table."
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
    param($PostContent, $FilePath, $DirectiveFiles, $EditRegion)
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
            if ($Prev -notmatch "#\s*directive:\s*[a-z0-9-]+") {
                if (Test-AllowOverride $PostContent $I 'R15' $FilePath) { continue }
                return "R15 Directive anchor: $FilePath line $($I+1) defines a function/class without '# directive: $Slug' on the line above. This file is in the active directive's scope. See .claude/standards/index.md R15 row. Path forward: add '# directive: <active-slug>' on the line immediately above the def/class. This is the grep anchor that lets future readers find the directive that explains why this function exists in its current shape."
            }
        }
    }
    # directive: hook-honesty-fence -- companion # see anchor required alongside # directive:.
    # Directives are transient; feature/flow docs are durable. Every def/class
    # with a # directive: anchor must also have a # see <feature-or-flow-slug>.<ID>
    # anchor somewhere in its scope. Edited-region-only to avoid firing on legacy.
    for ($I = 0; $I -lt $Lines.Length; $I++) {
        if ($Lines[$I] -match '^\s*(def|class)\s+\w+') {
            $Prev = if ($I -gt 0) { $Lines[$I-1] } else { '' }
            if ($Prev -match "#\s*directive:\s*[a-z0-9-]+") {
                $StartIndent = ($Lines[$I] -replace '^(\s*).*$','$1').Length
                $EndIdx = $Lines.Length - 1
                for ($J = $I + 1; $J -lt $Lines.Length; $J++) {
                    if ($Lines[$J] -match '^\s*(def|class)\s+' -and (($Lines[$J] -replace '^(\s*).*$','$1').Length -le $StartIndent)) { $EndIdx = $J - 1; break }
                }
                $Scope = ($Lines[$I..$EndIdx] -join "`n") + "`n" + $Prev
                if ($Scope -notmatch "#\s*see\s+[a-z0-9-]+\.(S|W|C|ST)\d+") {
                    if (-not (Test-LineInEditRegion ($I+1) $EditRegion)) { continue }
                    if (Test-AllowOverride $PostContent $I 'R15' $FilePath) { continue }
                    return "R15 Companion see anchor: $FilePath line $($I+1) has '# directive: <slug>' but no '# see <feature-or-flow-slug>.<ID>' in scope. Directives are transient; feature/flow docs are durable. Path forward: add '# see <feature-or-flow-slug>.<criterion-or-seam-id>' somewhere in the function/class body (or on the directive anchor line, pipe-separated). For new contracts, this means writing the feature/flow doc edit FIRST and citing it."
                }
            }
        }
    }
    return $null
}

function Test-R19-DatabaseManagerSteering {
    # directive: db-monolith-steering-hook -- steers new/modified methods on Repositories/DatabaseManager.py to their per-aggregate repo home; see Core/Database/repository-split.feature.md#perfect-end-state and .claude/standards/database-manager-aggregates.json.
    param($PostContent, $FilePath, $ToolName, $ToolInput, $EditRegion, $AllContent)
    $NormR19 = $FilePath -replace '\\','/'
    if ($NormR19 -notmatch '/Repositories/DatabaseManager\.py$') { return $null }
    if ($EditRegion -and $EditRegion.Mode -eq 'NoRegion') { return $null }
    $MapPath = Join-Path $RepoRoot ".claude\standards\database-manager-aggregates.json"
    if (-not (Test-Path $MapPath)) { return $null }
    $Map = $null
    try { $Map = Get-Content $MapPath -Raw -Encoding UTF8 | ConvertFrom-Json } catch { return $null }
    if (-not $Map -or -not $Map.prefixes) { return $null }
    $Prefixes = @($Map.prefixes | Sort-Object { -($_.match.Length) })
    $Anchor = if ($Map.feature_doc_anchor) { $Map.feature_doc_anchor } else { 'Core/Database/repository-split.feature.md#perfect-end-state' }
    $Lines = $PostContent -split "`n"
    for ($I = 0; $I -lt $Lines.Length; $I++) {
        $LineMatch = [regex]::Match($Lines[$I], '^(\s*)def\s+(\w+)\s*\(')
        if (-not $LineMatch.Success) { continue }
        $Indent = $LineMatch.Groups[1].Value.Length
        $MethodName = $LineMatch.Groups[2].Value
        $EndIdx = $Lines.Length - 1
        for ($J = $I + 1; $J -lt $Lines.Length; $J++) {
            $InnerMatch = [regex]::Match($Lines[$J], '^(\s*)(def|class)\s+\w+')
            if ($InnerMatch.Success -and $InnerMatch.Groups[1].Value.Length -le $Indent) { $EndIdx = $J - 1; break }
        }
        $StartLine = $I + 1
        $EndLine = $EndIdx + 1
        if (-not (Test-RangeOverlapsEditRegion $StartLine $EndLine $EditRegion)) { continue }
        if (Test-AllowOverride $PostContent $I 'R19' $FilePath) { continue }
        $Target = $null
        foreach ($P in $Prefixes) { if ($MethodName.StartsWith($P.match)) { $Target = $P.target; break } }
        if (-not $Target) {
            return "R19 DatabaseManagerSteering: $FilePath line $StartLine introduces or modifies method '$MethodName'. No prefix in .claude/standards/database-manager-aggregates.json matches this name -- the hook will not guess the target aggregate. See $Anchor for the end-state shape. Path forward: add a row to .claude/standards/database-manager-aggregates.json mapping a prefix of '$MethodName' to its target Features/<Aggregate>/<Aggregate>Repository.py, then put the method in that file rather than the monolith. Pure deletions do not require a map entry."
        }
        return "R19 DatabaseManagerSteering: $FilePath is the monolith being migrated. New/modified method '$MethodName' (line $StartLine) belongs in $Target per $Anchor. Pure deletions of methods from this file pass silently. Path forward: write the method body in $Target instead and update callers' imports in the same commit. If this is a deliberate one-line bugfix landing in the monolith, override with '# allow: one-line bugfix for <reason>' within 3 lines of the def."
    }
    return $null
}

# ============ Main ============

$HookInput = Read-StdinJson
if (-not $HookInput) { Emit-Allow }

$ToolName = $HookInput.tool_name
$ToolInput = $HookInput.tool_input
$TranscriptPath = $HookInput.transcript_path

if ($ToolName -eq 'Read') {
    $R18Refusal = Test-R18-DocReadBudget $ToolInput
    if ($R18Refusal) { Emit-DenyWithRepeatDetection $R18Refusal $ToolInput.file_path }
    Emit-Allow
}
if ($ToolName -notin @('Write','Edit','MultiEdit')) { Emit-Allow }
if (-not $ToolInput.file_path) { Emit-Allow }

$FilePath = $ToolInput.file_path

# Task-delegation gate: when no active directive AND no opt-in marker, refuse code edits.
# Applies universally (including hook/standards/rule edits). Operator-only toggle.
$State = Get-SessionState
$TaskDelegationRefusal = Test-TaskDelegationGate $State $ToolName $ToolInput
if ($TaskDelegationRefusal) { Emit-DenyWithRepeatDetection $TaskDelegationRefusal $FilePath }

# Skip enforcement for hook scripts themselves and directive maintenance
$NormFP = $FilePath -replace '\\','/'
if ($NormFP -match '/\.claude/(hooks|standards|directive\.md|directives/|rules/|plans/)') {
    # Hook + standards files are exempt from R1-R15 (they ARE the standards layer).
    # Phase gate still applies.
    $PhaseRefusal = Test-PhaseGate $State $ToolName $ToolInput
    if ($PhaseRefusal) { Emit-DenyWithRepeatDetection $PhaseRefusal $FilePath }
    Emit-Allow
}

$PhaseRefusal = Test-PhaseGate $State $ToolName $ToolInput
if ($PhaseRefusal) { Emit-DenyWithRepeatDetection $PhaseRefusal $FilePath }

$IsNew = -not (Test-Path $FilePath)
$PostContent = Synthesize-PostEditContent $ToolName $ToolInput
$ReadFiles = Get-ReadFilesFromTranscript $TranscriptPath
$DirectiveFiles = Get-DirectiveFiles
$EditRegion = Get-EditRegion $ToolName $ToolInput $PostContent

$Rules = @(
    { Test-R1-DocPreread $PostContent $FilePath $ReadFiles $PostContent },
    { Test-R2-SeedEvidence $PostContent $FilePath $PostContent },
    { Test-R3-NoCachedSettings $PostContent $FilePath $PostContent },
    { Test-R4-NoEnvVars $PostContent $FilePath $PostContent },
    { Test-R5-ExecuteQueryMisuse $PostContent $FilePath $PostContent },
    { Test-R6-PathShape $PostContent $FilePath $PostContent $EditRegion },
    { Test-R7-PolymorphicCascade $PostContent $FilePath $PostContent },
    { Test-R8-TestPlacement $PostContent $FilePath $PostContent $IsNew },
    { Test-R9-LikeEscape $PostContent $FilePath $PostContent },
    { Test-R10-ClaimPredicate $PostContent $FilePath $PostContent },
    { Test-R11-MigrationIdempotency $PostContent $FilePath $PostContent },
    { Test-R12-CommentVolume $PostContent $FilePath $PostContent $EditRegion },
    { Test-R13-NoNewFeatureDocs $PostContent $FilePath $PostContent $IsNew },
    { Test-R14-AnnotationDrift $PostContent $FilePath $ToolName $ToolInput $PostContent },
    { Test-R15-DirectiveAnchor $PostContent $FilePath $DirectiveFiles $EditRegion },
    { Test-R16-FeatureSlug $PostContent $FilePath $PostContent },
    { Test-R19-DatabaseManagerSteering $PostContent $FilePath $ToolName $ToolInput $EditRegion $PostContent }
)

try {
    foreach ($R in $Rules) {
        $Refusal = & $R
        if ($Refusal) { Emit-DenyWithRepeatDetection $Refusal $FilePath }
    }
} catch {
    Emit-Ask "Standards hook errored: $($_.Exception.Message). Asking for human review."
}

Emit-Allow
