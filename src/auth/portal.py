"""
通用 Web Portal 认证模板（兜底方案）
适用于无法识别具体认证系统的校园网 Portal。

认证流程:
1. 访问外网 → 被重定向到认证页面
2. 自动检测页面中的 <form> action URL 和 hidden input
3. 自动检测 password 字段名
4. 提交表单（username + password + 所有 hidden fields）
5. 成功后返回页面不含 "登录"/"login" 关键字，或外网可达
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests

from auth.base import AuthConfig, AuthSystemType, BaseAuth
from logger import log


class PortalAuth(BaseAuth):
    """通用 Web Portal 认证器（自动检测表单）"""

    SYSTEM_TYPE = AuthSystemType.PORTAL
    SYSTEM_NAME = "通用 Web Portal"

    # 常见的用户名字段名
    USERNAME_FIELDS = ("username", "user", "userId", "userid", "DDDDD", "account", "user_account")
    # 常见的密码字段名
    PASSWORD_FIELDS = ("password", "passwd", "pass", "upass", "pwd", "user_password")
    # 登录相关关键字（用于判断页面是否为登录页）
    LOGIN_KEYWORDS = ("登录", "login", "sign in", "认证", "authenticate", "登陆")

    def __init__(self, config: AuthConfig) -> None:
        super().__init__(config)

        # 允许通过 config.extra 覆盖默认行为
        self._username_field: str = config.extra.get("username_field", "")
        self._password_field: str = config.extra.get("password_field", "")
        self._login_url_override: str = config.extra.get("login_url", config.login_url)

    # ------------------------------------------------------------------
    # 表单自动检测
    # ------------------------------------------------------------------

    def _detect_redirect_url(self) -> Optional[str]:
        """
        访问外网探测 URL，获取 302 重定向目标（即认证页面地址）。
        """
        log.info("[认证:Portal] 探测重定向地址...")
        try:
            r = self._session.get(
                self.config.probe_url, timeout=8, allow_redirects=False,
            )
            self._log_resp("探测重定向", r)

            if r.status_code in (301, 302, 303, 307, 308):
                location = r.headers.get("Location", "")
                if location:
                    log.info("[认证:Portal] 检测到重定向: %s", location[:150])
                    return location
            # 没有重定向，可能已经认证或需要手动指定 URL
            log.info("[认证:Portal] 无重定向，网络可能已通")
            return None
        except requests.RequestException as e:
            log.error("[认证:Portal] 探测请求失败: %s", e)
            return None

    def _parse_form(self, html: str, base_url: str) -> Tuple[str, Dict[str, str], str, str]:
        """
        从 HTML 中提取第一个 <form> 的信息。
        返回: (action_url, hidden_fields, detected_username_field, detected_password_field)
        """
        # 提取 <form> 块
        form_match = re.search(
            r'<form[^>]*>(.*?)</form>',
            html, re.DOTALL | re.IGNORECASE,
        )
        if not form_match:
            log.warning("[认证:Portal] 未找到 <form> 标签，尝试匹配不带闭合标签的 form...")
            # 某些页面 form 没有正确闭合
            form_match = re.search(r'<form[^>]*>(.*)', html, re.DOTALL | re.IGNORECASE)

        form_html = form_match.group(1) if form_match else html

        # 提取 action URL
        action_match = re.search(
            r'<form[^>]*\saction=["\']([^"\']*)["\']',
            html, re.IGNORECASE,
        )
        action = action_match.group(1) if action_match else ""
        if action:
            action = urljoin(base_url, action)
        else:
            action = base_url

        # 提取所有 hidden input
        hidden_fields: Dict[str, str] = {}
        for m in re.finditer(
            r'<input[^>]*\stype=["\']hidden["\'][^>]*>',
            form_html, re.IGNORECASE,
        ):
            tag = m.group(0)
            name_m = re.search(r'name=["\']([^"\']+)["\']', tag, re.IGNORECASE)
            value_m = re.search(r'value=["\']([^"\']*)["\']', tag, re.IGNORECASE)
            if name_m:
                name = name_m.group(1)
                value = value_m.group(1) if value_m else ""
                hidden_fields[name] = value
                log.info("[认证:Portal] hidden field: %s = %s", name, value[:50])

        # 提取所有 input 用于字段检测
        all_inputs: List[str] = re.findall(
            r'<input[^>]*>',
            form_html, re.IGNORECASE,
        )

        # 检测用户名字段
        detected_user = self._username_field
        detected_pass = self._password_field

        if not detected_user:
            for inp in all_inputs:
                name_m = re.search(r'name=["\']([^"\']+)["\']', inp, re.IGNORECASE)
                if name_m:
                    name = name_m.group(1)
                    for candidate in self.USERNAME_FIELDS:
                        if candidate.lower() == name.lower():
                            detected_user = name
                            break
                    if detected_user:
                        break
            if not detected_user:
                detected_user = "username"

        if not detected_pass:
            for inp in all_inputs:
                type_m = re.search(r'type=["\']password["\']', inp, re.IGNORECASE)
                if type_m:
                    name_m = re.search(r'name=["\']([^"\']+)["\']', inp, re.IGNORECASE)
                    if name_m:
                        detected_pass = name_m.group(1)
                    break
            if not detected_pass:
                for inp in all_inputs:
                    name_m = re.search(r'name=["\']([^"\']+)["\']', inp, re.IGNORECASE)
                    if name_m:
                        name = name_m.group(1)
                        for candidate in self.PASSWORD_FIELDS:
                            if candidate.lower() == name.lower():
                                detected_pass = name
                                break
                    if detected_pass:
                        break
            if not detected_pass:
                detected_pass = "password"

        log.info("[认证:Portal] 表单分析: action=%s user_field=%s pass_field=%s hidden_count=%d",
                 action[:120], detected_user, detected_pass, len(hidden_fields))

        return action, hidden_fields, detected_user, detected_pass

    # ------------------------------------------------------------------
    # 核心接口实现
    # ------------------------------------------------------------------

    def login(self, username: str, password: str) -> bool:
        """
        通用 Portal 登录。
        自动检测认证页面 → 提取表单 → 提交登录。
        """
        log.info("=" * 60)
        log.info("[认证:Portal:登录] ========== 开始登录流程 ==========")
        log.info("[认证:Portal:登录] 账号: %s", username)

        # 先检查是否已在线
        if self.is_authenticated():
            log.info("[认证:Portal:登录] 网络已通，无需重复登录")
            self._logged_in = True
            log.info("=" * 60)
            return True

        # Step 1: 获取认证页面
        login_page_url = self._login_url_override
        if not login_page_url:
            login_page_url = self._detect_redirect_url()

        if not login_page_url:
            log.error("[认证:Portal:登录] 无法获取认证页面地址（无重定向且未指定 login_url）")
            log.info("=" * 60)
            return False

        log.info("[认证:Portal:登录] 访问认证页面: %s", login_page_url[:150])
        try:
            r = self._session.get(login_page_url, timeout=15, allow_redirects=True)
            self._log_resp("认证页面", r)
        except requests.RequestException as e:
            log.error("[认证:Portal:登录] 访问认证页面失败: %s", e)
            log.info("=" * 60)
            return False

        # Step 2: 解析表单
        log.info("[认证:Portal:登录] 解析表单...")
        action_url, hidden_fields, user_field, pass_field = self._parse_form(
            r.text, r.url,
        )

        # Step 3: 构造并提交表单
        form_data: Dict[str, str] = dict(hidden_fields)
        form_data[user_field] = username
        form_data[pass_field] = password

        log.info("[认证:Portal:登录] 提交表单到: %s", action_url[:150])
        log.info("[认证:Portal:登录] 表单字段: %s=%s %s=*** hidden=%d",
                 user_field, username, pass_field, len(hidden_fields))

        try:
            r2 = self._session.post(
                action_url, data=form_data, timeout=15, allow_redirects=True,
            )
            self._log_resp("Portal提交", r2)
            log.info("[认证:Portal:登录] 提交后URL: %s", r2.url[:150])
        except requests.RequestException as e:
            log.error("[认证:Portal:登录] 提交表单失败: %s", e)
            log.info("=" * 60)
            return False

        # Step 4: 判断结果
        log.info("[认证:Portal:登录] 判断登录结果...")

        # 方法 A: 检查是否仍然在登录页面
        text_lower = r2.text.lower()
        still_login_page = any(kw in text_lower for kw in self.LOGIN_KEYWORDS)
        # 排除页面中只是一般性提及 "login" 而不是表单的情况
        has_form = "<form" in text_lower
        has_password_field = 'type="password"' in text_lower or "type='password'" in text_lower

        if still_login_page and has_form and has_password_field:
            # 检查是否有错误提示
            err_match = re.search(
                r'class=["\'][^"\']*error[^"\']*["\'][^>]*>([^<]+)<',
                r2.text, re.IGNORECASE,
            )
            if not err_match:
                err_match = re.search(
                    r'(?:错误|失败|error|fail)[^<]{0,50}',
                    r2.text, re.IGNORECASE,
                )
            err_msg = err_match.group(0).strip() if err_match else "(无明确错误)"
            log.warning("[认证:Portal:登录] 仍在登录页面，可能失败: %s", err_msg)

        # 方法 B: 通过外网探测判断
        ok = self.is_authenticated()
        if ok:
            log.info("[认证:Portal:登录] 登录成功（网络可达）")
        else:
            log.warning("[认证:Portal:登录] 登录后网络仍不可达")

        self._logged_in = ok
        log.info("[认证:Portal:登录] 登录流程完成: %s", "成功" if ok else "失败")
        log.info("=" * 60)
        return ok

    def is_authenticated(self) -> bool:
        """
        检查当前是否已认证。
        访问外网看是否被重定向到认证页面。
        """
        log.info("[认证:Portal] 检测认证状态...")
        try:
            r = self._session.get(
                self.config.probe_url, timeout=8, allow_redirects=False,
            )
            self._log_resp("探测", r)

            # 如果被重定向，说明未认证
            if r.status_code in (301, 302, 303, 307, 308):
                location = r.headers.get("Location", "")
                log.info("[认证:Portal] 被重定向: %s", location[:120])
                # 如果重定向到非 HTTPS 外部站点，可能就是认证页面
                if location and not location.startswith("https://"):
                    log.info("[认证:Portal] 未认证（被重定向）")
                    return False
                # 某些 Portal 重定向到 HTTPS 认证页面
                if location and self.config.probe_url.split("/")[2] not in location:
                    log.info("[认证:Portal] 未认证（重定向到认证页面）")
                    return False

            # 正常返回且包含关键字
            ok = self.config.success_keyword in r.text
            log.info("[认证:Portal] 认证状态: %s", "已认证" if ok else "未认证")
            if ok:
                self._logged_in = True
            return ok
        except requests.RequestException as e:
            log.warning("[认证:Portal] 探测请求失败: %s", e)
            return False

    def logout(self) -> bool:
        """
        通用 Portal 登出。
        尝试访问常见登出 URL，然后清除 session。
        """
        log.info("[认证:Portal:登出] ========== 开始登出流程 ==========")

        # 尝试常见登出路径
        logout_paths = self.config.extra.get("logout_paths", "/logout,/logoff,/signout").split(",")
        logout_url_override = self.config.logout_url if hasattr(self.config, 'logout_url') else self.config.extra.get("logout_url", "")

        urls_to_try: List[str] = []
        if logout_url_override:
            urls_to_try.append(logout_url_override)

        gateway = self.config.gateway_base or self.config.extra.get("gateway_base", "")
        if gateway:
            for path in logout_paths:
                urls_to_try.append(f"{gateway}{path.strip()}")

        for url in urls_to_try:
            log.info("[认证:Portal:登出] 尝试: %s", url[:120])
            try:
                r = self._session.get(url, timeout=10, allow_redirects=True)
                self._log_resp("Portal登出", r)
                log.info("[认证:Portal:登出] 响应: %s", r.text[:200])
            except requests.RequestException as e:
                log.debug("[认证:Portal:登出] 请求失败: %s", e)

        # 清除 session
        self._session.cookies.clear()
        self._logged_in = False
        log.info("[认证:Portal:登出] Session 已清除，登出完成")
        return True

