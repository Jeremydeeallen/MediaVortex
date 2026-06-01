# directive: token-optimization-program
# Backfill **Slug:** field into every *.feature.md and *.flow.md in the repo.
# Slug = lowercase filename without .feature.md / .flow.md extension.
# Idempotent: skips files that already have **Slug:**.
# Uniqueness: collisions get prefixed with parent directory name (lowercase).

$ErrorActionPreference = "Stop"

$RepoRoot = (Get-Location).Path
$Docs = @()
$Docs += Get-ChildItem -Path $RepoRoot -Recurse -Filter '*.feature.md' -ErrorAction SilentlyContinue | Where-Object { $_.FullName -notmatch '\\\.claude\\|\\venv\\|\\node_modules\\' }
$Docs += Get-ChildItem -Path $RepoRoot -Recurse -Filter '*.flow.md' -ErrorAction SilentlyContinue | Where-Object { $_.FullName -notmatch '\\\.claude\\|\\venv\\|\\node_modules\\' }

function Get-DocType {
    param([string]$FilePath)
    if ($FilePath -match '\.feature\.md$') { return 'feature' }
    if ($FilePath -match '\.flow\.md$') { return 'flow' }
    return $null
}

function Get-BaseSlug {
    param([string]$FilePath)
    $Name = [System.IO.Path]::GetFileName($FilePath)
    return ($Name -replace '\.(feature|flow)\.md$', '').ToLower()
}

# Build per-type slug map. A "slug" is globally unique within its type (feature: vs flow: namespaces).
# Feature and flow with same base name are allowed to share base; the type namespace disambiguates.
$ByType = @{ 'feature' = @{}; 'flow' = @{} }
foreach ($D in $Docs) {
    $T = Get-DocType $D.FullName
    if (-not $T) { continue }
    $S = Get-BaseSlug $D.FullName
    if ($ByType[$T].ContainsKey($S)) {
        $ByType[$T][$S] += ,$D.FullName
    } else {
        $ByType[$T][$S] = @($D.FullName)
    }
}

# Resolve intra-type collisions by prefixing with parent dir
$ResolvedMap = @{}
foreach ($T in @('feature','flow')) {
    foreach ($Pair in $ByType[$T].GetEnumerator()) {
        if ($Pair.Value.Count -eq 1) {
            $ResolvedMap[$Pair.Value[0]] = $Pair.Key
        } else {
            foreach ($Path in $Pair.Value) {
                $Parent = (Split-Path $Path -Parent | Split-Path -Leaf).ToLower()
                $ResolvedMap[$Path] = "$Parent-$($Pair.Key)"
            }
        }
    }
}

$Added = 0
$Skipped = 0
$NoHeader = 0
foreach ($D in $Docs) {
    $Slug = $ResolvedMap[$D.FullName]
    $Lines = Get-Content $D.FullName -Encoding UTF8
    # Check if Slug already present in first 15 lines
    $HasSlug = $false
    for ($I = 0; $I -lt [Math]::Min(15, $Lines.Length); $I++) {
        if ($Lines[$I] -match '^\*\*Slug:\*\*\s*\S') { $HasSlug = $true; break }
    }
    if ($HasSlug) {
        $Skipped++
        continue
    }
    # Find the H1 line
    $HeaderIdx = -1
    for ($I = 0; $I -lt [Math]::Min(10, $Lines.Length); $I++) {
        if ($Lines[$I] -match '^#\s+\S') { $HeaderIdx = $I; break }
    }
    if ($HeaderIdx -lt 0) {
        Write-Warning "No H1 header found in $($D.FullName); skipping"
        $NoHeader++
        continue
    }
    # Insert **Slug:** <slug> as blank line + slug line directly after header
    $Before = @($Lines[0..$HeaderIdx])
    $After = if ($Lines.Length -gt ($HeaderIdx + 1)) { @($Lines[($HeaderIdx + 1)..($Lines.Length - 1)]) } else { @() }
    $Insertion = @('', "**Slug:** $Slug")
    $NewLines = $Before + $Insertion + $After
    Set-Content -Path $D.FullName -Value $NewLines -Encoding UTF8
    $Added++
}

Write-Output "Added Slug to: $Added files"
Write-Output "Already had Slug: $Skipped files"
if ($NoHeader -gt 0) { Write-Output "WARNING: No H1 header in: $NoHeader files" }

# Report any intra-type slug collisions resolved
$AnyCollision = $false
foreach ($T in @('feature','flow')) {
    $Coll = $ByType[$T].GetEnumerator() | Where-Object { $_.Value.Count -gt 1 }
    foreach ($C in $Coll) {
        if (-not $AnyCollision) { Write-Output ""; Write-Output "Collisions resolved with parent-dir prefix:"; $AnyCollision = $true }
        foreach ($P in $C.Value) {
            $Resolved = $ResolvedMap[$P]
            Write-Output ("  [$T] $Resolved <- $P")
        }
    }
}
