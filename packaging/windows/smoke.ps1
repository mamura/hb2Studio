[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Installer,
      [Parameter(Mandatory=$true)][string]$Report, [switch]$AllowUpgrade)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$InstallDir=Join-Path $env:LOCALAPPDATA 'Programs\HB2 Studio'
$StartMenu=[Environment]::GetFolderPath('Programs')
$Shortcut=Join-Path $StartMenu 'HB2 Studio\HB2 Studio.lnk'
if ((Test-Path $InstallDir) -and -not $AllowUpgrade) { throw 'Já existe uma instalação. Checagem automática interrompida para não sobrescrevê-la.' }
$Setup=Start-Process -FilePath $Installer -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/SP-','/NORESTART') -Wait -PassThru
if ($Setup.ExitCode -ne 0) { throw "Instalador falhou: $($Setup.ExitCode)" }
$Exe=Join-Path $InstallDir 'HB2Studio.exe'
$Native=Join-Path $InstallDir '_internal\tesseract\Library\bin\tesseract.exe'
$Model=Join-Path $InstallDir '_internal\tesseract\tessdata\por.traineddata'
$Tsv=Join-Path $InstallDir '_internal\tesseract\tessdata\configs\tsv'
$Licenses=Join-Path $InstallDir '_internal\licenses\LEIA-ME.txt'
foreach ($Required in @($Exe,$Native,$Model,$Tsv,$Licenses,$Shortcut,(Join-Path $InstallDir 'unins000.exe'))) {
    if (-not (Test-Path $Required)) { throw "Arquivo da instalação ausente: $Required" }
}
$UninstallKey='HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{32B7B5DD-9451-4A79-A3EC-03244BE36DA7}_is1'
if (-not (Test-Path $UninstallKey)) { throw 'Desinstalação por usuário não registrada no HKCU.' }
$Shell=New-Object -ComObject WScript.Shell
$Link=$Shell.CreateShortcut($Shortcut)
if ($Link.TargetPath -ne $Exe) { throw 'Atalho não aponta ao executável instalado.' }
$Before=@(Get-Process -Name HB2Studio -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
# Actual shell launch through the installed Start menu shortcut, no PDF/motor invocation.
Start-Process -FilePath $Shortcut
$App=$null
$Deadline=(Get-Date).AddSeconds(45)
do {
    Start-Sleep -Milliseconds 500
    $Candidates=@(Get-Process -Name HB2Studio -ErrorAction SilentlyContinue | Where-Object { $_.Id -notin $Before -and $_.Path -eq $Exe })
    $App=$Candidates | Where-Object { $_.MainWindowHandle -ne 0 -and $_.Responding } | Select-Object -First 1
} until ($App -or (Get-Date) -gt $Deadline)
if (-not $App) { throw 'A janela não abriu pelo atalho. A instalação permanece disponível para inspeção manual.' }
$Title=$App.MainWindowTitle
if ($Title -notlike '*HB2 Studio*Extrair PDF*') { throw 'A janela inicial não corresponde a Extrair PDF.' }
$null=$App.CloseMainWindow()
if (-not $App.WaitForExit(15000)) { throw 'A janela não encerrou normalmente após a checagem.' }
@(
    'INSTALACAO_POR_USUARIO=OK',
    'REGISTRO_DESINSTALACAO_HKCU=OK',
    'ATALHO_MENU_INICIAR=OK',
    'ABERTURA_PELO_ATALHO=OK',
    'QT_JANELA_RESPONSIVA=OK',
    'TESSERACT_E_POR_INCLUIDOS=OK',
    'LICENCAS_INCLUIDAS=OK',
    'VALIDACAO_MOTOR=NAO_EXECUTADA',
    "INSTALACAO=$InstallDir"
) | Set-Content -Encoding UTF8 $Report
Write-Output "CHECAGEM=OK; RELATORIO=$Report"
