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


def test_watchdog_allows_slow_network_probe_and_tracks_phase():
    app = TrayApp()

    app._touch_watchdog("network probe")

    assert app._watchdog_timeout_sec == 300
    assert app._watchdog_phase == "network probe"
    assert app._loop_heartbeat > 0


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


@patch("tray.enable_ethernet_adapter", return_value=True)
def test_wifi_online_with_disabled_ethernet_enables_adapter(enable_ethernet):
    app = TrayApp()
    snap = _snapshot(NetState.ONLINE, eth=False, wifi=True)
    snap.eth_admin_enabled = False

    app._observe_interface_mode(snap)

    assert app._using_wifi_fallback is True
    enable_ethernet.assert_called_once()


@patch("tray.take_snapshot")
@patch("subprocess.run")
@patch("tray.TrayApp._prefer_wifi")
@patch("tray.TrayApp._prefer_ethernet")
def test_switchback_does_not_disconnect_wifi_before_ethernet_probe(
    prefer_eth, prefer_wifi, run, snapshot
):
    app = TrayApp()
    snapshot.return_value = _snapshot(NetState.ONLINE, eth=True, wifi=True)
    snapshot.return_value.eth_internet_reachable = False
    snapshot.return_value.eth_auth_probe_ok = False

    app._switch_back_to_ethernet()

    run.assert_not_called()
    prefer_eth.assert_called_once()
    prefer_wifi.assert_called_once()
    assert app._using_wifi_fallback is True


@patch("tray.take_snapshot")
@patch("subprocess.run")
@patch("tray.TrayApp._prefer_wifi")
@patch("tray.TrayApp._prefer_ethernet")
def test_switchback_disconnects_wifi_only_after_ethernet_is_verified(
    prefer_eth, prefer_wifi, run, snapshot
):
    app = TrayApp()
    first = _snapshot(NetState.ONLINE, eth=True, wifi=True)
    first.eth_internet_reachable = True
    second = _snapshot(NetState.ONLINE, eth=True, wifi=False)
    second.eth_internet_reachable = True
    snapshot.side_effect = [first, first, second]

    app._switch_back_to_ethernet()

    run.assert_called_once()
    prefer_eth.assert_called_once()
    prefer_wifi.assert_not_called()
    assert app._using_wifi_fallback is False


@patch("wifi_switcher.connect_wifi", return_value=True)
@patch("wifi_switcher.list_available_ssids", return_value=[])
@patch("wifi_switcher.list_saved_profiles", return_value=["saved-profile"])
@patch("wifi_switcher.ensure_wifi_adapter_enabled", return_value=True)
def test_wifi_fallback_uses_saved_profile_when_ssid_not_configured(
    ensure, saved, available, connect
):
    import wifi_switcher

    with patch.object(wifi_switcher.CONFIG, "wifi_ssids", []):
        assert wifi_switcher.auto_connect_preferred_wifi() is True
    connect.assert_called_once_with("saved-profile")


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
