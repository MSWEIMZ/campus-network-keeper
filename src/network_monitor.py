"""
校园网保活工具 - 网络状态检测模块（带详细日志）
负责检测：网卡物理状态、IP/DNS、网关连通性、外网连通性、是否需要 Web 认证。
"""
from __future__ import annotations

import subprocess
import time
import json
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


class _SourceAddressAdapter(HTTPAdapter):
    """让 requests 从指定网卡的 IPv4 发起连接。"""

    def __init__(self, source_ip: str, *args, **kwargs):
        self._source_ip = source_ip
        super().__init__(*args, **kwargs)

    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        pool_kwargs["source_address"] = (self._source_ip, 0)
        return super().init_poolmanager(connections, maxsize, block, **pool_kwargs)

    def proxy_manager_for(self, proxy, **proxy_kwargs):
        proxy_kwargs["source_address"] = (self._source_ip, 0)
        return super().proxy_manager_for(proxy, **proxy_kwargs)


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


def _get_interface_probe_session(source_ip: str) -> requests.Session:
    session = requests.Session()
    # 健康检查必须直连，不能让系统代理或旧连接掩盖某一接口的故障。
    session.trust_env = False
    session.headers["User-Agent"] = "CampusKeeper/1.0"
    adapter = _SourceAddressAdapter(source_ip, pool_connections=1, pool_maxsize=1)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


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
    # 按接口统计，避免“Wi-Fi 可用”掩盖“以太网无网”。
    eth_alias: Optional[str] = None
    wifi_alias: Optional[str] = None
    eth_has_ip: bool = False
    eth_gateway: Optional[str] = None
    eth_gateway_reachable: bool = False
    eth_internet_reachable: bool = False
    eth_auth_probe_ok: bool = False
    wifi_has_ip: bool = False
    wifi_gateway: Optional[str] = None
    wifi_gateway_reachable: bool = False
    wifi_internet_reachable: bool = False
    wifi_auth_probe_ok: bool = False
    active_interface: Optional[str] = None


@dataclass
class _InterfaceConfig:
    """Windows 网卡的地址信息（不写入日志中的原始地址）。"""

    alias: str
    ipv4: Optional[str] = None
    gateway: Optional[str] = None


# ---------------------------------------------------------------------------
# 底层工具函数
# ---------------------------------------------------------------------------

def _run(cmd: str, timeout: int = 10) -> str:
    """运行 shell 命令并返回 stdout"""
    try:
        r = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
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


def _run_powershell(script: str, timeout: int = 10) -> str:
    """执行只读 PowerShell 查询；失败时返回空字符串。"""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        data = r.stdout or r.stderr
        for enc in ("utf-8", "gbk", "gb2312", "latin-1"):
            try:
                return data.decode(enc).strip()
            except UnicodeDecodeError:
                continue
        return str(data).strip()
    except Exception:
        return ""


def _get_interface_configs() -> list[_InterfaceConfig]:
    """读取每个接口自己的 IPv4/默认网关，避免使用全局默认路由误判。"""
    script = r"""
$ErrorActionPreference = 'SilentlyContinue'
Get-NetIPConfiguration | ForEach-Object {
  $ip = $_.IPv4Address | Select-Object -First 1 -ExpandProperty IPAddress
  $gw = $_.IPv4DefaultGateway | Select-Object -First 1 -ExpandProperty NextHop
  [pscustomobject]@{ Alias = $_.InterfaceAlias; IPv4 = $ip; Gateway = $gw }
} | ConvertTo-Json -Compress
"""
    raw = _run_powershell(script)
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if isinstance(payload, dict):
        payload = [payload]
    result: list[_InterfaceConfig] = []
    for item in payload if isinstance(payload, list) else []:
        if not isinstance(item, dict):
            continue
        alias = str(item.get("Alias") or "").strip()
        if alias:
            result.append(
                _InterfaceConfig(
                    alias=alias,
                    ipv4=str(item.get("IPv4") or "").strip() or None,
                    gateway=str(item.get("Gateway") or "").strip() or None,
                )
            )
    return result


def _select_interface_config(
    configs: list[_InterfaceConfig], kind: str
) -> Optional[_InterfaceConfig]:
    configured = (
        CONFIG.ethernet_adapter_name if kind == "eth" else CONFIG.wifi_adapter_name
    ).strip().casefold()
    if configured:
        for item in configs:
            if item.alias.casefold() == configured:
                return item
    keywords = (
        ("以太网", "ethernet")
        if kind == "eth"
        else ("wi-fi", "wifi", "wlan", "无线")
    )
    for item in configs:
        alias = item.alias.casefold()
        if any(keyword in alias for keyword in keywords):
            return item
    return None


def _ping(host: str, count: int = 1, timeout_ms: int = 2000) -> bool:
    """Windows ping"""
    out = _run(f"ping -n {count} -w {timeout_ms} {host}")
    ok = "TTL=" in out.upper() or "来自" in out
    log.info("[探测:ping] 网关 → %s", "可达" if ok else "不可达")
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
            log.info("[探测:网卡] 接口 → %s", "已连接" if connected else "已断开")
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
                log.info("[探测:以太网] 已连接")
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
                log.info("[探测:Wi-Fi] 已连接")
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
                    log.info("[探测:网关] 已发现默认网关")
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
                log.info("[探测:IP] 已获取有效 IPv4")
                return True
    log.info("[探测:IP] 未找到有效 IPv4 地址")
    return False


# ---------------------------------------------------------------------------
# 外网 / 认证探测
# ---------------------------------------------------------------------------

def probe_auth_page(source_ip: Optional[str] = None) -> bool:
    """
    探测认证页。
    返回 True = 认证探测通过（不需要认证）
    返回 False = 需要认证或无法访问
    """
    url = CONFIG.network.auth_probe_url
    keyword = CONFIG.network.auth_success_keyword
    session = _get_interface_probe_session(source_ip) if source_ip else _get_probe_session()
    log.info("[探测:认证] 开始检测%s", "指定接口" if source_ip else "当前路径")
    try:
        resp = session.get(url, timeout=5, allow_redirects=True)
        log.info("[探测:认证] HTTP %d", resp.status_code)
        if keyword in resp.text:
            log.info("[探测:认证] ✅ 无需认证")
            return True
        log.info("[探测:认证] ⚠️ 需要认证或响应异常")
        return False
    except requests.RequestException as e:
        log.warning("[探测:认证] 请求失败: %s", type(e).__name__)
        return False
    finally:
        if source_ip:
            session.close()
def probe_internet(source_ip: Optional[str] = None) -> bool:
    """探测外网连通性"""
    session = _get_interface_probe_session(source_ip) if source_ip else _get_probe_session()
    for url in (
        CONFIG.network.internet_probe_url,
        CONFIG.network.internet_probe_url_backup,
    ):
        log.info("[探测:外网] 开始检测%s", "指定接口" if source_ip else "当前路径")
        try:
            resp = session.get(url, timeout=4, allow_redirects=False)
            log.info("[探测:外网] HTTP %d", resp.status_code)
            # 204 探针必须返回预期的 204。302 通常正是校园网
            # Captive Portal 的认证重定向，绝不能视为已经联网。
            if resp.status_code == 204:
                log.info("[探测:外网] ✅ 外网可达")
                if source_ip:
                    session.close()
                return True
        except requests.RequestException as e:
            log.info("[探测:外网] 请求失败: %s", type(e).__name__)
            continue
    log.info("[探测:外网] ❌ 外网不可达")
    if source_ip:
        session.close()
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
    configs = _get_interface_configs()
    eth_cfg = _select_interface_config(configs, "eth")
    wifi_cfg = _select_interface_config(configs, "wifi")

    # PowerShell 不可用时兼容旧版全局探测，确保诊断命令和旧环境仍能工作。
    fallback_global = not configs
    global_has_ip = has_ipv4_address() if fallback_global else False
    global_gateway = get_default_gateway() if fallback_global else None

    def _probe_interface(connected: bool, cfg: Optional[_InterfaceConfig], kind: str):
        if not connected:
            return False, None, False, False, False
        if cfg is None and fallback_global:
            has_ip = global_has_ip
            gateway = global_gateway
            gateway_ok = _ping(gateway) if gateway else False
            internet_ok = probe_internet() if has_ip else False
            auth_ok = probe_auth_page() if has_ip and not internet_ok else False
            return has_ip, gateway, gateway_ok, internet_ok, auth_ok
        ip = cfg.ipv4 if cfg else None
        gateway = cfg.gateway if cfg else None
        gateway_ok = _ping(gateway) if gateway else False
        internet_ok = probe_internet(ip) if ip else False
        auth_ok = probe_auth_page(ip) if ip and not internet_ok else False
        return bool(ip), gateway, gateway_ok, internet_ok, auth_ok

    eth_has_ip, eth_gateway, eth_gateway_ok, eth_inet, eth_auth = _probe_interface(
        eth_ok, eth_cfg, "eth"
    )
    wifi_has_ip, wifi_gateway, wifi_gateway_ok, wifi_inet, wifi_auth = _probe_interface(
        wifi_ok, wifi_cfg, "wifi"
    )
    has_ip = eth_has_ip or wifi_has_ip

    eth_usable = eth_inet or eth_auth
    wifi_usable = wifi_inet or wifi_auth
    if eth_usable:
        active = "ethernet"
        gateway = eth_gateway
        gateway_ok = eth_gateway_ok
        inet_ok = eth_inet
        auth_ok = eth_auth
    elif wifi_usable:
        active = "wifi"
        gateway = wifi_gateway
        gateway_ok = wifi_gateway_ok
        inet_ok = wifi_inet
        auth_ok = wifi_auth
    elif eth_ok and eth_has_ip:
        active = None
        gateway = eth_gateway
        gateway_ok = eth_gateway_ok
        inet_ok = False
        auth_ok = False
    else:
        active = None
        gateway = wifi_gateway or eth_gateway
        gateway_ok = wifi_gateway_ok or eth_gateway_ok
        inet_ok = False
        auth_ok = False

    # 只要某一接口真实可用，整体就是 ONLINE；但明确标记实际使用路径。
    if eth_usable:
        state = NetState.ONLINE
        detail = "以太网可用"
    elif wifi_usable:
        state = NetState.ONLINE
        detail = "以太网不可用，使用 Wi-Fi 兜底" if eth_ok else "Wi-Fi 可用"
    elif not eth_ok and not wifi_ok:
        state = NetState.CABLE_DOWN
        detail = "网线和 Wi-Fi 均未连接"
    elif not has_ip:
        state = NetState.DHCP_LIMITED
        detail = "已连接接口均未获取有效 IPv4"
    elif eth_ok and eth_has_ip and not eth_gateway_ok and not wifi_ok:
        state = NetState.DHCP_LIMITED
        detail = "网线已连接但网关不可达"
    elif eth_ok and eth_has_ip and not eth_inet and eth_gateway_ok:
        state = NetState.WEB_AUTH_REQUIRED
        detail = "以太网网关可达但外网不可达，可能需要认证"
    else:
        state = NetState.WEB_AUTH_REQUIRED
        detail = "网关可达但外网不可达，可能需要认证"

    log.info("[探测] 最终状态: %s (%s)", state.name, detail)
    log.info("[探测] ---- 采集结束 ----")

    return NetworkSnapshot(
        state=state,
        eth_connected=eth_ok,
        wifi_connected=wifi_ok,
        has_ip=has_ip,
        gateway=gateway,
        gateway_reachable=gateway_ok,
        internet_reachable=inet_ok,
        auth_probe_ok=auth_ok,
        eth_admin_enabled=eth_admin_enabled,
        detail=detail,
        eth_alias=eth_cfg.alias if eth_cfg else CONFIG.ethernet_adapter_name or None,
        wifi_alias=wifi_cfg.alias if wifi_cfg else CONFIG.wifi_adapter_name or None,
        eth_has_ip=eth_has_ip,
        eth_gateway=eth_gateway,
        eth_gateway_reachable=eth_gateway_ok,
        eth_internet_reachable=eth_inet,
        eth_auth_probe_ok=eth_auth,
        wifi_has_ip=wifi_has_ip,
        wifi_gateway=wifi_gateway,
        wifi_gateway_reachable=wifi_gateway_ok,
        wifi_internet_reachable=wifi_inet,
        wifi_auth_probe_ok=wifi_auth,
        active_interface=active,
    )


def log_snapshot(snap: NetworkSnapshot) -> None:
    """打印快照日志"""
    log.info(
        "网络状态: %s | 网线=%s(启用=%s IP=%s 网关=%s 外网=%s 认证=%s) "
        "Wi-Fi=%s(IP=%s 网关=%s 外网=%s 认证=%s) 实际路径=%s | %s",
        snap.state.name,
        snap.eth_connected,
        snap.eth_admin_enabled,
        snap.eth_has_ip,
        snap.eth_gateway_reachable,
        snap.eth_internet_reachable,
        snap.eth_auth_probe_ok,
        snap.wifi_connected,
        snap.wifi_has_ip,
        snap.wifi_gateway_reachable,
        snap.wifi_internet_reachable,
        snap.wifi_auth_probe_ok,
        snap.active_interface or "-",
        snap.detail,
    )




