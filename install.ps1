param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'Runcom'),
    [string]$Ref = '',
    [ValidateSet('sv', 'en')][string]$Language,
    [switch]$NoShortcut
)
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
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if (-not $command -or $command.Source -like '*\WindowsApps\*') { continue }
        $candidateArgs = @('-c', 'import sys, tkinter; tkinter.Tcl(); sys.exit(0 if sys.version_info >= (3,8) else 1)')
        if ($candidate -eq 'py') { $candidateArgs = @('-3') + $candidateArgs }
        & $candidate @candidateArgs
        if ($LASTEXITCODE -eq 0) {
            $probe = @('-c', 'import sys; print(sys.executable)')
            if ($candidate -eq 'py') { $probe = @('-3') + $probe }
            $py = (& $candidate @probe | Select-Object -Last 1).Trim()
            break
        }
    }
    if (-not $py) { throw 'Install Python 3.8+ from python.org with Tcl/Tk and the Python launcher, then retry.' }
    New-Item -ItemType Directory -Path $tmp | Out-Null
    if ($Ref) {
        $zipUrl = 'https://api.github.com/repos/tvrdprijatelj/runcom/zipball/' + [Uri]::EscapeDataString($Ref)
        Write-Host "Installing source ref: $Ref"
    } else {
        $release = Invoke-RestMethod -Uri 'https://api.github.com/repos/tvrdprijatelj/runcom/releases/latest' -TimeoutSec 60
        if (-not $release.zipball_url) { throw 'The release has no source archive. Use -Ref main for current source.' }
        $zipUrl = $release.zipball_url
        Write-Host "Downloading Runcom $($release.tag_name)..."
    }
    $zip = Join-Path $tmp 'release.zip'
    Invoke-WebRequest -UseBasicParsing -Uri $zipUrl -OutFile $zip -TimeoutSec 180
    $source = Join-Path $tmp 'source'
    $extract = @'
import pathlib, sys, zipfile
archive_path, source = sys.argv[1:]
target = pathlib.Path(source).resolve()
with zipfile.ZipFile(archive_path) as archive:
    entries = archive.infolist()
    if sum(e.file_size for e in entries) > 100 * 1024 * 1024:
        raise SystemExit('Archive is unexpectedly large')
    for entry in entries:
        resolved = (target / entry.filename).resolve()
        if target not in resolved.parents or (entry.external_attr >> 16) & 0o170000 == 0o120000:
            raise SystemExit('Unsafe archive path or symlink')
    archive.extractall(target)
roots = list(target.iterdir())
if len(roots) != 1 or not roots[0].is_dir():
    raise SystemExit('Archive must contain one project directory')
app = roots[0] / 'runcom.py'
compile(app.read_bytes(), str(app), 'exec')
'@
    Invoke-Python -Exe $py -Arguments @('-c', $extract, $zip, $source)
    $folder = @(Get-ChildItem $source -Directory)[0].FullName
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    $InstallDir = (Resolve-Path $InstallDir).Path
    $venv = Join-Path $InstallDir 'venv'
    $venvPython = Join-Path $venv 'Scripts\python.exe'
    $validVenv = $false
    if (Test-Path $venvPython) {
        & $venvPython -c 'import sys, tkinter; sys.exit(0 if sys.version_info >= (3,8) else 1)'
        $validVenv = $LASTEXITCODE -eq 0
    }
    if (-not $validVenv) { Invoke-Python -Exe $py -Arguments @('-m', 'venv', '--clear', $venv) }
    Invoke-Python -Exe $venvPython -Arguments @('-c', 'import tkinter')
    $requirements = Join-Path $folder 'requirements.txt'
    if (Test-Path $requirements) { Invoke-Python -Exe $venvPython -Arguments @('-m', 'pip', 'install', '-r', $requirements) }
    if ($Language -eq 'en' -and -not (Select-String -Path (Join-Path $folder 'runcom.py') -Pattern 'TRANSLATIONS' -Quiet)) {
        throw 'This version does not support English. Retry with -Ref main.'
    }
    $appPath = Join-Path $InstallDir 'runcom.py'
    $copy = @'
import os, pathlib, sys, tempfile
source, target = map(pathlib.Path, sys.argv[1:])
fd, temporary = tempfile.mkstemp(prefix='.runcom-', dir=str(target.parent))
try:
    with os.fdopen(fd, 'wb') as stream:
        stream.write(source.read_bytes())
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, target)
finally:
    if os.path.exists(temporary):
        os.unlink(temporary)
'@
    Invoke-Python -Exe $py -Arguments @('-c', $copy, (Join-Path $folder 'runcom.py'), $appPath)
    foreach ($asset in @('help.html', 'help.css', 'style.css', 'runcom.png', 'runcom.ico')) {
        $assetSource = Join-Path $folder $asset
        if (Test-Path $assetSource -PathType Leaf) {
            Invoke-Python -Exe $py -Arguments @('-c', $copy, $assetSource, (Join-Path $InstallDir $asset))
        }
    }
    [IO.File]::WriteAllText((Join-Path $InstallDir 'runcom-revision'), ((Split-Path $folder -Leaf) -split '-')[-1], (New-Object Text.UTF8Encoding $false))
    if ($Language) {
        [IO.File]::WriteAllText((Join-Path $InstallDir 'runcom-language'), $Language, (New-Object Text.UTF8Encoding $false))
    }
    if (-not $NoShortcut) {
        try {
            $shell = New-Object -ComObject WScript.Shell
        } catch {
            $shell = $null
            Write-Warning 'Installed successfully, but Windows shortcut services are unavailable.'
        }
        $shortcutLocations = @(
            (Join-Path ([Environment]::GetFolderPath('Programs')) 'Runcom.lnk'),
            (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Runcom.lnk')
        )
        foreach ($location in $shortcutLocations) {
            if (-not $shell) { continue }
            try {
                New-Item -ItemType Directory -Force -Path (Split-Path $location) | Out-Null
                $shortcut = $shell.CreateShortcut($location)
                $shortcut.TargetPath = Join-Path $venv 'Scripts\pythonw.exe'
                $shortcut.Arguments = '"' + $appPath + '"'
                $shortcut.WorkingDirectory = $InstallDir
                $iconPath = Join-Path $InstallDir 'runcom.ico'
                if (Test-Path $iconPath -PathType Leaf) {
                    $shortcut.IconLocation = $iconPath + ',0'
                }
                $shortcut.Description = 'Runcom script editor'
                $shortcut.Save()
                Write-Host "Shortcut created: $location"
            } catch {
                Write-Warning "Installed successfully, but could not create shortcut: $location"
            }
        }
    }
    Write-Host "Installed in $InstallDir. Search for Runcom in Start, use the desktop shortcut or run:"
    Write-Host ("& '" + $venvPython.Replace("'", "''") + "' '" + $appPath.Replace("'", "''") + "'")
} catch {
    Write-Host "Installation failed: $_" -ForegroundColor Red
    exit 1
} finally {
    if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue }
}
