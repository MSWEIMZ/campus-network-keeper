"""
校园网保活工具 - 首次配置向导
引导用户完成：输入账号 → 自动探测认证系统 → 测试登录 → 保存配置
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from config import CONFIG, PROJECT_ROOT, LOG_DIR
from logger import log

# 向导专用日志文件
WIZARD_LOG = LOG_DIR / "wizard.log"


def _print_banner() -> None:
    print()
    print("=" * 55)
    print("  🌐 校园网保活工具 — 首次配置向导")
    print("=" * 55)
    print()


def _print_step(step: int, total: int, desc: str) -> None:
    print(f"\n--- 步骤 {step}/{total}: {desc} ---\n")
    log.info("[向导] 步骤%d/%d: %s", step, total, desc)


def run_wizard() -> bool:
    """
    运行首次配置向导。
    返回 True 表示配置成功。
    """
    _print_banner()
    log.info("[向导] ========== 开始首次配置 ==========")

    # ============================================================
    # 步骤 1: 输入账号密码
    # ============================================================
    _print_step(1, 3, "输入账号密码")

    username = CONFIG.auth_username
    password = CONFIG.auth_password

    if username:
        print(f"  检测到已有账号: {username[:3]}***")
        choice = input("  是否使用已有账号？(Y/n): ").strip().lower()
        if choice == "n":
            username = ""
            password = ""

    if not username:
        username = input("  请输入校园网账号（学号）: ").strip()
        if not username:
            print("  ❌ 账号不能为空")
            return False

    if not password:
        import getpass
        password = getpass.getpass("  请输入校园网密码: ").strip()
        if not password:
            print("  ❌ 密码不能为空")
            return False

    CONFIG.auth_username = username
    CONFIG.auth_password = password
    log.info("[向导] 账号: %s", username)

    # ============================================================
    # 步骤 2: 自动探测认证系统
    # ============================================================
    _print_step(2, 3, "自动探测认证系统")
    print("  正在探测校园网认证系统...")
    print()

    from auth.detector import detect_auth_system, AuthSystemType
    from auth.base import AuthConfig

    system_type, redirect_url, page_snippet = detect_auth_system()

    if system_type == AuthSystemType.UNKNOWN:
        if redirect_url:
            print(f"  ⚠️ 检测到认证页，但无法识别系统类型")
            print(f"  认证页 URL: {redirect_url[:80]}")
            print()
            print("  请选择认证系统类型:")
            print("    1. Dr.COM（城市热点）— 大连理工、东北大学等")
            print("    2. 锐捷 ePortal — 华中科技、西安电子等")
            print("    3. 深澜 Srun — 清华、北大、浙大等")
            print("    4. 通用 Web Portal — 其他")
            choice = input("  请选择 (1-4): ").strip()
            type_map = {"1": AuthSystemType.DRCOM, "2": AuthSystemType.RUIJIE,
                        "3": AuthSystemType.SRUN, "4": AuthSystemType.PORTAL}
            system_type = type_map.get(choice, AuthSystemType.PORTAL)
        else:
            print("  ❌ 无法访问认证页（可能物理断网）")
            print("  请检查网线/Wi-Fi 是否已连接")
            log.error("[向导] 无法访问认证页")
            return False

    system_names = {
        AuthSystemType.DRCOM: "Dr.COM + CAS SSO",
        AuthSystemType.RUIJIE: "锐捷 ePortal",
        AuthSystemType.SRUN: "深澜 Srun",
        AuthSystemType.PORTAL: "通用 Web Portal",
    }
    print(f"  识别结果: {system_names.get(system_type, '未知')}")
    print(f"  认证页: {redirect_url[:80] if redirect_url else '(自动检测)'}")
    log.info("[向导] 识别结果: %s", system_type.value)

    # 测试登录
    print()
    print("  正在测试登录...")
    log.info("[向导] 开始测试登录")

    auth_config = AuthConfig(
        method=system_type.value,
        username=username,
        password=password,
        probe_url=CONFIG.auth_probe_url,
        success_keyword=CONFIG.auth_success_keyword,
    )

    from auth.detector import create_auth_instance
    auth = create_auth_instance(system_type, auth_config)
    if auth is None:
        print("  ❌ 无法创建认证实例")
        return False

    try:
        ok = auth.login(username, password)
    except Exception as e:
        log.error("[向导] 登录测试异常: %s", e, exc_info=True)
        print(f"  ❌ 登录测试异常: {e}")
        ok = False

    if ok:
        print("  ✅ 登录测试成功!")
        log.info("[向导] 登录测试成功")
    else:
        print("  ❌ 登录测试失败")
        print("  请检查账号密码是否正确")
        print(f"  详细日志: {WIZARD_LOG}")
        log.error("[向导] 登录测试失败")
        # 不直接返回失败，让用户选择是否继续
        choice = input("  是否仍要保存配置？(y/N): ").strip().lower()
        if choice != "y":
            return False

    # ============================================================
    # 步骤 3: 保存配置
    # ============================================================
    _print_step(3, 3, "保存配置")

    # 从探测结果填充配置
    CONFIG.auth_method = system_type.value
    if redirect_url:
        # 提取网关地址
        import re
        gw_match = re.search(r'(https?://[\d.]+(?::\d+)?)', redirect_url)
        if gw_match:
            CONFIG.auth_gateway = gw_match.group(1)

    # Wi-Fi 配置
    wifi_input = input("  备用 Wi-Fi SSID（多个用逗号分隔，留空跳过）: ").strip()
    if wifi_input:
        CONFIG.wifi_ssids = [s.strip() for s in wifi_input.split(",") if s.strip()]

    # 开机自启
    autostart = input("  是否安装开机自启？(Y/n): ").strip().lower()
    if autostart != "n":
        try:
            import ctypes
            if ctypes.windll.shell32.IsUserAnAdmin() != 0:
                from main import install_autostart
                install_autostart()
                print("  ✅ 开机自启已安装")
            else:
                print("  ⚠️ 需要管理员权限才能安装开机自启")
                print("  请以管理员身份运行: python main.py --install")
        except Exception as e:
            print(f"  ⚠️ 安装开机自启失败: {e}")

    # 保存配置
    CONFIG.save()
    print()
    print(f"  ✅ 配置已保存到: {CONFIG.auth_method}")
    print(f"     账号: {username[:3]}***")
    print(f"     认证: {system_names.get(system_type, '未知')}")
    if CONFIG.wifi_ssids:
        print(f"     Wi-Fi: {', '.join(CONFIG.wifi_ssids)}")
    log.info("[向导] 配置已保存")

    print()
    print("=" * 55)
    print("  🎉 配置完成!")
    print()
    print("  启动托盘模式: python main.py --tray")
    print("  查看日志:     logs/campus_keeper.log")
    print("=" * 55)
    print()

    log.info("[向导] ========== 配置完成 ==========")
    return True
