"""
校园网保活工具 - 网卡重置模块
通过 netsh / powershell 禁用再启用网卡，或刷新 DHCP。
需要管理员权限运行。
"""
from __future__ import annotations

import time

from config import CONFIG
from logger import log
from network_monitor import _run


# ---------------------------------------------------------------------------
# 自动发现网卡名称
# ---------------------------------------------------------------------------

def find_ethernet_adapter() -> str | None:
    """自动发现以太网适配器名称"""
    name = CONFIG.ethernet_adapter_name
    if name:
        return name

    out = _run("netsh interface show interface")
    for line in out.splitlines():
        lower = line.lower()
        if any(kw in lower for kw in ("以太网", "ethernet")):
            parts = line.split()
            if len(parts) >= 4:
                # 格式: admin_state  state  type  adapter_name
                return " ".join(parts[3:])
    return None


# ---------------------------------------------------------------------------
# 禁用 / 启用网卡
# ---------------------------------------------------------------------------

def disable_adapter(name: str) -> bool:
    """禁用网卡，返回是否真正禁用成功"""
    log.info("正在禁用网卡: %s", name)
    out = _run(f'netsh interface set interface "{name}" admin=disable')
    # 检查是否有权限错误
    if "提升" in out or "elevation" in out.lower() or "denied" in out.lower():
        log.warning("禁用网卡失败（需要管理员权限）: %s", name)
        return False
    log.info("网卡已禁用: %s", name)
    return True


def enable_adapter(name: str) -> bool:
    """启用网卡，返回是否真正启用成功"""
    log.info("正在启用网卡: %s", name)
    out = _run(f'netsh interface set interface "{name}" admin=enable')
    if "提升" in out or "elevation" in out.lower() or "denied" in out.lower():
        log.warning("启用网卡失败（需要管理员权限）: %s", name)
        return False
    log.info("网卡已启用: %s", name)
    return True


# ---------------------------------------------------------------------------
# DHCP 刷新
# ---------------------------------------------------------------------------

def release_dhcp() -> bool:
    """释放所有 DHCP 租约"""
    log.info("正在释放 DHCP 租约...")
    out = _run("ipconfig /release", timeout=15)
    log.debug("release 输出: %s", out.strip())
    return True


def renew_dhcp() -> bool:
    """续订所有 DHCP 租约"""
    log.info("正在续订 DHCP 租约...")
    out = _run("ipconfig /renew", timeout=20)
    log.debug("renew 输出: %s", out.strip())
    return True


# ---------------------------------------------------------------------------
# 一键重置流程
# ---------------------------------------------------------------------------

def reset_ethernet() -> bool:
    """
    执行完整的以太网重置流程：
    1. 找到以太网适配器
    2. 禁用 → 等待 → 启用
    3. 等待恢复
    4. 刷新 DHCP
    返回 True 表示流程执行完毕（不代表网络一定恢复，需后续检测确认）。
    """
    adapter = find_ethernet_adapter()
    if not adapter:
        log.error("未找到以太网适配器，无法重置")
        return False

    log.info("===== 开始重置以太网卡: %s =====", adapter)

    # 禁用
    disabled = disable_adapter(adapter)
    if not disabled:
        log.error("网卡禁用失败（无管理员权限），跳过重置")
        return False

    wait_disable = CONFIG.network.nic_disable_wait_sec
    log.info("等待 %d 秒...", wait_disable)
    time.sleep(wait_disable)

    # 启用
    enabled = enable_adapter(adapter)
    if not enabled:
        log.error("网卡启用失败")
        return False

    wait_reset = CONFIG.network.nic_reset_wait_sec
    log.info("等待 %d 秒让网卡恢复...", wait_reset)
    time.sleep(wait_reset)

    # DHCP 刷新
    release_dhcp()
    time.sleep(2)
    renew_dhcp()
    time.sleep(3)

    log.info("===== 以太网卡重置完成 =====")
    return True



