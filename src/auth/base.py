"""
认证模板基类
所有认证系统（Dr.COM、锐捷、深澜等）都继承此基类。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from logger import log


class AuthSystemType(Enum):
    """认证系统类型"""
    DRCOM = "drcom"           # Dr.COM（城市热点）+ CAS SSO
    RUIJIE = "ruijie"         # 锐捷 ePortal
    SRUN = "srun"             # 深澜 Srun
    PORTAL = "portal"         # 通用 Web Portal
    UNKNOWN = "unknown"


@dataclass
class AuthConfig:
    """认证配置（从 config.ini 加载）"""
    method: str = "auto"           # auto / drcom / ruijie / srun / portal
    username: str = ""
    password: str = ""
    gateway_base: str = ""         # 认证网关地址（如 http://172.20.30.2:8080）
    login_url: str = ""            # 登录 URL
    logout_url: str = ""           # 登出 URL
    probe_url: str = "http://www.msftconnecttest.com/connecttest.txt"
    success_keyword: str = "Microsoft Connect Test"
    operator: str = ""             # 运营商（锐捷需要）
    extra: Dict[str, str] = field(default_factory=dict)  # 额外参数

    # 通用检测参数
    poll_interval_sec: int = 10
    heartbeat_interval_sec: int = 60


class BaseAuth(ABC):
    """
    认证模板基类。
    所有认证系统实现此类的抽象方法即可接入。
    """

    # 子类必须设置
    SYSTEM_TYPE: AuthSystemType = AuthSystemType.UNKNOWN
    SYSTEM_NAME: str = "Unknown"

    def __init__(self, config: AuthConfig) -> None:
        self.config = config
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        })
        retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[500, 502, 503])
        self._session.mount("http://", HTTPAdapter(max_retries=retry))
        self._session.mount("https://", HTTPAdapter(max_retries=retry))

        self._logged_in = False
        self._session_established = False
        self._last_heartbeat: float = 0.0

    # ------------------------------------------------------------------
    # 抽象方法（子类必须实现）
    # ------------------------------------------------------------------

    @abstractmethod
    def login(self, username: str, password: str) -> bool:
        """
        执行登录。
        返回 True 表示登录成功（网络可访问）。
        """
        ...

    @abstractmethod
    def is_authenticated(self) -> bool:
        """
        检查当前是否已认证（网络是否可用）。
        通常通过访问一个已知的外部 URL 来判断。
        """
        ...

    @abstractmethod
    def logout(self) -> bool:
        """
        登出当前账号。
        返回 True 表示登出成功。
        """
        ...

    # ------------------------------------------------------------------
    # 可选方法（子类可覆盖）
    # ------------------------------------------------------------------

    def heartbeat(self) -> bool:
        """
        心跳保活。默认每 heartbeat_interval_sec 秒检查一次认证状态。
        子类可覆盖实现特殊的保活逻辑。
        """
        import time
        now = time.time()
        if now - self._last_heartbeat < self.config.heartbeat_interval_sec:
            return self._logged_in

        alive = self.is_authenticated()
        self._last_heartbeat = now

        if not alive and self._logged_in:
            log.warning("[认证:心跳] 认证已失效!")
            self._logged_in = False
            self._session_established = False
        elif alive:
            self._logged_in = True

        return alive

    def get_traffic_info(self) -> dict:
        """
        获取流量信息（可选实现）。
        返回 dict，包含 used_str / remain_str / total_str / balance_str 等。
        """
        return {}

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    def _log_resp(self, tag: str, resp: requests.Response) -> None:
        """记录 HTTP 响应摘要"""
        log.info("[认证:%s] HTTP %s %s -> %d (len=%s)",
                 tag, resp.request.method, resp.url[:120],
                 resp.status_code, len(resp.text))

    def _get_local_ip(self, target: str = "10.0.0.1", port: int = 80) -> str:
        """获取本机 IP（通过 UDP 探测目标地址）"""
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((target, port))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            pass
        # 回退：从 ipconfig 提取
        import subprocess
        import re
        try:
            out = subprocess.run("ipconfig", shell=True, capture_output=True).stdout
            text = out.decode("utf-8", errors="ignore")
            for line in text.split("\n"):
                if "IPv4" in line:
                    m = re.search(r"(\d+\.\d+\.\d+\.\d+)", line)
                    if m and not m.group(1).startswith("169.254"):
                        return m.group(1)
        except Exception:
            pass
        return ""
