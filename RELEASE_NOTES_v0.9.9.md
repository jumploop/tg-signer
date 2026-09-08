## v0.9.9

### 中文

- WebUI 日志统一到 `<workdir>/logs/tg-signer.log`,所有日志聚合到同一份主日志文件
  - `runner.build_command` 不再为每个任务单独传 `--log-file`,子进程统一写到主日志
  - `runner.start` 把子进程 `stdout`/`stderr` 追加到主日志,作为 file handler 的双保险(原 `DEVNULL` 方案会静默丢日志)
  - WebUI 主进程启动时调 `configure_logger`,账号登录/登出/列表刷新等操作也写文件,不再只走 stderr
  - WebUI「日志」页默认路径与子进程写入路径对齐,下拉框优先扫 `workdir/logs`
- 修复 `pyrogram` 上游升级后 `pyrogram.storage.SQLiteStorage` import 路径变化(`pyrogram.storage.sqlite_storage.SQLiteStorage`)
- 完善 `pytest-asyncio` 配置(`pyproject.toml`),允许 async fixture 不用 `@pytest.mark.asyncio` 装饰
- 新增 11 个测试覆盖日志统一行为,其中 3 个端到端测试起真子进程并用 `data.load_logs` 读回

### English

- WebUI logging unified to `<workdir>/logs/tg-signer.log`; every log entry — WebUI process, child processes, and runner subprocess `stdout`/`stderr` — now lands in the same main log file
  - `runner.build_command` no longer passes `--log-file`; child processes write to the default main log
  - `runner.start` appends child `stdout`/`stderr` to the main log as a fallback (replacing the previous `DEVNULL` which silently dropped logs when the file handler was misconfigured)
  - `webui.app.main()` calls `configure_logger` at startup so WebUI-internal actions (login, logout, list refresh) are written to disk, not just stderr
  - The WebUI "Logs" tab default path now matches where child processes actually write; the dropdown prioritises `workdir/logs`
- Fix `pyrogram` upstream import path change: `pyrogram.storage.sqlite_storage.SQLiteStorage`
- Tighten `pytest-asyncio` config (`pyproject.toml`) so async fixtures work without per-test `@pytest.mark.asyncio` decorators
- 11 new tests including 3 end-to-end ones that spawn real child processes and read them back through `data.load_logs`
