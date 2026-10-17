# Remove only installer-owned files; preserve user scripts and extra files.
param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'Runcom'),
    [switch]$Yes
)
$ErrorActionPreference = 'Stop'
try {
    $InstallDir = [IO.Path]::GetFullPath($InstallDir).TrimEnd('\', '/')
    if ($InstallDir -eq [IO.Path]::GetPathRoot($InstallDir).TrimEnd('\', '/') -or $InstallDir -eq $HOME) {
        throw 'Unsafe installation directory'
    }
    if (Test-Path -LiteralPath $InstallDir) {
        $item = Get-Item -LiteralPath $InstallDir -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Refusing a linked installation directory' }
        if (-not (Test-Path -LiteralPath (Join-Path $InstallDir 'runcom.py') -PathType Leaf)) {
            throw 'Not a Runcom installation; nothing removed'
        }
    }
    Write-Host "Avinstallera / Uninstall Runcom: $InstallDir"
    Write-Host 'Stäng Runcom först. Egna skript sparas. / Close Runcom first. Your scripts are kept.'
    if (-not $Yes) {
        $answer = Read-Host 'Fortsätt? / Continue? [y/N]'
        if ($answer -notin @('y', 'yes', 'ja')) { Write-Host 'Avbrutet / Cancelled'; exit 0 }
    }
    # Remove only shortcuts that target this installation.
    $shell = $null
    try { $shell = New-Object -ComObject WScript.Shell } catch { Write-Warning 'Could not inspect shortcuts; remove them manually if needed.' }
    foreach ($location in @(
        (Join-Path ([Environment]::GetFolderPath('Programs')) 'Runcom.lnk'),
        (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Runcom.lnk'),
        (Join-Path ([Environment]::GetFolderPath('Programs')) 'Avinstallera Runcom.lnk')
    )) {
        if ($shell -and (Test-Path -LiteralPath $location)) {
            $shortcut = $shell.CreateShortcut($location)
            if ($shortcut.WorkingDirectory.TrimEnd('\', '/') -eq $InstallDir) {
                Remove-Item -LiteralPath $location -Force
            }
        }
    }
    $venv = Join-Path $InstallDir 'venv'
    if (Test-Path -LiteralPath $venv) {
        $item = Get-Item -LiteralPath $venv -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw 'Refusing to remove a linked venv; remove it manually'
        }
        if (Test-Path -LiteralPath (Join-Path $venv 'pyvenv.cfg') -PathType Leaf) {
            Remove-Item -LiteralPath $venv -Recurse -Force
        }
    }
    foreach ($name in @('runcom.py', 'runcom-language', 'runcom-revision', 'help.html', 'help.css', 'style.css', 'runcom.png', 'runcom.ico', 'uninstall.ps1', 'uninstall.sh')) {
        $path = Join-Path $InstallDir $name
        if (Test-Path -LiteralPath $path -PathType Leaf) { Remove-Item -LiteralPath $path -Force }
    }
    if ((Test-Path -LiteralPath $InstallDir) -and -not (Get-ChildItem -LiteralPath $InstallDir -Force | Select-Object -First 1)) {
        Remove-Item -LiteralPath $InstallDir
    }
    Write-Host 'Runcom har avinstallerats. Egna skript finns kvar. / Runcom uninstalled. Your scripts are kept.'
} catch {
    Write-Error "Uninstall failed: $_"
    exit 1
}
