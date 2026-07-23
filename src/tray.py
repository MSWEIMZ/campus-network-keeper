"""
校园网保活工具 - 系统托盘常驻模块（带详细日志）
使用 pystray + PIL 实现 Windows 系统托盘图标。
"""
from __future__ import annotations

import os
import sys
import threading
import ctypes
import time
import traceback
from typing import Optional

import requests
from config import CONFIG
from logger import log
from network_monitor import log_snapshot, NetState, take_snapshot
from nic_reset import enable_ethernet_adapter


def _global_exception_handler(exc_type, exc_value, exc_tb):
    """全局未捕获异常处理器——写日志后不退出"""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    log.error("[全局] 未捕获异常: %s: %s", exc_type.__name__, exc_value)
    log.error("[全局] 堆栈:\n%s", "".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
    # 强制刷新日志，确保异常信息写盘
    for _h in log.handlers:
        try: _h.flush()
        except Exception: pass

sys.excepthook = _global_exception_handler

try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False


_ICON_CACHE: dict[str, "Image.Image"] = {}
_INSTANCE_MUTEX = None


def _release_instance_mutex() -> None:
    """释放单实例锁；重启子进程前必须先调用。"""
    global _INSTANCE_MUTEX
    if _INSTANCE_MUTEX:
        try:
            ctypes.windll.kernel32.CloseHandle(_INSTANCE_MUTEX)
        finally:
            _INSTANCE_MUTEX = None


def _restart_current_process() -> None:
    """释放单实例锁后启动替代进程。"""
    import subprocess

    python_exe = sys.executable
    script = os.path.abspath(sys.argv[0]) if sys.argv else ""
    args = sys.argv[1:] if len(sys.argv) > 1 else ["--tray"]
    _release_instance_mutex()
    subprocess.Popen(
        [python_exe, script] + args,
        creationflags=subprocess.DETACHED_PROCESS,
    )


def _create_icon_image(color: str = "green") -> "Image.Image":
    """生成一个圆形托盘图标（带缓存，避免重复创建）"""
    if color in _ICON_CACHE:
        return _ICON_CACHE[color]
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    colors = {
        "green": (76, 175, 80, 255),
        "yellow": (255, 193, 7, 255),
        "red": (244, 67, 54, 255),
        "gray": (158, 158, 158, 255),
    }
    fill = colors.get(color, colors["gray"])
    draw.ellipse([8, 8, 56, 56], fill=fill)
    _ICON_CACHE[color] = img
    return img


class TrayApp:
    """系统托盘应用"""

    def __init__(self) -> None:
        self._icon: Optional["pystray.Icon"] = None
        self._status = "启动中..."
        self._color = "gray"
        self._running = True
        self._traffic_info: dict = {}
        self._traffic_last_update: float = 0.0
        self._traffic_interval = 300  # 5分钟更新
        self._auth = None
        self._last_state: Optional[NetState] = None
        self._consecutive_abnormal: int = 0
        self._pending_abnormal: Optional[NetState] = None
        self._user_initiated_exit = False
        self._using_wifi_fallback = False
        self._ethernet_stable_count = 0
        self._last_ethernet_enable_attempt = 0.0
        self._last_ethernet_disable_attempt = 0.0
        self._last_wifi_profiles: list[str] = []
        self._route_mode: Optional[str] = None
        self._watchdog_timeout_sec = 300

    def _update_status(self, text: str, color: str = "green") -> None:
        """更新状态并刷新托盘图标"""
        old_status = self._status
        self._status = text
        self._color = color
        log.info("[托盘] 状态更新: '%s' → '%s' (颜色=%s)", old_status, text, color)
        if self._icon:
            try:
                self._icon.icon = _create_icon_image(color)
                traffic_line = self._format_traffic_tooltip()
                title = f"校园网保活: {text}"
                if traffic_line:
                    title += f"\n{traffic_line}"
                self._icon.title = title
                self._icon.menu = self._build_menu()
            except Exception as e:
                log.error("[托盘] 刷新图标失败: %s", e)

    def _build_menu(self) -> "pystray.Menu":
        return pystray.Menu(
            pystray.MenuItem(
                f"状态: {self._status}",
                action=lambda icon, item: None,
                enabled=False,
            ),
            pystray.MenuItem(
                "手动登录",
                self._on_manual_login,
            ),
            pystray.MenuItem(
                "手动登出",
                self._on_manual_logout,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "退出",
                self._on_exit,
            ),
        )

    def _on_manual_login(self, icon, item):
        """手动登录"""
        log.info("[托盘] 用户点击: 手动登录")
        u = CONFIG.auth.username
        p = CONFIG.auth.password
        if u and p:
            self._update_status("手动登录中...", "yellow")
            threading.Thread(
                target=self._do_login, args=(u, p), daemon=True
            ).start()
        else:
            self._update_status("未配置账号密码", "red")
            log.warning("[托盘] 未配置账号密码，请检查 account.ini")

    def _do_login(self, u, p) -> bool:
        """执行登录（返回 True/False）"""
        log.info("[托盘:登录] ====== 开始登录 ======")
        try:
            from campus_auth import CampusAuth
            if self._auth is None:
                self._auth = CampusAuth()
            ok = self._auth.login(u, p)
            if ok:
                log.info("[托盘:登录] ✅ 登录成功")
                self._update_status("已认证", "green")
            else:
                log.error("[托盘:登录] ❌ 登录失败")
                self._update_status("登录失败", "red")
            return ok
        except Exception as e:
            log.error("[托盘:登录] ❌ 登录异常: %s", e, exc_info=True)
            self._update_status("登录异常", "red")
            return False

    def _on_manual_logout(self, icon, item):
        """手动登出"""
        log.info("[托盘] 用户点击: 手动登出")
        self._update_status("登出中...", "yellow")
        try:
            from campus_auth import CampusAuth
            auth = CampusAuth()
            ok = auth.logout()
            if ok:
                log.info("[托盘:登出] ✅ 登出成功")
                self._update_status("已登出", "yellow")
            else:
                log.error("[托盘:登出] ❌ 登出失败")
                self._update_status("登出失败", "red")
        except Exception as e:
            log.error("[托盘:登出] ❌ 登出异常: %s", e, exc_info=True)
            self._update_status("登出失败", "red")

    def _on_exit(self, icon, item):
        """退出（仅菜单点击触发）"""
        self._user_initiated_exit = True
        try:
            import traceback
            log.info("[托盘] 菜单退出触发，调用栈:\n%s", "".join(traceback.format_stack()))
        except Exception:
            pass
        self._running = False
        if self._icon:
            self._icon.stop()

    def _format_traffic_tooltip(self) -> str:
        """格式化流量信息用于 tooltip。"""
        info = self._traffic_info
        if not info:
            return ""
        parts = []
        if "userName" in info:
            parts.append(f"账号: {info['userName']}")
        if "used_str" in info:
            parts.append(f"已用: {info['used_str']}")
        if "remain_str" in info:
            parts.append(f"剩余: {info['remain_str']}")
        if "total_str" in info:
            parts.append(f"总流量: {info['total_str']}")
        if "userGroupName" in info:
            parts.append(f"套餐: {info['userGroupName']}")
        if "balance_str" in info:
            parts.append(f"余额: {info['balance_str']}")
        if "time_str" in info:
            parts.append(f"在线: {info['time_str']}")
        if "_device_count" in info:
            parts.append(f"设备: {info['_device_count']}台")
        return "\n".join(parts)

    def _update_traffic_info(self) -> None:
        """更新流量信息"""
        now = time.time()
        if now - self._traffic_last_update < self._traffic_interval:
            return
        self._traffic_last_update = now
        log.info("[托盘:流量] 开始查询流量信息...")
        try:
            from campus_auth import CampusAuth
            if self._auth is None:
                self._auth = CampusAuth()
            info = self._auth.get_traffic_info()
            if info and ("used_str" in info or "userName" in info):
                self._traffic_info = info
                log.info("[托盘:流量] ✅ 流量更新: %s", {k: v for k, v in info.items() if not k.startswith("_")})
            else:
                log.info("[托盘:流量] 未获取到有效流量信息")
        except Exception as e:
            log.error("[托盘:流量] 查询失败: %s", e)

    # ------------------------------------------------------------------
    # 后台保活循环
    # ------------------------------------------------------------------

    def _keepalive_loop(self) -> None:
        """后台保活线程（带阶段心跳的看门狗）。"""
        self._loop_heartbeat = time.monotonic()

        def _watchdog():
            while self._running:
                time.sleep(30)
                if time.monotonic() - self._loop_heartbeat > self._watchdog_timeout_sec:
                    log.error(
                        "[看门狗] 保活循环超过%d秒没有阶段心跳，强制重启进程...",
                        self._watchdog_timeout_sec,
                    )
                    for h in log.handlers:
                        try: h.flush()
                        except Exception: pass
                    log.error("[看门狗] 释放单实例锁并启动替代进程")
                    for h in log.handlers:
                        try: h.flush()
                        except Exception: pass
                    try:
                        _restart_current_process()
                    except Exception:
                        log.exception("[看门狗] 启动替代进程失败")
                    os._exit(1)

        threading.Thread(target=_watchdog, daemon=True).start()
        log.info("[保活] 后台保活线程启动")
        log.info("[保活] 轮询间隔: %ds, 防抖次数: %d", CONFIG.network.poll_interval_sec, CONFIG.network.confirm_count)

        while self._running:
            try:
                self._touch_watchdog("开始网络检测")
                snap = take_snapshot()
                self._touch_watchdog("网络检测完成")

                # 状态转换日志
                if self._last_state != snap.state:
                    log.info("[保活] ====== 状态转换: %s → %s ======",
                             self._last_state.name if self._last_state else "INIT",
                             snap.state.name)
                    self._last_state = snap.state

                if snap.state == NetState.ONLINE:
                    self._update_status("在线", "green")
                    self._consecutive_abnormal = 0
                    self._pending_abnormal = None
                    self._touch_watchdog("开始流量查询")
                    self._update_traffic_info()
                    self._touch_watchdog("流量查询完成")
                    self._observe_interface_mode(snap)

                    if self._should_switch_back_to_ethernet(
                        snap.eth_connected, snap.wifi_connected, snap
                    ):
                        self._switch_back_to_ethernet()
                        continue

                    # 认证保活心跳
                    if CONFIG.auth.enabled:
                        from campus_auth import CampusAuth
                        if self._auth is None:
                            self._auth = CampusAuth()
                        alive = self._auth.heartbeat()
                        if not alive:
                            log.warning("[保活] 心跳失败，需要重新认证")
                            self._do_login(CONFIG.auth.username, CONFIG.auth.password)

                else:
                    if snap.state != self._pending_abnormal:
                        self._pending_abnormal = snap.state
                        self._consecutive_abnormal = 1
                    else:
                        self._consecutive_abnormal += 1
                    log.warning("[保活] 异常检测 #%d/%d: %s",
                                self._consecutive_abnormal, CONFIG.network.confirm_count, snap.state.name)

                    if self._consecutive_abnormal < CONFIG.network.confirm_count:
                        self._update_status(
                            f"检测中 ({self._consecutive_abnormal}/{CONFIG.network.confirm_count})",
                            "yellow",
                        )
                    else:
                        # 达到防抖阈值，开始恢复
                        log.warning("[保活] ====== 防抖确认，开始恢复 ======")

                        if snap.state == NetState.CABLE_DOWN:
                            self._update_status("网线断开，恢复中...", "red")
                            self._recover_cable_down()
                        elif snap.state == NetState.DHCP_LIMITED:
                            self._update_status("DHCP 异常，刷新中...", "yellow")
                            self._recover_dhcp_limited(snap)
                        elif snap.state == NetState.WEB_AUTH_REQUIRED:
                            if CONFIG.auth.enabled:
                                self._update_status("需要认证，登录中...", "yellow")
                                if not self._do_login(CONFIG.auth.username, CONFIG.auth.password):
                                    log.warning("[保活] 认证登录失败，尝试网络恢复...")
                                    self._recover_auth_failed()
                            else:
                                self._update_status("需要认证（未启用）", "red")

            except Exception as e:
                log.error("[保活] ❌ 保活循环异常: %s", e, exc_info=True)
                self._update_status("运行异常", "red")
                time.sleep(5)

            # 关闭并重建探测 session，避免连接池/GDI 资源长期累积泄漏
            try:
                import network_monitor as _nm
                if _nm._probe_session is not None:
                    try:
                        _nm._probe_session.close()
                    except Exception:
                        pass
                    _nm._probe_session = None
            except Exception:
                pass

            # 定期清理 auth session（每30分钟重建一次，避免连接池老化）
            try:
                if self._auth is not None and hasattr(self._auth, "_auth"):
                    auth_inner = self._auth._auth
                    if auth_inner is not None and hasattr(auth_inner, "_session"):
                        import time as _t
                        if not hasattr(self, "_last_session_reset"):
                            self._last_session_reset = _t.time()
                        if _t.time() - self._last_session_reset > 1800:
                            try:
                                auth_inner._session.close()
                                auth_inner._session = requests.Session()
                                auth_inner._session.headers.update({
                                    "User-Agent": (
                                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                                        "Chrome/125.0.0.0 Safari/537.36"
                                    ),
                                })
                                self._last_session_reset = _t.time()
                                log.info("[保活] 已重建认证 session（30分钟定期清理）")
                            except Exception:
                                pass
            except Exception:
                pass

            # 更新看门狗心跳
            self._touch_watchdog("完成保活循环")
            time.sleep(CONFIG.network.poll_interval_sec)

    def _touch_watchdog(self, phase: str) -> None:
        """记录阶段心跳，避免慢速探测被误判为卡死。"""
        self._loop_heartbeat = time.monotonic()
        self._watchdog_phase = phase

    def _observe_interface_mode(self, snap) -> None:
        """根据每个接口的真实探测结果管理主路径和 Wi-Fi 兜底。"""
        eth_usable = bool(snap.eth_internet_reachable or snap.eth_auth_probe_ok)
        wifi_usable = bool(snap.wifi_internet_reachable or snap.wifi_auth_probe_ok)

        if snap.wifi_connected and (
            not snap.eth_connected or snap.eth_admin_enabled is False
        ):
            self._using_wifi_fallback = True

        # 记住当前 Wi-Fi 配置；即使配置文件没有填写 SSID，断线后也能重连原网络。
        if snap.wifi_connected:
            try:
                from wifi_switcher import get_connected_ssid
                profile = get_connected_ssid()
                if profile:
                    self._last_wifi_profiles = [profile]
            except Exception:
                pass

        if self._using_wifi_fallback:
            if not eth_usable and wifi_usable:
                self._ethernet_stable_count = 0
                self._prefer_wifi(snap)
            elif eth_usable and not wifi_usable:
                # Wi-Fi 已掉线时，若以太网真实可用，立即使用以太网。
                self._using_wifi_fallback = False
                self._ethernet_stable_count = 0
                self._prefer_ethernet(snap)
            # 两者都可用时保持 Wi-Fi 路由，等待连续稳定轮次后再切换。
        elif eth_usable:
            self._prefer_ethernet(snap)
        elif wifi_usable:
            self._using_wifi_fallback = True
            self._ethernet_stable_count = 0
            self._prefer_wifi(snap)

        if snap.eth_admin_enabled is False:
            now = time.monotonic()
            if now - self._last_ethernet_enable_attempt < 60:
                return
            self._last_ethernet_enable_attempt = now
            log.warning("[恢复:网线] 检测到以太网被管理员禁用，尝试启用")
            self._update_status("启用以太网中...", "yellow")
            if not enable_ethernet_adapter():
                log.warning("[恢复:网线] 以太网启用失败，继续使用 Wi-Fi")

    def _prefer_ethernet(self, snap) -> bool:
        if self._route_mode == "ethernet":
            return True
        from route_manager import prefer_ethernet
        ok = prefer_ethernet(snap.eth_alias or CONFIG.ethernet_adapter_name or "以太网",
                             snap.wifi_alias or CONFIG.wifi_adapter_name or "WLAN")
        if ok:
            self._route_mode = "ethernet"
        return ok

    def _prefer_wifi(self, snap) -> bool:
        if self._route_mode == "wifi":
            return True
        from route_manager import prefer_wifi
        ok = prefer_wifi(snap.eth_alias or CONFIG.ethernet_adapter_name or "以太网",
                         snap.wifi_alias or CONFIG.wifi_adapter_name or "WLAN")
        if ok:
            self._route_mode = "wifi"
            return True

        # 没有管理员权限修改 metric 时，禁用故障以太网，确保 Wi-Fi 真正接管流量。
        # 后续观察到管理员状态为禁用时，会按节流策略自动尝试重新启用。
        now = time.monotonic()
        if (
            snap.eth_connected
            and (snap.wifi_internet_reachable or snap.wifi_auth_probe_ok)
            and now - self._last_ethernet_disable_attempt >= 60
        ):
            from nic_reset import disable_adapter
            self._last_ethernet_disable_attempt = now
            alias = snap.eth_alias or CONFIG.ethernet_adapter_name
            if alias and disable_adapter(alias):
                self._route_mode = "wifi"
                log.warning("[路由] 无法调整 metric，已临时禁用故障以太网")
                return True
        return False

    def _wifi_fallback(self) -> bool:
        from wifi_switcher import auto_connect_preferred_wifi
        return auto_connect_preferred_wifi(self._last_wifi_profiles)

    def _recover_cable_down(self) -> None:
        """网线断开恢复"""
        log.warning("[恢复:网线] ====== 开始网线恢复流程 ======")
        from nic_reset import reset_ethernet

        # 第 1 步：重置网卡
        log.info("[恢复:网线] Step1: 尝试重置网卡...")
        self._update_status("重置网卡中...", "yellow")
        reset_ok = reset_ethernet()

        if not reset_ok:
            log.warning("[恢复:网线] 网卡重置失败（无管理员权限）")
        else:
            time.sleep(5)
            snap = take_snapshot()
            if snap.state == NetState.ONLINE:
                log.info("[恢复:网线] ✅ 网卡重置后恢复成功")
                self._update_status("在线", "green")
                return
            log.warning("[恢复:网线] 网卡重置后仍: %s", snap.state.name)

        # 第 2 步：切 Wi-Fi
        log.info("[恢复:网线] Step2: 切换 Wi-Fi...")
        self._update_status("切换 Wi-Fi...", "yellow")
        wifi_ok = self._wifi_fallback()

        if wifi_ok:
            time.sleep(5)
            snap2 = take_snapshot()
            if snap2.state == NetState.ONLINE:
                log.info("[恢复:网线] ✅ Wi-Fi 切换后恢复成功")
                self._using_wifi_fallback = True
                self._update_status("在线 (Wi-Fi)", "green")
                return
            elif snap2.state == NetState.WEB_AUTH_REQUIRED:
                log.info("[恢复:网线] Wi-Fi 已连接但需要认证")
                if CONFIG.auth.enabled:
                    if self._do_login(CONFIG.auth.username, CONFIG.auth.password):
                        return
                    log.warning("[恢复:网线] Wi-Fi 认证失败，保留 Wi-Fi 连接等待下轮重试")
                    self._update_status("Wi-Fi 认证待重试", "yellow")
                return

        log.error("[恢复:网线] ❌ 所有恢复手段均失败")
        self._update_status("恢复失败", "red")

    def _recover_dhcp_limited(self, snap=None) -> None:
        """DHCP 异常恢复（区分以太网和 WiFi 场景）"""
        if snap is None:
            snap = take_snapshot()

        eth_usable = bool(snap.eth_internet_reachable or snap.eth_auth_probe_ok)
        wifi_usable = bool(snap.wifi_internet_reachable or snap.wifi_auth_probe_ok)

        # 两张网卡都连接但只有 Wi-Fi 可用时，不重置或断开 Wi-Fi，先让它接管路由。
        if wifi_usable and not eth_usable:
            self._using_wifi_fallback = True
            self._prefer_wifi(snap)
            self._update_status("在线 (Wi-Fi)", "green")
            return

        # WiFi 在线但网关不通 → 不要 reset_ethernet（会把 WiFi 也断了）
        # 而是先尝试认证登录
        if snap.wifi_connected and not snap.eth_connected:
            log.warning("[恢复:DHCP] WiFi 在线但无法上网，尝试认证...")
            self._update_status("WiFi 需要认证...", "yellow")
            if CONFIG.auth.enabled:
                if self._do_login(CONFIG.auth.username, CONFIG.auth.password):
                    return
            # 认证失败，可能是 WiFi 信号问题
            log.warning("[恢复:DHCP] 认证失败，尝试重连 WiFi...")
            self._wifi_fallback()
            time.sleep(5)
            snap2 = take_snapshot()
            if snap2.state == NetState.ONLINE:
                self._update_status("在线 (Wi-Fi)", "green")
                self._consecutive_abnormal = 0
            return

        # 以太网场景：重置网卡
        log.warning("[恢复:DHCP] 以太网 DHCP 异常，开始刷新...")
        from nic_reset import reset_ethernet
        self._update_status("刷新 DHCP...", "yellow")
        reset_ethernet()
        time.sleep(3)
        snap = take_snapshot()
        log.info("[恢复:DHCP] 刷新后状态: %s", snap.state.name)
        if snap.wifi_internet_reachable or snap.wifi_auth_probe_ok:
            self._using_wifi_fallback = not (
                snap.eth_internet_reachable or snap.eth_auth_probe_ok
            )
            if self._using_wifi_fallback:
                self._prefer_wifi(snap)
                self._update_status("在线 (Wi-Fi)", "green")
                return
        if snap.state == NetState.WEB_AUTH_REQUIRED:
            if CONFIG.auth.enabled:
                self._do_login(CONFIG.auth.username, CONFIG.auth.password)
        elif not (snap.eth_internet_reachable or snap.eth_auth_probe_ok):
            log.warning("[恢复:DHCP] 以太网仍不可用，尝试启用 Wi-Fi 兜底")
            if self._wifi_fallback():
                self._using_wifi_fallback = True
                self._prefer_wifi(snap)

    def _recover_auth_failed(self) -> None:
        """认证登录失败后的恢复：尝试网卡重置 + 切换 WiFi"""
        from nic_reset import reset_ethernet

        # Step1: 尝试重置网卡
        log.warning("[恢复:认证失败] Step1: 尝试重置网卡...")
        self._update_status("重置网卡中...", "yellow")
        reset_ok = reset_ethernet()
        if reset_ok:
            time.sleep(5)
            snap = take_snapshot()
            log.info("[恢复:认证失败] 重置后状态: %s", snap.state.name)
            if snap.state == NetState.ONLINE:
                log.info("[恢复:认证失败] ✅ 网卡重置后恢复成功")
                self._update_status("在线", "green")
                self._consecutive_abnormal = 0
                return
            if snap.state == NetState.WEB_AUTH_REQUIRED:
                log.info("[恢复:认证失败] 重置后需要认证，再次尝试登录...")
                if self._do_login(CONFIG.auth.username, CONFIG.auth.password):
                    return

        # Step2: 切换 WiFi
        log.warning("[恢复:认证失败] Step2: 切换 Wi-Fi...")
        self._update_status("切换 Wi-Fi...", "yellow")
        wifi_ok = self._wifi_fallback()
        if wifi_ok:
            time.sleep(5)
            snap2 = take_snapshot()
            log.info("[恢复:认证失败] WiFi连接后状态: %s", snap2.state.name)
            if snap2.state == NetState.ONLINE:
                log.info("[恢复:认证失败] ✅ Wi-Fi 切换后恢复成功")
                self._update_status("在线 (Wi-Fi)", "green")
                self._consecutive_abnormal = 0
                return
            if snap2.state == NetState.WEB_AUTH_REQUIRED:
                log.info("[恢复:认证失败] WiFi已连接但需要认证...")
                if self._do_login(CONFIG.auth.username, CONFIG.auth.password):
                    return

        log.error("[恢复:认证失败] ❌ 所有恢复手段均失败")
        self._update_status("恢复失败", "red")

    def _switch_back_to_ethernet(self) -> None:
        """先验证以太网真实可用，再断开 Wi-Fi，失败时立即恢复 Wi-Fi。"""
        import subprocess
        log.info("[恢复:网线优先] 开始验证以太网，不先断开 Wi-Fi...")

        # Step1: 先让以太网获得路由优先级，但保留 Wi-Fi 作为保护。
        before = take_snapshot()
        self._prefer_ethernet(before)
        time.sleep(1)
        snap = take_snapshot()
        log.info("[恢复:网线优先] 验证结果: eth=%s wifi=%s eth_internet=%s eth_auth=%s",
                 snap.eth_connected, snap.wifi_connected,
                 snap.eth_internet_reachable, snap.eth_auth_probe_ok)

        if not (snap.eth_connected and (snap.eth_internet_reachable or snap.eth_auth_probe_ok)):
            log.warning("[恢复:网线优先] 以太网尚未验证可用，保持 Wi-Fi")
            self._using_wifi_fallback = True
            self._prefer_wifi(snap)
            return

        # Step2: 只有以太网确认可用后才断开 Wi-Fi。
        try:
            subprocess.run("netsh wlan disconnect", shell=True, capture_output=True, timeout=10)
        except Exception as e:
            log.warning("[恢复:网线优先] 断开WiFi失败: %s", e)

        time.sleep(2)
        snap = take_snapshot()
        log.info("[恢复:网线优先] 切换后状态: eth=%s wifi=%s state=%s",
                 snap.eth_connected, snap.wifi_connected, snap.state.name)

        if snap.eth_connected and (snap.eth_internet_reachable or snap.eth_auth_probe_ok):
            log.info("[恢复:网线优先] ✅ 已切回网线")
            self._update_status("在线", "green")
            self._consecutive_abnormal = 0
            self._using_wifi_fallback = False
            self._ethernet_stable_count = 0
            return

        # Step3: 切回失败，恢复 Wi-Fi 和路由优先级。
        log.warning("[恢复:网线优先] 切回网线失败，恢复 Wi-Fi...")
        self._using_wifi_fallback = True
        self._prefer_wifi(snap)
        self._wifi_fallback()
        time.sleep(5)
        snap2 = take_snapshot()
        if snap2.wifi_internet_reachable or snap2.wifi_auth_probe_ok:
            self._using_wifi_fallback = True
            self._update_status("在线 (Wi-Fi)", "green")
            return
        if snap2.state == NetState.WEB_AUTH_REQUIRED and CONFIG.auth.enabled:
            if self._do_login(CONFIG.auth.username, CONFIG.auth.password):
                return
        # 最终兜底：不管什么状态，标记异常但不卡死，下一轮会继续检测
        log.warning("[恢复:网线优先] 重新连WiFi后状态: %s，下轮继续检测", snap2.state.name)
        self._update_status("切回待定", "yellow")

    def _should_switch_back_to_ethernet(
        self, eth_connected: bool, wifi_connected: bool, snap=None
    ) -> bool:
        """仅在 Wi-Fi 兜底期间且网线连续三轮真实可用时切回。"""
        if not self._using_wifi_fallback:
            self._ethernet_stable_count = 0
            return False
        if not eth_connected or not wifi_connected:
            self._ethernet_stable_count = 0
            return False
        if snap is not None and not (
            snap.eth_internet_reachable or snap.eth_auth_probe_ok
        ):
            self._ethernet_stable_count = 0
            return False
        self._ethernet_stable_count += 1
        return self._ethernet_stable_count >= 3


    def run(self) -> None:
        """启动托盘应用（带崩溃保护自动重启）"""
        MAX_RESTARTS = 5
        restart_count = 0

        while restart_count <= MAX_RESTARTS:
            try:
                if restart_count > 0:
                    log.warning("[托盘] ====== 第 %d 次自动重启 ======", restart_count)

                log.info("=" * 60)
                log.info("[托盘] 启动托盘模式")
                log.info("[托盘] 账号: %s", CONFIG.auth.username[:3] + "***" if CONFIG.auth.username else "未配置")
                log.info("[托盘] 认证: %s", "启用" if CONFIG.auth.enabled else "未启用")
                log.info("[托盘] Wi-Fi: %s", CONFIG.network.wifi_ssids)
                log.info("[托盘] 检测间隔: %ds", CONFIG.network.poll_interval_sec)
                log.info("=" * 60)

                self._update_status("启动中...", "gray")
                self._icon = pystray.Icon(
                    "campus_keeper",
                    _create_icon_image("gray"),
                    "校园网保活: 启动中...",
                    menu=self._build_menu(),
                )

                # 后台保活线程
                self._running = True
                bg = threading.Thread(target=self._keepalive_loop, daemon=True)
                bg.start()

                # 托盘主循环（阻塞）
                log.info("[托盘] 托盘图标已显示，等待操作...")
                self._icon.run()

                # 正常退出（用户点了退出）
                if self._user_initiated_exit:
                    log.info("[托盘] 托盘正常退出：用户通过菜单点击退出")
                else:
                    log.warning("[托盘] 托盘退出：非菜单触发（系统消息/图标被关闭）")
                break

            except Exception as e:
                restart_count += 1
                log.error("[托盘] ❌ 托盘崩溃: %s", e, exc_info=True)
                log.error("[托盘] 将在 10 秒后自动重启... (第 %d/%d 次)", restart_count, MAX_RESTARTS)
                time.sleep(10)

        if restart_count > MAX_RESTARTS:
            log.error("[托盘] ❌ 已达最大重启次数 (%d)，退出", MAX_RESTARTS)


def run_tray_app() -> None:
    """供 main.py 调用的入口"""
    global _INSTANCE_MUTEX
    _mutex_name = "CampusNetworkKeeper_SingleInstance_Mutex"
    mutex = ctypes.windll.kernel32.CreateMutexW(0, False, _mutex_name)
    last_err = ctypes.windll.kernel32.GetLastError()
    ERROR_ALREADY_EXISTS = 183
    if last_err == ERROR_ALREADY_EXISTS:
        log.warning("[托盘] 检测到已有实例运行，跳过本次启动")
        ctypes.windll.kernel32.CloseHandle(mutex)
        return
    _INSTANCE_MUTEX = mutex
    if not HAS_TRAY:
        log.warning("[托盘] pystray/Pillow 未安装，回退到命令行模式")
        log.warning("[托盘] 安装: pip install pystray Pillow")
        from keepalive import KeepAlive
        keeper = KeepAlive()
        keeper.run()
        return

    try:
        app = TrayApp()
        app.run()
    finally:
        _release_instance_mutex()
