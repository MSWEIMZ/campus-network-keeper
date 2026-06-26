"""公共测试 fixture"""
import sys
import os
from pathlib import Path
from unittest.mock import patch

import pytest

# 确保 src 在 import path 中
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))


@pytest.fixture(autouse=True)
def _isolate_config(tmp_path):
    """隔离测试环境：不读取真实的 config.ini / account.ini"""
    with patch.dict(os.environ, {"CAMPUS_USER": "", "CAMPUS_PASS": ""}, clear=False):
        yield
