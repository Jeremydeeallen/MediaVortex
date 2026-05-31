# directive: ceo-mode-enforcement
# SessionStart hook: detects active directive, initializes phase state, injects standards-review reminder.
# PowerShell 5.1 compatible.

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$RepoRoot = (Get-Location).Path
$StateFile = Join-Path $RepoRoot ".claude\.session-state.json"
$DirectiveFile = Join-Path $RepoRoot ".claude\directive.md"
$StandardsIndex = Join-Path $RepoRoot ".claude\standards\index.md"

function Emit-Context {
    param([string]$Text)
    $Out = @{
        hookSpecificOutput = @{
            hookEventName = "SessionStart"
            additionalContext = $Text
        }
        continue = $true
    } | ConvertTo-Json -Depth 6 -Compress
    [Console]::Out.Write($Out)
    exit 0
}

function Emit-Silent { exit 0 }

if (-not (Test-Path $DirectiveFile)) { Emit-Silent }

$DirText = Get-Content $DirectiveFile -Raw
$SlugMatch = [regex]::Match($DirText, '\*\*Slug:\*\*\s*(\S+)')
if (-not $SlugMatch.Success) { Emit-Silent }
$Slug = $SlugMatch.Groups[1].Value
if ($Slug -eq '<previous-slug>' -or [string]::IsNullOrWhiteSpace($Slug)) { Emit-Silent }

$PhaseMatch = [regex]::Match($DirText, '\*\*Status:\*\*\s*Active\s*--\s*phase:\s*([A-Z_]+)')
$Phase = if ($PhaseMatch.Success) { $PhaseMatch.Groups[1].Value } else { 'NEEDS_STANDARDS_REVIEW' }

$Existing = $null
if (Test-Path $StateFile) {
    try { $Existing = Get-Content $StateFile -Raw | ConvertFrom-Json } catch { $Existing = $null }
}

$State = @{
    directive_slug = $Slug
    phase = $Phase
    session_started_at = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ")
}

if ($Existing -and $Existing.directive_slug -eq $Slug -and $Existing.phase) {
    $State.phase = $Existing.phase
    if ($Existing.session_started_at) { $State.session_started_at = $Existing.session_started_at }
}

$State | ConvertTo-Json | Out-File -FilePath $StateFile -Encoding utf8 -Force

$Reminder = @"
CEO MODE ACTIVE -- directive slug: $Slug -- current phase: $($State.phase)

Mechanical enforcement is live. The PreToolUse hook (.claude/hooks/pre-edit-standards.ps1) will refuse Edit/Write that violates phase gates or the 15 content rules in .claude/standards/index.md.

Per-phase exits:
  NEEDS_STANDARDS_REVIEW -- Read every .claude/rules/*.md + .claude/standards/index.md.
  NEEDS_PLAN             -- Edit only the directive doc until criteria + Files list are written.
  NEEDS_DOC_PREREAD      -- Read every *.feature.md / *.flow.md ancestor of files in the directive's ## Files.
  IMPLEMENTING           -- Edit/Write code; content rules gate each call.
  VERIFYING              -- Edit only the directive doc; record evidence per criterion.
  DELIVERING             -- Draft the delivery report in the directive doc Status.

Advance phase by editing the directive doc Status line: '**Status:** Active -- phase: <NEXT>'.
Override single rule firings with '# allow: <reason>' within 3 lines of the offending pattern. Overrides log to .claude/.standards-overrides.log.

Read the directive ($DirectiveFile) and the standards index ($StandardsIndex) now.
"@

Emit-Context $Reminder
