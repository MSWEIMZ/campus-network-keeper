"""
校园网保活工具 - Wi-Fi 自动切换模块（带详细日志）
通过 netsh wlan 实现 Wi-Fi 连接/断开/状态查询。
"""
from __future__ import annotations

import os
import time

from config import CONFIG
from logger import log
from network_monitor import _run


def list_available_ssids() -> list[str]:
    """列出当前能扫描到的 Wi-Fi SSID"""
    log.info("[Wi-Fi] 扫描可用 SSID...")
    out = _run("netsh wlan show networks mode=bssid")
    ssids: list[str] = []
    for line in out.splitlines():
        if line.strip().lower().startswith("ssid") and ":" in line:
            ssid = line.split(":", 1)[1].strip()
            if ssid:
                ssids.append(ssid)
    log.info("[Wi-Fi] 扫描到 %d 个 SSID", len(ssids))
    return ssids


def list_saved_profiles() -> list[str]:
    """读取本机已保存的 Wi-Fi 配置名，作为未配置 SSID 时的最后兜底。"""
    out = _run("netsh wlan show profiles")
    profiles: list[str] = []
    for line in out.splitlines():
        stripped = line.strip()
        lower = stripped.lower()
        if ("all user profile" in lower or "所有用户配置文件" in stripped) and ":" in stripped:
            name = stripped.split(":", 1)[1].strip()
            if name:
                profiles.append(name)
    return profiles


def get_connected_ssid() -> str | None:
    """获取当前已连接的 Wi-Fi SSID"""
    out = _run("netsh wlan show interfaces")
    connected = False
    for line in out.splitlines():
        stripped = line.strip()
        lower = stripped.lower()
        if ("state" in lower or "状态" in lower) and ":" in stripped:
            val = stripped.split(":", 1)[1].strip().lower()
            if "connected" in val or "已连接" in val:
                connected = True
        if connected and ("ssid" in lower and "bssid" not in lower) and ":" in stripped:
            ssid = stripped.split(":", 1)[1].strip()
            if ssid:
                log.info("[Wi-Fi] 当前已连接无线网络")
                return ssid
    log.info("[Wi-Fi] 当前未连接任何 SSID")
    return None


def disconnect_wifi() -> bool:
    """断开当前 Wi-Fi"""
    log.info("[Wi-Fi] 正在断开 Wi-Fi...")
    out = _run("netsh wlan disconnect")
    ok = "确定" in out or "Ok" in out or out.strip() == ""
    log.info("[Wi-Fi] 断开结果: %s", "成功" if ok else "失败")
    return ok


def connect_wifi(ssid: str, timeout_sec: int | None = None) -> bool:
    """连接指定 SSID 的 Wi-Fi"""
    timeout = timeout_sec or CONFIG.network.wifi_connect_timeout_sec
    log.info("[Wi-Fi] ========== 连接 Wi-Fi (超时 %ds) ==========", timeout)

    safe_ssid = ssid.replace('"', "")
    out = _run(f'netsh wlan connect name="{safe_ssid}"')
    log.info("[Wi-Fi] 已发送连接请求")

    if "已成功" not in out and "success" not in out.lower() and out.strip() != "":
        log.warning("[Wi-Fi] 连接命令返回异常")

    # 等待连接
    log.info("[Wi-Fi] 等待连接建立...")
    start = time.time()
    attempt = 0
    while time.time() - start < timeout:
        time.sleep(2)
        attempt += 1
        current = get_connected_ssid()
        if current:
            if current.lower() == ssid.lower():
                elapsed = time.time() - start
                log.info("[Wi-Fi] ✅ Wi-Fi 已连接 (耗时 %.1fs)", elapsed)
                return True
            log.warning("[Wi-Fi] ⚠️ 连接到了其他无线网络，停止本次尝试")
            return False
        if attempt % 3 == 0:
            log.info("[Wi-Fi] 仍在等待连接... (已等 %.0fs)", time.time() - start)

    log.warning("[Wi-Fi] ❌ 连接超时 (%ds)", timeout)
    return False


def _get_wifi_radio_state() -> str:
    """获取 Wi-Fi 射频状态"""
    out = _run("netsh wlan show interfaces")
    lines = out.splitlines()

    # 先检查是否有 SSID（已连接 = 射频肯定开）
    for line in lines:
        lower = line.lower()
        if "ssid" in lower and "bssid" not in lower and ":" in line:
            ssid_val = line.split(":", 1)[1].strip()
            if ssid_val:
                log.info("[Wi-Fi:射频] 检测到已连接无线网络，射频肯定是开的")
                return "Software On"

    # 检查 Radio status 行
    for i, line in enumerate(lines):
        lower = line.lower()
        if "radio status" in lower or ("无线" in line and "状态" in line):
            if "software" in lower:
                state = "Software On" if "on" in lower else "Software Off"
                log.info("[Wi-Fi:射频] 从 Radio status 行检测: %s", state)
                return state
            for j in range(i + 1, min(i + 3, len(lines))):
                if "software" in lines[j].lower():
                    state = "Software On" if "on" in lines[j].lower() else "Software Off"
                    log.info("[Wi-Fi:射频] 从 Radio 子行检测: %s", state)
                    return state

    # 回退
    lower_all = out.lower()
    if "software on" in lower_all:
        log.info("[Wi-Fi:射频] 从文本搜索检测: Software On")
        return "Software On"
    if "software off" in lower_all:
        log.info("[Wi-Fi:射频] 从文本搜索检测: Software Off")
        return "Software Off"

    log.info("[Wi-Fi:射频] 无法确定射频状态 (unknown)")
    log.info("[Wi-Fi:射频] 无法确定射频状态")
    return "unknown"


def _ensure_radio_task(task_name: str, ps_script: str) -> None:
    """确保管理员计划任务已注册"""
    check = _run(f'schtasks /Query /TN "{task_name}"', timeout=10)
    if task_name in check:
        log.info("[Wi-Fi:任务] 计划任务 '%s' 已存在", task_name)
        return

    log.info("[Wi-Fi:任务] 注册管理员计划任务: %s", task_name)
    xml_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_radio_task.xml")
    xml_content = f'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>校园网保活工具 - 开启Wi-Fi射频</Description>
  </RegistrationInfo>
  <Principals>
    <Principal>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT30S</ExecutionTimeLimit>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>powershell.exe</Command>
      <Arguments>-ExecutionPolicy Bypass -WindowStyle Hidden -File "{ps_script}"</Arguments>
    </Exec>
  </Actions>
</Task>'''
    try:
        with open(xml_path, "w", encoding="utf-16") as f:
            f.write(xml_content)
        result = _run(f'schtasks /Create /TN "{task_name}" /XML "{xml_path}" /F', timeout=15)
        log.info("[Wi-Fi:任务] 注册结果: %s", result.strip()[:200])
        if os.path.exists(xml_path):
            os.remove(xml_path)
    except Exception as e:
        log.error("[Wi-Fi:任务] 注册失败: %s", e)


def _enable_wifi_radio() -> bool:
    """开启 Wi-Fi 射频"""
    log.info("[Wi-Fi:射频] ========== 开启 Wi-Fi 射频 ==========")
    ps_script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "enable_wifi_radio.ps1")
    if not os.path.exists(ps_script):
        log.error("[Wi-Fi:射频] 射频脚本不存在: %s", ps_script)
        return False

    # 方案1: schtasks（最高权限，无 UAC）
    task_name = "CampusKeeper_EnableWifi"
    _ensure_radio_task(task_name, ps_script)

    log.info("[Wi-Fi:射频] 通过计划任务执行...")
    out = _run(f'schtasks /Run /TN "{task_name}"', timeout=15)
    log.info("[Wi-Fi:射频] schtasks run 输出: %s", out.strip()[:200])

    time.sleep(6)
    state = _get_wifi_radio_state()
    if state == "Software On":
        log.info("[Wi-Fi:射频] ✅ 射频已开启（计划任务方式）")
        return True

    # 方案2: UAC 提权
    log.info("[Wi-Fi:射频] 计划任务方式未成功，尝试 UAC 提权...")
    ps_cmd = (
        f'Start-Process powershell -ArgumentList '
        f'"-ExecutionPolicy Bypass -File \\"{ps_script}\\"" '
        f'-Verb RunAs -WindowStyle Hidden -Wait'
    )
    out = _run(f'powershell -Command "{ps_cmd}"', timeout=20)
    log.info("[Wi-Fi:射频] UAC 方式输出: %s", out.strip()[:200])

    time.sleep(3)
    state = _get_wifi_radio_state()
    if state == "Software On":
        log.info("[Wi-Fi:射频] ✅ 射频已开启（UAC 方式）")
        return True

    log.warning("[Wi-Fi:射频] ❌ 射频仍为: %s", state)
    return False


def ensure_wifi_adapter_enabled() -> bool:
    """确保 Wi-Fi 适配器和射频都已启用"""
    log.info("[Wi-Fi] ====== 检查 Wi-Fi 适配器状态 ======")

    radio_state = _get_wifi_radio_state()
    log.info("[Wi-Fi] 当前射频状态: %s", radio_state)

    if radio_state in ("Software Off", "unknown"):
        log.info("[Wi-Fi] 射频状态: %s，尝试开启...", radio_state)
        if not _enable_wifi_radio():
            log.warning("[Wi-Fi] 射频开启失败")
            if radio_state == "Software Off":
                return False

    # 检查 WLAN 接口是否启用
    out = _run("netsh interface show interface")
    for line in out.splitlines():
        lower = line.lower()
        if any(kw in lower for kw in ("wi-fi", "wlan", "无线")):
            if "disabled" in lower or "已禁用" in line:
                log.info("[Wi-Fi] WLAN 接口已禁用，尝试启用...")
                _run('netsh interface set interface "WLAN" admin=enable')
                time.sleep(3)

    time.sleep(2)
    final_state = _get_wifi_radio_state()
    if final_state == "Software On":
        log.info("[Wi-Fi] ✅ 适配器就绪（射频已开）")
        return True
    elif final_state == "unknown":
        log.info("[Wi-Fi] 射频状态未知，尝试直接连接")
        return True
    else:
        log.warning("[Wi-Fi] ❌ 适配器未就绪: %s", final_state)
        return False


def auto_connect_preferred_wifi(preferred_ssids: list[str] | None = None) -> bool:
    """按优先级列表依次尝试连接 Wi-Fi"""
    ssids = list(preferred_ssids or CONFIG.network.wifi_ssids)
    log.info("[Wi-Fi] ========== 自动连接 Wi-Fi ==========")
    log.info("[Wi-Fi] 候选网络数量: %d", len(ssids))

    if not ssids:
        ssids = list_saved_profiles()
        log.info("[Wi-Fi] 未配置备用 SSID，使用已保存配置数量: %d", len(ssids))
        if not ssids:
            log.warning("[Wi-Fi] 没有可用的已保存 Wi-Fi 配置")
            return False

    # 确保 Wi-Fi 适配器开启
    log.info("[Wi-Fi] Step1: 检查 Wi-Fi 适配器...")
    if not ensure_wifi_adapter_enabled():
        log.warning("[Wi-Fi] ❌ Wi-Fi 适配器无法启用")
        return False

    time.sleep(2)

    # 扫描可用 SSID
    log.info("[Wi-Fi] Step2: 扫描可用 SSID...")
    available = list_available_ssids()

    # 按优先级连接
    log.info("[Wi-Fi] Step3: 按优先级连接...")
    for ssid in ssids:
        if ssid in available:
            log.info("[Wi-Fi] 发现候选无线网络，开始连接...")
            if connect_wifi(ssid):
                return True
        else:
            log.info("[Wi-Fi] 候选无线网络当前不可见，跳过")

    # 如果扫描列表为空，直接连接已保存 Profile
    if not available:
        log.info("[Wi-Fi] Step4: 扫描列表为空，尝试直接连接已保存 Profile...")
        for ssid in ssids:
            log.info("[Wi-Fi] 尝试直接连接已保存无线配置")
            if connect_wifi(ssid):
                return True

    log.warning("[Wi-Fi] ❌ 所有备用 Wi-Fi 均连接失败")
    return False
