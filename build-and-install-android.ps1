param(
    [string]$ProjectPath = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$UnityExe = "D:\unity\2022.3.62f2c1\Editor\Unity.exe",
    [string]$AdbExe = "E:\AndroidBuild\android-sdk\platform-tools\adb.exe",
    [string]$OutputDir = "",
    [string]$ApkName = "MR_System.apk",
    [string]$KeystorePath = "",
    [string]$KeystorePass = "",
    [string]$KeyaliasName = "",
    [string]$KeyaliasPass = "",
    [switch]$SkipInstall,
    [switch]$CleanupInjectedScript = $true
)

$ErrorActionPreference = "Stop"

function Write-Section {
    param([string]$Text)
    Write-Host ""
    Write-Host "== $Text =="
}

function Resolve-ToolPath {
    param(
        [string]$PreferredPath,
        [string]$CommandName
    )

    if ($PreferredPath -and (Test-Path -LiteralPath $PreferredPath)) {
        return (Resolve-Path -LiteralPath $PreferredPath).Path
    }

    $command = Get-Command $CommandName -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    return $null
}

function Get-FileHashSafe {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}

function Read-JsonFile {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    try {
        return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    }
    catch {
        return $null
    }
}

function Write-JsonFile {
    param(
        [string]$Path,
        [object]$Value
    )
    $Value | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Quote-Argument {
    param([string]$Value)
    if ($null -eq $Value) {
        return '""'
    }
    if ($Value -match '[\s"]') {
        return '"' + ($Value -replace '"', '\"') + '"'
    }
    return $Value
}

function Invoke-UnityProcess {
    param(
        [string]$UnityPath,
        [string[]]$Arguments,
        [string]$StageName,
        [string]$LogPath
    )

    if (Test-Path -LiteralPath $LogPath) {
        Remove-Item -LiteralPath $LogPath -Force
    }

    $argumentText = ($Arguments | ForEach-Object { Quote-Argument $_ }) -join ' '
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $UnityPath
    $startInfo.Arguments = $argumentText
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    $started = $process.Start()
    if (-not $started) {
        throw "Failed to start Unity process for stage: $StageName"
    }

    $lastLineCount = 0
    $idleCounter = 0

    while (-not $process.HasExited) {
        Start-Sleep -Milliseconds 1200
        if (Test-Path -LiteralPath $LogPath) {
            $lines = Get-Content -LiteralPath $LogPath
            $newLineCount = $lines.Count
            if ($newLineCount -gt $lastLineCount) {
                $delta = $newLineCount - $lastLineCount
                $tailCount = [Math]::Min($delta, 12)
                $lines | Select-Object -Last $tailCount | ForEach-Object {
                    $trimmed = $_.Trim()
                    if ($trimmed) {
                        Write-Host "[$StageName] $trimmed"
                    }
                }
                $lastLineCount = $newLineCount
                $idleCounter = 0
            }
            else {
                $idleCounter++
                if ($idleCounter -ge 10) {
                    Write-Host "[$StageName] still running..."
                    $idleCounter = 0
                }
            }
        }
        else {
            $idleCounter++
            if ($idleCounter -ge 10) {
                Write-Host "[$StageName] waiting for Unity log..."
                $idleCounter = 0
            }
        }
    }

    $process.WaitForExit()
    $process.Refresh()
    $exitCode = $process.ExitCode
    if ($null -eq $exitCode) {
        Write-Host "$StageName exit code: <null>" -ForegroundColor Red
        Write-Host ""
        Write-Host "Unity $StageName failed because no exit code was available. Log: $LogPath" -ForegroundColor Red
        exit 1
    }

    Write-Host "$StageName exit code: $exitCode"
    if ([int]$exitCode -ne 0) {
        Write-Host ""
        Write-Host "Unity $StageName failed. Log: $LogPath" -ForegroundColor Red
        exit ([int]$exitCode)
    }
}

function Get-ConnectedDevices {
    param([string]$AdbPath)

    $adbOutput = & $AdbPath devices
    if ($LASTEXITCODE -ne 0) {
        throw "adb devices failed."
    }

    $devices = @()
    foreach ($line in $adbOutput) {
        if ($line -match "^(?<serial>\S+)\s+device$") {
            $devices += $Matches["serial"]
        }
    }

    return $devices
}

function Sync-BuildScript {
    param([string]$ProjectDir)

    $source = Join-Path $PSScriptRoot "AndroidBuildTools.cs"
    $sourceMeta = Join-Path $PSScriptRoot "AndroidBuildTools.cs.meta"
    if (-not (Test-Path -LiteralPath $source)) {
        throw "Build script template not found: $source"
    }
    if (-not (Test-Path -LiteralPath $sourceMeta)) {
        throw "Build script meta template not found: $sourceMeta"
    }

    $editorDir = Join-Path $ProjectDir "Assets\Editor"
    New-Item -ItemType Directory -Force -Path $editorDir | Out-Null

    $destination = Join-Path $editorDir "AndroidBuildTools.cs"
    $destinationMeta = "$destination.meta"
    $backupDir = Join-Path $ProjectDir "Library\CodexApkBuilderBackup"
    New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

    $scriptBackup = Join-Path $backupDir "AndroidBuildTools.cs.bak"
    $metaBackup = Join-Path $backupDir "AndroidBuildTools.cs.meta.bak"
    $hadExistingScript = Test-Path -LiteralPath $destination
    $hadExistingMeta = Test-Path -LiteralPath $destinationMeta

    if ($hadExistingScript) {
        Copy-Item -LiteralPath $destination -Destination $scriptBackup -Force
    }
    if ($hadExistingMeta) {
        Copy-Item -LiteralPath $destinationMeta -Destination $metaBackup -Force
    }

    Copy-Item -LiteralPath $source -Destination $destination -Force
    Copy-Item -LiteralPath $sourceMeta -Destination $destinationMeta -Force

    return [PSCustomObject]@{
        ScriptPath = $destination
        MetaPath = $destinationMeta
        BackupDir = $backupDir
        ScriptBackup = $scriptBackup
        MetaBackup = $metaBackup
        HadExistingScript = $hadExistingScript
        HadExistingMeta = $hadExistingMeta
    }
}

function Get-PrecompileReuseState {
    param(
        [string]$ProjectDir,
        [string]$UnityPath
    )

    $destination = Join-Path $ProjectDir "Assets\Editor\AndroidBuildTools.cs"
    $destinationMeta = "$destination.meta"
    $cacheDir = Join-Path $ProjectDir "Library\CodexApkBuilderCache"
    $stampPath = Join-Path $cacheDir 'precompile-stamp.json'
    $source = Join-Path $PSScriptRoot "AndroidBuildTools.cs"
    $sourceMeta = Join-Path $PSScriptRoot "AndroidBuildTools.cs.meta"
    $stamp = Read-JsonFile -Path $stampPath

    $sourceHash = Get-FileHashSafe -Path $source
    $sourceMetaHash = Get-FileHashSafe -Path $sourceMeta
    $destHash = Get-FileHashSafe -Path $destination
    $destMetaHash = Get-FileHashSafe -Path $destinationMeta

    $scriptInjected = ($sourceHash -and $sourceHash -eq $destHash)
    $metaInjected = ($sourceMetaHash -and $sourceMetaHash -eq $destMetaHash)
    $stampMatches = $stamp -and
        $stamp.source_hash -eq $sourceHash -and
        $stamp.source_meta_hash -eq $sourceMetaHash -and
        $stamp.unity_path -eq $UnityPath

    return [PSCustomObject]@{
        CanSkipSync = ($scriptInjected -and $metaInjected)
        CanSkipPrecompile = ($stampMatches -and ($scriptInjected -and $metaInjected))
        HasReusableStamp = [bool]$stampMatches
        StampPath = $stampPath
        SourceHash = $sourceHash
        SourceMetaHash = $sourceMetaHash
    }
}

function Save-PrecompileStamp {
    param(
        [string]$StampPath,
        [string]$UnityPath,
        [string]$SourceHash,
        [string]$SourceMetaHash
    )

    $dir = Split-Path -Parent $StampPath
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    Write-JsonFile -Path $StampPath -Value @{
        unity_path = $UnityPath
        source_hash = $SourceHash
        source_meta_hash = $SourceMetaHash
        updated_at = (Get-Date).ToString('s')
    }
}

function Restore-BuildScript {
    param(
        $SyncResult,
        [bool]$CleanupInjected
    )

    if (-not $SyncResult) {
        return
    }

    if ($CleanupInjected) {
        if (Test-Path -LiteralPath $SyncResult.ScriptPath) {
            Remove-Item -LiteralPath $SyncResult.ScriptPath -Force
        }
        if (Test-Path -LiteralPath $SyncResult.MetaPath) {
            Remove-Item -LiteralPath $SyncResult.MetaPath -Force
        }
    }

    if ($SyncResult.HadExistingScript -and (Test-Path -LiteralPath $SyncResult.ScriptBackup)) {
        Copy-Item -LiteralPath $SyncResult.ScriptBackup -Destination $SyncResult.ScriptPath -Force
    }
    if ($SyncResult.HadExistingMeta -and (Test-Path -LiteralPath $SyncResult.MetaBackup)) {
        Copy-Item -LiteralPath $SyncResult.MetaBackup -Destination $SyncResult.MetaPath -Force
    }

    if (Test-Path -LiteralPath $SyncResult.ScriptBackup) {
        Remove-Item -LiteralPath $SyncResult.ScriptBackup -Force
    }
    if (Test-Path -LiteralPath $SyncResult.MetaBackup) {
        Remove-Item -LiteralPath $SyncResult.MetaBackup -Force
    }
    if ((Test-Path -LiteralPath $SyncResult.BackupDir) -and -not (Get-ChildItem -LiteralPath $SyncResult.BackupDir -Force | Select-Object -First 1)) {
        Remove-Item -LiteralPath $SyncResult.BackupDir -Force
    }
}

if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir = Join-Path $ProjectPath "Builds\Android"
}

$unityPath = Resolve-ToolPath -PreferredPath $UnityExe -CommandName "Unity.exe"
if (-not $unityPath) {
    throw "Unity.exe not found. Expected at '$UnityExe'."
}

$adbPath = Resolve-ToolPath -PreferredPath $AdbExe -CommandName "adb"
if (-not $adbPath) {
    throw "adb not found. Expected at '$AdbExe'."
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$logDir = Join-Path $ProjectPath "Logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$precompileLog = Join-Path $logDir "unity-android-precompile.log"
$buildLog = Join-Path $logDir "unity-android-build.log"
$apkPath = Join-Path $OutputDir $ApkName
$reuseState = Get-PrecompileReuseState -ProjectDir $ProjectPath -UnityPath $unityPath

Write-Section "Build"
Write-Host "Project : $ProjectPath"
Write-Host "Unity   : $unityPath"
Write-Host "ADB     : $adbPath"
Write-Host "APK     : $apkPath"
Write-Host "Flow    : Sync script -> Precompile -> Build APK -> Install"
Write-Host "Reuse   : skip_sync=$($reuseState.CanSkipSync), skip_precompile=$($reuseState.CanSkipPrecompile), stamp=$($reuseState.HasReusableStamp)"

$env:UNITY_ANDROID_BUILD_OUTPUT_DIR = $OutputDir
$env:UNITY_ANDROID_BUILD_APK_NAME = $ApkName
$env:UNITY_ANDROID_KEYSTORE_PATH = $KeystorePath
$env:UNITY_ANDROID_KEYSTORE_PASS = $KeystorePass
$env:UNITY_ANDROID_KEYALIAS_NAME = $KeyaliasName
$env:UNITY_ANDROID_KEYALIAS_PASS = $KeyaliasPass

$syncResult = $null
try {
    if ($reuseState.CanSkipSync) {
        Write-Section "Stage 1/4 Sync Build Script"
        Write-Host "Skipped: injected script matches template."
    }
    else {
        Write-Section "Stage 1/4 Sync Build Script"
        $syncResult = Sync-BuildScript -ProjectDir $ProjectPath
        Write-Host "Injected: $($syncResult.ScriptPath)"
        $reuseState = Get-PrecompileReuseState -ProjectDir $ProjectPath -UnityPath $unityPath
    }

    if ($reuseState.CanSkipPrecompile) {
        Write-Section "Stage 2/4 Precompile"
        Write-Host "Skipped: reusable precompile stamp found."
    }
    else {
        Write-Section "Stage 2/4 Precompile"
        Invoke-UnityProcess -UnityPath $unityPath -Arguments @(
            '-batchmode',
            '-quit',
            '-projectPath', $ProjectPath,
            '-logFile', $precompileLog
        ) -StageName 'precompile' -LogPath $precompileLog

        Save-PrecompileStamp -StampPath $reuseState.StampPath -UnityPath $unityPath -SourceHash $reuseState.SourceHash -SourceMetaHash $reuseState.SourceMetaHash
    }

    Write-Section "Stage 3/4 Build APK"
    Invoke-UnityProcess -UnityPath $unityPath -Arguments @(
        '-batchmode',
        '-quit',
        '-projectPath', $ProjectPath,
        '-buildTarget', 'Android',
        '-logFile', $buildLog,
        '-executeMethod', 'AndroidBuildTools.BuildAndroidRelease'
    ) -StageName 'build' -LogPath $buildLog
}
finally {
    Restore-BuildScript -SyncResult $syncResult -CleanupInjected $CleanupInjectedScript.IsPresent
}

if (-not (Test-Path -LiteralPath $apkPath)) {
    throw "Unity reported success but APK was not found: $apkPath"
}

Write-Host "Build succeeded." -ForegroundColor Green

if ($SkipInstall) {
    Write-Host "Install skipped. APK kept at: $apkPath" -ForegroundColor Yellow
    exit 0
}

Write-Section "Stage 4/4 Install"
$devices = Get-ConnectedDevices -AdbPath $adbPath
if ($devices.Count -eq 0) {
    Write-Host "No Android device detected over USB. APK kept at: $apkPath" -ForegroundColor Yellow
    exit 0
}

foreach ($serial in $devices) {
    Write-Host "Installing to $serial ..."
    & $adbPath -s $serial install -r $apkPath
    if ($LASTEXITCODE -ne 0) {
        throw "APK install failed for device: $serial"
    }
}

Write-Host "Install completed." -ForegroundColor Green

exit 0

