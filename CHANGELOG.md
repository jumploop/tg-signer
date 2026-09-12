# Changelog / 版本变动日志

## 版本变动日志

### 0.9.17
- 修复 WebUI「删除配置」后配置仍残留的问题:原实现只删除 `config.json` 与空目录,配置目录内遗留的旧版签到记录(按用户 ID 的子目录 / `sign_record.json`)会让目录保留,且 `list_task_names` 只按目录存在与否列配置,导致删除后配置名仍出现在下拉列表。现在 `list_task_names` 只列出真正含 `config.json` 的配置,`delete_config` 删除整个配置目录(遗留记录一并清除,签到记录主存储 SQLite 不受影响)

### 0.9.16
- WebUI 新增主题与暗色模式:Telegram 风格品牌色(`#3390ec` 主色 + 青色点缀)、卡片圆角/阴影统一、暗色模式开关(浏览器记忆偏好),Dashboard 与 Auth 页共用统一的品牌 Header;`ui.dark()` 弃用 API 改为标准 `ui.dark_mode()`
- 代码清理(ponytail 审计):`generate_random_config_name` 移除本会话去重缓存与磁盘名缓存(`_RECENTLY_GENERATED` / `_DISK_NAMES_CACHE` / `_existing_names`),改为一次性磁盘检查 + `token_hex(8)` 随机后缀(碰撞时回退 16 hex),逻辑更简单且不再依赖模块级缓存;相关测试同步删除缓存清理 fixture 并简化饱和测试
- 数据序列化去重:新增 `core.chat_to_dict`,CLI `login`、WebUI 账号登录 `_complete`、`refresh_dialogs` 三处重复的 chat 序列化字典统一复用
- CLI 选项去重:`--num-of-dialogs` 在 `signer` / `automation` / `monitor` 中的 6 处重复 `@click.option` 收敛为 `dialogs_option` 装饰器(signer 默认 50,automation/monitor 默认 20)
- `utils.py` 的 `TypeAlias` 从 `typing_extensions` 改为标准库 `typing`,移除一处第三方依赖

### 0.9.15
- 修复群组/频道下拉显示 `[object Object]` 的问题:root cause 是 NiceGUI `ui.select` 不支持 Quasar 原生 `[{"label","value"}]` dict 列表格式,改用 `{value: label}` dict 映射后正常显示群组名称

### 0.9.14
- WebUI 配置管理:「选择配置」与群组/频道下拉双向联动 —— 加载某配置后右侧自动高亮其绑定的聊天(`chats[0].chat_id` / `match_cfgs[0].chat_id`),支持按 int chat.id 或 `@username` 匹配;填入聊天后下拉框即时同步到该群组,目标聊天不在缓存时保持用户选择
- 优化 `generate_random_config_name`:新增本会话去重缓存与磁盘配置名缓存,连续/批量生成不再撞生日悖论(1000 次调用从分钟级降到约 0.5s),并补充缓存清理 fixture 与测试
- 新增 `resolve_chat_id_for_selector` 与相关参数化测试(18 个断言场景)

### 0.9.13
- WebUI 配置管理页:群组/频道从「筛选框+卡片列表」改为单个可搜索下拉框(支持按标题/类型/用户名/ID 过滤),账号下拉、刷新按钮与「填入签到/监控配置」按钮合并到一个卡片内
- 填入配置时自动生成未占用的随机配置名(如 `sign_<chat>_<hex>`),写入「保存为/新建名称」输入框,不再误覆盖当前选中的已有配置;名称冲突时循环重试,极端情况下使用更长随机后缀
- 新增 `data.generate_random_config_name` 并补充 6 个测试(前缀、slug、冲突、饱和)
- 修复早退测试 flaky,确保子进程退出后被收割
- 配置 ↔ 群组/频道双向联动:在「选择配置」下拉框加载某一配置后,右侧群组/频道下拉框自动高亮该配置已绑定的聊天(`chats[0].chat_id` / `match_cfgs[0].chat_id`);点击「填入签到/监控配置」后下拉框同样即时同步。支持按 int chat.id 或 `@username` 匹配,缺失时不干预用户手动选择

### 0.9.12
- 修复 WebUI「统一运行」一键启动同一账号下全部任务时的 `sqlite3.OperationalError: database is locked`:`runner.start` 改为按 `(kind, account)` 单进程多任务模型,同一账号的所有任务共享一个 `pyrogram.Client` 实例与同一份 SQLite session 连接,根除多子进程争抢 `<workdir>/<account>.session` 写锁
- 新增账号级文件锁 `<workdir>/<account>.lock`(`flock` / `msvcrt.locking` 跨平台),同账号的 signer 与 monitor 不会并发启动,跨 WebUI 标签页 / 跨机器也安全;锁随子进程退出自动释放
- `tg-signer monitor run` / `tg-signer automation run` 命令的 `task_name` 参数改为 `task_names` 且 `nargs=-1`,支持一次跑多个任务(单任务调用保持向后兼容)
- 重构 `runner.py`:`process_key` 从 `(kind, task)` 改为 `(kind, account)`;`build_command` / `start` / `stop` / `status` / `running_tasks` 等所有 API 接受 `tasks: List[str]`,自动拼接到 CLI 命令末尾;`shutdown_all` 同时清空 `_PROCESSES` 与 `_LOCKS`
- 重构 WebUI「统一运行」状态面板:从「每任务一行」改为「每 (类型, 账号) 一个进程一行」,列出任务数与当前 PID;停止按钮作用于一整个进程
- 移除过时的 `runner.log_path(...)` 函数(0.9.9 起所有日志统一到主日志文件,按 task 命名的日志路径不再适用)
- 新增 11 个回归测试(账号锁互斥/可重入/PID 写入/释放幂等/不同账号并行/`build_command` 多任务拼接/状态面板新 key 等)

### 0.9.11
- 修复 WebUI 统一运行反复启停累计 fd 泄漏:`runner.start` 在 `Popen` 后立即关闭父进程日志文件对象,长会话不再累积 fd 到系统上限(Windows 下同时避免日志文件无法轮转/重命名);早退路径 `child.wait()` 收割已退出子进程,避免 POSIX 僵尸进程
- 修复 `MatchConfig.match_text` 对图片/语音/贴纸/dice 等无文本消息崩溃:非 `all` 规则下文本为 `None` 时返回不匹配,不再触发 `AttributeError`
- 修复 WebUI「统一运行」一键启动同步阻塞:`start_all` 改用 `asyncio.to_thread` 调用 `runner.start`,避免 1.5s×任务数的同步启动冻结 NiceGUI 事件循环
- 将 `UIState` / `_setup_webui_logger` 从 `app` 下沉到 `data`,日志相关测试不再依赖 `nicegui`,无 GUI 依赖环境可跑完整测试
- 新增 6 个回归测试(fd 泄漏、僵尸进程收割、`match_text(None)` 参数化);无 `nicegui` 环境下跳过懒加载正向测试

### 0.9.10
- 修复无 `nicegui` 依赖环境下 `import tg_signer.webui` 失败的问题:`webui/__init__.py` 改用 PEP 562 模块级懒加载,`data` / `runner` / `account` / `auth` / `schema_utils` 等轻量子模块在未安装 `tg-signer[gui]` 时也可正常导入,`AUTH_CODE_ENV` / `build_ui` / `main` 保持按需懒加载,向后兼容
- 新增 6 个测试覆盖无 `nicegui` 环境下的懒加载导入行为(CI 默认 runner 不再需要额外安装 GUI 依赖即可跑完整测试)

### 0.9.9
- WebUI 日志统一到 `<workdir>/logs/tg-signer.log`,所有日志聚合到同一份主日志文件
  - `runner.build_command` 不再为每个任务单独传 `--log-file`,子进程统一写到主日志
  - `runner.start` 把子进程 `stdout`/`stderr` 追加到主日志,作为 file handler 的双保险(原 `DEVNULL` 方案会静默丢日志)
  - WebUI 主进程启动时调 `configure_logger`,账号登录/登出/列表刷新等操作也写文件,不再只走 stderr
  - WebUI「日志」页默认路径与子进程写入路径对齐,下拉框优先扫 `workdir/logs`
- 修复 `pyrogram` 上游升级后 `pyrogram.storage.SQLiteStorage` import 路径变化(`pyrogram.storage.sqlite_storage.SQLiteStorage`)
- 完善 `pytest-asyncio` 配置(`pyproject.toml`),允许 async fixture 不用 `@pytest.mark.asyncio` 装饰
- 新增 11 个测试覆盖日志统一行为,其中 3 个端到端测试起真子进程并用 `data.load_logs` 读回

### 0.9.8
- 修复 `tg_signer/__main__.py` 缺少 `if __name__ == "__main__"` 入口块,导致 WebUI「统一运行」页面用 `python -m tg_signer` 拉起子进程时立即退出、启动全部失败

### 0.9.7
- WebUI"统一运行"独立为顶级页面,与"配置管理""日志"等并列,方便一键启动/停止全部签到或监控进程
- 修复 `UserSigner.normal_run` 在 `while True` 循环内重复注册消息处理器,导致 handler 累积
- 修复 `MatchConfig` 缺少 `rule_value` 校验,运行时 `rule_value=None` 触发 `AttributeError`,`UserMonitor.on_message` 未捕获
- 修复 WebUI 登录会话未清理 `core._CLIENT_INSTANCES` / `_CLIENT_REFS`,同一账号二次登录可能拿到绑定旧 loop 的 client
- 修复 WebUI runner 乐观启动:子进程启动后立即失败时返回"已启动",新增 1.5s grace + 早期失败检测
- WebUI 退出时主动清理 runner 跟踪的子进程,避免孤儿进程
- 修复 automation `forward` / `ai_reply.get_chat_history` 绕过 `_call_telegram_api` 限流与 FloodWait 重试
- 修复 `SafeGetForumTopics.get_forum_topics` 直接调 `self.invoke` 绕过 FloodWait 重试
- 修复 `RuleStateStore.save` 非原子写入,崩溃/Ctrl-C 中途会损坏 `state.json`;损坏时备份为 `.corrupt-<ts>` 并以空状态继续
- WebUI:将"群组配置"并入"配置管理"页面右侧,点击群组直接填入签到或监控配置

### 0.9.6
- 修复 WebUI 账号鉴权、刷新对话与登出时的“got Future attached to a different loop”跨事件循环报错
- 修复 WebUI“刷新最近 50 个对话”缓存未真正写入、登出后 session 文件未删除的问题

### 0.9.5
- WebUI 新增“统一运行”：选择账号后可一键启动/停止全部签到或监控持续进程，日志按任务写入 <workdir>/logs/
- WebUI 群组配置页新增“刷新最近 50 个对话”，自动更新账号缓存后立即刷新列表
- 运行前校验账号 session 有效性，启动后立即退出的任务会给出日志提示
- 修复 WebUI 登录后刷新对话因客户端事件循环复用导致的报错
- 账号下拉仅列出 .session 文件账号，进程状态列表自动刷新避免闪烁

### 0.9.4
- WebUI 登录/登出改为后台线程执行，不再阻塞界面
- WebUI 登录前检测账号已登录，避免重复发送验证码
- WebUI 登出时删除账号对应的 `users/<id>` 缓存与账号映射
- WebUI 群组填入签到/监控配置基于完整模板生成，修复 `sign_at` 等必填字段校验报错
- 升级 Docker Actions：`setup-qemu`/`setup-buildx`/`login` 到 v4，`build-push` 到 v7

### 0.9.3
- WebUI 日志页自动识别工作目录下的日志文件，切换工作目录后可正确显示日志

### 0.9.2
- WebUI 新增账号管理：登录账号获取 session，登出并删除 session 文件
- WebUI 新增群组配置页：列出账号缓存的群组/频道，可快速填入签到或监控配置
- WebUI 认证加固：使用安全比较并增加失败次数锁定（5 次失败锁定 60 秒）
- WebUI 删除配置增加二次确认，日志支持自动刷新，保存后同步选中状态
- CI 升级 `actions/checkout` 到 v5、`actions/setup-python` 到 v6，规避 Node.js 20 弃用
- 修复 Windows 下 `test_initializes_defaults` 的路径断言，使测试跨平台通过

### 0.9.0
- 新增 `list-folders` 和 `--from-folder`，支持从 Telegram 普通对话 Folder 加载手动添加的对话
- 兼容 Kurigram 同步与异步论坛话题解析接口
- 修复连续动作处理中已消费消息占位导致 `wait_for` 崩溃的问题
- `根据图片选择选项` 动作支持图片与 InlineKeyboard 按钮分离的验证码场景
- 将版本变动日志从 README 移至独立的 `CHANGELOG.md`
- 监控配置支持 `send_text_template`，可将正则捕获结果或消息文本渲染到自动回复内容中
- 修复图片消息中的计算题无法识别 `caption` 的问题
- `回复计算题` 动作在存在 InlineKeyboard 选项时，会将按钮选项传给大模型并点击匹配按钮
- `根据图片选择选项` 动作会将消息文本或 `caption` 作为图片识别问题，并校验大模型返回的选项序号

### 0.8.6
- 支持 Telegram 论坛群组话题 `message_thread_id`
- 登录时可发现群组话题，新增 `list-topics` 用于查询话题 ID
- `send-text`、`send-dice`、`schedule-messages`、签到配置与 WebUI 支持发送到指定话题
- 签到记录迁移到 SQLite，新增 `list-sign-records` 与 `migrate-sign-records`
- 兼容读取旧版 `sign_record.json`，运行任务时可自动导入历史记录
- 发布官方 GHCR 镜像：`ghcr.io/amchii/tg-signer:<tag>` 与 `ghcr.io/amchii/tg-signer:<tag>-webui`
- 改进论坛群组、频道私信等场景下的话题发现与消息发送兼容性

### 0.8.5
- `kurigram>=2.2.19,<2.3.0`
- 单账户多任务时进行并发请求限流

### 0.8.4
- 新增 WebGUI
- 新增 `--log-dir` 选项，更改日志默认目录为 `logs`，warning 和 error 分为单独文件

### 0.8.2
- 支持持久化 OpenAI API 和模型配置
- Python 最小版本要求：3.10
- 支持处理编辑后的消息（如键盘）

### 0.8.0
- 支持单个账号同一进程内同时运行多个任务

### 0.7.6
- fix: 监控多个聊天时消息转发至每个聊天 (#55)

### 0.7.5
- 捕获并记录执行任务期间的所有 RPC 错误
- bump kurigram version to 2.2.7

### 0.7.4
- 执行多个 action 时，支持固定时间间隔
- 通过 `crontab` 配置定时执行时不再限制每日执行一次

### 0.7.2
- 支持将消息转发至外部端点，通过：
  - UDP
  - HTTP
- 将 kurirogram 替换为 kurigram

### 0.7.0
- 支持每个聊天会话按序执行多个动作，动作类型：
  - 发送文本
  - 发送骰子
  - 按文本点击键盘
  - 通过图片选择选项
  - 通过计算题回复

### 0.6.6
- 增加对发送 DICE 消息的支持

### 0.6.5
- 修复使用同一套配置运行多个账号时签到记录共用的问题

### 0.6.4
- 增加对简单计算题的支持
- 改进签到配置和消息处理

### 0.6.3
- 兼容 kurigram 2.1.38 版本的破坏性变更
> Remove coroutine param from run method [a7afa32](https://github.com/KurimuzonAkuma/pyrogram/commit/a7afa32df208333eecdf298b2696a2da507bde95)

### 0.6.2
- 忽略签到时发送消息失败的聊天

### 0.6.1
- 支持点击按钮文本后继续进行图片识别

### 0.6.0
- Signer 支持通过 crontab 定时
- Monitor 匹配规则添加 `all` 支持所有消息
- Monitor 支持匹配到消息后通过 server 酱推送
- Signer 新增 `multi-run` 用于使用一套配置同时运行多个账号

### 0.5.2
- Monitor 支持配置 AI 进行消息回复
- 增加批量配置「Telegram 自带的定时发送消息功能」的功能

### 0.5.1
- 添加 `import` 和 `export` 命令用于导入导出配置

### 0.5.0
- 根据配置的文本点击键盘
- 调用 AI 识别图片点击键盘

## Changelog

### 0.9.15
- Fix the group/channel picker showing `[object Object]`: the root cause was NiceGUI `ui.select` not supporting Quasar's native `[{"label","value"}]` list-of-dicts format; switching to a `{value: label}` dict mapping makes channel names display correctly

### 0.9.14
- WebUI config page: two-way sync between the "select config" dropdown and the group/channel picker — loading a config auto-highlights its bound chat (`chats[0].chat_id` / `match_cfgs[0].chat_id`), matching by int chat.id or `@username`; picking a group immediately syncs the picker, and an unknown chat keeps the user's selection
- Optimize `generate_random_config_name` with an in-session dedup cache and a disk-name cache: bulk generation no longer hits the birthday paradox (1000 calls dropped from minutes to ~0.5s), plus cache-reset fixtures and tests
- Add `resolve_chat_id_for_selector` with parametrized tests (18 assertion scenarios)

### 0.9.13
- WebUI config page: the group/channel picker is now a single searchable dropdown (filter by title/type/username/ID) instead of a filter box plus a card list; the account dropdown, refresh button and the "fill signer/monitor config" buttons are merged into one card
- Filling a config now auto-generates an unused random config name (e.g. `sign_<chat>_<hex>`) into the "save as / new name" input, so it never overwrites the currently selected config; it retries on name collisions and falls back to a longer random suffix in the worst case
- Add `data.generate_random_config_name` plus 6 tests (prefix, slug, collision, saturation)
- Fix flaky early-exit tests and ensure child processes are reaped

### 0.9.12
- Fix `sqlite3.OperationalError: database is locked` when the WebUI "Unified Run" page launches all tasks for the same account: `runner.start` now uses a `(kind, account)` single-process, multi-task model so every task of one account shares the same `pyrogram.Client` and SQLite session connection, eliminating cross-process contention on `<workdir>/<account>.session`
- Add per-account file lock `<workdir>/<account>.lock` (cross-platform via `flock` / `msvcrt.locking`): signer and monitor for the same account can no longer start concurrently; safe across WebUI tabs and across machines; the lock is released automatically when the child process exits
- `tg-signer monitor run` / `tg-signer automation run` now accept `task_names` (`nargs=-1`) instead of `task_name`, so multiple tasks can be run in one invocation (single-task callers are still supported)
- Refactor `runner.py`: `process_key` is now `(kind, account)` instead of `(kind, task)`; `build_command` / `start` / `stop` / `status` / `running_tasks` all take `tasks: List[str]` and append them to the CLI command; `shutdown_all` clears both `_PROCESSES` and `_LOCKS`
- Refactor the WebUI "Unified Run" status panel: one row per `(kind, account)` process instead of one row per task, showing the task count and PID; the Stop button now acts on a whole process
- Drop the obsolete `runner.log_path(...)` helper (since 0.9.9 every log goes to the unified main log file, per-task log paths no longer exist)
- Add 11 regression tests (lock mutual exclusion, reentrancy, PID write, idempotent release, parallel accounts, multi-task `build_command`, status panel under the new key, etc.)

### 0.9.11
- Fix fd leak in the WebUI unified runner: `runner.start` closes the parent-side log file object right after `Popen`, so repeated start/stop cycles no longer accumulate FDs up to the OS limit (and no longer block log rotation/rename on Windows); the early-exit path now uses `child.wait()` to reap exited children, avoiding zombie processes on POSIX
- Fix `MatchConfig.match_text` crashing on text-less messages (images, voice, stickers, dice): non-`all` rules now return `False` when text is `None` instead of raising `AttributeError`
- Fix the WebUI "start all" button blocking the event loop: `start_all` now calls `runner.start` via `asyncio.to_thread` so the sequential 1.5s×N startup no longer freezes the NiceGUI UI
- Move `UIState` / `_setup_webui_logger` from `app` into `data` so logging tests no longer require `nicegui` and the full suite runs without the GUI extra
- Add 6 regression tests (fd leak, zombie reaping, parametrized `match_text(None)`); skip the positive lazy-loading test in environments without NiceGUI

### 0.9.10
- WebUI package no longer requires NiceGUI at import time: `tg_signer/webui/__init__.py` uses a PEP 562 lazy module-level `__getattr__`, so the lightweight submodules (`data`, `runner`, `account`, `auth`, `schema_utils`) import cleanly without the `tg-signer[gui]` extra, while `AUTH_CODE_ENV` / `build_ui` / `main` remain lazily loaded for backward compatibility
- Add 6 tests covering lazy-import behavior in environments without NiceGUI (CI default runners can now run the full suite without the GUI extra)

### 0.9.9
- WebUI logging unified to `<workdir>/logs/tg-signer.log`; every log entry — WebUI process, child processes, and runner subprocess `stdout`/`stderr` — now lands in the same main log file
  - `runner.build_command` no longer passes `--log-file`; child processes write to the default main log
  - `runner.start` appends child `stdout`/`stderr` to the main log as a fallback (replacing the previous `DEVNULL` which silently dropped logs when the file handler was misconfigured)
  - `webui.app.main()` calls `configure_logger` at startup so WebUI-internal actions (login, logout, list refresh) are written to disk, not just stderr
  - The WebUI "Logs" tab default path now matches where child processes actually write; the dropdown prioritises `workdir/logs`
- Fix `pyrogram` upstream import path change: `pyrogram.storage.sqlite_storage.SQLiteStorage`
- Tighten `pytest-asyncio` config (`pyproject.toml`) so async fixtures work without per-test `@pytest.mark.asyncio` decorators
- 11 new tests including 3 end-to-end ones that spawn real child processes and read them back through `data.load_logs`

### 0.9.8
- Fix `tg_signer/__main__.py` missing the `if __name__ == "__main__"` entry block, which made the WebUI "Unified Run" page spawn child processes via `python -m tg_signer` that exited immediately, failing every start

### 0.9.7
- WebUI: split "Unified Run" out as a top-level tab alongside "Config" and "Logs" for one-click start/stop of all signer/monitor processes
- Fix `UserSigner.normal_run` re-registering message handlers on every scheduler tick, causing handler accumulation over time
- Fix `MatchConfig` missing `rule_value` validation, which raised `AttributeError` at runtime when `rule_value` was None (and `UserMonitor.on_message` did not catch it)
- Fix WebUI login session not clearing `core._CLIENT_INSTANCES` / `_CLIENT_REFS`, so a second login of the same account could receive a client bound to a closed loop
- Fix WebUI runner optimistic startup: a child process that exited immediately after start was reported as "started"; add 1.5s grace and early-exit detection
- WebUI now actively terminates runner-tracked child processes on shutdown to avoid orphans
- Fix automation `forward` and `ai_reply.get_chat_history` bypassing `_call_telegram_api` rate-limiting and FloodWait retry
- Fix `SafeGetForumTopics.get_forum_topics` calling `self.invoke` directly, bypassing FloodWait retry
- Fix `RuleStateStore.save` non-atomic write, which could corrupt `state.json` on crash/Ctrl-C; on corrupt read, back the file up as `.corrupt-<ts>` and continue with empty state
- WebUI: move the "Groups" picker into the right pane of the "Config" tab so a group/chat can be selected and applied to the signer/monitor config directly

### 0.9.0
- Add `list-folders` and `--from-folder` to load manually added chats from regular Telegram folders
- Support both synchronous and asynchronous Kurigram forum topic parsers
- Fix `wait_for` crashes caused by consumed message placeholders during multi-action flows
- Support captcha flows where the image and InlineKeyboard buttons are sent as separate messages for `ChooseOptionByImageAction`
- Move the changelog out of README files and into standalone `CHANGELOG.md`
- Add `send_text_template` support for monitor configs, allowing regex captures or message text to be rendered into automatic replies
- Fix calculation questions in image messages not being detected from `caption`
- When `ReplyByCalculationProblemAction` sees InlineKeyboard options, pass those options to the LLM and click the matching button
- Pass message text or `caption` as the image-recognition question for `ChooseOptionByImageAction`, and validate the returned option index

### 0.8.6
- Support Telegram forum group topics via `message_thread_id`
- Discover group topics during login, and add `list-topics` for querying topic IDs
- `send-text`, `send-dice`, `schedule-messages`, check-in configuration, and WebUI now support sending to a specific topic
- Migrate check-in records to SQLite, and add `list-sign-records` plus `migrate-sign-records`
- Keep compatibility for reading the old `sign_record.json`, and auto-import legacy records when running tasks
- Publish official GHCR images: `ghcr.io/amchii/tg-signer:<tag>` and `ghcr.io/amchii/tg-signer:<tag>-webui`
- Improve compatibility for topic discovery and message delivery in forum groups, channel DMs, and similar scenarios

### 0.8.5
- `kurigram>=2.2.19,<2.3.0`
- Add concurrent request throttling when multiple tasks run under a single account

### 0.8.4
- Add WebGUI
- Add the `--log-dir` option, change the default log directory to `logs`, and split warning and error logs into separate files

### 0.8.2
- Support persistent OpenAI API and model configuration
- Minimum supported Python version is now 3.10
- Support handling edited messages (for example, updated keyboards)

### 0.8.0
- Support running multiple tasks in the same process for a single account

### 0.7.6
- Fix: when monitoring multiple chats, forwarded messages are delivered to each target chat correctly (#55)

### 0.7.5
- Capture and log all RPC errors during task execution
- Bump kurigram to version 2.2.7

### 0.7.4
- Support fixed intervals when executing multiple actions
- Remove the once-per-day limitation when scheduling with `crontab`

### 0.7.2
- Support forwarding messages to external endpoints through:
  - UDP
  - HTTP
- Replace kurirogram with kurigram

### 0.7.0
- Support executing multiple actions sequentially for each chat session. Supported action types:
  - Send text
  - Send dice
  - Click a keyboard button by text
  - Select an option by image
  - Reply to a math question

### 0.6.6
- Add support for sending DICE messages

### 0.6.5
- Fix shared check-in records when multiple accounts run with the same configuration

### 0.6.4
- Add support for simple math questions
- Improve check-in configuration and message handling

### 0.6.3
- Compatible with the breaking change introduced in kurigram 2.1.38
> Remove coroutine param from run method [a7afa32](https://github.com/KurimuzonAkuma/pyrogram/commit/a7afa32df208333eecdf298b2696a2da507bde95)

### 0.6.2
- Ignore chats where sending a check-in message fails

### 0.6.1
- Support continuing with image recognition after clicking a button by text

### 0.6.0
- Add crontab scheduling to Signer
- Add the `all` rule to Monitor for matching all messages
- Add ServerChan push support for Monitor
- Add `multi-run` so multiple accounts can run with one shared configuration

### 0.5.2
- Monitor supports AI-based replies
- Add batch configuration for Telegram's built-in scheduled messages

### 0.5.1
- Add `import` and `export` commands for configuration import/export

### 0.5.0
- Click keyboard buttons based on configured text
- Use AI to recognize images and click keyboard buttons
