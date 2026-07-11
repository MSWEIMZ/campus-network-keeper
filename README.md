<p align="center">
  <img src="https://img.shields.io/badge/Campus_Network_Keeper-v1.0.5-blue?style=for-the-badge" alt="version">
</p>

<p align="center">
  <strong>校园网自动保活 · 断线重连 · 认证登录 · 流量监控</strong>
</p>

<p align="center">
  <a href="https://github.com/MSWEIMZ/campus-network-keeper/releases"><img src="https://img.shields.io/github/v/release/MSWEIMZ/campus-network-keeper?style=flat-square" alt="Release"></a>
  <a href="https://github.com/MSWEIMZ/campus-network-keeper/actions"><img src="https://img.shields.io/github/actions/workflow/status/MSWEIMZ/campus-network-keeper/build-and-release.yml?style=flat-square" alt="Build"></a>
  <img src="https://img.shields.io/badge/Windows-10%20%7C%2011-blue?style=flat-square&logo=windows" alt="Windows">
  <img src="https://img.shields.io/badge/Python-3.10+-green?style=flat-square&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Tests-34%20passed-brightgreen?style=flat-square" alt="Tests">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-yellow?style=flat-square" alt="License"></a>
</p>

---

> 网线掉了？自动重置网卡。网卡不行？自动切 WiFi。  
> 认证过期？自动重新登录。你只管做你的事，网络的事交给它。

---

## 🎯 解决了什么问题

每个大学生都经历过：

1. 🖥️ 训练任务跑到一半 / 文件下载到一半 / 网课上到一半
2. 📡 校园网突然断了
3. 🏃 跑过去拔网线、插网线、等弹出认证页、输入账号密码
4. 💀 回来发现任务已经挂了

**这个工具让这一切全部自动完成。**

---

## ✨ 功能一览

<table>
<tr>
<td width="50%">

### 🔌 网线优先策略
网线断了 → 重置网卡 → 等待恢复  
还不行 → 切换 WiFi 兜底  
网线恢复 → 自动切回网线

</td>
<td width="50%">

### 🌐 认证自动保活
检测到认证页面 → 自动填写账号密码  
认证过期 → 心跳检测 → 静默重新登录  
支持 Dr.COM / 锐捷 / 深澜 / 通用 Portal

</td>
</tr>
<tr>
<td>

### 📊 流量监控
鼠标悬停托盘图标即可查看：  
已用流量 · 剩余流量 · 账户余额 · 在线时长

</td>
<td>

### 🛡️ 稳定运行保障
看门狗线程：卡住 120 秒强制重启  
崩溃自动重启（最多 5 次）  
Session 池定期重建，防止内存泄漏

</td>
</tr>
<tr>
<td>

### 📡 WiFi 射频控制
WiFi 软件关闭？自动开启射频  
支持计划任务提权，无需手动 UAC

</td>
<td>

### 🧪 TDD 测试覆盖
45 个单元测试：<br>
DES 加密 · 状态判定 · 认证系统识别 · 托盘生命周期<br>
`pytest tests/ -v` 全绿

</td>
</tr>
</table>

---

## 🚀 快速开始

### 方式一：下载 exe（推荐）

```
1. 前往 Releases 页面下载 CampusNetworkKeeper.exe
2. 右键 → 以管理员身份运行
3. 按向导提示输入账号密码
4. 完成！开机自动运行
```

<p align="center">
  <a href="https://github.com/MSWEIMZ/campus-network-keeper/releases">
    <img src="https://img.shields.io/badge/⬇️_下载最新版-CampusNetworkKeeper.exe-blue?style=for-the-badge&logo=github" alt="Download">
  </a>
</p>

### 方式二：从源码运行

```powershell
# 安装依赖
pip install -r requirements.txt

# 首次配置（自动识别你学校的认证系统）
cd src
python main.py --wizard

# 启动托盘模式
python main.py --tray

# 安装开机自启（需要管理员权限）
python main.py --install
```

---

## 🔄 运行流程

```
每 10 秒检测一次：

  ┌─ 网线 + WiFi 都断了？
  │    → 等 5 秒确认 → 重置网卡 → 还不行？→ 连接 WiFi
  │
  ├─ WiFi 连上但网关不通？
  │    → 尝试 Portal 认证（不重置网卡）
  │
  ├─ 网线"已连接"但网关不通？
  │    → 物理层异常，重置网卡
  │
  ├─ 外网不通，DNS 正常？
  │    → 自动认证登录 → 失败？→ 重置网卡 + 切 WiFi
  │
  ├─ DNS 完全不通？
  │    → 跳过登录，等待恢复（避免无意义重试）
  │
  ├─ WiFi 在线，网线恢复了？
  │    → 断开 WiFi → 切回网线（网线优先！）
  │
  └─ 一切正常？
       → 心跳保活（60 秒）→ 更新流量信息

  🛡️ 看门狗：循环卡住超过 120 秒 → 强制重启进程
```

---

## 🏫 支持的认证系统

| 认证系统 | 代表高校 | 自动识别 |
|:---------|:---------|:--------:|
| **Dr.COM + CAS SSO** | 大连理工、东北大学、南京邮电… | ✅ |
| **锐捷 ePortal** | 华中科技、西安电子、华南理工… | ✅ |
| **深澜 Srun** | 清华、北大、浙大、上交… | ✅ |
| **通用 Web Portal** | 其他使用网页登录的学校 | ✅ |

> 💡 不确定你学校用哪个？运行 `--wizard` 会自动检测。

---

## 🖥️ 托盘图标

| 颜色 | 含义 |
|:----:|:-----|
| 🟢 绿色 | 正常在线 |
| 🟡 黄色 | 正在处理（重连中 / 登录中） |
| 🔴 红色 | 异常，需要关注 |
| ⚪ 灰色 | 启动中 |

鼠标悬停可查看：

```
校园网保活: 在线
已用: 147.5 GB | 剩余: 730 MB
余额: 20.03 元 | 在线: 14h 33m
```

---

## 📖 命令行参数

| 参数 | 说明 |
|:-----|:-----|
| `--wizard` | 🧙 首次配置向导（推荐新用户） |
| `--tray` | 📌 托盘常驻模式（日常使用） |
| `--install` | ⚙️ 安装开机自启（需管理员） |
| `--uninstall` | 🗑️ 卸载开机自启 |
| `--diagnose` | 🔍 网络诊断 |
| `--test-login` | 🔑 测试认证登录 |
| `--test-logout` | 🚪 测试登出 |

---

## 📁 项目结构

```
campus-network-keeper/
├── src/
│   ├── main.py               # 入口
│   ├── config.py             # 配置管理
│   ├── wizard.py             # 首次配置向导
│   ├── campus_auth.py        # 认证路由（自动选择模板）
│   ├── auth/
│   │   ├── base.py           # 认证基类
│   │   ├── detector.py       # 自动识别认证系统
│   │   ├── drcom.py          # Dr.COM + CAS SSO
│   │   ├── ruijie.py         # 锐捷 ePortal
│   │   ├── srun.py           # 深澜 Srun
│   │   └── portal.py         # 通用 Web Portal
│   ├── network_monitor.py    # 网络状态检测
│   ├── nic_reset.py          # 网卡重置
│   ├── wifi_switcher.py      # WiFi 自动切换
│   ├── des_crypto.py         # DES 加密（纯 Python）
│   ├── tray.py               # 系统托盘 UI
│   └── keepalive.py          # 保活主循环
├── tests/                    # TDD 测试套件
├── scripts/
│   ├── build.py              # PyInstaller 打包
│   └── enable_wifi_radio.ps1 # WiFi 射频控制
└── .github/workflows/        # CI/CD 自动构建
```

---

## ❓ FAQ

<details>
<summary><b>网卡重置失败？</b></summary>

需要管理员权限。以管理员身份运行，或使用 `--install` 设置开机自启（自动提权）。
</details>

<details>
<summary><b>登录失败？</b></summary>

运行 `--test-login` 查看详细日志。检查 `logs/campus_keeper.log` 中的错误信息。
</details>

<details>
<summary><b>WiFi 连不上？</b></summary>

必须曾经手动连接过该 WiFi 至少一次（Windows 需要保存过的 Profile）。
</details>

<details>
<summary><b>如何完全卸载？</b></summary>

```powershell
python main.py --uninstall
# 然后删除整个文件夹即可
```
</details>

---

## 🤝 参与贡献

目前在大连理工大学测试通过。如果你的学校使用不同的认证系统，欢迎提交 Issue，附上：

1. 断网后浏览器跳转到的 URL
2. 登录表单的字段名（F12 → Network → 找到 POST 请求）
3. 登录成功后的页面/返回内容

或者直接提交 PR，添加新的认证模板（参考 `src/auth/` 下的现有模板）。

---

## 📄 License

[MIT](LICENSE)
