"""
校园网保活工具 - 系统托盘常驻模块（带详细日志）
使用 pystray + PIL 实现 Windows 系统托盘图标。
"""
from __future__ import annotations

import os
import threading
import time
from typing import Optional

from config import CONFIG
from logger import log
from network_monitor import log_snapshot, NetState, take_snapshot

try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False


def _create_icon_image(color: str = "green") -> "Image.Image":
    """生成一个圆形托盘图标"""
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

    def _do_login(self, u, p):
        """执行登录（后台线程）"""
        log.info("[托盘:登录] ====== 开始登录 ======")
        try:
            from campus_auth import CampusAuth
            auth = CampusAuth()
            ok = auth.login(u, p)
            if ok:
                log.info("[托盘:登录] ✅ 登录成功")
                self._update_status("已认证", "green")
            else:
                log.error("[托盘:登录] ❌ 登录失败")
                self._update_status("登录失败", "red")
        except Exception as e:
            log.error("[托盘:登录] ❌ 登录异常: %s", e, exc_info=True)
            self._update_status("登录异常", "red")

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
        """退出"""
        log.info("[托盘] 用户点击: 退出")
        self._running = False
        if self._icon:
            self._icon.stop()

    def _format_traffic_tooltip(self) -> str:
        """格式化流量信息用于 tooltip"""
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
        """后台保活线程"""
        log.info("[保活] 后台保活线程启动")
        log.info("[保活] 轮询间隔: %ds, 防抖次数: %d", CONFIG.network.poll_interval_sec, CONFIG.network.confirm_count)

        while self._running:
            try:
                snap = take_snapshot()

                # 状态转换日志
                if self._last_state != snap.state:
                    log.info("[保活] ====== 状态转换: %s → %s ======",
                             self._last_state.name if self._last_state else "INIT",
                             snap.state.name)
                    self._last_state = snap.state

                if snap.state == NetState.ONLINE:
                    self._update_status("在线", "green")
                    self._consecutive_abnormal = 0
                    self._update_traffic_info()

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
                            self._recover_dhcp_limited()
                        elif snap.state == NetState.WEB_AUTH_REQUIRED:
                            if CONFIG.auth.enabled:
                                self._update_status("需要认证，登录中...", "yellow")
                                self._do_login(CONFIG.auth.username, CONFIG.auth.password)
                            else:
                                self._update_status("需要认证（未启用）", "red")

            except Exception as e:
                log.error("[保活] ❌ 保活循环异常: %s", e, exc_info=True)
                self._update_status("运行异常", "red")

            time.sleep(CONFIG.network.poll_interval_sec)

    def _recover_cable_down(self) -> None:
        """网线断开恢复"""
        log.warning("[恢复:网线] ====== 开始网线恢复流程 ======")
        from nic_reset import reset_ethernet
        from wifi_switcher import auto_connect_preferred_wifi

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
        wifi_ok = auto_connect_preferred_wifi()

        if wifi_ok:
            time.sleep(5)
            snap2 = take_snapshot()
            if snap2.state == NetState.ONLINE:
                log.info("[恢复:网线] ✅ Wi-Fi 切换后恢复成功")
                self._update_status("在线 (Wi-Fi)", "green")
                return
            elif snap2.state == NetState.WEB_AUTH_REQUIRED:
                log.info("[恢复:网线] Wi-Fi 已连接但需要认证")
                if CONFIG.auth.enabled:
                    self._do_login(CONFIG.auth.username, CONFIG.auth.password)
                return

        log.error("[恢复:网线] ❌ 所有恢复手段均失败")
        self._update_status("恢复失败", "red")

    def _recover_dhcp_limited(self) -> None:
        """DHCP 异常恢复"""
        log.warning("[恢复:DHCP] 开始刷新 DHCP...")
        from nic_reset import reset_ethernet
        self._update_status("刷新 DHCP...", "yellow")
        reset_ethernet()
        time.sleep(3)
        snap = take_snapshot()
        log.info("[恢复:DHCP] 刷新后状态: %s", snap.state.name)

    def run(self) -> None:
        """启动托盘应用"""
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
        bg = threading.Thread(target=self._keepalive_loop, daemon=True)
        bg.start()

        # 托盘主循环（阻塞）
        log.info("[托盘] 托盘图标已显示，等待操作...")
        self._icon.run()


def run_tray_app() -> None:
    """供 main.py 调用的入口"""
    if not HAS_TRAY:
        log.warning("[托盘] pystray/Pillow 未安装，回退到命令行模式")
        log.warning("[托盘] 安装: pip install pystray Pillow")
        from keepalive import KeepAlive
        keeper = KeepAlive()
        keeper.run()
        return

    app = TrayApp()
    app.run()
