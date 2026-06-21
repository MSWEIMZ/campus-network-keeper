"""
校园网认证模块
支持多种认证系统：Dr.COM、锐捷、深澜、通用 Portal、CAS SSO
"""
from auth.base import BaseAuth
from auth.detector import detect_auth_system, AuthSystemType

__all__ = ["BaseAuth", "detect_auth_system", "AuthSystemType"]
