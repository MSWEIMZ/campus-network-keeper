from unittest.mock import Mock, patch

import tray
from tray import TrayApp
from network_monitor import NetState, NetworkSnapshot


def _snapshot(state, *, eth=False, wifi=True):
    return NetworkSnapshot(
        state=state,
        eth_connected=eth,
        wifi_connected=wifi,
        has_ip=True,
        gateway="10.0.0.1",
        gateway_reachable=True,
        internet_reachable=state == NetState.ONLINE,
        auth_probe_ok=state == NetState.ONLINE,
    )


def test_tray_initializes_lifecycle_state_and_tooltip_formatter():
    app = TrayApp()
    app._traffic_info = {"used_str": "1 GB", "balance_str": "10元"}

    assert app._user_initiated_exit is False
    assert app._format_traffic_tooltip() == "已用: 1 GB\n余额: 10元"


@patch("campus_auth.CampusAuth")
@patch("socket.getaddrinfo", side_effect=AssertionError("不应解析学校专用域名"))
def test_login_does_not_depend_on_dlut_dns(getaddrinfo, auth_cls):
    auth_cls.return_value.login.return_value = True
    app = TrayApp()

    assert app._do_login("user", "pass") is True
    getaddrinfo.assert_not_called()


def test_restart_releases_single_instance_mutex_before_spawning():
    calls = []
    tray._INSTANCE_MUTEX = 123

    with patch.object(
        tray.ctypes.windll.kernel32,
        "CloseHandle",
        side_effect=lambda handle: calls.append(("close", handle)),
    ), patch("subprocess.Popen", side_effect=lambda *a, **k: calls.append(("spawn", a))):
        tray._restart_current_process()

    assert calls[0] == ("close", 123)
    assert calls[1][0] == "spawn"
    assert tray._INSTANCE_MUTEX is None


def test_ethernet_switch_requires_wifi_fallback_and_stability():
    app = TrayApp()

    assert app._should_switch_back_to_ethernet(True, True) is False
    app._using_wifi_fallback = True
    assert app._should_switch_back_to_ethernet(True, True) is False
    assert app._should_switch_back_to_ethernet(True, True) is False
    assert app._should_switch_back_to_ethernet(True, True) is True


@patch("time.sleep")
@patch("wifi_switcher.auto_connect_preferred_wifi", return_value=True)
@patch("nic_reset.reset_ethernet", return_value=True)
@patch("tray.take_snapshot")
def test_wifi_portal_failure_does_not_reset_ethernet_twice(
    snapshot, reset_ethernet, connect_wifi, sleep
):
    snapshot.side_effect = [
        _snapshot(NetState.CABLE_DOWN, eth=False, wifi=False),
        _snapshot(NetState.WEB_AUTH_REQUIRED),
        _snapshot(NetState.WEB_AUTH_REQUIRED),
    ]
    app = TrayApp()
    app._do_login = Mock(return_value=False)

    app._recover_cable_down()

    assert reset_ethernet.call_count == 1
