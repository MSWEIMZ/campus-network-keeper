from unittest.mock import patch

from keepalive import KeepAlive
from network_monitor import NetState, NetworkSnapshot


def _snapshot(state):
    return NetworkSnapshot(
        state=state,
        eth_connected=True,
        wifi_connected=False,
        has_ip=True,
        gateway="10.0.0.1",
        gateway_reachable=False,
        internet_reachable=False,
        auth_probe_ok=False,
    )


@patch("keepalive.CampusAuth")
def test_debounce_requires_same_abnormal_state(auth_cls):
    keeper = KeepAlive()
    with patch.object(keeper, "_recover_dhcp_limited") as recover_dhcp, patch.object(
        keeper, "_recover_auth_required"
    ) as recover_auth:
        keeper._handle_abnormal(_snapshot(NetState.DHCP_LIMITED))
        keeper._handle_abnormal(_snapshot(NetState.WEB_AUTH_REQUIRED))

    recover_dhcp.assert_not_called()
    recover_auth.assert_not_called()


@patch("keepalive.CampusAuth")
def test_same_abnormal_state_reaches_debounce_threshold(auth_cls):
    keeper = KeepAlive()
    snap = _snapshot(NetState.WEB_AUTH_REQUIRED)
    with patch.object(keeper, "_recover_auth_required") as recover:
        keeper._handle_abnormal(snap)
        keeper._handle_abnormal(snap)

    recover.assert_called_once_with(snap)
