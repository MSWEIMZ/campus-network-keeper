from unittest.mock import patch

import route_manager


@patch("route_manager.subprocess.run")
def test_prefer_wifi_sets_active_store_metrics(run):
    run.return_value.returncode = 0

    assert route_manager.prefer_wifi("Ethernet", "WLAN") is True
    assert run.call_count == 2
    commands = [call.args[0] for call in run.call_args_list]
    assert all(command[:3] == ["powershell", "-NoProfile", "-NonInteractive"] for command in commands)
    assert all("ActiveStore" in command[-1] for command in commands)


@patch("route_manager.subprocess.run")
def test_route_failure_is_reported(run):
    run.return_value.returncode = 1

    assert route_manager.prefer_ethernet("Ethernet", "WLAN") is False
