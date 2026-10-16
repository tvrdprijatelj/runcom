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
    # Exercise real .lnk files while keeping all shortcuts inside the test sandbox.
    $desktop = Join-Path $root 'Desktop'
    $programs = Join-Path $root 'Start Menu Programs'
    $installer = Join-Path $root 'install.ps1'
    $installerText = Get-Content (Join-Path $PSScriptRoot '..\install.ps1') -Raw
    $installerText = $installerText.Replace("[Environment]::GetFolderPath('Desktop')", "'" + $desktop.Replace("'", "''") + "'")
    $installerText = $installerText.Replace("[Environment]::GetFolderPath('Programs')", "'" + $programs.Replace("'", "''") + "'")
    Set-Content -Path $installer -Value $installerText -Encoding utf8

    foreach ($expected in @('installed', 'updated')) {
        $env:RUNCOM_TEST_VALUE = $expected
        python -c 'import os,zipfile; z=zipfile.ZipFile(os.environ["RUNCOM_FIXTURE"],"w"); z.writestr("release/runcom.py", "print("+repr(os.environ["RUNCOM_TEST_VALUE"])+")"); z.writestr("release/help.html","<h1>Help</h1>"); z.writestr("release/help.css","body{}"); z.writestr("release/style.css","body{}"); z.close()'
        if ($LASTEXITCODE) { throw 'Fixture generation failed.' }
        & $installer -InstallDir $install -Ref main
        $shell = New-Object -ComObject WScript.Shell
        foreach ($directory in @($desktop,$programs)) {
            $link = Join-Path $directory 'Runcom.lnk'
            if (-not (Test-Path $link)) { throw "Shortcut missing: $link" }
            $saved = $shell.CreateShortcut($link)
            python -c 'import os,sys; assert os.path.samefile(sys.argv[1],sys.argv[2])' $saved.TargetPath (Join-Path $install 'venv\Scripts\pythonw.exe')
            if ($LASTEXITCODE) { throw 'Wrong shortcut target' }
            python -c 'import os,sys; assert os.path.samefile(sys.argv[1],sys.argv[2])' $saved.Arguments.Trim('"') (Join-Path $install 'runcom.py')
            if ($LASTEXITCODE) { throw 'Wrong shortcut arguments' }
            python -c 'import os,sys; assert os.path.samefile(sys.argv[1],sys.argv[2])' $saved.WorkingDirectory $install
            if ($LASTEXITCODE) { throw 'Wrong shortcut working directory' }
        }
        $result = & (Join-Path $install 'venv\Scripts\python.exe') (Join-Path $install 'runcom.py')
        foreach ($asset in @('help.html', 'help.css', 'style.css')) {
            if (-not (Test-Path (Join-Path $install $asset))) { throw "Missing offline help asset: $asset" }
        }
        if ($LASTEXITCODE -ne 0 -or $result.Trim() -ne $expected) { throw "Installed app did not produce $expected" }
    }
    Write-Host 'Native Windows install and update with spaces and ampersand: PASS'
} finally {
    Remove-Item $root -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item Env:RUNCOM_FIXTURE -ErrorAction SilentlyContinue
    Remove-Item Env:RUNCOM_TEST_VALUE -ErrorAction SilentlyContinue
}
