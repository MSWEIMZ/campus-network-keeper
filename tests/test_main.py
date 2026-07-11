import sys
from unittest.mock import patch

import main


def test_smoke_test_argument_loads_frozen_runtime_dependencies():
    with patch.object(main, "smoke_test") as smoke, patch.object(
        sys, "argv", ["main.py", "--smoke-test"]
    ):
        main.main()

    smoke.assert_called_once_with()
