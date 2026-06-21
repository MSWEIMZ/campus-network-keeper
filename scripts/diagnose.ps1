# diagnose.ps1 - Windows 网络诊断脚本
# 在 PowerShell 中运行: .\diagnose.ps1

Write-Host "===== 校园网保活工具 - 网络诊断 =====" -ForegroundColor Cyan

# 1. 网卡状态
Write-Host "`n[1] 网卡状态:" -ForegroundColor Yellow
netsh interface show interface

# 2. IP 配置
Write-Host "`n[2] IP 配置:" -ForegroundColor Yellow
ipconfig | Select-String -Pattern "IPv4|默认网关|Default Gateway|以太网|Wi-Fi|Ethernet|Wireless"

# 3. 以太网连接状态
Write-Host "`n[3] 以太网连接测试:" -ForegroundColor Yellow
$gw = (ipconfig | Select-String "默认网关|Default Gateway" | Where-Object { $_ -notmatch "0.0.0.0" } | Select-Object -First 1).ToString().Split(":")[-1].Trim()
if ($gw) {
    Write-Host "  网关: $gw"
    ping -n 2 -w 2000 $gw
} else {
    Write-Host "  未找到有效网关" -ForegroundColor Red
}

# 4. 外网连通性
Write-Host "`n[4] 外网连通性:" -ForegroundColor Yellow
ping -n 2 -w 3000 connect.rom.miui.com

# 5. DNS 解析
Write-Host "`n[5] DNS 解析测试:" -ForegroundColor Yellow
nslookup www.baidu.com 2>&1

# 6. 认证页探测
Write-Host "`n[6] 认证页探测:" -ForegroundColor Yellow
try {
    $r = Invoke-WebRequest -Uri "http://www.msftconnecttest.com/connecttest.txt" -TimeoutSec 5 -UseBasicParsing
    if ($r.Content -match "Microsoft Connect Test") {
        Write-Host "  认证探测通过（无需登录）" -ForegroundColor Green
    } else {
        Write-Host "  可能需要认证登录，响应内容:" -ForegroundColor Yellow
        Write-Host "  $($r.Content.Substring(0, [Math]::Min(200, $r.Content.Length)))"
    }
} catch {
    Write-Host "  认证探测失败: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`n===== 诊断完成 =====" -ForegroundColor Cyan
