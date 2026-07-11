"""
校园网保活工具 - 主循环调度器
核心逻辑：定期检测网络 → 判定状态 → 执行恢复动作。
"""
from __future__ import annotations

import os
import time

from campus_auth import CampusAuth
from config import CONFIG
from logger import log
from network_monitor import NetState, NetworkSnapshot, log_snapshot, take_snapshot
from nic_reset import reset_ethernet
from wifi_switcher import auto_connect_preferred_wifi


class KeepAlive:
    """保活调度主循环"""

    def __init__(self) -> None:
        self._auth = CampusAuth()
        self._consecutive_abnormal: int = 0
        self._retry_count: int = 0
        self._last_state: NetState = NetState.UNKNOWN
        self._pending_abnormal: NetState = NetState.UNKNOWN

        # 从环境变量或配置读取账号密码
        self._username = os.environ.get("CAMPUS_USER", CONFIG.auth.username)
        self._password = os.environ.get("CAMPUS_PASS", CONFIG.auth.password)

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------

    def run(self) -> None:
        """阻塞式主循环，Ctrl+C 退出"""
        log.info("=" * 50)
        log.info("校园网保活工具已启动")
        log.info("检测间隔: %ds | 防抖次数: %d",
                 CONFIG.network.poll_interval_sec, CONFIG.network.confirm_count)
        log.info("备用 Wi-Fi: %s", CONFIG.network.wifi_ssids)
        log.info("认证模块: %s | 账号: %s",
                 "启用" if CONFIG.auth.enabled else "未启用",
                 self._username[:3] + "***" if self._username else "未配置")
        log.info("按 Ctrl+C 退出")
        log.info("=" * 50)

        while True:
            try:
                self._tick()
            except KeyboardInterrupt:
                log.info("用户中断，正在退出...")
                break
            except Exception as e:
                log.error("主循环异常: %s", e, exc_info=True)
                time.sleep(5)

            time.sleep(CONFIG.network.poll_interval_sec)

    # ------------------------------------------------------------------
    # 单次检测
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        snap = take_snapshot()
        log_snapshot(snap)

        if snap.state == NetState.ONLINE:
            self._handle_online(snap)
        else:
            self._handle_abnormal(snap)

    # ------------------------------------------------------------------
    # 正常状态处理
    # ------------------------------------------------------------------

    def _handle_online(self, snap: NetworkSnapshot) -> None:
        if self._last_state != NetState.ONLINE:
            log.info("✅ 网络已恢复正常")

        # 重置计数器
        self._consecutive_abnormal = 0
        self._retry_count = 0
        self._last_state = NetState.ONLINE
        self._pending_abnormal = NetState.UNKNOWN

        # 认证保活心跳
        if CONFIG.auth.enabled:
            alive = self._auth.heartbeat()
            if not alive:
                log.warning("认证心跳失败，尝试重新登录...")
                self._do_login()

    # ------------------------------------------------------------------
    # 异常状态处理
    # ------------------------------------------------------------------

    def _handle_abnormal(self, snap: NetworkSnapshot) -> None:
        if snap.state != self._pending_abnormal:
            self._pending_abnormal = snap.state
            self._consecutive_abnormal = 1
        else:
            self._consecutive_abnormal += 1
        self._last_state = snap.state

        # 防抖
        if self._consecutive_abnormal < CONFIG.network.confirm_count:
            log.info(
                "检测到异常（第 %d/%d 次确认），暂不动作",
                self._consecutive_abnormal,
                CONFIG.network.confirm_count,
            )
            return

        # 退避检查
        if self._retry_count >= CONFIG.network.max_retries:
            wait = min(
                CONFIG.network.backoff_base_sec * (2 ** (self._retry_count - CONFIG.network.max_retries)),
                CONFIG.network.backoff_max_sec,
            )
            log.warning(
                "已连续重试 %d 次，进入退避等待 %ds...",
                self._retry_count, int(wait),
            )
            time.sleep(wait)
            # 不重置 retry_count，让退避间隔递增直到网络恢复正常

        self._retry_count += 1

        # 根据状态分派
        if snap.state == NetState.CABLE_DOWN:
            self._recover_cable_down(snap)
        elif snap.state == NetState.DHCP_LIMITED:
            self._recover_dhcp_limited(snap)
        elif snap.state == NetState.WEB_AUTH_REQUIRED:
            self._recover_auth_required(snap)
        else:
            log.warning("未知异常状态: %s", snap.state)

    # ------------------------------------------------------------------
    # 恢复策略
    # ------------------------------------------------------------------

    def _recover_cable_down(self, snap: NetworkSnapshot) -> None:
        """网线断开恢复"""
        log.warning("🔌 网线断开，尝试恢复...")

        if reset_ethernet():
            time.sleep(3)
            new_snap = take_snapshot()
            log_snapshot(new_snap)
            if new_snap.state == NetState.ONLINE:
                log.info("✅ 网卡重置后恢复成功")
                return
            # 重置后可能需要重新认证
            if new_snap.state == NetState.WEB_AUTH_REQUIRED:
                self._do_login()
                return

        log.warning("网卡重置未恢复，尝试连接备用 Wi-Fi...")
        if auto_connect_preferred_wifi():
            time.sleep(3)
            new_snap = take_snapshot()
            log_snapshot(new_snap)
            if new_snap.state == NetState.ONLINE:
                log.info("✅ Wi-Fi 备用连接成功")
                return
            if new_snap.state == NetState.WEB_AUTH_REQUIRED:
                self._do_login()
                return

        log.error("❌ 所有恢复手段均失败，请手动检查网络")

    def _recover_dhcp_limited(self, snap: NetworkSnapshot) -> None:
        """有 IP 但无法上网"""
        log.warning("⚠️ 有 IP 但无法上网，尝试刷新 DHCP...")
        reset_ethernet()

        time.sleep(3)
        new_snap = take_snapshot()
        log_snapshot(new_snap)
        if new_snap.state == NetState.ONLINE:
            log.info("✅ DHCP 刷新后恢复成功")
        elif new_snap.state == NetState.WEB_AUTH_REQUIRED:
            self._do_login()
        else:
            log.warning("DHCP 刷新后仍无法上网")

    def _recover_auth_required(self, snap: NetworkSnapshot) -> None:
        """需要 Web 认证"""
        log.warning("🔐 检测到需要 Web 认证")
        self._do_login()

    def _do_login(self) -> None:
        """执行登录"""
        if not CONFIG.auth.enabled:
            log.warning("认证模块未启用")
            return

        if not self._username or not self._password:
            log.error(
                "未配置校园网账号密码！请设置环境变量 CAMPUS_USER 和 CAMPUS_PASS，"
                "或在 config.py 中配置"
            )
            return

        ok = self._auth.login(self._username, self._password)
        if ok:
            time.sleep(2)
            new_snap = take_snapshot()
            log_snapshot(new_snap)
            if new_snap.state == NetState.ONLINE:
                log.info("✅ 认证登录后网络恢复正常")
                self._consecutive_abnormal = 0
                self._retry_count = 0
            else:
                log.warning("认证登录后网络状态: %s", new_snap.state.name)
        else:
            log.error("❌ 认证登录失败")


