"""
锐捷 ePortal 认证模板
适用于锐捷 RG-SAM 认证系统（ePortal 网页认证）。

认证流程:
1. 访问外网 → 被重定向到 http://网关IP/eportal/index.jsp?...
2. 登录: POST http://网关IP/eportal/InterFace.do?method=login
3. 表单: userId/password/service/operatorPwd/operatorUserId/validcode/passwordEncrypt
4. 成功后返回 JSON: {"result":"success", ...}
5. 登出: http://网关IP/eportal/InterFace.do?method=logout
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

import requests

from auth.base import AuthConfig, AuthSystemType, BaseAuth
from logger import log


class RuijieAuth(BaseAuth):
    """锐捷 ePortal 认证器"""

    SYSTEM_TYPE = AuthSystemType.RUIJIE
    SYSTEM_NAME = "锐捷 ePortal"

    # 运营商映射（常见值）
    OPERATOR_MAP: Dict[str, str] = {
        "移动": "中国移动",
        "cmcc": "中国移动",
        "china_mobile": "中国移动",
        "联通": "中国联通",
        "cu": "中国联通",
        "china_unicom": "中国联通",
        "电信": "中国电信",
        "ct": "中国电信",
        "china_telecom": "中国电信",
    }

    def __init__(self, config: AuthConfig) -> None:
        super().__init__(config)

        # 从 config 读取网关地址
        self._gateway_ip: str = config.extra.get(
            "gateway_ip",
            config.gateway_base.replace("http://", "").replace("https://", "").split(":")[0]
            if config.gateway_base else "10.10.10.10",
        )
        self._gateway_port: str = config.extra.get(
            "gateway_port",
            config.gateway_base.split(":")[-1] if config.gateway_base and ":" in config.gateway_base.split("//")[-1] else "80",
        )

        # 运营商
        self._operator: str = self._resolve_operator(config.operator)

    @property
    def _base_url(self) -> str:
        """网关 base URL"""
        port = f":{self._gateway_port}" if self._gateway_port not in ("80", "443", "") else ""
        return f"http://{self._gateway_ip}{port}"

    def _resolve_operator(self, raw: str) -> str:
        """解析运营商名称（支持简称映射）"""
        if not raw:
            return ""
        lower = raw.strip().lower()
        if lower in self.OPERATOR_MAP:
            return self.OPERATOR_MAP[lower]
        # 已经是全称则直接返回
        for full in set(self.OPERATOR_MAP.values()):
            if full in raw:
                return full
        return raw

    # ------------------------------------------------------------------
    # 核心接口实现
    # ------------------------------------------------------------------

    def login(self, username: str, password: str) -> bool:
        """
        锐捷 ePortal 登录。
        POST http://网关IP/eportal/InterFace.do?method=login
        """
        log.info("=" * 60)
        log.info("[认证:锐捷:登录] ========== 开始登录流程 ==========")
        log.info("[认证:锐捷:登录] 账号: %s, 运营商: %s", username, self._operator or "(无)")

        # 先检查是否已在线
        if self.is_authenticated():
            log.info("[认证:锐捷:登录] 网络已通，无需重复登录")
            self._logged_in = True
            log.info("=" * 60)
            return True

        login_url = f"{self._base_url}/eportal/InterFace.do?method=login"
        log.info("[认证:锐捷:登录] 登录 URL: %s", login_url)

        form_data = {
            "userId": username,
            "password": password,
            "service": self._operator,
            "operatorPwd": "",
            "operatorUserId": "",
            "validcode": "",
            "passwordEncrypt": "false",
        }
        log.info("[认证:锐捷:登录] 表单字段: userId=%s service=%s passwordEncrypt=false",
                 username, self._operator)

        try:
            r = self._session.post(login_url, data=form_data, timeout=15, allow_redirects=True)
            self._log_resp("锐捷登录", r)
            log.info("[认证:锐捷:登录] 响应内容: %s", r.text[:500])
        except requests.RequestException as e:
            log.error("[认证:锐捷:登录] 登录请求失败: %s", e)
            log.info("=" * 60)
            return False

        # 解析返回 JSON
        try:
            result = r.json()
            status = result.get("result", "")
            log.info("[认证:锐捷:登录] JSON result=%s", status)

            if status == "success":
                log.info("[认证:锐捷:登录] 登录成功!")
                self._logged_in = True
                log.info("=" * 60)
                return True
            else:
                msg = result.get("message", result.get("msg", "(无消息)"))
                log.error("[认证:锐捷:登录] 登录失败: %s", msg)
                log.info("=" * 60)
                return False
        except (json.JSONDecodeError, ValueError):
            # 非 JSON 响应，尝试通过网络状态判断
            log.warning("[认证:锐捷:登录] 响应非 JSON，尝试通过网络状态判断...")
            ok = self.is_authenticated()
            self._logged_in = ok
            log.info("[认证:锐捷:登录] 登录流程完成: %s", "成功" if ok else "失败")
            log.info("=" * 60)
            return ok

    def is_authenticated(self) -> bool:
        """
        检查当前是否已认证。
        访问外网看是否被重定向到 ePortal 页面。
        """
        log.info("[认证:锐捷] 检测认证状态...")
        try:
            r = self._session.get(
                self.config.probe_url, timeout=8, allow_redirects=False,
            )
            self._log_resp("探测", r)

            # 如果返回 302 重定向到 eportal，说明未认证
            if r.status_code in (301, 302):
                location = r.headers.get("Location", "")
                if "eportal" in location.lower() or self._gateway_ip in location:
                    log.info("[认证:锐捷] 未认证（被重定向到 ePortal）")
                    return False

            # 如果正常返回 200 且包含探测关键字
            ok = self.config.success_keyword in r.text
            log.info("[认证:锐捷] 认证状态: %s", "已认证" if ok else "未认证")
            if ok:
                self._logged_in = True
            return ok
        except requests.RequestException as e:
            log.warning("[认证:锐捷] 探测请求失败: %s", e)
            return False

    def logout(self) -> bool:
        """
        锐捷 ePortal 登出。
        GET http://网关IP/eportal/InterFace.do?method=logout
        """
        log.info("[认证:锐捷:登出] ========== 开始登出流程 ==========")
        logout_url = f"{self._base_url}/eportal/InterFace.do?method=logout"
        log.info("[认证:锐捷:登出] 登出 URL: %s", logout_url)

        try:
            r = self._session.get(logout_url, timeout=10, allow_redirects=True)
            self._log_resp("锐捷登出", r)
            log.info("[认证:锐捷:登出] 响应内容: %s", r.text[:500])

            try:
                result = r.json()
                status = result.get("result", "")
                if status == "success":
                    log.info("[认证:锐捷:登出] 登出成功")
                else:
                    log.warning("[认证:锐捷:登出] 服务端返回: %s", result)
            except (json.JSONDecodeError, ValueError):
                pass

            self._logged_in = False
            log.info("[认证:锐捷:登出] 登出完成")
            return True
        except requests.RequestException as e:
            log.error("[认证:锐捷:登出] 登出请求失败: %s", e)
            return False
