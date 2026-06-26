# Campus Network Keeper

**The only campus network tool with auto-reconnect + captive portal auth + traffic monitor.**

> Your cable drops? It resets the NIC. NIC reset fails? It switches to Wi-Fi. Portal login expired? It re-authenticates silently. You never lose connection again.

[![Release](https://img.shields.io/github/v/release/MSWEIMZ/campus-network-keeper)](https://github.com/MSWEIMZ/campus-network-keeper/releases)
[![Platform](https://img.shields.io/badge/Windows-10%2F11-blue)]()
[![Python](https://img.shields.io/badge/Python-3.10%2B-green)]()
[![License](https://img.shields.io/badge/license-MIT-yellow)]()

---

## Why This Exists

Every Chinese university student has experienced this:

- You're running a long training job / downloading a large file / in an online meeting
- Suddenly the network drops
- You walk over, unplug the cable, plug it back in
- A captive portal page pops up asking for login
- You type your credentials, but your running task is already dead

**This tool makes all of that automatic.**

---

## Features

| Feature | What It Does |
|---------|-------------|
| **Cable Auto-Reconnect** | NIC disable/enable + DHCP refresh, all without touching your computer |
| **Wi-Fi Fallback** | If cable reset fails, auto-connect to saved Wi-Fi (even turns on radio) |
| **Portal Auto-Login** | Detects captive portal, submits credentials, restores connection |
| **Heartbeat Keep-Alive** | Pings every 60s to prevent silent logout |
| **Traffic Monitor** | Hover tray icon to see used/remaining data, balance, online devices |
| **System Tray** | Runs in background with status indicator (green/yellow/red) |
| **Auto-Start** | Windows Task Scheduler, runs at login with admin privileges |
| **Detailed Logging** | Every HTTP request, every state change logged to file |

### Supported Auth Systems

| System | Universities | Detection |
|--------|-------------|----------|
| Dr.COM + CAS SSO | DUT, NEU, NJUPT, ... | Auto |
| Ruijie ePortal | HUST, XDU, SCUT, ... | Auto |
| Srun (ShenLan) | Tsinghua, PKU, ZJU, SJTU, ... | Auto |
| Generic Portal | Any web form login | Auto |

> Not sure which one your school uses? Run `--wizard` and it auto-detects.

---

## Quick Start

### Option A: Download exe (no Python needed)

1. Go to [Releases](https://github.com/MSWEIMZ/campus-network-keeper/releases)
2. Download `CampusNetworkKeeper.exe`
3. Right-click -> Run as Administrator
4. Follow the wizard

### Option B: Run from source

```powershell
# Install dependencies
pip install -r requirements.txt

# First-time setup (auto-detects your school's auth system)
cd src
python main.py --wizard

# Start tray mode
python main.py --tray

# Install auto-start (needs admin)
python main.py --install
```

---

## How It Works

```
Every 10 seconds:
  |
  +-- Check: cable connected?
  |     NO -> wait 5s confirm -> reset NIC -> still no? -> connect Wi-Fi
  |
  +-- Check: has IP?
  |     NO -> release/renew DHCP
  |
  +-- Check: can reach internet?
  |     NO -> check: captive portal?
  |              YES -> auto-login -> verify -> done
  |
  +-- All OK -> heartbeat (every 60s) -> update traffic info
```

---

## Tray Icon

| Color | Status |
|-------|--------|
| Green | Online, everything working |
| Yellow | Processing (reconnecting / logging in) |
| Red | Error, needs attention |
| Gray | Starting up |

Hover over the icon to see:
```
Campus Network Keeper: Online
Account: 20240001
Used: 137.3 GB
Remaining: 14.2 GB
Balance: 20.03 yuan
Online: 12h 52m
Devices: 3
```

---

## CLI Reference

| Command | Description |
|---------|-------------|
| `--wizard` | First-time setup (recommended for new users) |
| `--tray` | System tray mode (recommended for daily use) |
| `--install` | Install auto-start via Task Scheduler |
| `--uninstall` | Remove auto-start |
| `--diagnose` | Network diagnostics |
| `--test-login` | Test authentication |
| `--test-logout` | Test logout |

---

## Project Structure

```
src/
  main.py              Entry point
  config.py            Config management (config.ini + env vars)
  wizard.py            First-time setup wizard
  campus_auth.py       Auth router (auto-selects template)
  auth/
    base.py            Auth base class
    detector.py        Auto-detect auth system
    drcom.py           Dr.COM + CAS SSO
    ruijie.py          Ruijie ePortal
    srun.py            Srun (ShenLan)
    portal.py          Generic web portal
  network_monitor.py   Network state detection
  nic_reset.py         NIC reset (needs admin)
  wifi_switcher.py     Wi-Fi auto-connect
  des_crypto.py        Pure Python DES encryption
  tray.py              System tray UI
  keepalive.py         CLI keepalive loop
  logger.py            Logging (console + rotating file)
scripts/
  build.py             PyInstaller build script
  enable_wifi_radio.ps1 Wi-Fi radio control
```

---

## FAQ

**Q: NIC reset failed?**
A: Needs admin. Run as Administrator, or use `--install` to set up auto-start with admin.

**Q: Login failed?**
A: Run `--test-login` to see detailed logs. Check `logs/campus_keeper.log`.

**Q: Wi-Fi not connecting?**
A: You must have connected to that Wi-Fi at least once (Windows needs a saved profile).

**Q: How to completely uninstall?**
A: `python main.py --uninstall`, then delete the folder.

---

## Contributing

Currently tested at DUT (Dalian University of Technology). If your school uses a different auth system, please open an issue with:
1. The URL you get redirected to when disconnected
2. The login form fields (F12 -> Network -> find the POST request)
3. What a successful login looks like

---

## License

MIT
