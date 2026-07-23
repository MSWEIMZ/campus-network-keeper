"""运行时网络接口优先级管理。

只修改 Windows 的 ActiveStore，不写入持久配置；应用退出或系统重启后由系统恢复。
切换失败时调用方仍可保持当前可用接口，不把路由调整当成网络恢复成功的证据。
"""
from __future__ import annotations

import subprocess
from typing import Optional

from config import CONFIG
from logger import log


def _set_metric(alias: str | None, metric: int) -> bool:
    if not alias or not CONFIG.network.route_metric_enabled:
        return not CONFIG.network.route_metric_enabled
    try:
        # ActiveStore 只影响当前运行期，避免永久覆盖用户的网络配置。
        escaped = alias.replace("'", "''")
        script = (
            "Set-NetIPInterface -AddressFamily IPv4 "
            f"-InterfaceAlias '{escaped}' -AutomaticMetric Disabled "
            f"-InterfaceMetric {int(metric)} -PolicyStore ActiveStore"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode == 0:
            return True
        log.warning("[路由] 设置接口优先级失败: metric=%d", metric)
    except Exception as exc:
        log.warning("[路由] 设置接口优先级异常: %s", type(exc).__name__)
    return False


def prefer_ethernet(ethernet_alias: str | None, wifi_alias: str | None) -> bool:
    """将以太网设为主路径，Wi-Fi 保持较低优先级。"""
    eth_ok = _set_metric(ethernet_alias, CONFIG.network.ethernet_metric)
    wifi_ok = _set_metric(wifi_alias, CONFIG.network.wifi_metric)
    if eth_ok and wifi_ok:
        log.info("[路由] 当前优先路径: 以太网")
    return eth_ok and wifi_ok

def prefer_wifi(ethernet_alias: str | None, wifi_alias: str | None) -> bool:
    """以太网不可用时让 Wi-Fi 接管默认流量。"""
    eth_ok = _set_metric(ethernet_alias, CONFIG.network.fallback_ethernet_metric)
    wifi_ok = _set_metric(wifi_alias, CONFIG.network.wifi_metric)
    if eth_ok and wifi_ok:
        log.info("[路由] 当前优先路径: Wi-Fi 兜底")
    return eth_ok and wifi_ok
