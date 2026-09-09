## v0.9.12

### 中文

- 修复 WebUI「统一运行」一键启动同一账号下全部任务时的 `sqlite3.OperationalError: database is locked`: `runner.start` 改为按 `(kind, account)` 单进程多任务模型,同一账号的所有任务共享一个 `pyrogram.Client` 实例与同一份 SQLite session 连接,根除多子进程争抢 `<workdir>/<account>.session` 写锁
- 新增账号级文件锁 `<workdir>/<account>.lock` (`flock` / `msvcrt.locking` 跨平台),同账号的 signer 与 monitor 不会并发启动,跨 WebUI 标签页 / 跨机器也安全;锁随子进程退出自动释放
- `tg-signer monitor run` / `tg-signer automation run` 命令的 `task_name` 参数改为 `task_names` 且 `nargs=-1`,支持一次跑多个任务 (单任务调用保持向后兼容)
- 重构 `runner.py`: `process_key` 从 `(kind, task)` 改为 `(kind, account)`; `build_command` / `start` / `stop` / `status` / `running_tasks` 等所有 API 接受 `tasks: List[str]`,自动拼接到 CLI 命令末尾; `shutdown_all` 同时清空 `_PROCESSES` 与 `_LOCKS`
- 重构 WebUI「统一运行」状态面板:从「每任务一行」改为「每 (类型, 账号) 一个进程一行」,列出任务数与当前 PID;停止按钮作用于一整个进程
- 移除过时的 `runner.log_path(...)` 函数 (0.9.9 起所有日志统一到主日志文件,按 task 命名的日志路径不再适用)
- 新增 11 个回归测试 (账号锁互斥/可重入/PID 写入/释放幂等/不同账号并行/`build_command` 多任务拼接/状态面板新 key 等)

### English

- Fix `sqlite3.OperationalError: database is locked` when the WebUI "Unified Run" page launches all tasks for the same account: `runner.start` now uses a `(kind, account)` single-process, multi-task model so every task of one account shares the same `pyrogram.Client` and SQLite session connection, eliminating cross-process contention on `<workdir>/<account>.session`
- Add per-account file lock `<workdir>/<account>.lock` (cross-platform via `flock` / `msvcrt.locking`): signer and monitor for the same account can no longer start concurrently; safe across WebUI tabs and across machines; the lock is released automatically when the child process exits
- `tg-signer monitor run` / `tg-signer automation run` now accept `task_names` (`nargs=-1`) instead of `task_name`, so multiple tasks can be run in one invocation (single-task callers are still supported)
- Refactor `runner.py`: `process_key` is now `(kind, account)` instead of `(kind, task)`; `build_command` / `start` / `stop` / `status` / `running_tasks` all take `tasks: List[str]` and append them to the CLI command; `shutdown_all` clears both `_PROCESSES` and `_LOCKS`
- Refactor the WebUI "Unified Run" status panel: one row per `(kind, account)` process instead of one row per task, showing the task count and PID; the Stop button now acts on a whole process
- Drop the obsolete `runner.log_path(...)` helper (since 0.9.9 every log goes to the unified main log file, per-task log paths no longer exist)
- Add 11 regression tests (lock mutual exclusion, reentrancy, PID write, idempotent release, parallel accounts, multi-task `build_command`, status panel under the new key, etc.)