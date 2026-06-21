"""
深澜 Srun 认证模板
适用于深澜 Srun 计费系统（常见于高校校园网）。

认证流程:
1. 访问外网 → 被重定向到 http://网关IP/srun_portal_pc?...
2. 登录: POST http://网关IP:801/eportal/?c=ACSetting&a=Login
3. 表单: DDDDD=账号&upass=密码&0MKKey=登录
4. 或 JSON API: http://网关IP/cgi-bin/srun_portal?action=auto_dm&...
5. 成功后返回包含 "login_ok" 或 JSON result
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

import requests

from auth.base import AuthConfig, AuthSystemType, BaseAuth
from logger import log


class SrunAuth(BaseAuth):
    """深澜 Srun 认证器"""

    SYSTEM_TYPE = AuthSystemType.SRUN
    SYSTEM_NAME = "深澜 Srun"

    def __init__(self, config: AuthConfig) -> None:
        super().__init__(config)

        # 从 config 读取网关地址
        self._gateway_ip: str = config.extra.get(
            "gateway_ip",
            config.gateway_base.replace("http://", "").replace("https://", "").split(":")[0]
            if config.gateway_base else "10.10.10.10",
        )
        self._auth_port: str = config.extra.get("auth_port", "801")
        self._portal_path: str = config.extra.get("portal_path", "/srun_portal_pc")
        self._ac_id: str = config.extra.get("ac_id", "1")

        # API 路径（深澜两种接口模式）
        self._eportal_path: str = config.extra.get("eportal_path", "/eportal/")
        self._cgi_path: str = config.extra.get("cgi_path", "/cgi-bin/srun_portal")

    @property
    def _gateway_base(self) -> str:
        """网关 base URL"""
        return f"http://{self._gateway_ip}"

    @property
    def _auth_base(self) -> str:
        """认证端口 base URL"""
        return f"http://{self._gateway_ip}:{self._auth_port}"

    # ------------------------------------------------------------------
    # 核心接口实现
    # ------------------------------------------------------------------

    def login(self, username: str, password: str) -> bool:
        """
        深澜 Srun 登录。
        优先使用 eportal 表单接口，失败则尝试 CGI JSON API。
        """
        log.info("=" * 60)
        log.info("[认证:深澜:登录] ========== 开始登录流程 ==========")
        log.info("[认证:深澜:登录] 账号: %s", username)

        # 先检查是否已在线
        if self.is_authenticated():
            log.info("[认证:深澜:登录] 网络已通，无需重复登录")
            self._logged_in = True
            log.info("=" * 60)
            return True

        # 方式一: eportal 表单登录
        log.info("[认证:深澜:登录] 尝试 eportal 表单登录...")
        ok = self._login_eportal(username, password)
        if ok:
            self._logged_in = True
            log.info("[认证:深澜:登录] eportal 登录成功!")
            log.info("=" * 60)
            return True

        # 方式二: CGI JSON API
        log.info("[认证:深澜:登录] eportal 失败，尝试 CGI JSON API...")
        ok = self._login_cgi(username, password)
        self._logged_in = ok
        log.info("[认证:深澜:登录] 登录流程完成: %s", "成功" if ok else "失败")
        log.info("=" * 60)
        return ok

    def _login_eportal(self, username: str, password: str) -> bool:
        """
        eportal 表单登录模式。
        POST http://网关IP:801/eportal/?c=ACSetting&a=Login
        表单: DDDDD=账号&upass=密码&0MKKey=登录
        """
        login_url = (
            f"{self._auth_base}{self._eportal_path}"
            f"?c=ACSetting&a=Login"
        )
        log.info("[认证:深澜:eportal] 登录 URL: %s", login_url)

        form_data = {
            "DDDDD": username,
            "upass": password,
            "0MKKey": "登录",
        }
        log.info("[认证:深澜:eportal] 表单字段: DDDDD=%s 0MKKey=登录", username)

        try:
            r = self._session.post(login_url, data=form_data, timeout=15, allow_redirects=True)
            self._log_resp("深澜eportal登录", r)
            log.info("[认证:深澜:eportal] 响应内容: %s", r.text[:500])
        except requests.RequestException as e:
            log.error("[认证:深澜:eportal] 登录请求失败: %s", e)
            return False

        # 判断成功
        text_lower = r.text.lower()
        if "login_ok" in text_lower or "success" in text_lower:
            log.info("[认证:深澜:eportal] 登录成功")
            return True

        # 检查是否仍然重定向（未认证状态）
        if "srun_portal" in r.text or "eportal" in r.text.lower():
            log.info("[认证:深澜:eportal] 仍在认证页面，登录可能失败")
            return False

        # 不确定状态，通过探测判断
        return self.is_authenticated()

    def _login_cgi(self, username: str, password: str) -> bool:
        """
        CGI JSON API 登录模式。
        GET http://网关IP/cgi-bin/srun_portal?action=auto_dm&...
        """
        cgi_url = (
            f"{self._gateway_base}{self._cgi_path}"
            f"?action=auto_dm"
            f"&username={username}"
            f"&password={password}"
            f"&ac_id={self._ac_id}"
            f"&type=1"
        )
        log.info("[认证:深澜:CGI] 登录 URL: %s", cgi_url)

        try:
            r = self._session.get(cgi_url, timeout=15, allow_redirects=True)
            self._log_resp("深澜CGI登录", r)
            log.info("[认证:深澜:CGI] 响应内容: %s", r.text[:500])
        except requests.RequestException as e:
            log.error("[认证:深澜:CGI] 登录请求失败: %s", e)
            return False

        # 尝试解析 JSON
        try:
            result = r.json()
            error_code = result.get("error", result.get("ecode", ""))
            if error_code == "ok" or error_code == 0:
                log.info("[认证:深澜:CGI] 登录成功")
                return True
            msg = result.get("error_msg", result.get("msg", str(error_code)))
            log.error("[认证:深澜:CGI] 登录失败: %s", msg)
            return False
        except (json.JSONDecodeError, ValueError):
            text_lower = r.text.lower()
            if "login_ok" in text_lower:
                return True
            log.warning("[认证:深澜:CGI] 响应非 JSON 且无 login_ok")
            return False

    def is_authenticated(self) -> bool:
        """
        检查当前是否已认证。
        访问外网看是否正常返回（未被重定向到认证页面）。
        """
        log.info("[认证:深澜] 检测认证状态...")
        try:
            # allow_redirects=False 以检测 302 重定向
            r = self._session.get(
                self.config.probe_url, timeout=8, allow_redirects=False,
            )
            self._log_resp("探测", r)

            # 如果被重定向到 srun_portal 或 eportal，说明未认证
            if r.status_code in (301, 302):
                location = r.headers.get("Location", "")
                if ("srun_portal" in location or "eportal" in location
                        or self._gateway_ip in location):
                    log.info("[认证:深澜] 未认证（被重定向到认证页面）")
                    return False

            # 正常返回且包含关键字
            ok = self.config.success_keyword in r.text
            log.info("[认证:深澜] 认证状态: %s", "已认证" if ok else "未认证")
            if ok:
                self._logged_in = True
            return ok
        except requests.RequestException as e:
            log.warning("[认证:深澜] 探测请求失败: %s", e)
            return False

    def logout(self) -> bool:
        """
        深澜 Srun 登出。
        尝试调用登出 API 或访问登出页面。
        """
        log.info("[认证:深澜:登出] ========== 开始登出流程 ==========")

        # 方式一: CGI 登出
        logout_url = (
            f"{self._gateway_base}{self._cgi_path}"
            f"?action=logout"
            f"&username={self.config.username}"
        )
        log.info("[认证:深澜:登出] 登出 URL: %s", logout_url)

        try:
            r = self._session.get(logout_url, timeout=10, allow_redirects=True)
            self._log_resp("深澜登出", r)
            log.info("[认证:深澜:登出] 响应内容: %s", r.text[:500])
        except requests.RequestException as e:
            log.error("[认证:深澜:登出] CGI 登出请求失败: %s", e)

        # 方式二: eportal 登出
        eportal_logout = (
            f"{self._auth_base}{self._eportal_path}"
            f"?c=ACSetting&a=Logout"
        )
        log.info("[认证:深澜:登出] eportal 登出 URL: %s", eportal_logout)

        try:
            r2 = self._session.get(eportal_logout, timeout=10, allow_redirects=True)
            self._log_resp("深澜eportal登出", r2)
        except requests.RequestException as e:
            log.error("[认证:深澜:登出] eportal 登出请求失败: %s", e)

        self._logged_in = False
        log.info("[认证:深澜:登出] 登出完成")
        return True
