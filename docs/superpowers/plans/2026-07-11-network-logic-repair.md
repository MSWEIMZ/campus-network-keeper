# Network Logic Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复校园网保活工具的状态误判、认证选择、恢复策略和托盘生命周期问题。

**Architecture:** 让网络采集返回可信快照，以 `KeepAlive` 为唯一恢复策略控制器，并把托盘缩减为状态展示和人工操作适配器。认证类型仅在发现 Portal 时选择，所有恢复动作按接口执行。

**Tech Stack:** Python 3.10+、requests、pytest、unittest.mock、Windows netsh/Mutex

---

### Task 1: 网络状态判定

**Files:**
- Modify: `src/network_monitor.py`
- Test: `tests/test_network_monitor.py`

- [ ] 增加 302 不算在线、英文 Disconnected 不算已连接、探测冲突返回认证状态的失败测试。
- [ ] 运行定向测试并确认按预期失败。
- [ ] 精确解析接口状态，并让互联网探针只接受预期成功响应。
- [ ] 运行网络状态测试并确认通过。

### Task 2: 认证器延迟选择

**Files:**
- Modify: `src/auth/detector.py`
- Modify: `src/campus_auth.py`
- Test: `tests/test_auth_detector.py`
- Create: `tests/test_campus_auth.py`

- [ ] 增加在线时不锁定 Dr.COM、发现 Portal 后才缓存认证器的失败测试。
- [ ] 运行定向测试并确认失败原因正确。
- [ ] 区分 ONLINE、UNREACHABLE、UNKNOWN，并实现可重试的延迟初始化。
- [ ] 运行认证测试并确认通过。

### Task 3: 单一保活状态机

**Files:**
- Modify: `src/keepalive.py`
- Modify: `src/tray.py`
- Create: `tests/test_keepalive.py`

- [ ] 增加同状态防抖、状态切换清零、按接口恢复和以太网稳定切回测试。
- [ ] 运行定向测试并确认失败。
- [ ] 将单次 tick、恢复结果和状态通知集中到 `KeepAlive`，托盘调用同一控制器。
- [ ] 运行保活与托盘测试并确认通过。

### Task 4: 托盘生命周期与重启

**Files:**
- Modify: `src/tray.py`
- Test: `tests/test_tray.py`

- [ ] 增加 tooltip、退出标志、无学校域名硬编码和 Mutex 释放顺序测试。
- [ ] 运行定向测试并确认失败。
- [ ] 恢复 tooltip 方法、初始化退出状态、删除 DLUT DNS 前置检查，并封装单实例锁生命周期。
- [ ] 运行托盘测试并确认通过。

### Task 5: 完整验证与提交

**Files:**
- Modify: `README.md`（仅在行为说明需要同步时）

- [ ] 运行 `pytest -q`，确认全部测试通过。
- [ ] 运行 `python -m compileall -q src tests`，确认退出码为 0。
- [ ] 检查 `git diff --check` 和 `git status --short`，确认没有混入账号、日志或用户脚本。
- [ ] 按网络判定、认证、状态机、托盘生命周期拆分提交。
