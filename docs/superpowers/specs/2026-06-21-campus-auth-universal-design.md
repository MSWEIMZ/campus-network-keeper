# 校园网保活工具 - 通用化设计文档

> 日期: 2026-06-21
> 状态: 已批准

## 1. 目标

将当前仅适配大连理工大学（DLUT CAS + Dr.COM）的校园网保活工具，改造为**通用化**的校园网自动认证 + 断线重连工具，适配中国大多数高校。

**核心决策：**
- 用户模式：小白模式（自动探测）+ 高级模式（手动配置 config.ini）
- 平台：Windows 桌面托盘工具
- 首次使用：启动向导自动探测认证系统，用户只需填账号密码

## 2. 支持的认证系统

| 模板名 | 适用系统 | 用户需要提供 | 自动探测依据 |
|--------|---------|-------------|-------------|
| `drcom` | Dr.COM（城市热点） | 账号+密码 | URL 含 `dr.com`、`Self/sso_login` |
| `cas_sso` | CAS 统一认证 | 账号+密码 | URL 含 `cas/login` |
| `ruijie` | 锐捷 ePortal | 账号+密码+运营商 | URL 含 `eportal`、`portal` |
| `srun` | 深澜 Srun | 账号+密码 | URL 含 `srun`、页面含关键字 |
| `portal` | 通用 Web Portal | 账号+密码 | 页面有 `<form>` + 密码框 |
| `custom` | 高级自定义 | 完整配置 | 手动选择 |

**覆盖估计：** 90%+ 中国高校

## 3. 首次启动向导

### 流程

1. **步骤1 - 输入账号密码**
   - 用户填入校园网账号和密码
   - 密码本地加密存储

2. **步骤2 - 自动探测**
   - 访问 HTTP 外网 → 被重定向到认证页
   - 根据 URL 特征和页面内容自动识别认证系统
   - 用对应模板测试登录
   - 全程写日志到 `logs/wizard.log`

3. **步骤3 - 配置完成**
   - 显示探测结果
   - 选项：开机自启、流量监控
   - 保存到 `config.ini`

### 探测逻辑

```
访问 http://connect.rom.miui.com/generate_204
  ↓ 被重定向？
  是 → 记录 URL + 页面内容
  ↓
URL 含 dr.com / Self/sso_login → drcom
URL 含 cas/login → cas_sso
URL 含 eportal / portal → ruijie
URL 含 srun / 页面含"深澜" → srun
页面有 <form> + password → portal
以上都不匹配 → unknown（提示手动配置）
```

### 日志设计

向导全程记录到 `logs/wizard.log`，格式：

```
[2026-06-21 19:00:01] [向导] 步骤1: 用户输入账号 20240001
[2026-06-21 19:00:02] [向导] 步骤2: 开始探测认证系统
[2026-06-21 19:00:02] [向导]   访问探测URL: http://connect.rom.miui.com/generate_204
[2026-06-21 19:00:02] [向导]   被重定向到: http://172.20.30.2:8080/Self/sso_login
[2026-06-21 19:00:02] [向导]   页面特征匹配: Dr.COM + CAS SSO
[2026-06-21 19:00:02] [向导]   选择模板: cas_sso
[2026-06-21 19:00:03] [向导]   测试登录: 成功 ✅
[2026-06-21 19:00:05] [向导] 步骤3: 配置已保存到 config.ini
```

探测失败时：

```
[2026-06-21 19:00:03] [向导]   测试登录: 失败 ❌
[2026-06-21 19:00:03] [向导]   无法自动识别，请手动配置 config.ini
[2026-06-21 19:00:03] [向导]   日志文件: logs/wizard.log（可发给开发者排查）
```

## 4. 配置文件

`config.ini`（向导自动生成，高级用户可手动编辑）：

```ini
[auth]
method = cas_sso
username = 20240001
password = your_password_here
login_url = http://172.20.30.2:8080/Self/sso_login
cas_url = https://sso.dlut.edu.cn/cas/login
detect_url = http://www.msftconnecttest.com/connecttest.txt
success_keyword = Microsoft Connect Test

[network]
wifi_ssids = DLUT-EDA, DLUT-EDA-5G
poll_interval_sec = 10

[app]
auto_start = true
traffic_monitor = true
```

## 5. 项目结构

```
campus-network-keeper/
├─ src/
│  ├─ main.py                 # 入口（--wizard / --tray / --install）
│  ├─ config.py               # 配置管理（读写 config.ini）
│  ├─ logger.py               # 日志模块
│  ├─ network_monitor.py      # 网络状态检测（通用）
│  ├─ nic_reset.py            # 网卡重置（通用）
│  ├─ wifi_switcher.py        # Wi-Fi 切换（通用）
│  ├─ keepalive.py            # 保活主循环
│  ├─ tray.py                 # 系统托盘 + 流量显示
│  ├─ wizard.py               # 首次启动向导（新增）
│  ├─ auth/
│  │  ├─ __init__.py
│  │  ├─ base.py              # 认证基类（接口定义）
│  │  ├─ detector.py          # 自动探测认证系统
│  │  ├─ drcom.py             # Dr.COM 模板
│  │  ├─ cas_sso.py           # CAS SSO 模板
│  │  ├─ ruijie.py            # 锐捷模板
│  │  ├─ srun.py              # 深澜模板
│  │  └─ portal.py            # 通用 Web Portal 模板
│  └─ scripts/
│      ├─ enable_wifi_radio.ps1
│      ├─ install.ps1
│      └─ start-tray.ps1
├─ config.ini                 # 用户配置
├─ logs/
├─ README.md
└─ LICENSE
```

## 6. 认证基类接口

```python
class BaseAuth:
    """认证模板基类"""
    def detect(self, response) -> bool:
        """判断是否匹配此认证系统"""
        ...

    def login(self, username, password, **kwargs) -> bool:
        """执行登录，返回是否成功"""
        ...

    def is_authenticated(self) -> bool:
        """检测当前是否已认证"""
        ...

    def logout(self) -> bool:
        """登出"""
        ...

    def get_traffic_info(self) -> dict:
        """获取流量信息（可选）"""
        ...
```

## 7. 用户体验流程

```
新用户下载 → 解压 → 双击 main.py
  ↓
首次？→ 启动向导（填密码 → 自动探测 → 完成）
  ↓
托盘常驻 → 自动保活 → 流量显示
  ↓
断网？→ 自动重连 Wi-Fi → 自动重新认证 → 恢复
```

## 8. 不在范围内

- Playwright 浏览器自动化（v2 考虑）
- macOS / Linux 支持
- Web 控制台
- 多账号管理

## 9. 迁移计划

从当前 DLUT 版本迁移：
1. 将 `campus_auth.py` 中的 DLUT 逻辑移到 `auth/cas_sso.py` 和 `auth/drcom.py`
2. 流量查询逻辑移到各模板的 `get_traffic_info()`
3. 网络监控、网卡重置、Wi-Fi 切换、托盘模块保持不变
4. 新增 `wizard.py` 和 `auth/detector.py`
5. 保留 DLUT 的完整兼容性

