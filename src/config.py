"""
校园网保活工具 - 配置管理
支持 config.ini 文件 + 环境变量 + 默认值。
"""
from __future__ import annotations

import configparser
import os
from pathlib import Path
from typing import List

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 配置文件路径
CONFIG_INI = PROJECT_ROOT / "config.ini"
ACCOUNT_INI = PROJECT_ROOT / "account.ini"


class Config:
    """
    应用配置管理器。
    优先级: 环境变量 > config.ini > account.ini > 默认值
    """

    def __init__(self) -> None:
        # ---------- 认证配置 ----------
        self.auth_method: str = "auto"           # auto / drcom / ruijie / srun / portal
        self.auth_username: str = ""
        self.auth_password: str = ""
        self.auth_gateway: str = ""              # 认证网关地址
        self.auth_login_url: str = ""
        self.auth_logout_url: str = ""
        self.auth_probe_url: str = "http://www.msftconnecttest.com/connecttest.txt"
        self.auth_success_keyword: str = "Microsoft Connect Test"
        self.auth_operator: str = ""             # 运营商（锐捷需要）
        self.auth_enabled: bool = True
        self.auth_heartbeat_interval: int = 60   # 心跳间隔（秒）

        # ---------- 网络配置 ----------
        self.poll_interval: int = 10             # 检测间隔（秒）
        self.confirm_count: int = 2              # 防抖次数
        self.nic_reset_wait: int = 8             # 网卡重置等待（秒）
        self.nic_disable_wait: int = 4           # 网卡禁用等待（秒）
        self.wifi_ssids: List[str] = []          # Wi-Fi SSID 列表
        self.wifi_timeout: int = 20              # Wi-Fi 连接超时（秒）

        # ---------- 应用配置 ----------
        self.log_level: str = "INFO"
        self._log_max_mb: int = 10
        self._log_backup_count: int = 5
        self.ethernet_adapter: str = ""          # 网卡名称（空=自动检测）
        self.wifi_adapter: str = "WLAN"

        # ---------- 加载配置 ----------
        self._load()

    def _load(self) -> None:
        """按优先级加载配置"""
        # 1. 从 config.ini 加载
        if CONFIG_INI.exists():
            self._load_from_ini(CONFIG_INI)

        # 2. 从 account.ini 加载账号密码（兼容旧版）
        if ACCOUNT_INI.exists():
            self._load_account_from_ini(ACCOUNT_INI)

        # 3. 环境变量覆盖
        self._load_from_env()

    def _load_from_ini(self, path: Path) -> None:
        """从 INI 文件加载配置"""
        cp = configparser.ConfigParser()
        cp.read(str(path), encoding="utf-8")

        # [auth] 节
        if cp.has_section("auth"):
            self.auth_method = cp.get("auth", "method", fallback=self.auth_method)
            self.auth_username = cp.get("auth", "username", fallback=self.auth_username)
            self.auth_password = cp.get("auth", "password", fallback=self.auth_password)
            self.auth_gateway = cp.get("auth", "gateway", fallback=self.auth_gateway)
            self.auth_login_url = cp.get("auth", "login_url", fallback=self.auth_login_url)
            self.auth_logout_url = cp.get("auth", "logout_url", fallback=self.auth_logout_url)
            self.auth_probe_url = cp.get("auth", "probe_url", fallback=self.auth_probe_url)
            self.auth_success_keyword = cp.get("auth", "success_keyword", fallback=self.auth_success_keyword)
            self.auth_operator = cp.get("auth", "operator", fallback=self.auth_operator)
            self.auth_enabled = cp.getboolean("auth", "enabled", fallback=self.auth_enabled)
            self.auth_heartbeat_interval = cp.getint("auth", "heartbeat_interval", fallback=self.auth_heartbeat_interval)

        # [network] 节
        if cp.has_section("network"):
            self.poll_interval = cp.getint("network", "poll_interval", fallback=self.poll_interval)
            self.confirm_count = cp.getint("network", "confirm_count", fallback=self.confirm_count)
            self.wifi_timeout = cp.getint("network", "wifi_timeout", fallback=self.wifi_timeout)
            ssids_str = cp.get("network", "wifi_ssids", fallback="")
            if ssids_str:
                self.wifi_ssids = [s.strip() for s in ssids_str.split(",") if s.strip()]

        # [app] 节
        if cp.has_section("app"):
            self.log_level = cp.get("app", "log_level", fallback=self.log_level)
            self.ethernet_adapter = cp.get("app", "ethernet_adapter", fallback=self.ethernet_adapter)
            self.wifi_adapter = cp.get("app", "wifi_adapter", fallback=self.wifi_adapter)

    def _load_account_from_ini(self, path: Path) -> None:
        """从 account.ini 加载账号密码（兼容旧版）"""
        if self.auth_username and self.auth_password:
            return  # config.ini 已有，不覆盖
        cp = configparser.ConfigParser()
        cp.read(str(path), encoding="utf-8")
        self.auth_username = cp.get("account", "username", fallback=self.auth_username)
        self.auth_password = cp.get("account", "password", fallback=self.auth_password)

    def _load_from_env(self) -> None:
        """从环境变量加载"""
        self.auth_username = os.environ.get("CAMPUS_USER", self.auth_username)
        self.auth_password = os.environ.get("CAMPUS_PASS", self.auth_password)
        self.auth_method = os.environ.get("CAMPUS_AUTH_METHOD", self.auth_method)
        self.auth_gateway = os.environ.get("CAMPUS_GATEWAY", self.auth_gateway)

    def save(self) -> None:
        """保存配置到 config.ini"""
        cp = configparser.ConfigParser()

        cp.add_section("auth")
        cp.set("auth", "method", self.auth_method)
        cp.set("auth", "username", self.auth_username)
        cp.set("auth", "password", self.auth_password)
        cp.set("auth", "gateway", self.auth_gateway)
        cp.set("auth", "login_url", self.auth_login_url)
        cp.set("auth", "logout_url", self.auth_logout_url)
        cp.set("auth", "probe_url", self.auth_probe_url)
        cp.set("auth", "success_keyword", self.auth_success_keyword)
        cp.set("auth", "operator", self.auth_operator)
        cp.set("auth", "enabled", str(self.auth_enabled))
        cp.set("auth", "heartbeat_interval", str(self.auth_heartbeat_interval))

        cp.add_section("network")
        cp.set("network", "poll_interval", str(self.poll_interval))
        cp.set("network", "confirm_count", str(self.confirm_count))
        cp.set("network", "wifi_ssids", ", ".join(self.wifi_ssids))
        cp.set("network", "wifi_timeout", str(self.wifi_timeout))

        cp.add_section("app")
        cp.set("app", "log_level", self.log_level)
        cp.set("app", "ethernet_adapter", self.ethernet_adapter)
        cp.set("app", "wifi_adapter", self.wifi_adapter)

        with open(CONFIG_INI, "w", encoding="utf-8") as f:
            cp.write(f)

    # ------------------------------------------------------------------
    # 兼容旧版接口（让现有 tray.py / keepalive.py 不用大改）
    # ------------------------------------------------------------------

    class _AuthProxy:
        """兼容旧版 CONFIG.auth.xxx 接口"""
        def __init__(self, cfg: "Config"):
            self._cfg = cfg
        @property
        def username(self): return self._cfg.auth_username
        @username.setter
        def username(self, v): self._cfg.auth_username = v
        @property
        def password(self): return self._cfg.auth_password
        @password.setter
        def password(self, v): self._cfg.auth_password = v
        @property
        def enabled(self): return self._cfg.auth_enabled
        @property
        def gateway_base(self): return self._cfg.auth_gateway
        @property
        def heartbeat_interval_sec(self): return self._cfg.auth_heartbeat_interval

    class _NetworkProxy:
        """兼容旧版 CONFIG.network.xxx 接口"""
        def __init__(self, cfg: "Config"):
            self._cfg = cfg
        @property
        def poll_interval_sec(self): return self._cfg.poll_interval
        @property
        def confirm_count(self): return self._cfg.confirm_count
        @property
        def wifi_ssids(self): return self._cfg.wifi_ssids
        @property
        def wifi_connect_timeout_sec(self): return self._cfg.wifi_timeout
        @property
        def auth_probe_url(self): return self._cfg.auth_probe_url
        @property
        def auth_success_keyword(self): return self._cfg.auth_success_keyword
        @property
        def internet_probe_url(self): return "http://connect.rom.miui.com/generate_204"
        @property
        def internet_probe_url_backup(self): return "http://www.gstatic.com/generate_204"
        @property
        def nic_reset_wait_sec(self): return self._cfg.nic_reset_wait
        @property
        def nic_disable_wait_sec(self): return self._cfg.nic_disable_wait
        @property
        def max_retries(self): return 5
        @property
        def backoff_base_sec(self): return 30
        @property
        def backoff_max_sec(self): return 300

    @property
    def auth(self):
        return self._AuthProxy(self)

    @property
    def network(self):
        return self._NetworkProxy(self)

    # ---------- 旧版兼容属性 ----------
    @property
    def ethernet_adapter_name(self) -> str:
        return self.ethernet_adapter

    @property
    def wifi_adapter_name(self) -> str:
        return self.wifi_adapter

    @property
    def log_max_mb(self) -> int:
        return self._log_max_mb

    @log_max_mb.setter
    def log_max_mb(self, v: int):
        self._log_max_mb = v

    @property
    def log_backup_count(self) -> int:
        return self._log_backup_count

    @log_backup_count.setter
    def log_backup_count(self, v: int):
        self._log_backup_count = v


# 全局单例
CONFIG = Config()

