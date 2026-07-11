"""
校园网保活工具 - 认证路由层
根据配置自动选择认证模板（Dr.COM / 锐捷 / 深澜 / 通用 Portal）。
保留旧版接口兼容，让 tray.py / keepalive.py 不需要大改。
"""
from __future__ import annotations

import time
from typing import Optional

from auth.base import BaseAuth, AuthConfig, AuthSystemType
from auth.detector import detect_auth_system, create_auth_instance
from config import CONFIG
from logger import log


class CampusAuth:
    """
    认证路由器。
    自动探测或根据配置选择认证模板，提供统一的 login/logout/heartbeat 接口。
    """

    def __init__(self) -> None:
        self._auth: Optional[BaseAuth] = None
        self._auth_type: AuthSystemType = AuthSystemType.UNKNOWN
        self._initialized = False

    def _ensure_auth(self) -> Optional[BaseAuth]:
        """延迟初始化认证实例"""
        if self._auth is not None:
            return self._auth

        method = CONFIG.auth_method
        log.info("[认证] 初始化认证模块 (method=%s)", method)

        # 构造 AuthConfig
        auth_config = AuthConfig(
            method=method,
            username=CONFIG.auth_username,
            password=CONFIG.auth_password,
            gateway_base=CONFIG.auth_gateway,
            login_url=CONFIG.auth_login_url,
            logout_url=CONFIG.auth_logout_url,
            probe_url=CONFIG.auth_probe_url,
            success_keyword=CONFIG.auth_success_keyword,
            operator=CONFIG.auth_operator,
            heartbeat_interval_sec=CONFIG.auth_heartbeat_interval,
        )

        if method == "auto":
            # 自动探测
            log.info("[认证] 自动探测认证系统...")
            system_type, redirect_url, _ = detect_auth_system()
            if system_type == AuthSystemType.UNKNOWN:
                # 在线状态和暂时无法访问认证页时都可能得到 UNKNOWN。
                # 此时猜测 Dr.COM 会让其他学校在后续掉线时使用错误模板；
                # 保持未初始化，让下一次真正出现 Portal 时重新探测。
                log.info("[认证] 当前未发现认证页面，暂不锁定认证模板")
                self._initialized = False
                return None
            self._auth_type = system_type
            self._auth = create_auth_instance(system_type, auth_config)
        else:
            # 手动指定
            type_map = {
                "drcom": AuthSystemType.DRCOM,
                "ruijie": AuthSystemType.RUIJIE,
                "srun": AuthSystemType.SRUN,
                "portal": AuthSystemType.PORTAL,
            }
            system_type = type_map.get(method, AuthSystemType.DRCOM)
            self._auth_type = system_type
            self._auth = create_auth_instance(system_type, auth_config)

        if self._auth:
            log.info("[认证] 使用认证模板: %s", self._auth_type.value)
        else:
            log.error("[认证] 无法创建认证实例")

        self._initialized = True
        return self._auth

    # ------------------------------------------------------------------
    # 公开接口（兼容旧版 tray.py / keepalive.py）
    # ------------------------------------------------------------------

    def is_authenticated(self) -> bool:
        """检查当前是否已认证"""
        auth = self._ensure_auth()
        if auth is None:
            return False
        try:
            return auth.is_authenticated()
        except Exception as e:
            log.error("[认证] 检测认证状态异常: %s", e)
            return False

    def login(self, username: str, password: str) -> bool:
        """执行登录"""
        auth = self._ensure_auth()
        if auth is None:
            log.error("[认证] 认证实例未初始化")
            return False
        try:
            return auth.login(username, password)
        except Exception as e:
            log.error("[认证] 登录异常: %s", e, exc_info=True)
            return False

    def heartbeat(self) -> bool:
        """心跳保活"""
        auth = self._ensure_auth()
        if auth is None:
            return False
        try:
            return auth.heartbeat()
        except Exception as e:
            log.error("[认证] 心跳异常: %s", e)
            return False

    def logout(self) -> bool:
        """登出"""
        auth = self._ensure_auth()
        if auth is None:
            return False
        try:
            return auth.logout()
        except Exception as e:
            log.error("[认证] 登出异常: %s", e, exc_info=True)
            return False

    def get_traffic_info(self) -> dict:
        """获取流量信息"""
        auth = self._ensure_auth()
        if auth is None:
            return {}
        try:
            return auth.get_traffic_info()
        except Exception as e:
            log.error("[认证] 流量查询异常: %s", e)
            return {}

