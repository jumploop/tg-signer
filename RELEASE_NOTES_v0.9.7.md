## v0.9.7

### 改进

- **WebUI "统一运行" 独立为顶级页面**：与"配置管理"、"日志"等并列，方便一键启动/停止全部签到或监控进程
- **WebUI 群组配置并入配置管理页面**：将"群组配置"并入"配置管理"页面右侧，点击群组直接填入签到或监控配置

### 修复

- **core**：修复 `UserSigner.normal_run` 在 `while True` 循环内重复注册消息处理器，导致 handler 累积 (#1)
- **config**：修复 `MatchConfig` 缺少 `rule_value` 校验，运行时 `rule_value=None` 触发 `AttributeError`，`UserMonitor.on_message` 未捕获 (#2)
- **webui/account**：修复登录会话未清理 `core._CLIENT_INSTANCES` / `_CLIENT_REFS`，同一账号二次登录可能拿到绑定旧 loop 的 client (#3)
- **webui/runner**：修复乐观启动——子进程启动后立即失败时返回"已启动"；新增 1.5s grace + 早期失败检测；WebUI 退出时主动清理 runner 跟踪的子进程，避免孤儿进程 (#4)
- **automation/handlers**：修复 `forward` / `ai_reply.get_chat_history` 绕过 `_call_telegram_api` 限流与 FloodWait 重试 (#5)
- **_kurigram/methods**：修复 `SafeGetForumTopics.get_forum_topics` 直接调用 `self.invoke` 绕过 FloodWait 重试 (#5)
- **automation/models**：修复 `RuleStateStore.save` 非原子写入，崩溃/Ctrl-C 中途会损坏 `state.json`；损坏时备份为 `.corrupt-<ts>` 并以空状态继续 (#6)

### 测试

新增 17 个测试覆盖上述修复路径（`pytest` 177 passed / 3 skipped）。

完整变更日志：[CHANGELOG.md](./CHANGELOG.md)
