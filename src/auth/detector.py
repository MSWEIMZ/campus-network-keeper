"""
认证系统自动探测器
访问外网 → 被重定向到认证页 → 根据 URL/页面特征识别认证系统类型。
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

import requests

from auth.base import AuthSystemType, AuthConfig
from logger import log


# 探测 URL 列表（按优先级）
PROBE_URLS = [
    "http://www.msftconnecttest.com/connecttest.txt",
    "http://connect.rom.miui.com/generate_204",
    "http://www.gstatic.com/generate_204",
    "http://baidu.com",
]


def detect_auth_system(session: Optional[requests.Session] = None) -> Tuple[AuthSystemType, str, str]:
    """
    自动探测校园网认证系统类型。

    返回: (system_type, redirect_url, page_content_snippet)
    """
    if session is None:
        session = requests.Session()
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        })

    log.info("[探测] ========== 开始认证系统探测 ==========")

    redirect_url = ""
    page_content = ""

    # Step 1: 访问探测 URL，看是否被重定向
    for probe_url in PROBE_URLS:
        log.info("[探测] 访问: %s", probe_url)
        try:
            resp = session.get(probe_url, timeout=8, allow_redirects=True)
            final_url = resp.url
            log.info("[探测]   最终 URL: %s", final_url[:120])
            log.info("[探测]   状态码: %d, 内容长度: %d", resp.status_code, len(resp.text))

            # 如果没有被重定向到认证页，说明已在线
            if _is_normal_response(resp, probe_url):
                log.info("[探测] ✅ 网络正常，无需认证（已在线）")
                return AuthSystemType.UNKNOWN, "", ""

            # 被重定向到了认证页
            redirect_url = final_url
            page_content = resp.text[:5000]
            log.info("[探测] 检测到认证重定向: %s", redirect_url[:120])
            break

        except requests.RequestException as e:
            log.info("[探测]   请求失败: %s", e)
            continue

    if not redirect_url:
        log.warning("[探测] 所有探测 URL 均无法访问（可能物理断网）")
        return AuthSystemType.UNKNOWN, "", ""

    # Step 2: 根据 URL 和页面内容识别认证系统
    system_type = _identify_system(redirect_url, page_content)
    log.info("[探测] 识别结果: %s", system_type.value)
    log.info("[探测] ========== 探测结束 ==========")

    return system_type, redirect_url, page_content[:1000]


def _is_normal_response(resp: requests.Response, probe_url: str) -> bool:
    """判断响应是否为正常网络响应（非认证重定向）"""
    # msftconnecttest 正常返回 "Microsoft Connect Test"
    if "connecttest" in probe_url and "Microsoft Connect Test" in resp.text:
        return True
    # generate_204 正常返回 204 或空 body
    if "generate_204" in probe_url and resp.status_code in (204, 200) and len(resp.text) < 100:
        return True
    # 如果最终 URL 和探测 URL 相同，说明没被重定向
    if resp.url == probe_url or resp.url.rstrip("/") == probe_url.rstrip("/"):
        return True
    return False


def _identify_system(url: str, content: str) -> AuthSystemType:
    """根据 URL 和页面内容识别认证系统类型"""
    url_lower = url.lower()
    content_lower = content.lower()

    # Dr.COM（城市热点）
    # 特征: URL 含 dr.com、Self/sso_login、或网关 IP:8080
    if any(kw in url_lower for kw in ["dr.com", "self/sso_login", "self/login"]):
        log.info("[探测] URL 匹配: Dr.COM")
        return AuthSystemType.DRCOM

    # CAS SSO（通常和 Dr.COM 配合使用）
    # 特征: URL 含 cas/login
    if "cas/login" in url_lower:
        log.info("[探测] URL 匹配: CAS SSO (归类为 Dr.COM)")
        return AuthSystemType.DRCOM

    # 锐捷 ePortal
    # 特征: URL 含 eportal、portal
    if any(kw in url_lower for kw in ["eportal", "portal/login", "portal/index"]):
        log.info("[探测] URL 匹配: 锐捷 ePortal")
        return AuthSystemType.RUIJIE

    # 深澜 Srun
    # 特征: URL 含 srun，或页面含"深澜"、"srun"
    if "srun" in url_lower:
        log.info("[探测] URL 匹配: 深澜 Srun")
        return AuthSystemType.SRUN
    if any(kw in content_lower for kw in ["深澜", "srun", "srunportal"]):
        log.info("[探测] 内容匹配: 深澜 Srun")
        return AuthSystemType.SRUN

    # 通用 Web Portal
    # 特征: 页面有 <form> + password input
    if re.search(r'<form[^>]*>.*?<input[^>]*type=["\']password', content, re.DOTALL | re.IGNORECASE):
        log.info("[探测] 内容匹配: 通用 Web Portal（有表单+密码框）")
        return AuthSystemType.PORTAL

    # 有 form 但没检测到密码框，也可能是 portal
    if "<form" in content_lower and ("password" in content_lower or "passwd" in content_lower):
        log.info("[探测] 内容匹配: 通用 Web Portal（有 form + password 关键字）")
        return AuthSystemType.PORTAL

    log.warning("[探测] 无法识别认证系统 (URL: %s)", url[:80])
    return AuthSystemType.UNKNOWN


def create_auth_instance(system_type: AuthSystemType, config: AuthConfig):
    """
    根据认证系统类型创建对应的认证实例。
    """
    if system_type == AuthSystemType.DRCOM:
        from auth.drcom import DrComAuth
        return DrComAuth(config)
    elif system_type == AuthSystemType.RUIJIE:
        from auth.ruijie import RuijieAuth
        return RuijieAuth(config)
    elif system_type == AuthSystemType.SRUN:
        from auth.srun import SrunAuth
        return SrunAuth(config)
    elif system_type == AuthSystemType.PORTAL:
        from auth.portal import PortalAuth
        return PortalAuth(config)
    else:
        log.error("[探测] 不支持的认证系统类型: %s", system_type)
        return None

