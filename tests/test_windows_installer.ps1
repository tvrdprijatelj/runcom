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
        python -c 'import os,sys,zipfile; z=zipfile.ZipFile(os.environ["RUNCOM_FIXTURE"],"a"); [z.write(os.path.join(sys.argv[1],name),"release/"+name) for name in ("runcom.png","runcom.ico","uninstall.ps1","uninstall.sh")]; z.close()' (Join-Path $PSScriptRoot '..')
        if ($LASTEXITCODE) { throw 'Icon fixture generation failed.' }
        & $installer -InstallDir $install -Ref main
        $shell = New-Object -ComObject WScript.Shell
        foreach ($directory in @($desktop,$programs)) {
            $link = Join-Path $directory 'Runcom.lnk'
            if (-not (Test-Path $link)) { throw "Shortcut missing: $link" }
            $saved = $shell.CreateShortcut($link)
            $iconPath = $saved.IconLocation -replace ',0$', ''
            python -c 'import os,sys; assert os.path.samefile(sys.argv[1],sys.argv[2])' $iconPath (Join-Path $install 'runcom.ico')
            if ($LASTEXITCODE) { throw 'Wrong shortcut icon' }
            python -c 'import os,sys; assert os.path.samefile(sys.argv[1],sys.argv[2])' $saved.TargetPath (Join-Path $install 'venv\Scripts\pythonw.exe')
            if ($LASTEXITCODE) { throw 'Wrong shortcut target' }
            python -c 'import os,sys; assert os.path.samefile(sys.argv[1],sys.argv[2])' $saved.Arguments.Trim('"') (Join-Path $install 'runcom.py')
            if ($LASTEXITCODE) { throw 'Wrong shortcut arguments' }
            python -c 'import os,sys; assert os.path.samefile(sys.argv[1],sys.argv[2])' $saved.WorkingDirectory $install
            if ($LASTEXITCODE) { throw 'Wrong shortcut working directory' }
        }
        $result = & (Join-Path $install 'venv\Scripts\python.exe') (Join-Path $install 'runcom.py')
        foreach ($asset in @('help.html', 'help.css', 'style.css', 'runcom.png', 'runcom.ico')) {
            if (-not (Test-Path (Join-Path $install $asset))) { throw "Missing offline help asset: $asset" }
        }
        if ($LASTEXITCODE -ne 0 -or $result.Trim() -ne $expected) { throw "Installed app did not produce $expected" }
    }
    $uninstallLink = Join-Path $programs 'Avinstallera Runcom.lnk'
    if (-not (Test-Path $uninstallLink)) { throw 'Missing Start-menu uninstaller' }
    $saved = $shell.CreateShortcut($uninstallLink)
    if ($saved.Arguments -notlike '*-InstallDir*') { throw 'Missing installation path in uninstall shortcut' }
    $uninstaller = Join-Path $install 'uninstall.ps1'
    $removeText = Get-Content $uninstaller -Raw
    $removeText = $removeText.Replace("[Environment]::GetFolderPath('Desktop')", "'" + $desktop.Replace("'", "''") + "'")
    $removeText = $removeText.Replace("[Environment]::GetFolderPath('Programs')", "'" + $programs.Replace("'", "''") + "'")
    Set-Content -Path $uninstaller -Value $removeText -Encoding utf8
    $personal = Join-Path $install 'my-script.py'
    Set-Content $personal 'print("keep")'
    & $uninstaller -InstallDir $install -Yes
    if (Test-Path (Join-Path $install 'runcom.py')) { throw 'Application was not removed' }
    if (Test-Path (Join-Path $install 'venv')) { throw 'Virtual environment was not removed' }
    if (-not (Test-Path $personal)) { throw 'Personal script was removed' }
    foreach ($link in @((Join-Path $desktop 'Runcom.lnk'),(Join-Path $programs 'Runcom.lnk'),$uninstallLink)) {
        if (Test-Path $link) { throw "Shortcut was not removed: $link" }
    }
    Write-Host 'Native Windows install, update and uninstall preserving personal scripts: PASS' 
} finally {
    Remove-Item $root -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item Env:RUNCOM_FIXTURE -ErrorAction SilentlyContinue
    Remove-Item Env:RUNCOM_TEST_VALUE -ErrorAction SilentlyContinue
}
