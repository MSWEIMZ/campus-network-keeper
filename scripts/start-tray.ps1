# start-tray.ps1 - 以托盘模式启动校园网保活工具
# 双击此文件即可启动

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$srcDir = Join-Path (Split-Path -Parent $scriptDir) "src"
$mainPy = Join-Path $srcDir "main.py"

Start-Process -FilePath python -ArgumentList "`"$mainPy`" --tray" -WorkingDirectory $srcDir -WindowStyle Hidden
