"""
校园网保活工具 - 入口
用法:
  python main.py                # 启动保活主循环
  python main.py --tray         # 托盘常驻模式
  python main.py --diagnose     # 网络诊断
  python main.py --test-login   # 测试认证登录
  python main.py --test-logout  # 测试登出
  python main.py --smoke-test   # 验证打包运行时依赖
  python main.py --wizard       # 首次配置向导`n  python main.py --install      # 安装开机自启（需管理员）
  python main.py --uninstall    # 卸载开机自启
"""
from __future__ import annotations

import configparser
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import CONFIG, PROJECT_ROOT
from logger import log


def load_account_from_ini() -> tuple[str, str]:
    """从 account.ini 加载账号密码"""
    ini_path = PROJECT_ROOT / "account.ini"
    if not ini_path.exists():
        return "", ""
    try:
        cp = configparser.ConfigParser()
        cp.read(str(ini_path), encoding="utf-8")
        username = cp.get("account", "username", fallback="")
        password = cp.get("account", "password", fallback="")
        return username, password
    except Exception:
        return "", ""


def setup_account() -> tuple[str, str]:
    """按优先级加载账号：环境变量 > account.ini > config"""
    username = os.environ.get("CAMPUS_USER", "")
    password = os.environ.get("CAMPUS_PASS", "")
    if username and password:
        return username, password

    ini_user, ini_pass = load_account_from_ini()
    if ini_user and ini_pass:
        return ini_user, ini_pass

    return CONFIG.auth.username, CONFIG.auth.password


def run_keepalive() -> None:
    from keepalive import KeepAlive
    u, p = setup_account()
    CONFIG.auth.username = u
    CONFIG.auth.password = p
    keeper = KeepAlive()
    keeper.run()


def run_tray() -> None:
    """托盘常驻模式"""
    from tray import run_tray_app
    u, p = setup_account()
    CONFIG.auth.username = u
    CONFIG.auth.password = p
    run_tray_app()


def diagnose() -> None:
    from network_monitor import take_snapshot, log_snapshot
    from campus_auth import CampusAuth
    from nic_reset import find_ethernet_adapter
    from wifi_switcher import list_available_ssids

    log.info("=" * 50)
    log.info("开始网络诊断...")
    log.info("=" * 50)

    adapter = find_ethernet_adapter()
    log.info("以太网适配器: %s", adapter or "(未找到)")

    ssids = list_available_ssids()
    log.info("可扫描到的 Wi-Fi: %s", ssids if ssids else "(无)")

    snap = take_snapshot()
    log_snapshot(snap)

    auth = CampusAuth()
    if auth.is_authenticated():
        log.info("✅ 当前已通过校园网认证")
    else:
        log.warning("⚠️ 当前未通过校园网认证")

    log.info("=" * 50)
    log.info("诊断完成")


def test_login() -> None:
    from campus_auth import CampusAuth
    u, p = setup_account()
    if not u or not p:
        log.error("未配置账号密码！请编辑 account.ini 或设置环境变量 CAMPUS_USER / CAMPUS_PASS")
        return

    auth = CampusAuth()
    log.info("当前认证状态: %s", "已认证" if auth.is_authenticated() else "未认证")
    ok = auth.login(u, p)
    log.info("登录测试: %s", "成功" if ok else "失败")


def test_logout() -> None:
    from campus_auth import CampusAuth
    u, p = setup_account()
    CONFIG.auth.username = u
    CONFIG.auth.password = p
    auth = CampusAuth()
    auth.logout()
    log.info("登出后认证状态: %s", "已认证" if auth.is_authenticated() else "未认证")


def smoke_test() -> None:
    """导入冻结程序的关键运行路径，不访问网络或修改系统状态。"""
    import keepalive  # noqa: F401
    import tray  # noqa: F401
    import network_monitor  # noqa: F401
    import campus_auth  # noqa: F401
    import auth.base  # noqa: F401
    import auth.detector  # noqa: F401
    import auth.drcom  # noqa: F401
    import auth.portal  # noqa: F401
    import auth.ruijie  # noqa: F401
    import auth.srun  # noqa: F401

    print("SMOKE_TEST_OK")


def install_autostart() -> None:
    """安装开机自启（Windows 任务计划程序）"""
    import subprocess
    python_exe = sys.executable
    script_path = os.path.abspath(__file__)
    task_name = "CampusNetworkKeeper"

    # 创建 XML 任务定义（以最高权限运行，UAC 提权模式）
    # 使用 GroupId=Administrators + RunLevel=HighestAvailable
    # 这样用户登录时自动以管理员权限启动，无需手动 UAC
    import getpass
    current_user = getpass.getuser()
    import ctypes
    is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0

    # 如果当前就是管理员，直接用当前用户 + HighestAvailable
    # 否则用 BUILTIN\Administrators 组
    if is_admin:
        principal_xml = f"""    <Principal>
      <UserId>{current_user}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>"""
    else:
        principal_xml = f"""    <Principal id="Author">
      <UserId>{current_user}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>"""

    xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>校园网断线自动重连 + 认证保活工具（管理员权限）</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
  </Triggers>
  <Principals>
{principal_xml}
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>4</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>"{python_exe}"</Command>
      <Arguments>"{script_path}" --tray</Arguments>
      <WorkingDirectory>{os.path.dirname(script_path)}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>"""

    xml_path = os.path.join(os.path.dirname(script_path), "_task.xml")
    with open(xml_path, "w", encoding="utf-16") as f:
        f.write(xml)

    result = subprocess.run(
        f'schtasks /Create /TN "{task_name}" /XML "{xml_path}" /F',
        shell=True, capture_output=True, text=True
    )
    os.remove(xml_path)

    if result.returncode == 0:
        log.info("✅ 开机自启已安装: %s", task_name)
        log.info("   登录后会自动以托盘模式运行")

        # 同时注册 Wi-Fi 射频开启任务（管理员权限，无需 UAC）
        _install_radio_task()

        log.info("   如需卸载: python main.py --uninstall")
    else:
        log.error("安装失败: %s", result.stdout + result.stderr)


def _install_radio_task() -> None:
    """注册 Wi-Fi 射频开启的管理员计划任务"""
    ps_script = os.path.join(PROJECT_ROOT, "scripts", "enable_wifi_radio.ps1")
    if not os.path.exists(ps_script):
        log.warning("射频脚本不存在: %s", ps_script)
        return

    task_name = "CampusKeeper_EnableWifi"
    xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>校园网保活工具 - 开启Wi-Fi射频（管理员权限）</Description>
  </RegistrationInfo>
  <Principals>
    <Principal>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT30S</ExecutionTimeLimit>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>powershell.exe</Command>
      <Arguments>-ExecutionPolicy Bypass -WindowStyle Hidden -File "{ps_script}"</Arguments>
    </Exec>
  </Actions>
</Task>"""

    xml_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_radio_task.xml")
    with open(xml_path, "w", encoding="utf-16") as f:
        f.write(xml)

    result = subprocess.run(
        f'schtasks /Create /TN "{task_name}" /XML "{xml_path}" /F',
        shell=True, capture_output=True, text=True
    )
    os.remove(xml_path)

    if result.returncode == 0:
        log.info("✅ Wi-Fi 射频任务已注册: %s", task_name)
    else:
        log.warning("射频任务注册失败: %s", result.stdout.strip() or result.stderr.strip())


def uninstall_autostart() -> None:
    """卸载开机自启"""
    import subprocess
    for task_name in ("CampusNetworkKeeper", "CampusKeeper_EnableWifi"):
        result = subprocess.run(
            f'schtasks /Delete /TN "{task_name}" /F',
            shell=True, capture_output=True, text=True
        )
        if result.returncode == 0:
            log.info("✅ 已卸载: %s", task_name)
        else:
            log.debug("卸载 %s: %s", task_name, result.stdout.strip() or result.stderr.strip())


def main() -> None:
    args = sys.argv[1:]

    if "--diagnose" in args or "-d" in args:
        diagnose()
    elif "--test-login" in args:
        test_login()
    elif "--test-logout" in args:
        test_logout()
    elif "--smoke-test" in args:
        smoke_test()
    elif "--install" in args:
        install_autostart()
    elif "--uninstall" in args:
        uninstall_autostart()
    elif "--tray" in args:
        run_tray()
    elif "--help" in args or "-h" in args:
        print(__doc__)
        u, _ = setup_account()
        print(f"  账号: {u[:3] + '***' if u else '(未配置)'}")
        print(f"  认证: {'启用' if CONFIG.auth.enabled else '未启用'}")
        print(f"  Wi-Fi: {CONFIG.network.wifi_ssids}")
    else:
        run_keepalive()


if __name__ == "__main__":
    main()


