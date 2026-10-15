<#
.SYNOPSIS
  runcom Windows installer (PowerShell)
.DESCRIPTION
  Downloads latest release from GitHub, extracts, creates venv and installs requirements.
  If Python is missing, suggests installation via winget/choco or manual steps.
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

Write-Host "runcom installer — querying latest release..."

try {
  $rel = Invoke-RestMethod -UseBasicParsing -Uri $Api
} catch {
  Write-Error "Failed to query GitHub API: $_"
  exit 1
}

$zipUrl = $rel.zipball_url
if (-not $zipUrl) {
  Write-Error "Could not find zipball_url in release metadata"
  exit 1
}

Write-Host "Release zip: $zipUrl"
$tmp = Join-Path $env:TEMP ("runcom_install_{0}" -f ([guid]::NewGuid().ToString()))
New-Item -ItemType Directory -Path $tmp | Out-Null
Push-Location $tmp

$zipPath = Join-Path $tmp 'release.zip'
Write-Host "Downloading..."
Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath

$extractDir = Join-Path $tmp 'release_dir'
New-Item -ItemType Directory -Path $extractDir | Out-Null
Write-Host "Extracting..."
try {
  Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force
} catch {
  Write-Error "Extraction failed: $_"
  Pop-Location
  exit 1
}

$dirs = Get-ChildItem -Path $extractDir -Directory
if ($dirs.Count -eq 0) {
  Write-Error "No extracted folder found"
  Pop-Location
  exit 1
}
$releaseFolder = $dirs[0].FullName
Write-Host "Release folder: $releaseFolder"
Set-Location $releaseFolder

# Find Python
$py = $null
if (Has-Cmd py) { $py = 'py' }
elseif (Has-Cmd python) { $py = 'python' }

if (-not $py) {
  Write-Warning "Python 3 not found on PATH."
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
      Write-Host "Automatic install tools not available. Please install Python 3 from https://www.python.org/downloads/ and re-run."
      exit 2
    }
  } else {
    Write-Host "Please install Python 3 and re-run (or run with -InstallPythonAutomatically)."
    exit 2
  }
}

Write-Host "Using Python: $($py) --version"
& $py --version

# Create venv
Write-Host "Creating virtual environment in .\venv"
& $py -m venv .\venv

# Activate venv and install requirements
$activate = Join-Path (Get-Location) 'venv\Scripts\Activate.ps1'
if (Test-Path $activate) {
  Write-Host "Installing requirements (if present)..."
  $p = Join-Path (Get-Location) 'venv\Scripts\python.exe'
  & $p -m pip install --upgrade pip setuptools wheel
  if (Test-Path 'requirements.txt') {
    & $p -m pip install -r requirements.txt
  } else {
    Write-Host "No requirements.txt found; skipping pip install."
  }
  Write-Host "`nDone. Activate virtualenv with:`n  .\venv\Scripts\Activate.ps1"
} else {
  Write-Warning "Virtualenv activation script not found; venv may not have been created correctly."
}

Pop-Location
Write-Host "Installer finished."
