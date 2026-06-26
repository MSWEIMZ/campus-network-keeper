# install.ps1 - 校园网保活工具一键安装脚本
# 以管理员身份运行此脚本

Write-Host "====================================" -ForegroundColor Cyan
Write-Host " 校园网保活工具 - 安装向导" -ForegroundColor Cyan
Write-Host "====================================" -ForegroundColor Cyan
Write-Host ""

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$srcDir = Join-Path $projectRoot "src"
$mainPy = Join-Path $srcDir "main.py"
$accountIni = Join-Path $projectRoot "account.ini"

# 检查管理员权限
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "[!] 请以管理员身份运行此脚本！" -ForegroundColor Red
    Write-Host "    右键 PowerShell -> 以管理员身份运行" -ForegroundColor Yellow
    pause
    exit 1
}

# 检查 Python
Write-Host "[1/4] 检查 Python..." -ForegroundColor Yellow
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "[!] 未找到 Python，请先安装 Python 3.10+" -ForegroundColor Red
    pause
    exit 1
}
$pyVer = python --version 2>&1
Write-Host "  Python: $pyVer" -ForegroundColor Green

# 检查 Node.js
Write-Host "[2/4] 检查 Node.js..." -ForegroundColor Yellow
$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) {
    Write-Host "[!] 未找到 Node.js，请先安装 Node.js" -ForegroundColor Red
    pause
    exit 1
}
$nodeVer = node --version 2>&1
Write-Host "  Node.js: $nodeVer" -ForegroundColor Green

# 安装 Python 依赖
Write-Host "[3/4] 安装 Python 依赖..." -ForegroundColor Yellow
pip install requests pystray Pillow --quiet 2>&1 | Out-Null
Write-Host "  依赖已安装" -ForegroundColor Green

# 检查账号配置
Write-Host "[4/4] 检查账号配置..." -ForegroundColor Yellow
if (Test-Path $accountIni) {
    Write-Host "  account.ini 已存在" -ForegroundColor Green
} else {
    Write-Host "  account.ini 不存在，请先配置账号" -ForegroundColor Yellow
}

# 安装开机自启
Write-Host ""
Write-Host "是否安装开机自启？" -ForegroundColor Cyan
$choice = Read-Host "输入 Y 安装，N 跳过"
if ($choice -eq "Y" -or $choice -eq "y") {
    python $mainPy --install
} else {
    Write-Host "  跳过开机自启安装" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "====================================" -ForegroundColor Cyan
Write-Host " 安装完成！" -ForegroundColor Green
Write-Host "====================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "使用方法:" -ForegroundColor White
Write-Host "  托盘模式:  python $mainPy --tray" -ForegroundColor White
Write-Host "  命令行模式: python $mainPy" -ForegroundColor White
Write-Host "  诊断模式:  python $mainPy --diagnose" -ForegroundColor White
Write-Host ""
pause
