$ErrorActionPreference = 'Stop'
$root = Join-Path ([IO.Path]::GetTempPath()) ('runcom test ' + [guid]::NewGuid())
New-Item -ItemType Directory $root | Out-Null
$env:RUNCOM_FIXTURE = Join-Path $root 'release.zip'
function Invoke-WebRequest {
    param([switch]$UseBasicParsing, [string]$Uri, [string]$OutFile, [int]$TimeoutSec)
    Copy-Item $env:RUNCOM_FIXTURE $OutFile
}
function Invoke-RestMethod {
    param([string]$Uri, [int]$TimeoutSec)
    return @{ zipball_url = 'https://example.test/release.zip'; tag_name = 'test' }
}
try {
    $install = Join-Path $root 'app & space'
    foreach ($expected in @('installed', 'updated')) {
        $env:RUNCOM_TEST_VALUE = $expected
        python -c 'import os,zipfile; z=zipfile.ZipFile(os.environ["RUNCOM_FIXTURE"],"w"); z.writestr("release/runcom.py", "print("+repr(os.environ["RUNCOM_TEST_VALUE"])+")"); z.close()'
        if ($LASTEXITCODE) { throw 'Fixture generation failed.' }
        & (Join-Path $PSScriptRoot '..\install.ps1') -InstallDir $install -Ref main -NoShortcut
        $result = & (Join-Path $install 'venv\Scripts\python.exe') (Join-Path $install 'runcom.py')
        if ($LASTEXITCODE -ne 0 -or $result.Trim() -ne $expected) { throw "Installed app did not produce $expected" }
    }
    Write-Host 'Native Windows install and update with spaces and ampersand: PASS'
} finally {
    Remove-Item $root -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item Env:RUNCOM_FIXTURE -ErrorAction SilentlyContinue
    Remove-Item Env:RUNCOM_TEST_VALUE -ErrorAction SilentlyContinue
}
