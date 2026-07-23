"""网络状态判定逻辑测试（mock 外部调用，只测状态机逻辑）"""
import sys
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from network_monitor import (
    _InterfaceConfig,
    NetState,
    NetworkSnapshot,
    get_adapter_status,
    get_adapter_admin_status,
    probe_internet,
    take_snapshot,
)


class TestProbeSemantics:
    @patch("network_monitor._get_probe_session")
    def test_captive_portal_redirect_is_not_internet(self, get_session):
        response = Mock(status_code=302, headers={"Location": "http://portal/login"})
        get_session.return_value.get.return_value = response

        assert probe_internet() is False

    @patch("network_monitor._run")
    def test_english_disconnected_adapter_is_not_connected(self, run):
        run.return_value = "Enabled  Disconnected  Dedicated  Ethernet"

        assert get_adapter_status("Ethernet") is False

    @patch("network_monitor._run")
    def test_disabled_adapter_is_distinguished_from_link_down(self, run):
        run.return_value = "Enabled  Disconnected  Dedicated  Ethernet"
        assert get_adapter_admin_status("Ethernet") is True

        run.return_value = "Disabled  Disconnected  Dedicated  Ethernet"
        assert get_adapter_admin_status("Ethernet") is False


class TestNetStateEnum:
    def test_all_states_exist(self):
        assert hasattr(NetState, 'ONLINE')
        assert hasattr(NetState, 'CABLE_DOWN')
        assert hasattr(NetState, 'DHCP_LIMITED')
        assert hasattr(NetState, 'WEB_AUTH_REQUIRED')
        assert hasattr(NetState, 'UNKNOWN')

    def test_states_are_unique(self):
        states = [NetState.ONLINE, NetState.CABLE_DOWN, NetState.DHCP_LIMITED,
                  NetState.WEB_AUTH_REQUIRED, NetState.UNKNOWN]
        assert len(set(states)) == 5


class TestSnapshotDetermination:

    @patch('network_monitor._get_interface_configs', return_value=[])
    @patch('network_monitor.probe_auth_page', return_value=True)
    @patch('network_monitor.probe_internet', return_value=True)
    @patch('network_monitor._ping', return_value=True)
    @patch('network_monitor.get_default_gateway', return_value='172.29.0.1')
    @patch('network_monitor.has_ipv4_address', return_value=True)
    @patch('network_monitor.is_wifi_connected', return_value=False)
    @patch('network_monitor.is_ethernet_connected', return_value=True)
    def test_ethernet_online(self, *mocks):
        snap = take_snapshot()
        assert snap.state == NetState.ONLINE

    @patch('network_monitor._get_interface_configs', return_value=[])
    @patch('network_monitor.probe_auth_page', return_value=False)
    @patch('network_monitor.probe_internet', return_value=False)
    @patch('network_monitor._ping', return_value=False)
    @patch('network_monitor.get_default_gateway', return_value=None)
    @patch('network_monitor.has_ipv4_address', return_value=False)
    @patch('network_monitor.is_wifi_connected', return_value=False)
    @patch('network_monitor.is_ethernet_connected', return_value=False)
    def test_cable_down(self, *mocks):
        snap = take_snapshot()
        assert snap.state == NetState.CABLE_DOWN

    @patch('network_monitor._get_interface_configs', return_value=[])
    @patch('network_monitor.probe_auth_page', return_value=False)
    @patch('network_monitor.probe_internet', return_value=False)
    @patch('network_monitor._ping', return_value=False)
    @patch('network_monitor.get_default_gateway', return_value='172.29.0.1')
    @patch('network_monitor.has_ipv4_address', return_value=False)
    @patch('network_monitor.is_wifi_connected', return_value=True)
    @patch('network_monitor.is_ethernet_connected', return_value=False)
    def test_dhcp_limited(self, *mocks):
        snap = take_snapshot()
        assert snap.state == NetState.DHCP_LIMITED

    @patch('network_monitor._get_interface_configs', return_value=[])
    @patch('network_monitor.probe_auth_page', return_value=True)
    @patch('network_monitor.probe_internet', return_value=False)
    @patch('network_monitor._ping', return_value=True)
    @patch('network_monitor.get_default_gateway', return_value='172.29.0.1')
    @patch('network_monitor.has_ipv4_address', return_value=True)
    @patch('network_monitor.is_wifi_connected', return_value=True)
    @patch('network_monitor.is_ethernet_connected', return_value=False)
    def test_auth_probe_pass_means_online(self, *mocks):
        snap = take_snapshot()
        assert snap.state == NetState.ONLINE

    @patch('network_monitor._get_interface_configs', return_value=[])
    @patch('network_monitor.probe_auth_page', return_value=False)
    @patch('network_monitor.probe_internet', return_value=False)
    @patch('network_monitor._ping', return_value=True)
    @patch('network_monitor.get_default_gateway', return_value='172.29.0.1')
    @patch('network_monitor.has_ipv4_address', return_value=True)
    @patch('network_monitor.is_wifi_connected', return_value=True)
    @patch('network_monitor.is_ethernet_connected', return_value=False)
    def test_gateway_ok_but_no_internet_means_auth_required(self, *mocks):
        """网关可达+外网不通 → 才判定为需要认证"""
        snap = take_snapshot()
        assert snap.state == NetState.WEB_AUTH_REQUIRED

    @patch('network_monitor._get_interface_configs', return_value=[])
    @patch('network_monitor.probe_auth_page', return_value=False)
    @patch('network_monitor.probe_internet', return_value=False)
    @patch('network_monitor._ping', return_value=False)
    @patch('network_monitor.get_default_gateway', return_value='172.29.0.1')
    @patch('network_monitor.has_ipv4_address', return_value=True)
    @patch('network_monitor.is_wifi_connected', return_value=False)
    @patch('network_monitor.is_ethernet_connected', return_value=True)
    def test_eth_connected_but_gateway_unreachable_is_dhcp_limited(self, *mocks):
        """网线已连接+有IP+但网关不通 → DHCP_LIMITED（不是WEB_AUTH！）"""
        snap = take_snapshot()
        assert snap.state == NetState.DHCP_LIMITED

    @patch('network_monitor._get_interface_configs', return_value=[])
    @patch('network_monitor.probe_auth_page', return_value=False)
    @patch('network_monitor.probe_internet', return_value=False)
    @patch('network_monitor._ping', return_value=False)
    @patch('network_monitor.get_default_gateway', return_value=None)
    @patch('network_monitor.has_ipv4_address', return_value=True)
    @patch('network_monitor.is_wifi_connected', return_value=True)
    @patch('network_monitor.is_ethernet_connected', return_value=False)
    def test_wifi_only_gateway_unreachable_is_auth_required(self, *mocks):
        """WiFi连接+有IP+网关不可达 → WEB_AUTH_REQUIRED（WiFi物理层正常，需要认证）"""
        snap = take_snapshot()
        assert snap.state == NetState.WEB_AUTH_REQUIRED

    @patch('network_monitor._get_interface_configs', return_value=[])
    @patch('network_monitor.probe_auth_page', side_effect=Exception("timeout"))
    @patch('network_monitor.probe_internet', side_effect=Exception("timeout"))
    @patch('network_monitor._ping', return_value=False)
    @patch('network_monitor.get_default_gateway', return_value=None)
    @patch('network_monitor.has_ipv4_address', return_value=True)
    @patch('network_monitor.is_wifi_connected', return_value=True)
    @patch('network_monitor.is_ethernet_connected', return_value=True)
    def test_exception_returns_unknown(self, *mocks):
        snap = take_snapshot()
        assert snap.state == NetState.UNKNOWN


class TestSnapshotDataclass:
    def test_snapshot_fields(self):
        snap = NetworkSnapshot(
            state=NetState.ONLINE,
            eth_connected=True, wifi_connected=False,
            has_ip=True, gateway="172.29.0.1",
            gateway_reachable=True, internet_reachable=True,
            auth_probe_ok=True, detail="正常",
        )
        assert snap.state == NetState.ONLINE
        assert snap.detail == "正常"


@patch('network_monitor.is_ethernet_connected', return_value=True)
@patch('network_monitor.is_wifi_connected', return_value=True)
@patch('network_monitor.is_ethernet_admin_enabled', return_value=True)
@patch('network_monitor._ping', side_effect=[True, True])
@patch('network_monitor.probe_internet', side_effect=[False, True])
@patch('network_monitor.probe_auth_page', return_value=False)
@patch('network_monitor._get_interface_configs', return_value=[
    _InterfaceConfig('Ethernet', '10.0.0.10', '10.0.0.1'),
    _InterfaceConfig('WLAN', '192.168.0.10', '192.168.0.1'),
])
def test_wifi_is_reported_as_fallback_when_ethernet_has_no_internet(*mocks):
    """双网卡同时连接时，Wi-Fi 可用不能掩盖以太网无外网。"""
    snap = take_snapshot()

    assert snap.state == NetState.ONLINE
    assert snap.eth_connected is True
    assert snap.eth_internet_reachable is False
    assert snap.wifi_internet_reachable is True
    assert snap.active_interface == "wifi"
    assert "Wi-Fi" in snap.detail
