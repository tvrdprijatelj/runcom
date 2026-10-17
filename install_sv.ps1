# Download the installer, then install Runcom in the selected language.
$ErrorActionPreference = 'Stop'
$runcomInstallerTemp = Join-Path ([IO.Path]::GetTempPath()) ('runcom-' + [guid]::NewGuid() + '.ps1')
try {
    Invoke-WebRequest -UseBasicParsing 'https://raw.githubusercontent.com/tvrdprijatelj/runcom/main/install.ps1' -OutFile $runcomInstallerTemp
    & $runcomInstallerTemp @args -Language sv
} finally {
    Remove-Item $runcomInstallerTemp -ErrorAction SilentlyContinue
}
