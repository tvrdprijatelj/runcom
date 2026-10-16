param([string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'Runcom'))
$ErrorActionPreference = 'Stop'
function Invoke-Python {
    param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Python command failed (exit $LASTEXITCODE)." }
}
$tmp = Join-Path ([IO.Path]::GetTempPath()) ('runcom-' + [guid]::NewGuid())
try {
    $py = $null
    foreach ($candidate in @('py', 'python')) {
        if (Get-Command $candidate -ErrorAction SilentlyContinue) {
            & $candidate -c 'import sys, tkinter; sys.exit(0 if sys.version_info >= (3,8) else 1)'
            if ($LASTEXITCODE -eq 0) { $py = $candidate; break }
        }
    }
    if (-not $py) { throw 'Install Python 3.8+ from python.org with Tcl/Tk and the Python launcher, then retry.' }
    New-Item -ItemType Directory -Path $tmp | Out-Null
    $release = Invoke-RestMethod -Uri 'https://api.github.com/repos/tvrdprijatelj/runcom/releases/latest'
    if (-not $release.zipball_url) { throw 'The release has no source archive.' }
    Write-Host "Downloading Runcom $($release.tag_name)..."
    $zip = Join-Path $tmp 'release.zip'
    Invoke-WebRequest -UseBasicParsing -Uri $release.zipball_url -OutFile $zip
    $source = Join-Path $tmp 'source'
    Expand-Archive -Path $zip -DestinationPath $source
    $folder = @(Get-ChildItem $source -Directory)[0].FullName
    if (-not (Test-Path (Join-Path $folder 'runcom.py'))) { throw 'Release does not contain runcom.py.' }
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    $venv = Join-Path $InstallDir 'venv'
    $venvPython = Join-Path $venv 'Scripts\python.exe'
    if (-not (Test-Path $venvPython)) { Invoke-Python -Exe $py -Arguments @('-m', 'venv', $venv) }
    Invoke-Python -Exe $venvPython -Arguments @('-c', 'import tkinter')
    $requirements = Join-Path $folder 'requirements.txt'
    if (Test-Path $requirements) { Invoke-Python -Exe $venvPython -Arguments @('-m', 'pip', 'install', '-r', $requirements) }
    Copy-Item (Join-Path $folder 'runcom.py') (Join-Path $InstallDir 'runcom.py') -Force
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Runcom.lnk'))
    $shortcut.TargetPath = Join-Path $venv 'Scripts\pythonw.exe'
    $shortcut.Arguments = '"' + (Join-Path $InstallDir 'runcom.py') + '"'
    $shortcut.WorkingDirectory = $InstallDir
    $shortcut.Save()
    Write-Host "Installed in $InstallDir. Start Runcom using the desktop shortcut."
} catch {
    Write-Error $_
    exit 1
} finally {
    if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
}
