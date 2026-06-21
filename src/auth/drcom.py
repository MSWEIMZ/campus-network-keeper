"""
Dr.COM + CAS SSO 认证模板
适用于城市热点 Dr.COM 认证系统 + CAS 单点登录（如 DLUT）。

认证流程:
1. 访问 HTTP 外网 → 被网关劫持到 gateway_base/Self/sso_login
2. sso_login 重定向到 CAS (sso_url/cas/login)
3. CAS 登录表单: rsa/ul/pl/sl（非 username/password），rsa 使用 DES 加密
4. 提交 → 获取 CASTGC → CAS 回调到 Dr.COM → 网络放行
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, Optional

import requests

from auth.base import AuthConfig, AuthSystemType, BaseAuth
from logger import log


class DrComAuth(BaseAuth):
    """Dr.COM + CAS SSO 认证器"""

    SYSTEM_TYPE = AuthSystemType.DRCOM
    SYSTEM_NAME = "Dr.COM + CAS SSO"

    def __init__(self, config: AuthConfig) -> None:
        super().__init__(config)

        # 从 config 读取网关地址（兼容旧字段 gateway_base 和 extra 配置）
        self._gateway_base: str = (
            config.gateway_base
            or config.extra.get("gateway_base", "http://172.20.30.2:8080")
        )
        self._cas_base: str = config.extra.get("cas_base", "https://sso.dlut.edu.cn")
        self._cas_login_path: str = config.extra.get("cas_login_path", "/cas/login")
        self._self_sso_login: str = config.extra.get("self_sso_login", "/Self/sso_login")
        self._wlan_ac_ip: str = config.extra.get("wlan_ac_ip", "172.20.30.254")

        self._session_established: bool = False

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _des_encrypt(username: str, password: str, lt: str) -> str:
        """
        DES 加密: strEnc(username + password + lt, '1', '2', '3')
        使用纯 Python des_crypto 模块
        """
        try:
            from des_crypto import str_enc
            data = username + password + lt
            result = str_enc(data, "1", "2", "3")
            return result
        except ImportError:
            log.error("[认证:DrCOM:DES] des_crypto 模块未找到")
        except Exception as e:
            log.error("[认证:DrCOM:DES] 加密异常: %s", e)
        return ""

    def _build_cas_service_url(self, local_ip: str) -> str:
        """构造 CAS service 回调 URL"""
        return (
            f"{self._gateway_base}{self._self_sso_login}"
            f"?type=1"
            f"&wlan_user_ip={local_ip}"
            f"&wlan_user_ipv6="
            f"&wlan_ac_ip={self._wlan_ac_ip}"
        )

    def _do_cas_login(self, username: str, password: str) -> bool:
        """
        执行 CAS 登录流程（建立 session）。
        DLUT CAS 登录表单字段:
          - rsa: strEnc(username + password + lt, '1', '2', '3')
          - ul: 用户名长度
          - pl: 密码长度
          - sl: 0 (密码登录) / 1 (手机登录)
          - lt: 隐藏字段
          - execution: 隐藏字段
          - _eventId: submit
        """
        local_ip = self._get_local_ip(
            target=self._gateway_base.split("//")[1].split(":")[0]
        )
        log.info("[认证:DrCOM:登录] 本机 IP = %s", local_ip or "(空!)")
        if not local_ip:
            log.error("[认证:DrCOM:登录] 无法获取本机 IP，网卡可能未连接")
            return False

        # Step 1: 访问 CAS 登录页
        service_url = self._build_cas_service_url(local_ip)
        cas_url = (
            f"{self._cas_base}{self._cas_login_path}"
            f"?service={requests.utils.quote(service_url, safe='')}"
        )
        log.info("[认证:DrCOM:登录] 访问 CAS 登录页...")
        log.info("[认证:DrCOM:登录]   service = %s", service_url)

        try:
            r = self._session.get(cas_url, timeout=15, allow_redirects=True)
            self._log_resp("CAS登录页", r)
            log.info("[认证:DrCOM:登录]   Cookie数量: %d", len(self._session.cookies))
        except requests.RequestException as e:
            log.error("[认证:DrCOM:登录] 访问 CAS 登录页失败: %s", e)
            return False

        # Step 2: 提取隐藏参数
        log.info("[认证:DrCOM:登录] 提取 lt + execution 参数...")
        lt_match = re.search(r'name="lt"\s+value="([^"]+)"', r.text)
        exec_match = re.search(r'name="execution"\s+value="([^"]+)"', r.text)

        lt = lt_match.group(1) if lt_match else ""
        execution = exec_match.group(1) if exec_match else ""

        log.info("[认证:DrCOM:登录]   lt = %s", (lt[:50] + "...") if len(lt) > 50 else lt or "(空!)")
        log.info("[认证:DrCOM:登录]   execution = %s", execution or "(空!)")

        if not lt or not execution:
            log.error("[认证:DrCOM:登录] 未找到 lt/execution 参数")
            return False

        # Step 3: DES 加密 → rsa 字段
        log.info("[认证:DrCOM:登录] DES 加密 (strEnc(user+pass+lt, '1','2','3'))...")
        rsa_val = self._des_encrypt(username, password, lt)
        if not rsa_val:
            log.error("[认证:DrCOM:登录] DES 加密失败")
            return False
        log.info("[认证:DrCOM:登录]   rsa 加密结果长度: %d chars", len(rsa_val))

        # Step 4: 提交表单 (关键: rsa/ul/pl/sl, 不是 username/password!)
        log.info("[认证:DrCOM:登录] 提交 CAS 登录表单...")
        post_url = f"{self._cas_base}{self._cas_login_path}"
        form_data = {
            "rsa": rsa_val,
            "ul": str(len(username)),
            "pl": str(len(password)),
            "sl": "0",
            "lt": lt,
            "execution": execution,
            "_eventId": "submit",
        }
        log.info("[认证:DrCOM:登录]   表单字段: rsa(len=%d) ul=%s pl=%s sl=%s",
                 len(rsa_val), len(username), len(password), "0")

        try:
            r2 = self._session.post(post_url, data=form_data, timeout=15, allow_redirects=True)
            self._log_resp("CAS提交", r2)
            log.info("[认证:DrCOM:登录]   提交后URL: %s", r2.url[:150])
        except requests.RequestException as e:
            log.error("[认证:DrCOM:登录] CAS 提交失败: %s", e)
            return False

        # Step 5: 检查结果
        log.info("[认证:DrCOM:登录] 检查登录结果...")
        castgc = None
        for ck in self._session.cookies:
            if ck.name == "CASTGC":
                castgc = ck.value
                break
        log.info("[认证:DrCOM:登录]   CASTGC cookie: %s",
                 ("有 (len=%d)" % len(castgc)) if castgc else "无!")

        # 如果还在 CAS 登录页，说明登录失败
        if "cas/login" in r2.url.lower():
            err_match = re.search(r'id="errormsg"[^>]*>([^<]+)<', r2.text)
            err_msg = err_match.group(1).strip() if err_match else "(未找到错误提示)"
            log.error("[认证:DrCOM:登录] 登录失败: %s", err_msg)
            return False

        self._session_established = True
        log.info("[认证:DrCOM:登录] CAS session 已建立")
        return True

    def _check_dashboard_session(self) -> bool:
        """检查 dashboard session 是否可用"""
        try:
            r = self._session.get(
                f"{self._gateway_base}/Self/dashboard",
                timeout=10, allow_redirects=True,
            )
            self._log_resp("dashboard检查", r)
            if r.status_code == 200 and "/login" not in r.url:
                log.info("[认证:DrCOM] Dashboard session 有效")
                return True
            log.info("[认证:DrCOM] Dashboard session 无效 (url=%s)", r.url[:80])
            return False
        except Exception as e:
            log.debug("[认证:DrCOM] Dashboard 检查失败: %s", e)
            return False

    # ------------------------------------------------------------------
    # 核心接口实现
    # ------------------------------------------------------------------

    def login(self, username: str, password: str) -> bool:
        """
        登录入口。
        - 如果 dashboard session 已有效，直接返回
        - 否则执行 CAS 登录建立 session
        - 最后验证网络是否恢复
        """
        log.info("=" * 60)
        log.info("[认证:DrCOM:登录] ========== 开始登录流程 ==========")
        log.info("[认证:DrCOM:登录] 账号: %s", username)

        # Step 0: 检查网络和 dashboard session
        already_online = self.is_authenticated()
        log.info("[认证:DrCOM:登录] 网络状态: %s", "已通" if already_online else "未通")

        if self._session_established and self._check_dashboard_session():
            log.info("[认证:DrCOM:登录] Dashboard session 已存在且有效，跳过")
            self._logged_in = True
            log.info("=" * 60)
            return True

        # Step 1: 执行 CAS 登录
        log.info("[认证:DrCOM:登录] 执行 CAS 登录建立 session...")
        cas_ok = self._do_cas_login(username, password)

        if not cas_ok:
            if already_online:
                log.warning("[认证:DrCOM:登录] CAS 登录失败，但网络仍可用")
                self._logged_in = True
                log.info("=" * 60)
                return True
            else:
                log.error("[认证:DrCOM:登录] CAS 登录失败且网络不通")
                log.info("=" * 60)
                return False

        # Step 2: 验证网络
        if not already_online:
            log.info("[认证:DrCOM:登录] 等待网络恢复...")
            time.sleep(2)
            ok = self.is_authenticated()
            if ok:
                log.info("[认证:DrCOM:登录] 网络已恢复!")
            else:
                log.warning("[认证:DrCOM:登录] CAS 登录成功但网络未恢复")
        else:
            ok = True

        # Step 3: 验证 dashboard
        log.info("[认证:DrCOM:登录] 验证 dashboard session...")
        dash_ok = self._check_dashboard_session()
        if dash_ok:
            log.info("[认证:DrCOM:登录] Dashboard session 建立成功")
        else:
            log.warning("[认证:DrCOM:登录] Dashboard session 仍不可用")

        self._logged_in = ok
        log.info("[认证:DrCOM:登录] 登录流程完成: %s", "成功" if ok else "失败")
        log.info("=" * 60)
        return ok

    def is_authenticated(self) -> bool:
        """检查当前是否已认证（访问外网探测）"""
        log.info("[认证:DrCOM] 检测认证状态...")
        try:
            r = self._session.get(
                self.config.probe_url, timeout=8, allow_redirects=True,
            )
            self._log_resp("探测", r)
            ok = self.config.success_keyword in r.text
            log.info("[认证:DrCOM] 认证状态: %s", "已认证" if ok else "未认证")
            if ok:
                self._logged_in = True
            return ok
        except requests.RequestException as e:
            log.warning("[认证:DrCOM] 探测请求失败: %s", e)
            return False

    def logout(self) -> bool:
        """登出当前账号（通过 dashboard 获取在线设备并逐一下线）"""
        log.info("[认证:DrCOM:登出] ========== 开始登出流程 ==========")

        # 确保 session 已建立
        if not self._session_established:
            log.info("[认证:DrCOM:登出] Session 未建立，先建立...")
            if self.config.username and self.config.password:
                self._do_cas_login(self.config.username, self.config.password)

        log.info("[认证:DrCOM:登出] Step1: 获取在线设备列表...")
        try:
            r = self._session.get(
                f"{self._gateway_base}/Self/dashboard/getOnlineList",
                timeout=10,
            )
            self._log_resp("getOnlineList", r)
            log.info("[认证:DrCOM:登出]   响应: %s", r.text[:200])
        except requests.RequestException as e:
            log.error("[认证:DrCOM:登出] 获取在线列表失败: %s", e)
            return False

        try:
            data = r.json()
            log.info("[认证:DrCOM:登出]   在线设备数: %d",
                     len(data) if isinstance(data, list) else -1)
            if isinstance(data, list):
                for idx, d in enumerate(data):
                    uid = d.get("userId", d.get("uid", ""))
                    user_ip = d.get("userIp", d.get("ip", ""))
                    user_mac = d.get("userMac", d.get("mac", ""))
                    log.info("[认证:DrCOM:登出]   设备%d: userId=%s ip=%s mac=%s",
                             idx, uid, user_ip, user_mac)

                    offline_url = (
                        f"{self._gateway_base}{self._self_sso_login}"
                        f"?wlan_user_ip={user_ip}&wlan_user_mac={user_mac}"
                        f"&type=2"
                    )
                    log.info("[认证:DrCOM:登出] Step2: 下线: %s", offline_url[:120])
                    try:
                        r2 = self._session.get(offline_url, timeout=10)
                        self._log_resp("tooffline", r2)
                        log.info("[认证:DrCOM:登出]   下线响应: %s", r2.text[:100])
                    except requests.RequestException as e:
                        log.error("[认证:DrCOM:登出]   下线请求失败: %s", e)

            self._logged_in = False
            self._session_established = False
            log.info("[认证:DrCOM:登出] 登出完成")
            return True
        except Exception as e:
            log.error("[认证:DrCOM:登出] 解析在线列表失败: %s", e)
            return False

    # ------------------------------------------------------------------
    # 流量查询（Dr.COM Dashboard 特有）
    # ------------------------------------------------------------------

    def get_traffic_info(self) -> dict:
        """获取用户流量信息（Dr.COM Dashboard 页面解析）"""
        info: Dict[str, Any] = {}
        log.info("[认证:DrCOM:流量] 查询流量信息...")

        if not self._session_established:
            log.info("[认证:DrCOM:流量] Session 未建立，先建立...")
            if self.config.username and self.config.password:
                self._do_cas_login(self.config.username, self.config.password)

        try:
            r = self._session.get(
                f"{self._gateway_base}/Self/dashboard",
                timeout=10, allow_redirects=True,
            )
            self._log_resp("dashboard", r)

            if r.status_code != 200 or "/login" in r.url:
                log.info("[认证:DrCOM:流量] dashboard 不可用")
                return info

            # 提取 JSON (Dr.COM IIFE 格式)
            m = re.search(r'\}\)\s*\(\s*(\{)', r.text)
            if m:
                brace_start = m.start(1)
                depth = 0
                end = -1
                for ci in range(brace_start, min(brace_start + 20000, len(r.text))):
                    ch = r.text[ci]
                    if ch == '{':
                        depth += 1
                    elif ch == '}':
                        depth -= 1
                        if depth == 0:
                            end = ci + 1
                            break
                if end > 0:
                    try:
                        data = json.loads(r.text[brace_start:end])
                        if isinstance(data, dict) and ("userName" in data or "useFlow" in data):
                            info = data
                            log.info("[认证:DrCOM:流量] 提取到 JSON: keys=%s",
                                     list(data.keys())[:10])
                    except json.JSONDecodeError:
                        pass

            # 从 <dt> 标签解析
            dt_blocks = re.findall(
                r'<dt>\s*(\d[\d,.]*)\s*<small[^>]*>([^<]*)</small>\s*</dt>\s*<dd>([^<]+)</dd>',
                r.text,
            )
            for val, unit, label in dt_blocks:
                val_f = float(val.replace(',', ''))
                unit = unit.strip().upper()
                if '已用' in label:
                    info['_used_raw'] = val_f
                    info['_used_unit'] = unit
                    if unit == 'M':
                        info['used_str'] = (
                            f"{val_f / 1024:.1f} GB" if val_f >= 1024 else f"{val_f:.0f} MB"
                        )
                    elif unit == 'G':
                        info['used_str'] = f"{val_f:.1f} GB"
                elif '可用' in label:
                    info['_remain_raw'] = val_f
                    info['_remain_unit'] = unit
                    if unit == 'M':
                        info['remain_str'] = (
                            f"{val_f / 1024:.1f} GB" if val_f >= 1024 else f"{val_f:.0f} MB"
                        )
                    elif unit == 'G':
                        info['remain_str'] = f"{val_f:.1f} GB"
                    if '_used_raw' in info:
                        total = info['_used_raw'] + val_f
                        info['total_str'] = (
                            f"{total / 1024:.1f} GB" if total >= 1024 else f"{total:.0f} MB"
                        )
                elif '余额' in label:
                    info['balance_str'] = f"{val_f} 元"

            # getOnlineList
            try:
                r2 = self._session.get(
                    f"{self._gateway_base}/Self/dashboard/getOnlineList",
                    timeout=10,
                )
                if r2.status_code == 200:
                    devices = r2.json()
                    if isinstance(devices, list):
                        total_up = sum(int(d.get("upFlow", 0)) for d in devices)
                        total_down = sum(int(d.get("downFlow", 0)) for d in devices)
                        info["_total_up_kb"] = total_up
                        info["_total_down_kb"] = total_down
                        info["_device_count"] = len(devices)
            except Exception:
                pass

            # 格式化
            if "used_str" not in info and "useFlow" in info:
                val = float(info["useFlow"])
                info["used_str"] = (
                    f"{val / 1024:.1f} GB" if val > 1024 else f"{val:.0f} MB"
                )
            if "useTime" in info:
                t = int(info["useTime"])
                if t >= 86400:
                    info["time_str"] = f"{t // 86400}天{(t % 86400) // 3600}小时"
                elif t >= 3600:
                    info["time_str"] = f"{t // 3600}小时{(t % 3600) // 60}分"
                elif t > 0:
                    info["time_str"] = f"{t // 60}分{t % 60}秒"
            if "baseMoney" in info:
                info["balance_str"] = f"{info.get('baseMoney', 0)}元"

            log.info("[认证:DrCOM:流量] 查询完成: used=%s remain=%s",
                     info.get("used_str", "N/A"), info.get("remain_str", "N/A"))

        except Exception as e:
            log.error("[认证:DrCOM:流量] 查询失败: %s", e, exc_info=True)

        return info
