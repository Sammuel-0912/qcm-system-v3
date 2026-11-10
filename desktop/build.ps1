# 在開發機（可連網）產生 desktop\output\QCM-Setup.exe（spec §21，步驟見 DEPLOY.windows.md）。
# 需要：Node（npm）、Python 3（決定打包的 Python 版本）、Inno Setup 6。
# 用法：powershell -ExecutionPolicy Bypass -File desktop\build.ps1
#
# 後端用 Python 官方的可嵌入版（embeddable package）執行，不用 PyInstaller：
# 官方 python.exe 有簽章；PyInstaller 產生的未簽章 exe 會被企業防毒（例：Trend Micro）在寫檔時靜默終止。
$ErrorActionPreference = 'Stop'
$Desktop = $PSScriptRoot
$Root = Split-Path $Desktop -Parent
$Vendor = Join-Path $Desktop 'vendor'
$Stage = Join-Path $Desktop 'build\stage'
New-Item -ItemType Directory -Force $Vendor | Out-Null

function Get-Vendor($Name, $Url) {
    $Path = Join-Path $Vendor $Name
    if (-not (Test-Path $Path)) { Invoke-WebRequest -UseBasicParsing $Url -OutFile $Path }
    $Path
}

# 打包的 Python 與開發機的 Python 同版本，pip 才會裝到相符的二進位套件（cp3XX-win_amd64）
$PyVersion = (python -c "import platform; print(platform.python_version())").Trim()
$PyTag = (python -c "import sys; print(f'python{sys.version_info[0]}{sys.version_info[1]}')").Trim()
$Embed = Get-Vendor "python-$PyVersion-embed-amd64.zip" "https://www.python.org/ftp/python/$PyVersion/python-$PyVersion-embed-amd64.zip"
$WinSW = Get-Vendor 'WinSW-x64.exe' 'https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe'

$Iscc = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Iscc) { throw '找不到 Inno Setup 6（winget install JRSoftware.InnoSetup）' }

Write-Host '== 1/3 前端建置'
Push-Location (Join-Path $Root 'frontend')
npm run build
if ($LASTEXITCODE -ne 0) { throw '前端建置失敗' }
Pop-Location

Write-Host "== 2/3 後端（Python $PyVersion 可嵌入版＋套件）"
if (Test-Path $Stage) { Remove-Item -Recurse -Force $Stage }
$PyDir = Join-Path $Stage 'python'
Expand-Archive $Embed -DestinationPath $PyDir
# ._pth 決定 sys.path：標準庫、套件，以及上一層（app\ 與 launcher.py 所在）
Set-Content -Encoding ascii (Join-Path $PyDir "$PyTag._pth") @("$PyTag.zip", '.', 'Lib\site-packages', '..', 'import site')
python -m pip install --quiet --disable-pip-version-check --only-binary=:all: `
    --target (Join-Path $PyDir 'Lib\site-packages') -r (Join-Path $Root 'backend\requirements.txt')
if ($LASTEXITCODE -ne 0) { throw '安裝後端套件失敗' }
Copy-Item -Recurse (Join-Path $Root 'backend\app') (Join-Path $Stage 'app')
Get-ChildItem -Recurse -Directory -Filter __pycache__ $Stage | Remove-Item -Recurse -Force
Copy-Item -Recurse (Join-Path $Root 'frontend\dist') (Join-Path $Stage 'web')
Copy-Item (Join-Path $Desktop 'launcher.py') $Stage
Copy-Item $WinSW (Join-Path $Stage 'qcm-service.exe')
Copy-Item (Join-Path $Desktop 'qcm-service.xml') $Stage

Write-Host '== 3/3 安裝程式（Inno Setup）'
$Version = (Get-Date -Format 'yyyy.M.d') + '.' + (git -C $Root rev-parse --short HEAD)
& $Iscc "/DAppVersion=$Version" (Join-Path $Desktop 'installer.iss')
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup 失敗' }

Write-Host "完成：$(Join-Path $Desktop 'output\QCM-Setup.exe')（版本 $Version）"
