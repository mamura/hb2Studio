[CmdletBinding()]
param(
    [string]$WorkRoot,
    [switch]$Smoke,
    [string]$NativeLock,
    [string]$Wheelhouse
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($env:OS -ne 'Windows_NT') { throw 'Execute este script no PowerShell do Windows x64.' }
$Project = (Get-Item (Join-Path $PSScriptRoot '..\..')).FullName
$Version = '0.1.1'
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
if (-not $WorkRoot) { $WorkRoot = Join-Path $env:TEMP "HB2Studio-build\$Stamp" }
$WorkRoot = [System.IO.Path]::GetFullPath($WorkRoot)
$null = New-Item -ItemType Directory -Force -Path $WorkRoot
$Stage = Join-Path $WorkRoot 'source'
$Tools = Join-Path $WorkRoot 'tools'
$null = New-Item -ItemType Directory -Force -Path $Stage,$Tools
# Deliberate allowlist: never copy client PDFs, resultados/, photos or Git metadata.
foreach ($Folder in @('hb2_studio','packaging')) {
    $Source = (Get-Item (Join-Path $Project $Folder)).FullName
    Get-ChildItem $Source -Recurse -File | Where-Object {
        $_.Extension -in @('.py','.ps1','.iss','.spec','.txt','.md') -and $_.FullName -notmatch '__pycache__'
    } | ForEach-Object {
        $Relative = $_.FullName.Substring($Source.Length).TrimStart('\')
        $Target = Join-Path (Join-Path $Stage $Folder) $Relative
        $null = New-Item -ItemType Directory -Force -Path (Split-Path $Target -Parent)
        Copy-Item $_.FullName $Target -Force
    }
}
Copy-Item (Join-Path $Project 'pyproject.toml') $Stage -Force
function Native-Check([string]$Step) { if ($LASTEXITCODE -ne 0) { throw "$Step falhou (código $LASTEXITCODE)." } }
function Fetch([string]$Url, [string]$Path, [string]$Sha = '') {
    if (-not (Test-Path $Path)) { Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Path }
    $Actual = (Get-FileHash -Algorithm SHA256 $Path).Hash.ToLowerInvariant()
    if ($Sha -and $Actual -ne $Sha.ToLowerInvariant()) { throw "SHA-256 incorreto: $Path" }
    "$Actual  $Url" | Add-Content -Encoding UTF8 (Join-Path $WorkRoot 'downloads.sha256.txt')
}
if ($NativeLock) { $NativeLock = (Get-Item $NativeLock).FullName }
if ($Wheelhouse) { $Wheelhouse = (Get-Item $Wheelhouse).FullName }
$OriginalPath = $env:PATH
$OriginalMamba = $env:MAMBA_ROOT_PREFIX
$OriginalVendor = $env:HB2_VENDOR
Push-Location $Stage
try {
$Mamba = Join-Path $Tools 'micromamba.exe'
Fetch 'https://github.com/mamba-org/micromamba-releases/releases/download/2.10.0-0/micromamba-win-64.exe' $Mamba 'f8b4284bd4eb1134122eaf93b3ea6c7be567e596de5829e1a6f478e34e41974a'
$env:MAMBA_ROOT_PREFIX = Join-Path $WorkRoot 'mamba'
$Prefix = Join-Path $WorkRoot 'native'
$NativeCommand = if (Test-Path (Join-Path $Prefix 'conda-meta\history')) { 'install' } else { 'create' }
if ($NativeLock) {
    & $Mamba --no-rc $NativeCommand --yes --prefix $Prefix --file $NativeLock
} else {
    $CommittedLock = Join-Path $Project 'packaging\windows\tesseract-win64.explicit.txt'
    if (Test-Path $CommittedLock) {
        & $Mamba --no-rc $NativeCommand --yes --prefix $Prefix --file $CommittedLock
    } else {
        & $Mamba --no-rc $NativeCommand --yes --prefix $Prefix --override-channels -c conda-forge 'tesseract=5.5.4' 'libarchive=*=lgpl_*' 'python=3.12' 'pip'
    }
}
Native-Check 'Tesseract redistribuível Windows'
$Python = Join-Path $Prefix 'python.exe'
$env:PATH = "$Prefix;$(Join-Path $Prefix 'Library\bin');$env:SystemRoot\System32;$env:SystemRoot"
& $Python -c "import struct,sys; assert sys.platform=='win32' and struct.calcsize('P')==8 and sys.version_info[:2]==(3,12)"
Native-Check 'CPython Windows 3.12 x64'
# Conda's unversioned ICU aliases shadow the Windows ICU API used by current Qt.
# Keep versioned ICU DLLs for native dependencies; quarantine aliases in this build only.
$Quarantine = Join-Path $Tools 'icu-aliases'
$null = New-Item -ItemType Directory -Force -Path $Quarantine
foreach ($Name in @('icuuc.dll','icuin.dll','icudt.dll','icuio.dll','icutu.dll','icutest.dll')) {
    $Alias = Join-Path $Prefix "Library\bin\$Name"
    if (Test-Path $Alias) { Move-Item $Alias (Join-Path $Quarantine $Name) -Force }
}

$PipArgs = @('-m','pip','install','--disable-pip-version-check','--no-cache-dir','-r',(Join-Path $Stage 'packaging\windows\requirements-windows.txt'))
if ($Wheelhouse) { $PipArgs += @('--no-index','--find-links',$Wheelhouse) }
& $Python @PipArgs
Native-Check 'Dependências de compilação'
& $Python -c "from PySide6 import QtCore, QtGui, QtWidgets; print('Qt '+QtCore.qVersion())"
Native-Check 'Dependências DLL do Qt'
& $Python -m pip list --format=freeze --disable-pip-version-check | Set-Content -Encoding UTF8 (Join-Path $WorkRoot 'python-resolved.txt')

& $Python (Join-Path $Stage 'packaging\windows\write_native_lock.py') $Prefix (Join-Path $WorkRoot 'tesseract-win64.explicit.txt')
Native-Check 'Lock nativo'
$env:HB2_VENDOR = Join-Path $WorkRoot 'vendor'
& $Python (Join-Path $Stage 'packaging\windows\prepare_vendor.py') --prefix $Prefix --cache (Join-Path $env:MAMBA_ROOT_PREFIX 'pkgs') --output $env:HB2_VENDOR
Native-Check 'Licenças e runtime'
Fetch 'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0/LICENSE' (Join-Path $env:HB2_VENDOR 'licenses\tessdata_fast-LICENSE')
# Tool bootstrap is portable: no admin, registration or global shortcuts.
$InnoSetup = Join-Path $Tools 'innosetup-6.7.3.exe'
Fetch 'https://github.com/jrsoftware/issrc/releases/download/is-6_7_3/innosetup-6.7.3.exe' $InnoSetup
$Signature = Get-AuthenticodeSignature $InnoSetup
if ($Signature.Status -ne 'Valid') { throw 'Assinatura Authenticode do compilador Inno Setup inválida.' }
$Inno = Join-Path $Tools 'inno'
$Install = Start-Process -FilePath $InnoSetup -ArgumentList @('/PORTABLE=1','/CURRENTUSER','/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/NOICONS',"/DIR=`"$Inno`"") -Wait -PassThru
if ($Install.ExitCode -ne 0) { throw 'Falha ao preparar Inno Setup portátil.' }
Copy-Item (Join-Path $Inno 'license.txt') (Join-Path $env:HB2_VENDOR 'licenses\InnoSetup-LICENSE.txt')
& $Python -m PyInstaller --noconfirm --clean --distpath (Join-Path $WorkRoot 'dist') --workpath (Join-Path $WorkRoot 'pyinstaller') (Join-Path $Stage 'packaging\windows\HB2Studio.spec')
Native-Check 'PyInstaller onedir'
$Bundle = Join-Path $WorkRoot 'dist\HB2Studio'
& (Join-Path $Inno 'ISCC.exe') "/DAppVersion=$Version" "/DDistDir=$Bundle" "/DOutputPath=$(Join-Path $WorkRoot 'installer')" (Join-Path $Stage 'packaging\windows\installer.iss')
Native-Check 'Instalador Inno Setup'
$Output = Join-Path $Project "dist\windows\$Version-$Stamp"
$null = New-Item -ItemType Directory -Force -Path $Output
Copy-Item -Recurse $Bundle $Output
$Installer = Join-Path $Output "HB2Studio-$Version-x64-Setup.exe"
Copy-Item (Join-Path $WorkRoot "installer\HB2Studio-$Version-x64-Setup.exe") $Installer
Copy-Item (Join-Path $WorkRoot 'downloads.sha256.txt'),(Join-Path $WorkRoot 'python-resolved.txt'),(Join-Path $WorkRoot 'tesseract-win64.explicit.txt') $Output
(Get-FileHash -Algorithm SHA256 $Installer).Hash | Set-Content (Join-Path $Output 'installer.sha256.txt')
$null = New-Item -ItemType Directory -Force -Path (Join-Path $Project 'build\windows')
$Output | Set-Content -Encoding UTF8 (Join-Path $Project 'build\windows\last-output.txt')
if ($Smoke) { & (Join-Path $PSScriptRoot 'smoke.ps1') -Installer $Installer -Report (Join-Path $Output 'installer-smoke.txt') }
Write-Output "INSTALADOR=$Installer"
Write-Output "BUILD=$WorkRoot"

} finally {
    Pop-Location
    $env:PATH = $OriginalPath
    $env:MAMBA_ROOT_PREFIX = $OriginalMamba
    $env:HB2_VENDOR = $OriginalVendor
}
