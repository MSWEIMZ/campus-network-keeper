"""
打包脚本：将项目打包为单个 exe 文件
用法: python scripts/build.py
"""
import os
import subprocess
import sys

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
MAIN_SCRIPT = os.path.join(SRC_DIR, "main.py")

# 排除不需要的模块（减小体积）
EXCLUDE_MODULES = [
    "numpy", "setuptools", "pkg_resources", "multiprocessing",
    "xml", "email", "html", "pydoc", "lib2to3",
    "tkinter", "_tkinter",
    # Pillow 不需要的图片格式
    "PIL.ImageQt", "PIL.ImageTk",
    "PIL.Jpeg2KImagePlugin", "PIL.PdfImagePlugin",
    "PIL.FitsStubImagePlugin", "PIL.MpoImagePlugin",
    "PIL.MicImagePlugin", "PIL.FpxImagePlugin",
    "PIL.BufrStubImagePlugin", "PIL.GribStubImagePlugin",
    "PIL.Hdf5StubImagePlugin", "PIL.EpsImagePlugin",
    "PIL.PcdImagePlugin", "PIL.WalImagePlugin",
    "PIL.PalmImagePlugin", "PIL.PcxImagePlugin",
    "PIL.SgiImagePlugin", "PIL.SunImagePlugin",
    "PIL.XbmImagePlugin", "PIL.XpmImagePlugin",
]


def build():
    print("=" * 50)
    print("  Campus Network Keeper - Build")
    print("=" * 50)
    print()

    print("[1/3] Checking dependencies...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-r",
                    os.path.join(PROJECT_ROOT, "requirements.txt"),
                    "--quiet"], check=True)

    print("[2/3] Building exe...")
    args = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "CampusNetworkKeeper",
        "--console",
        "--add-data", f"{SRC_DIR}{os.pathsep}.",
        "--clean",
        MAIN_SCRIPT,
    ]

    for mod in EXCLUDE_MODULES:
        args.extend(["--exclude-module", mod])

    # Hidden imports
    hidden = [
        "pystray", "PIL", "PIL.Image", "PIL.ImageDraw",
        "requests", "des_crypto", "campus_auth", "config", "logger",
        "network_monitor", "nic_reset", "wifi_switcher", "keepalive",
        "tray", "wizard", "main",
        "auth", "auth.base", "auth.detector", "auth.drcom",
        "auth.ruijie", "auth.srun", "auth.portal",
    ]
    for mod in hidden:
        args.extend(["--hidden-import", mod])

    result = subprocess.run(args, cwd=PROJECT_ROOT)

    if result.returncode == 0:
        exe_path = os.path.join(PROJECT_ROOT, "dist", "CampusNetworkKeeper.exe")
        size_mb = os.path.getsize(exe_path) / 1024 / 1024
        print()
        print(f"[3/3] Build OK! Size: {size_mb:.1f} MB")
        print(f"  Output: {exe_path}")
    else:
        print()
        print("[3/3] Build FAILED!")
        sys.exit(1)


if __name__ == "__main__":
    build()
