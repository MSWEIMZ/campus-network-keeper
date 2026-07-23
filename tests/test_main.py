import sys
from unittest.mock import patch

import main


def test_smoke_test_argument_loads_frozen_runtime_dependencies():
    with patch.object(main, "smoke_test") as smoke, patch.object(
        sys, "argv", ["main.py", "--smoke-test"]
    ):
        main.main()

    smoke.assert_called_once_with()


def test_frozen_no_argument_starts_tray_instead_of_cli_loop():
    with patch.object(main, "run_tray") as tray, patch.object(
        main, "run_keepalive"
    ) as keepalive, patch.object(sys, "argv", ["CampusNetworkKeeper.exe"]):
        main.sys.frozen = True
        try:
            main.main()
        finally:
            del main.sys.frozen

    tray.assert_called_once_with()
    keepalive.assert_not_called()
