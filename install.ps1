<#
.SYNOPSIS
  runcom Windows installer (PowerShell)
.DESCRIPTION
  Downloads the latest GitHub release for runcom, extracts it, creates a venv,
  and installs dependencies. If Python is missing, it can prompt to install it.
#>

param(
  [switch]$InstallPythonAutomatically
)

$Owner = 'tvrdprijatelj'
$Repo  = 'runcom'
$Api   = "https://api.github.com/repos/$Owner/$Repo/releases/latest"

function Has-Cmd($name) {
  $null -ne (Get-Command $name -ErrorAction SilentlyContinue)
}

Write-Host "runcom installer — fetching the latest release..."

try {
  $rel = Invoke-RestMethod -UseBasicParsing -Uri $Api -ErrorAction Stop
} catch {
  Write-Error "Failed to query GitHub API: $_"
  exit 1
}

$zipUrl = $rel.zipball_url
if (-not $zipUrl) {
  Write-Error "Could not find zipball_url in the GitHub release metadata."
  exit 1
}

Write-Host "Release: $($rel.tag_name)"
$tmp = Join-Path $env:TEMP ("runcom_install_{0}" -f ([guid]::NewGuid().ToString()))
New-Item -ItemType Directory -Path $tmp | Out-Null
Push-Location $tmp

$zipPath = Join-Path $tmp 'release.zip'
Write-Host "Downloading release archive..."
Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath

$extractDir = Join-Path $tmp 'release_dir'
New-Item -ItemType Directory -Path $extractDir | Out-Null
Write-Host "Extracting archive..."
try {
  if (Get-Command Expand-Archive -ErrorAction SilentlyContinue) {
    Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force
  } else {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory($zipPath, $extractDir)
  }
} catch {
  Write-Error "Extraction failed: $_"
  Pop-Location
  exit 1
}

$dirs = Get-ChildItem -Path $extractDir -Directory
if ($dirs.Count -eq 0) {
  Write-Error "No extracted directory was found inside the archive."
  Pop-Location
  exit 1
}

$releaseFolder = $dirs[0].FullName
Write-Host "Release folder: $releaseFolder"
Set-Location $releaseFolder

$py = $null
if (Has-Cmd py) { $py = 'py' }
elseif (Has-Cmd python) { $py = 'python' }

if (-not $py) {
  Write-Warning "Python 3 was not found on PATH."
  if ($InstallPythonAutomatically) {
    if (Has-Cmd winget) {
      Write-Host "Attempting to install Python via winget..."
      winget install --id Python.Python.3 -e --silent
      $py = 'py'
    } elseif (Has-Cmd choco) {
      Write-Host "Attempting to install Python via choco..."
      choco install -y python
      $py = 'python'
    } else {
      Write-Host "Automatic install tools are not available. Please install Python 3 manually and re-run this script."
      exit 2
    }
  } else {
    Write-Host "Python 3 is required. Please install Python 3 and re-run, or use -InstallPythonAutomatically."
    exit 2
  }
}

Write-Host "Using Python: $($py) --version"
& $py --version

Write-Host "Creating virtual environment in .\venv"
& $py -m venv .\venv

$activateScript = Join-Path (Get-Location) 'venv\Scripts\Activate.ps1'
if (Test-Path $activateScript) {
  $venvPython = Join-Path (Get-Location) 'venv\Scripts\python.exe'
  & $venvPython -m pip install --upgrade pip setuptools wheel
  if (Test-Path 'requirements.txt') {
    & $venvPython -m pip install -r requirements.txt
  } else {
    Write-Host "No requirements.txt file was found; skipping dependency installation."
  }
  Write-Host "Installation complete. Activate it with: .\venv\Scripts\Activate.ps1"
} else {
  Write-Warning "The virtual environment activation script was not found. The environment may not have been created correctly."
}

Pop-Location
Write-Host "Installer finished."
