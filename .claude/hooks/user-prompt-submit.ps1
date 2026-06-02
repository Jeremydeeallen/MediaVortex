# directive: task-delegation-opt-in
# UserPromptSubmit hook: when .claude/.task-delegation-on exists, inject a system-reminder
# instructing the assistant to lead every response with a warning that task-delegation is ON.
# PowerShell 5.1 compatible.

$ErrorActionPreference = "SilentlyContinue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$RepoRoot = (Get-Location).Path
$MarkerPath = Join-Path $RepoRoot ".claude\.task-delegation-on"

if (-not (Test-Path $MarkerPath)) { exit 0 }

$Warning = "WARNING: TASK-DELEGATION MODE ON -- operator opt-in via .claude/.task-delegation-on; directive discipline bypassed for this session. Start your response with this warning verbatim on its own line before any other content. Disable by deleting the marker file."

$Out = @{
    hookSpecificOutput = @{
        hookEventName = "UserPromptSubmit"
        additionalContext = $Warning
    }
    continue = $true
} | ConvertTo-Json -Depth 5 -Compress

[Console]::Out.Write($Out)
exit 0
