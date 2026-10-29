# Builds the Windows installer: build\installer\JobHunterSetup.exe
#
#   powershell -ExecutionPolicy Bypass -File installer\build.ps1            (version from bot.py)
#   powershell -ExecutionPolicy Bypass -File installer\build.ps1 -Version 1.3.0
#
# Needs Python 3.10+ and Inno Setup 6 (winget install JRSoftware.InnoSetup).
# GitHub Actions runs this for every v* tag (.github/workflows/release.yml).
param([string]$Version = "")  # empty: the VERSION in bot.py
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$build = Join-Path $root "build"
$icon = Join-Path $PSScriptRoot "icon.ico"

# The window compares bot.VERSION with the latest release to offer updates, so the two must agree.
$appVersion = (Select-String -Path (Join-Path $root "bot.py") -Pattern '^VERSION = "(.+)"').Matches[0].Groups[1].Value
if (-not $Version) { $Version = $appVersion }
if ($Version -ne "0.0.0" -and $Version -ne $appVersion) {
    throw "Version $Version does not match VERSION = `"$appVersion`" in bot.py. Update bot.py first."
}

python -m pip install --disable-pip-version-check "pyinstaller==6.20.0"
if ($LASTEXITCODE) { throw "pip install pyinstaller failed" }

# One folder (not --onefile): starts faster and antivirus flags it less often.
python -m PyInstaller --noconfirm --clean --windowed --onedir --name JobHunter `
    --icon $icon --add-data "$icon;." `
    --distpath (Join-Path $build "dist") --workpath (Join-Path $build "work") --specpath $build `
    (Join-Path $root "jobhunter.py")
if ($LASTEXITCODE) { throw "PyInstaller failed" }

$iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source
foreach ($p in @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
                 "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe")) {
    if (-not $iscc -and (Test-Path $p)) { $iscc = $p }
}
if (-not $iscc) { throw "Inno Setup 6 not found. Install it: winget install JRSoftware.InnoSetup" }
& $iscc "/DAppVersion=$Version" (Join-Path $PSScriptRoot "JobHunter.iss")
if ($LASTEXITCODE) { throw "Inno Setup failed" }
Write-Host "Done: $(Join-Path $build 'installer\JobHunterSetup.exe')"
