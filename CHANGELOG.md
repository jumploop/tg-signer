# Changelog / 版本变动日志

## 版本变动日志
### 0.10.3
- WebUI「群组/频道 → 复制到配置」改为优先写入群组/频道的数字 ID（此前固定写 `@username`），仅在拿不到 ID 时才退回用户名
- 修复 Automation 规则的 `chat_id` 为数字字符串时规则永不触发且不报错：`_match_chat` / `_normalize_user_id` 只对 `int` 做数字比较，字符串会落进 `@username` 分支。新增 `normalize_chat_ref()` 归一化纯数字字符串为 `int`（`@username` 保持字符串），并在 `MessageTriggerParams` / `TimerTriggerParams` / `StartupTriggerParams` / `FilterConfig` 上通过 `ChatRefsMixin` 于解析阶段统一处理
- WebUI「复制到配置」为 Signer 配置自动填写群组任务名（优先标题、其次用户名）与随机 `random_seconds`（100~1000）；仅在新建时填写，编辑已有配置不覆盖用户已填的群组名与延迟
- WebUI「复制到配置」为 Automation 配置同步锁定过滤器 `filters.chat_id`，避免其他群的消息也命中该规则
- `generate_random_config_name()` 支持 `automation` 类型（`auto_<slug>_<hex>`），`GET /api/configs/{kind}/suggest-name` 的守卫由 `CONFIG_META` 改为 `NAME_PREFIXES`，修复 automation 类型的 400 报错
- 配置校验错误现在透出字段明细：此前所有失败都是无信息的「配置校验失败」。`BaseJSONConfig` 新增 `load_checked()` 返回 `(cfg, migrated, err)` 并通过 `format_validation_error()` 输出 `字段路径: 原因`，`load()` 委托它以保持 V1/V2/V3 兼容链唯一实现；WebUI 读写与 CLI 加载路径均已接入
- 修复 `sign_at` 不校验的问题：此前 `sign_at` 写任意字符串都能保存成功，运行时再把 `None` 传给 `croniter` 崩溃。新增 `normalize_sign_at()` 校验并由 `SignConfigV3` 的 field validator 接入（只校验不改写，存量配置不会被静默重写）
- 修复 V1 老配置永远不会被迁移：`BaseJSONConfig.load_checked()` 遍历 `olds` 时只做一层校验，`SignConfigV3` 在 V2 处断链导致 V1 格式无法升级。改为递归 `old.load_checked(d)`，V1 → V2 → V3 现可完整走通

### 0.10.2
- 修复 WebUI 复制按钮在非安全上下文下必然失败：`navigator.clipboard` 只在 HTTPS 或 localhost 存在，通过局域网 IP 以 HTTP 访问（如 `http://192.168.x.x:8080`）时为 `undefined`。新增 `copyText()` 统一处理，安全上下文走异步剪贴板，否则降级为隐藏 textarea + `document.execCommand('copy')`。群组/频道「复制ID」与日志「复制日志」均已修复
- WebUI 群组/频道「复制到配置」现在会自动生成配置名（`sign_<标题>_<hex>` 形式）。此前只填入 `chat_id`，名称留空导致保存时提示「请填写配置名称」。自动命名仅在新建模式下生效，不会覆盖已填名称或正在编辑的配置
- 新增 `GET /api/configs/{kind}/suggest-name`，对外暴露此前已存在但无任何调用方的 `generate_random_config_name()`
- 新增浏览器回归测试 `tg_signer/webui/frontend/e2e/clipboard.mjs`（Playwright），同时覆盖安全上下文与非安全上下文两条复制分支；CI 新增 `e2e` job，纯 Node 执行、不依赖 Python，复用 runner 自带 Chrome

### 0.10.1
- 修复 WebUI 线上白屏：前端入口 bundle 的 `__vite__mapDeps` 引用了两个从未提交的构建产物（`index-AwMIY2pU.js` / `index-BQVSlQXh.js`），导致登录视图动态 import 404、页面渲染为空白。现已补齐并随包发布
- 新增回归测试 `test_static_assets_referenced_by_entry_are_committed`，校验入口 chunk 引用的每个静态资源都已提交，防止构建产物再次漏提交
- 修复 `OpenAIConfig` 在 Python 3.10 / 3.11 下触发 `PydanticUserError` 的问题（改用 `typing_extensions.TypedDict`），恢复 3.10 / 3.11 的 CI 测试矩阵

### 0.10.0
- 移除 legacy `monitor` 子系统：删除 `UserMonitor` 类、`tg-signer monitor` 命令组、`MonitorConfig` / `MatchConfig` 配置模型，以及 WebUI 的 Monitor 配置类型与任务运行入口；消息监控、转发与自动回复统一由 `tg-signer automation` 提供
- `UserMonitor.udp_forward` / `http_api_callback` 迁入 `tg_signer/automation/handlers.py` 作为模块级函数，`external_forward` handler 行为不变
- 磁盘上已有的 `<workdir>/monitors/` 目录不再被读取，需按 README 迁移对照表改写为 automation 规则
- WebUI 前端整体重做：侧栏布局、主题样式与各功能页（账号、群组/频道、用户、签到记录、日志、基础设置等）统一刷新
- README / README_EN 大幅精简，监控相关内容改为 automation 迁移对照说明

### 0.9.5
- WebUI 改为前后端分离架构：后端 FastAPI 提供 REST API 并托管静态产物，前端基于 Vue 3 + Vite（源码在 `tg_signer/webui/frontend/`，构建产物随包发布到 `tg_signer/webui/static/`）
- 移除 NiceGUI 依赖与旧单体页面，`tg-signer[gui]` 现在只依赖 `fastapi` / `uvicorn`
- 新增后端 REST API 冒烟测试与 FastAPI 懒加载测试
- WebUI 新增「交互式配置向导」：分步表单快速创建签到配置（基础设置 + 多签到任务、多动作），替换旧 NiceGUI 向导
- WebUI 界面整体重塑：深蓝 + 电报蓝主题与纸飞机品牌形象，登录页、侧栏导航、按钮层级与空状态等全站视觉统一重设计
- WebUI 配置管理新增 Automation 配置编辑：支持读取 `config.json` / `config.yaml` / `config.yml`（JSON 优先）、模板初始化、校验保存与删除
- Automation 默认模板对齐 CLI 示例结构（`demo_message_reply`，含完整 trigger params / filters / handlers / vars），可直接保存运行
- WebUI 任务运行页任务名改为从配置列表多选；同一账号同类型的多个任务合并到一个子进程运行，共享 Client 以避免 SQLite session 文件锁冲突
- WebUI 移除 legacy Monitor 入口（配置管理与任务运行页均不再提供 Monitor），统一推荐使用 `tg-signer automation` 管理自动化规则
- WebUI 群组/频道页新增「复制到配置」：一键将群组/频道 ID 填入 Signer 或 Automation 配置对应字段，并自动跳转到配置管理页
- WebUI 群组/频道页「读取缓存」补充 loading 状态与空缓存/失败提示，空状态文案给出明确操作引导
- 修复 WebUI 群组/频道过滤失效：`latest_chats.json` 中 CLI 登录写入的 `ChatType.BOT` 等枚举形式类型此前会被整份丢弃，现统一归一化为小写名称（WebUI 登录写入的 `bot` 形式同样兼容）
- 签到动作 `wait_for` 默认超时由 10 秒提升至 30 秒，给 Telegram API 慢响应与 FloodWait 重试更大余量
- WebUI 任务运行页新增任务「全选」，并展示每个运行中进程实际执行的任务名（后端 `/api/run` 新增 `task_names` 字段）

### 0.9.4
- 修复 `OpenAIConfigManager.has_config()` 判定逻辑，改为环境变量与本地配置任一存在即视为已配置
- 修复 `AITools.calculate_problem()` 在模型返回 `content=None` 时崩溃的问题
- 修复自动化 `_match_user` 过滤漏洞，无发送者（频道帖、服务消息）的消息不再命中 `from_user_ids` 过滤
- WebUI 支持纯 `.session_string` 账号的实时获取对话与登出流程，`_new_client` 自动切换内存会话，下拉框一并纳入该类账号


### 0.9.3
- WebUI 账号管理新增 LLM 连通性测试，调用 OpenAI 兼容接口的模型列表接口验证 API 配置（含 base_url / model）
- WebUI 新增实时获取对话列表，可选择账号实时拉取最近对话，不写入本地缓存


### 0.9.2
- WebUI 新增账号管理：支持账号登录/登出、会话可用性检查、`.session`/`.session_string` 会话识别、登录验证码与二次登录流程
- WebUI 监控新增基于正则去重的对话选择与配置生成，新增 `resolve_chat_id_for_selector` 与 `generate_random_config_name` 辅助
- `ai_reply` 统一走 worker 侧限流与 FloodWait 重试，`forward` 与历史消息解析不再逐条裸调用
- 兼容 Kurigram 同步与异步论坛话题解析，修复 markup-only 动画图片与计算题 `caption` 识别
- 修复连续动作处理中已消费消息占位导致 `wait_for` 崩溃的问题
- `根据图片选择选项` 动作支持图片与 InlineKeyboard 按钮分离的验证码场景
- 修复 WebUI 登录日志文件滚动、账号数据持久化、Schema 校验与初始化等若干问题
- 测试覆盖 WebUI 账号、鉴权、数据、日志与自动化动作

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

### 0.9.2
- WebUI account management: login/logout, session availability checks, `.session`/`.session_string` session detection, login verification codes, and re-login flows
- WebUI monitor: chat selection with regex-based deduplication and config generation, with `resolve_chat_id_for_selector` and `generate_random_config_name` helpers
- `ai_reply` now goes through worker-side throttling and FloodWait retries; `forward` and history message parsing no longer make bare per-item calls
- Compatible with both synchronous and asynchronous Kurigram forum topic parsers; fix recognition of markup-only animated images and calculation question `caption`
- Fix `wait_for` crashes caused by consumed message placeholders during multi-action flows
- Support captcha flows where the image and InlineKeyboard buttons are sent as separate messages for `ChooseOptionByImageAction`
- Fix several WebUI issues including login log file rotation, account data persistence, schema validation, and initialization
- Add/update unit tests covering WebUI accounts, auth, data, logs, and automation actions

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
