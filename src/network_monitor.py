"""
校园网保活工具 - 网络状态检测模块（带详细日志）
负责检测：网卡物理状态、IP/DNS、网关连通性、外网连通性、是否需要 Web 认证。
"""
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import CONFIG
from logger import log

# 模块级共享 session（避免每次探测都创建新连接）
_probe_session: requests.Session | None = None


def _get_probe_session() -> requests.Session:
    """获取共享的探测 session（延迟初始化）"""
    global _probe_session
    if _probe_session is None:
        _probe_session = requests.Session()
        _probe_session.headers["User-Agent"] = "CampusKeeper/1.0"
        adapter = HTTPAdapter(pool_connections=2, pool_maxsize=2)
        _probe_session.mount("http://", adapter)
        _probe_session.mount("https://", adapter)
    return _probe_session


class NetState(Enum):
    """网络状态枚举"""
    ONLINE = auto()              # 正常上网
    CABLE_DOWN = auto()          # 网线物理断开
    DHCP_LIMITED = auto()        # 有 IP 但无法上网
    WEB_AUTH_REQUIRED = auto()   # 需要 Web 认证
    UNKNOWN = auto()             # 未知


@dataclass
class NetworkSnapshot:
    """一次网络检测的快照"""
    state: NetState
    eth_connected: bool
    wifi_connected: bool
    has_ip: bool
    gateway: Optional[str]
    gateway_reachable: bool
    internet_reachable: bool
    auth_probe_ok: bool
    eth_admin_enabled: Optional[bool] = None
    detail: str = ""


# ---------------------------------------------------------------------------
# 底层工具函数
# ---------------------------------------------------------------------------

def _run(cmd: str, timeout: int = 10) -> str:
    """运行 shell 命令并返回 stdout"""
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, timeout=timeout
        )
        for enc in ("utf-8", "gbk", "gb2312", "latin-1"):
            try:
                return (r.stdout + r.stderr).decode(enc)
            except (UnicodeDecodeError, AttributeError):
                continue
        return str(r.stdout + r.stderr)
    except subprocess.TimeoutExpired:
        return "[timeout]"
    except Exception as e:
        return f"[error] {e}"


def _ping(host: str, count: int = 1, timeout_ms: int = 2000) -> bool:
    """Windows ping"""
    out = _run(f"ping -n {count} -w {timeout_ms} {host}")
    ok = "TTL=" in out.upper() or "来自" in out
    log.info("[探测:ping] %s → %s", host, "可达" if ok else "不可达")
    return ok


# ---------------------------------------------------------------------------
# 网卡状态
# ---------------------------------------------------------------------------

def get_adapter_status(adapter_name: str) -> Optional[bool]:
    """查询指定网卡的连接状态"""
    out = _run('netsh interface show interface')
    for line in out.splitlines():
        if adapter_name.lower() in line.lower():
            connected = _parse_adapter_link_status(line)
            log.info("[探测:网卡] %s → %s | %s", adapter_name, "已连接" if connected else "已断开", line.strip()[:80])
            return connected
    return None


def _parse_adapter_link_status(line: str) -> bool:
    """解析 netsh 链路状态，避免 disconnected 匹配 connected。"""
    lower = line.lower()
    return "已连接" in line or (
        "connected" in lower and "disconnected" not in lower
    )


def get_adapter_admin_status(adapter_name: str) -> Optional[bool]:
    """返回网卡是否被系统启用；None 表示未找到网卡。"""
    out = _run("netsh interface show interface")
    for line in out.splitlines():
        if adapter_name.lower() not in line.lower():
            continue
        lower = line.lower().strip()
        if lower.startswith("已启用") or lower.startswith("enabled"):
            return True
        if lower.startswith("已禁用") or lower.startswith("disabled"):
            return False
        return None
    return None


def is_ethernet_admin_enabled() -> Optional[bool]:
    """检测以太网管理状态，区分禁用和物理断开。"""
    name = CONFIG.ethernet_adapter_name
    if name:
        return get_adapter_admin_status(name)
    out = _run("netsh interface show interface")
    for line in out.splitlines():
        lower = line.lower()
        if any(kw in lower for kw in ("以太网", "ethernet")):
            stripped = lower.strip()
            if stripped.startswith("已启用") or stripped.startswith("enabled"):
                return True
            if stripped.startswith("已禁用") or stripped.startswith("disabled"):
                return False
    return None


def is_ethernet_connected() -> bool:
    """检测以太网是否连接"""
    name = CONFIG.ethernet_adapter_name
    if name:
        status = get_adapter_status(name)
        if status is not None:
            return status

    out = _run('netsh interface show interface')
    for line in out.splitlines():
        lower = line.lower()
        if any(kw in lower for kw in ("以太网", "ethernet")):
            if _parse_adapter_link_status(line):
                log.info("[探测:以太网] 已连接 | %s", line.strip()[:80])
                return True
    log.info("[探测:以太网] 未连接")
    return False


def is_wifi_connected() -> bool:
    """检测 Wi-Fi 是否连接"""
    name = CONFIG.wifi_adapter_name
    if name:
        status = get_adapter_status(name)
        if status is not None:
            return status

    out = _run('netsh interface show interface')
    for line in out.splitlines():
        lower = line.lower()
        if any(kw in lower for kw in ("wi-fi", "wlan", "无线")):
            if _parse_adapter_link_status(line):
                log.info("[探测:Wi-Fi] 已连接 | %s", line.strip()[:80])
                return True
    log.info("[探测:Wi-Fi] 未连接")
    return False


# ---------------------------------------------------------------------------
# IP / 网关
# ---------------------------------------------------------------------------

def get_default_gateway() -> Optional[str]:
    """获取默认网关"""
    import re
    out = _run("ipconfig")
    ipv4_pattern = re.compile(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})")
    for line in out.splitlines():
        stripped = line.strip()
        if "默认网关" in stripped or "Default Gateway" in stripped:
            match = ipv4_pattern.search(stripped)
            if match:
                gw = match.group(1)
                if gw != "0.0.0.0":
                    log.info("[探测:网关] 默认网关: %s", gw)
                    return gw
    log.info("[探测:网关] 未找到有效网关")
    return None


def has_ipv4_address() -> bool:
    """检测是否有非回环 IPv4 地址"""
    out = _run("ipconfig")
    for line in out.splitlines():
        stripped = line.strip()
        if ("IPv4" in stripped or "IPv4 地址" in stripped) and ":" in stripped:
            addr = stripped.split(":")[-1].strip()
            if addr and not addr.startswith("169.254.") and addr != "127.0.0.1":
                log.info("[探测:IP] 有效 IPv4: %s", addr)
                return True
    log.info("[探测:IP] 未找到有效 IPv4 地址")
    return False


# ---------------------------------------------------------------------------
# 外网 / 认证探测
# ---------------------------------------------------------------------------

def probe_auth_page() -> bool:
    """
    探测认证页。
    返回 True = 认证探测通过（不需要认证）
    返回 False = 需要认证或无法访问
    """
    url = CONFIG.network.auth_probe_url
    keyword = CONFIG.network.auth_success_keyword
    log.info("[探测:认证] 访问 %s ...", url)
    try:
        resp = _get_probe_session().get(url, timeout=5, allow_redirects=True)
        log.info("[探测:认证] HTTP %d, URL=%s, 长度=%d", resp.status_code, resp.url[:100], len(resp.text))
        if keyword in resp.text:
            log.info("[探测:认证] ✅ 无需认证 (keyword='%s' found)", keyword)
            return True
        log.info("[探测:认证] ⚠️ 需要认证 (keyword='%s' not found)", keyword)
        log.info("[探测:认证]   响应片段: %s", resp.text[:200])
        return False
    except requests.RequestException as e:
        log.warning("[探测:认证] 请求失败: %s", e)
        return False


def probe_internet() -> bool:
    """探测外网连通性"""
    for url in (
        CONFIG.network.internet_probe_url,
        CONFIG.network.internet_probe_url_backup,
    ):
        log.info("[探测:外网] 访问 %s ...", url)
        try:
            resp = _get_probe_session().get(url, timeout=4, allow_redirects=False)
            log.info("[探测:外网] HTTP %d", resp.status_code)
            # 204 探针必须返回预期的 204。302 通常正是校园网
            # Captive Portal 的认证重定向，绝不能视为已经联网。
            if resp.status_code == 204:
                log.info("[探测:外网] ✅ 外网可达")
                return True
        except requests.RequestException as e:
            log.info("[探测:外网] 请求失败: %s", e)
            continue
    log.info("[探测:外网] ❌ 外网不可达")
    return False


# ---------------------------------------------------------------------------
# 综合状态判定
# ---------------------------------------------------------------------------

def take_snapshot() -> NetworkSnapshot:
    """执行一次完整的网络状态采集（带异常保护）"""
    log.info("[探测] ---- 开始网络状态采集 ----")
    try:
        return _do_take_snapshot()
    except Exception as e:
        log.error("[探测] ❌ 状态采集异常: %s", e)
        return NetworkSnapshot(
            state=NetState.UNKNOWN, eth_connected=False, wifi_connected=False,
            has_ip=False, gateway=None, gateway_reachable=False,
            internet_reachable=False, auth_probe_ok=False,
            eth_admin_enabled=None,
            detail=f"采集异常: {e}",
        )


def _do_take_snapshot() -> NetworkSnapshot:
    """实际的状态采集逻辑"""
    eth_ok = is_ethernet_connected()
    eth_admin_enabled = is_ethernet_admin_enabled()
    wifi_ok = is_wifi_connected()
    has_ip = has_ipv4_address()
    gw = get_default_gateway()
    gw_ok = _ping(gw) if gw else False
    inet_ok = probe_internet() if has_ip else False
    auth_ok = probe_auth_page() if has_ip else False

    if not eth_ok and not wifi_ok:
        state = NetState.CABLE_DOWN
        detail = "网线和 Wi-Fi 均未连接"
    elif not has_ip:
        state = NetState.DHCP_LIMITED
        detail = "网卡已连接但未获取有效 IP"
    elif inet_ok or auth_ok:
        state = NetState.ONLINE
        detail = "网络正常"
    elif not gw_ok:
        # 网关 ping 不通
        if not eth_ok and wifi_ok:
            # WiFi 在线但网关不可达 → 很可能是需要 portal 认证
            state = NetState.WEB_AUTH_REQUIRED
            detail = "WiFi 已连接但网关不通，可能需要认证"
        elif eth_ok and not wifi_ok:
            # 以太网"已连接"但网关不通 → 物理层可能异常
            state = NetState.DHCP_LIMITED
            detail = "网线已连接但网关不通（可能物理层异常）"
        elif not eth_ok:
            state = NetState.CABLE_DOWN
            detail = "网线断开且外网不通"
        else:
            # 双网卡都在但都不通 → 可能需要认证
            state = NetState.WEB_AUTH_REQUIRED
            detail = "双网卡在线但网关不通，可能需要认证"
    else:
        # 网关可达但外网不通 → 判定为需要认证
        state = NetState.WEB_AUTH_REQUIRED
        detail = "网关可达但外网不通，可能需要认证"

    log.info("[探测] 最终状态: %s (%s)", state.name, detail)
    log.info("[探测] ---- 采集结束 ----")

    return NetworkSnapshot(
        state=state,
        eth_connected=eth_ok,
        wifi_connected=wifi_ok,
        has_ip=has_ip,
        gateway=gw,
        gateway_reachable=gw_ok,
        internet_reachable=inet_ok,
        auth_probe_ok=auth_ok,
        eth_admin_enabled=eth_admin_enabled,
        detail=detail,
    )


def log_snapshot(snap: NetworkSnapshot) -> None:
    """打印快照日志"""
    log.info(
        "网络状态: %s | 网线=%s(启用=%s) Wi-Fi=%s IP=%s 网关=%s(%s) 外网=%s 认证=%s | %s",
        snap.state.name,
        snap.eth_connected,
        snap.eth_admin_enabled,
        snap.wifi_connected,
        snap.has_ip,
        snap.gateway or "-",
        snap.gateway_reachable,
        snap.internet_reachable,
        snap.auth_probe_ok,
        snap.detail,
    )




