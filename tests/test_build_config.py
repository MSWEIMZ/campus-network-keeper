import importlib.util
from pathlib import Path


_BUILD_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build.py"
_SPEC = importlib.util.spec_from_file_location("build_script", _BUILD_PATH)
assert _SPEC and _SPEC.loader
_BUILD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_BUILD)


def test_pyinstaller_keeps_runtime_standard_library_dependencies():
    """requests/urllib3 在冻结程序启动时依赖 email 标准库。"""
    excluded_stdlib = {"email", "xml", "html", "multiprocessing"}
    assert excluded_stdlib.isdisjoint(_BUILD.EXCLUDE_MODULES)


def test_release_build_uses_windowed_bootloader_for_tray_app():
    """发布版双击启动托盘时不应弹出控制台窗口。"""
    source = _BUILD_PATH.read_text(encoding="utf-8")
    assert '"--windowed"' in source
    assert '"--console"' not in source
