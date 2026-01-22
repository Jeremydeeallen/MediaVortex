# File Organization Script - MediaVortex
# Organizes files based on search terms and destination folders
# Follows MVVM pattern using MVVM architecture

param(
    [string]$ConfigFile = "FileOrganizationConfig.json",
    [string]$LogFile = "FileOrganization.log",
    [switch]$DryRun = $false,
    [switch]$CleanupEmptyFolders = $true,
    [switch]$Verbose = $false
)

# Script configuration
$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ConfigPath = Join-Path $ScriptPath $ConfigFile
$LogPath = Join-Path $ScriptPath $LogFile

# Load configuration
function LoadConfiguration {
    if (Test-Path $ConfigPath) {
        try {
            $Config = Get-Content $ConfigPath -Raw | ConvertFrom-Json
            Write-Log "Configuration loaded from $ConfigPath" "Info"
            
            # Convert SearchTerms PSCustomObject to Hashtable
            $SearchTermsHashtable = @{}
            $Config.SearchTerms.PSObject.Properties | ForEach-Object {
                $SearchTermsHashtable[$_.Name] = $_.Value
            }
            $Config.SearchTerms = $SearchTermsHashtable
            
            return $Config
        }
        catch {
            Write-Log "Error loading configuration: $($_.Exception.Message)" "Error"
            exit 1
        }
    }
    else {
        Write-Log "Configuration file not found: $ConfigPath" "Error"
        Write-Log "Please create the configuration file with your search terms and destinations" "Error"
        exit 1
    }
}

# Save configuration
function SaveConfiguration($Config) {
    try {
        $Config | ConvertTo-Json -Depth 3 | Set-Content $ConfigPath -Encoding UTF8
        Write-Log "Configuration saved to $ConfigPath" "Info"
    }
    catch {
        Write-Log "Error saving configuration: $($_.Exception.Message)" "Error"
    }
}

# Logging function
function Write-Log {
    param(
        [string]$Message,
        [string]$Level = "Info"
    )
    
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $LogEntry = "[$Timestamp] [$Level] $Message"
    
    # Write to console with color coding
    switch ($Level) {
        "Error" { Write-Host $LogEntry -ForegroundColor Red }
        "Warning" { Write-Host $LogEntry -ForegroundColor Yellow }
        "Info" { Write-Host $LogEntry -ForegroundColor White }
        "Debug" { Write-Host $LogEntry -ForegroundColor Cyan }
    }
    
    # Write to log file
    Add-Content -Path $LogPath -Value $LogEntry -Encoding UTF8
}

# Ensure directory exists
function Ensure-DirectoryExists {
    param([string]$DirectoryPath)
    
    if (-not (Test-Path $DirectoryPath)) {
        try {
            New-Item -ItemType Directory -Path $DirectoryPath -Force | Out-Null
            Write-Log "Created directory: $DirectoryPath" "Info"
            return $true
        }
        catch {
            Write-Log "Failed to create directory '$DirectoryPath': $($_.Exception.Message)" "Error"
            return $false
        }
    }
    return $true
}

# Check if file should be processed
function Should-ProcessFile {
    param(
        [string]$FilePath,
        [string[]]$ExcludeFolders
    )
    
    # Check if file is in excluded folder
    $DirectoryName = Split-Path (Split-Path $FilePath -Parent) -Leaf
    if ($ExcludeFolders -contains $DirectoryName) {
        return $false
    }
    
    return $true
}

# Move file to destination
function Move-FileToDestination {
    param(
        [string]$FilePath,
        [string]$DestinationFolder,
        [string]$SearchTerm,
        [bool]$DryRun
    )
    
    try {
        $FileName = Split-Path $FilePath -Leaf
        $DestinationPath = Join-Path $DestinationFolder $FileName
        
        # Handle duplicate filenames
        $Counter = 1
        $OriginalDestination = $DestinationPath
        while (Test-Path $DestinationPath) {
            $NameWithoutExt = [System.IO.Path]::GetFileNameWithoutExtension($OriginalDestination)
            $Extension = [System.IO.Path]::GetExtension($OriginalDestination)
            $DestinationPath = Join-Path $DestinationFolder "$NameWithoutExt($Counter)$Extension"
            $Counter++
        }
        
        if ($DryRun) {
            Write-Log "DRY RUN - Would move: '$FileName' -> '$DestinationPath' (matched: '$SearchTerm')" "Info"
        }
        else {
            Move-Item -LiteralPath $FilePath -Destination $DestinationPath -Force
            Write-Log "Moved: '$FileName' -> '$DestinationPath' (matched: '$SearchTerm')" "Info"
        }
        return $true
    }
    catch {
        Write-Log "Error moving file '$FilePath': $($_.Exception.Message)" "Error"
        return $false
    }
}

# Process files based on search terms
function Process-Files {
    param(
        [string]$RootFolder,
        [hashtable]$SearchTerms,
        [bool]$CaseSensitive = $false,
        [bool]$CreateDirectories = $true,
        [bool]$MoveFiles = $true,
        [string[]]$ExcludeFolders = @(),
        [bool]$DryRun = $false
    )
    
    Write-Log "Starting file processing..." "Info"
    Write-Log "Root folder: $RootFolder" "Info"
    Write-Log "Search terms: $($SearchTerms.Count)" "Info"
    Write-Log "Dry run mode: $DryRun" "Info"
    
    # Check if root folder exists
    if (-not (Test-Path $RootFolder)) {
        Write-Log "Root folder '$RootFolder' does not exist" "Error"
        return @{
            Success = $false
            MovedFiles = 0
            SkippedFiles = 0
            ErrorFiles = 0
        }
    }
    
    # Ensure destination directories exist
    if ($CreateDirectories -and -not $DryRun) {
        foreach ($Destination in $SearchTerms.Values) {
            Ensure-DirectoryExists $Destination
        }
    }
    
    # Get all files recursively
    $Files = Get-ChildItem -LiteralPath $RootFolder -File -Recurse
    Write-Log "Found $($Files.Count) files to process" "Info"
    
    $MovedFiles = 0
    $SkippedFiles = 0
    $ErrorFiles = 0
    $ProcessedFiles = 0
    
    foreach ($File in $Files) {
        $ProcessedFiles++
        
        # Check if file should be processed
        if (-not (Should-ProcessFile $File.FullName $ExcludeFolders)) {
            $SkippedFiles++
            continue
        }
        
        $Matched = $false
        
        foreach ($SearchTerm in $SearchTerms.GetEnumerator()) {
            $FileName = $File.Name
            $SearchText = if ($CaseSensitive) { $SearchTerm.Key } else { $SearchTerm.Key.ToLower() }
            $FileText = if ($CaseSensitive) { $FileName } else { $FileName.ToLower() }
            
            if ($FileText -like "*$SearchText*") {
                if ($MoveFiles) {
                    if (Move-FileToDestination $File.FullName $SearchTerm.Value $SearchTerm.Key $DryRun) {
                        $MovedFiles++
                    }
                    else {
                        $ErrorFiles++
                    }
                }
                else {
                    Write-Log "Would move: '$($File.Name)' -> '$($SearchTerm.Value)' (matched: '$($SearchTerm.Key)')" "Info"
                    $MovedFiles++
                }
                $Matched = $true
                break
            }
        }
        
        if (-not $Matched) {
            $SkippedFiles++
        }
        
        # Progress indicator
        if ($ProcessedFiles % 100 -eq 0) {
            Write-Log "Processed $ProcessedFiles files..." "Debug"
        }
    }
    
    $Result = @{
        Success = $true
        MovedFiles = $MovedFiles
        SkippedFiles = $SkippedFiles
        ErrorFiles = $ErrorFiles
        ProcessedFiles = $ProcessedFiles
    }
    
    Write-Log "Processing complete. Processed: $ProcessedFiles, Moved: $MovedFiles, Skipped: $SkippedFiles, Errors: $ErrorFiles" "Info"
    return $Result
}

# Flatten directory structure - move all files from subfolders to root
function Flatten-DirectoryStructure {
    param([string]$RootFolder, [bool]$DryRun = $false)
    
    Write-Log "Starting directory flattening..." "Info"
    Write-Log "Moving all files from subfolders to root: $RootFolder" "Info"
    
    # Get all files in subfolders (not in root)
    $Files = Get-ChildItem -LiteralPath $RootFolder -File -Recurse | Where-Object { $_.DirectoryName -ne $RootFolder }
    
    Write-Log "Found $($Files.Count) files in subfolders to move" "Info"
    
    $MovedFiles = 0
    $ErrorFiles = 0
    
    foreach ($File in $Files) {
        try {
            $FileName = $File.Name
            $DestinationPath = Join-Path $RootFolder $FileName
            
            # Handle duplicate filenames
            $Counter = 1
            $OriginalDestination = $DestinationPath
            while (Test-Path $DestinationPath) {
                $NameWithoutExt = [System.IO.Path]::GetFileNameWithoutExtension($OriginalDestination)
                $Extension = [System.IO.Path]::GetExtension($OriginalDestination)
                $DestinationPath = Join-Path $RootFolder "$NameWithoutExt($Counter)$Extension"
                $Counter++
            }
            
            if ($DryRun) {
                Write-Log "DRY RUN - Would move: '$FileName' from '$($File.DirectoryName)' to '$DestinationPath'" "Info"
            }
            else {
                Move-Item -LiteralPath $File.FullName -Destination $DestinationPath -Force
                Write-Log "Moved: '$FileName' from '$($File.DirectoryName)' to '$DestinationPath'" "Info"
            }
            $MovedFiles++
        }
        catch {
            Write-Log "Error moving file '$($File.FullName)': $($_.Exception.Message)" "Error"
            $ErrorFiles++
        }
    }
    
    Write-Log "Directory flattening complete. Moved: $MovedFiles files, Errors: $ErrorFiles" "Info"
    return @{
        MovedFiles = $MovedFiles
        ErrorFiles = $ErrorFiles
    }
}

# Clean up empty folders
function Clean-EmptyFolders {
    param([string]$RootFolder, [bool]$DryRun = $false)
    
    Write-Log "Starting empty folder cleanup..." "Info"
    
    # Get all directories recursively, sort by depth (deepest first)
    $Directories = Get-ChildItem -LiteralPath $RootFolder -Directory -Recurse | Sort-Object -Property FullName -Descending
    
    $DeletedFolders = 0
    
    foreach ($Dir in $Directories) {
        if (-not (Get-ChildItem -LiteralPath $Dir.FullName)) {
            try {
                if ($DryRun) {
                    Write-Log "DRY RUN - Would delete empty folder: $($Dir.FullName)" "Info"
                }
                else {
                    Remove-Item -LiteralPath $Dir.FullName -Recurse -Force
                    Write-Log "Deleted empty folder: $($Dir.FullName)" "Info"
                }
                $DeletedFolders++
            }
            catch {
                Write-Log "Error deleting folder '$($Dir.FullName)': $($_.Exception.Message)" "Error"
            }
        }
    }
    
    Write-Log "Empty folder cleanup complete. Deleted: $DeletedFolders folders" "Info"
    return $DeletedFolders
}

# Group files by filename prefix (characters before first period)
function Show-FileGrouping {
    param([string]$RootFolder)
    
    Write-Log "=== FILE GROUPING ANALYSIS ===" "Info"
    
    if (-not (Test-Path $RootFolder)) {
        Write-Log "Root folder '$RootFolder' does not exist" "Error"
        return
    }
    
    # Get all files recursively
    $Files = Get-ChildItem -LiteralPath $RootFolder -File -Recurse
    Write-Log "Analyzing $($Files.Count) files for grouping..." "Info"
    
    # Group files by prefix (characters before first period)
    $PrefixGroups = @{}
    
    foreach ($File in $Files) {
        $FileName = $File.Name
        
        # Extract prefix (characters before first period)
        $FirstPeriodIndex = $FileName.IndexOf('.')
        if ($FirstPeriodIndex -gt 0) {
            $Prefix = $FileName.Substring(0, $FirstPeriodIndex)
        }
        else {
            # If no period found, use entire filename as prefix
            $Prefix = $FileName
        }
        
        # Initialize count if prefix doesn't exist
        if (-not $PrefixGroups.ContainsKey($Prefix)) {
            $PrefixGroups[$Prefix] = 0
        }
        
        # Increment count for this prefix
        $PrefixGroups[$Prefix]++
    }
    
    # Separate groups with count > 1 from 1-offs
    $MultipleFiles = @{}
    $OneOffFiles = 0
    
    foreach ($Key in $PrefixGroups.Keys) {
        if ($PrefixGroups[$Key] -gt 1) {
            $MultipleFiles[$Key] = $PrefixGroups[$Key]
        }
        else {
            $OneOffFiles++
        }
    }
    
    # Display grouped files (count > 1)
    Write-Log "" "Info"
    Write-Log "Files grouped by prefix (multiple occurrences):" "Info"
    foreach ($Prefix in ($MultipleFiles.Keys | Sort-Object)) {
        Write-Log "$Prefix* - $($MultipleFiles[$Prefix])" "Info"
    }
    
    # Display 1-offs count
    Write-Log "" "Info"
    Write-Log "1off - $OneOffFiles" "Info"
    
    Write-Log "" "Info"
    Write-Log "Total unique prefixes with multiple files: $($MultipleFiles.Count)" "Info"
    Write-Log "Total 1-off files: $OneOffFiles" "Info"
}

# Main execution
function Main {
    Write-Log "MediaVortex File Organization Script started" "Info"
    Write-Log "Script path: $ScriptPath" "Debug"
    Write-Log "Config path: $ConfigPath" "Debug"
    Write-Log "Log path: $LogPath" "Debug"
    
    # Load configuration
    $Config = LoadConfiguration
    
    # Override with command line parameters
    if ($DryRun) {
        $Config.MoveFiles = $false
    }
    
    # Step 1: Flatten directory structure - move all files from subfolders to root
    Write-Log "=== STEP 1: FLATTENING DIRECTORY STRUCTURE ===" "Info"
    $FlattenResult = Flatten-DirectoryStructure -RootFolder $Config.RootFolder -DryRun $DryRun
    
    # Step 2: Clean up empty folders after flattening
    Write-Log "=== STEP 2: CLEANING UP EMPTY FOLDERS ===" "Info"
    $CleanupResult = Clean-EmptyFolders -RootFolder $Config.RootFolder -DryRun $DryRun
    
    # Step 3: Process files based on search terms
    Write-Log "=== STEP 3: ORGANIZING FILES BY SEARCH TERMS ===" "Info"
    $Result = Process-Files -RootFolder $Config.RootFolder -SearchTerms $Config.SearchTerms -CaseSensitive $Config.CaseSensitive -CreateDirectories $Config.CreateDirectories -MoveFiles $Config.MoveFiles -ExcludeFolders $Config.ExcludeFolders -DryRun $DryRun
    
    # Clean up empty folders if requested
    if ($CleanupEmptyFolders -and $Result.Success) {
        Clean-EmptyFolders -RootFolder $Config.RootFolder -DryRun $DryRun
    }
    
    # Summary
    Write-Log "=== PROCESSING SUMMARY ===" "Info"
    Write-Log "=== FLATTENING RESULTS ===" "Info"
    Write-Log "Files moved from subfolders: $($FlattenResult.MovedFiles)" "Info"
    Write-Log "Flattening errors: $($FlattenResult.ErrorFiles)" "Info"
    Write-Log "Empty folders deleted: $CleanupResult" "Info"
    Write-Log "=== ORGANIZATION RESULTS ===" "Info"
    Write-Log "Files processed: $($Result.ProcessedFiles)" "Info"
    Write-Log "Files moved by search terms: $($Result.MovedFiles)" "Info"
    Write-Log "Files skipped: $($Result.SkippedFiles)" "Info"
    Write-Log "Organization errors: $($Result.ErrorFiles)" "Info"
    Write-Log "Success: $($Result.Success)" "Info"
    
    if ($DryRun) {
        Write-Log "This was a dry run - no files were actually moved" "Warning"
    }
    
    # Step 4: Show file grouping analysis
    Write-Log "=== STEP 4: FILE GROUPING ANALYSIS ===" "Info"
    Show-FileGrouping -RootFolder $Config.RootFolder
    
    Write-Log "MediaVortex File Organization Script completed" "Info"
    
    # Return exit code
    if ($Result.Success) {
        exit 0
    }
    else {
        exit 1
    }
}

# Run the main function
Main
