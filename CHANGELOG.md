# Changelog / 版本变动日志

## 版本变动日志
### 0.10.11
- **feat: 把后端实际使用的工作目录打进日志**：`server._log_workdir()` 在服务启动与 `POST /api/state` 切换工作目录时各写一行 `WebUI 工作目录[启动|切换 旧 ->]: workdir=... | log_path=... | cwd=... | 是否绝对路径=...`，写入 `<workdir>/logs/tg-signer.log`。此前「基础设置」显示的目录与后端实际读写的目录只能靠猜，现在 grep 这一行即可核对
- 背景：代码侧已确认后端只有 `state.workdir` 一个数据源，不存在「显示 A 实际读 B」的双数据源问题。剩余最可能的成因是线上 Python 进程未随 `git pull` 重启（静态产物每请求读磁盘，后端代码在内存里），故提供可观测手段
- 测试：新增 `test_workdir_is_logged_on_startup_and_switch`（覆盖启动行与切换行，断言 workdir / log_path 与实际一致）

### 0.10.10
- **fix: 切换工作目录后，基础设置显示的「主日志路径」与实际写入位置不一致**：日志 handler 在进程启动时按当时的 workdir 绑定（`server._setup_logger()`），`POST /api/state` 切换目录后只改了 `state.workdir` / `state.log_path`，没有重绑 handler。结果是页面显示新目录的 `log_path`，日志却仍写进旧目录，**新目录的 `logs/` 甚至根本不会被创建** —— 切到全新目录时日志页必然空白，基础设置显示的主日志路径也成了假路径。现 `set_state()` 在切换后重新调用 `_setup_webui_logger(state.workdir)`
- 已核对：所有读写接口（配置、自动化、签到记录、用户信息、群组、账号登录、日志）均显式传入 `state.workdir` / `state.log_path.parent`，不存在回落到 `data.LOG_DIR`（相对 `logs`）的情况
- 测试：新增 `test_switch_workdir_rebinds_log_file_to_new_dir`（已验证：回退 `set_state()` 的重绑即失败）

### 0.10.9
- **fix: 日志页仍然空白（v0.10.8 的真正根因）**：`get_workdir()` 原样返回传入的路径，而 `DEFAULT_WORKDIR` 默认是相对的 `.signer`，于是 `UIState.log_path` 变成相对路径 `.signer/logs/tg-signer.log`。`/api/logs/files` 把这个相对路径发给前端，前端再原样回传给 `/api/logs`，`resolve_log_under()` 按「相对 logs/ 根目录」再拼一次 → 必然越界 → **400** → 前端 `catch` 把内容清空。实测默认 workdir 下 `/api/logs`（连不带 `path` 的默认请求）也是 400，整页永远空白。现 `get_workdir()` 统一返回绝对路径
- **fix: `tg-signer webgui` 完全无视全局 `--workdir`**：`webgui` 子命令只把 host/port 传给 `main()`，没接 `ctx.obj["workdir"]`，WebUI 永远读 CWD 下的 `.signer`。CLI 指定了工作目录、日志却在别处时，页面当然什么都没有。现 `main()` 新增 `workdir` 参数，内部调用 `UIState.init_workdir()`（不走 WebUI 的工作目录白名单 —— 那条白名单约束的是远程切换动作，CLI 操作者本就拥有该机器的完整文件权限）
- `/api/logs` 未指定 `path` 时不再强行回落到主日志，改为交给 `_resolve_log_path()` 选「非空 + 最新」的文件
- 前端：文件列表加载后若已自动选中文件，不再额外重复请求一次日志
- 此前所有日志用例都传绝对路径 `tmp_path`，从未覆盖「相对 workdir」这条线上真实路径 —— 这也是前两轮修复全部落空的原因。新增 `test_logs_work_with_relative_workdir`（已验证：回退 `get_workdir()` 即失败）、`tests/test_cli_webgui_workdir.py::test_webgui_passes_workdir_to_main`

### 0.10.8
- **fix: 日志页整页空白（v0.10.7 只修了表象）**：真正原因有两层。其一，`webui/runner.py` 为避免多个子进程的 `RotatingFileHandler` 互相截断，把任务日志写到 `<workdir>/logs/<kind>-<account>/tg-signer.log` 子目录，但 `data.list_log_files()` 用 `glob("*.log")` **不递归** —— 所有真正有内容的任务日志一个都列不出来。其二，顶层 `tg-signer.log` 靠 WebUI「运行」页启动任务时的 stdout 重定向写入，纯 CLI 签到时是 0 字节，前端默认选中逻辑正好落到它身上，页面显示「暂无日志内容」。现改为 `rglob` 递归列举 + 按「非空优先、mtime 倒序」排序，前端取第一个作为默认项；`/api/logs` 未指定 `path` 时同样回退到该最佳文件而非主日志
- **fix: 子目录日志列得出来却读不了**：0.10.4 收紧 P1-1 任意文件读取时，`utils.resolve_within()` 只允许 `root` 的直接子项，导致 `logs/<kind>-<account>/tg-signer.log` 被 400「路径越界」拒绝。现新增 `utils.resolve_log_under()`：允许一层子目录，但强制 `.log` 后缀，越界与符号链接逃逸仍拒；`resolve_within` 本身不动（仍有其它调用方，放宽它等于把 `*.session_string` / `.openai_config.json` 重新暴露给 `?path=`）
- WebUI 日志下拉框改为展示相对 `logs/` 的路径（如 `signer-demo/tg-signer.log`）而非纯文件名 —— 子目录日志与主日志同名，只显示文件名分不清谁是谁
- 测试：新增 `test_list_log_files_includes_task_subdirectories`、`test_list_log_files_puts_non_empty_and_recent_first`、`test_load_logs_reads_task_log_in_one_level_subdirectory`、`test_load_logs_rejects_paths_outside_allowed_log_shape`（越深/越界/非 `.log` 三类负向）、`test_load_logs_without_path_falls_back_to_non_empty_log`、`test_logs_expose_task_logs_from_subdirectories`；`e2e/logs.mjs` 改为覆盖子目录日志场景
- **安全修复**：WebUI 授权码爆破防护形同虚设。`require_auth()` 是全部受保护端点的依赖，但它只**检查**锁定状态、**从不记账**，`record_auth_failure()` 只挂在 `/api/auth/login` 上 —— 攻击者改打任意受保护端点携带猜测的 Bearer 即可完全绕开限流（实测 30 次错误请求无一被锁、计数存储始终为空）。现把记账移入 `require_auth()` 的错误分支，任何携带错误凭据的请求都参与「连续 5 次锁定 60 秒」计数
- **安全修复**：锁定机制可被用于拒绝服务。失败计数是模块级全局单例，且登录端点「先锁后验」，导致锁定期内**正确的授权码同样被 429** —— 未认证者每 60 秒发 5 个错误请求（无需知道授权码）即可把合法用户永久锁在门外。现改为「先验后锁」：凭据正确直接放行（不受锁定期影响），错误才记账并触发限流；触发上限的那次请求也会直接返回 429（旧实现要等下一次请求才生效）
- **安全加固**：授权码比较改用 `secrets.compare_digest()`（编码为 bytes 后比较，避免非 ASCII 输入触发 `TypeError`），消除字符串短路比较的时序侧信道
- 测试语义同步：`test_auth_login_locks_out_after_max_attempts` 原本断言「锁定期内正确授权码也 429」，正是被推翻的 DoS 语义，已改写；新增 `test_protected_endpoints_record_auth_failures`（堵爆破绕过）、`test_correct_credential_is_exempt_from_lockout`（堵锁定 DoS）、`test_non_ascii_authorization_header_is_rejected_not_crash` 三条判别性用例

### 0.10.7
- **fix: WebUI 日志页一进来就是空白**：`/api/logs/files` 按文件名升序返回，而前端取 `files[files.length - 1]` 作为默认选中项，恰好落到 `warn.log` 这类空文件上，页面直接显示「暂无日志内容」，看起来像日志功能整体失效。现改为优先选主日志 `tg-signer.log`，没有主日志时退回第一个；实测其它接口与渲染均正常，手动切换文件也能正常显示
- 日志文件下拉框改为只显示文件名，不再展示完整绝对路径（绝对路径仍作为请求参数回传，不影响后端路径校验）
- 新增浏览器回归测试 `e2e/logs.mjs`，接入 `npm run test:e2e` 与 CI 的 e2e job

### 0.10.6
- **fix: WebUI 升级后整页白屏**：`/` 与 `/assets/*` 此前都没有 `Cache-Control`，浏览器按 `Last-Modified` 做启发式缓存。Vite 每次构建按内容 hash 重命名 chunk（例如 `Configs-D3OhaQpj.js` -> `Configs-DeKRQTYv.js`），被缓存的旧 `index.html` 仍指向升级后已删除的 chunk，入口 JS 404 导致整页白屏。现 `index.html` 发 `Cache-Control: no-cache, must-revalidate` 强制回源校验，带 hash 的 chunk 发 `public, max-age=31536000, immutable` 长期缓存
- 新增回归测试 `test_index_disables_cache_and_assets_are_immutable` 锁定上述两条缓存头

### 0.10.5
- **仅文档更新，无代码变更**：`docs/security_audit_2026-09-29.md` 新增第七轮审计（§13），补齐历轮未覆盖的前端源码 / WebUI 认证实现 / docker 部署配置三块，新发现 3 项 P2、2 项 P3（P2-18 爆破防护形同虚设、P2-19 锁定可被用于 DoS、P2-20 docker 以 root 运行且 compose 引用不存在的 `start.sh`、P3-9 授权码非常量时间比较、P3-10 令牌即授权码）。本版本未修复这些发现，修复方向见 §13.8
- 同时复验两项 P1 修复仍然生效（`/api/logs?path=` 越界返回 400；`account` 目录穿越被 `resolve_under()` 拒绝），并记录了 `data.py:_check_workdir()` 这处此前未记载的纵深防御

### 0.10.4
- **安全修复**：`GET /api/logs?path=` 任意文件读取。此前该参数原样接受任意绝对路径，可直接读出 `<workdir>/*.session_string`、`.openai_config.json` 乃至 `~/.ssh/id_rsa`。现限定为只能读 `<workdir>/logs` 下的文件（前端回传的绝对路径仍然可用），越界返回 400。修复见 `docs/security_audit_2026-09-29.md`
- **安全修复**：`account` 与配置名未归一化导致的目录穿越。`/api/accounts/logout`、`/api/accounts/send-code`、`/api/chats/fetch`、`/api/run/start` 传 `../x` 可在 workdir 之外创建锁文件、删改任意文件。现统一由 `tg_signer.utils.resolve_under()` 校验为单一路径分量，数据层与 HTTP 层一致拒绝
- **安全修复**：WebGUI 绑定非回环地址且未设置授权码时改为拒绝启动（fail-closed）。此前 `--host 0.0.0.0` 会让上述接口在整个网络无鉴权开放，现在必须同时提供 `--auth-code` 或 `TG_SIGNER_GUI_AUTHCODE`
- **安全修复**：`GET /api/llm-config` 明文回显 API Key。现只返回掩码（如 `****1234`），明文不再离开服务端；保存时「留空」或「原样回填掩码」都表示不修改已有密钥（前端即使把回显值原样提交也不会覆盖真实密钥），「测试连通性」在密钥留空时回退到服务端已保存的密钥
- **安全修复**：`POST /api/state` 可把工作目录切到任意路径，既能任意建目录，又会让插件加载指向非预期目录（`<workdir>/handlers/*.py` 会被 `exec_module` 执行）。现限定为只能切到白名单根目录之下，默认是启动时工作目录的父目录，可用 `TG_SIGNER_WEBUI_WORKDIR_ROOTS`（`os.pathsep` 分隔）放宽；越界直接 400 且**不会创建目录**
- **健壮性修复**：`data.sqlite3` 并发写入失败。多账号并存时连接不设 `timeout`/WAL，冷启动 6/8、稳态 5/8 线程抛 `database is locked`；而 `sqlite3.Error` 不是 `OSError`，会逃逸出 `normal_run` 的异常捕获把签到任务打死。现启用 `timeout=30s` + `busy_timeout` + WAL（并发切换 WAL 时的 `SQLITE_BUSY` 容错重试），并把 `persist_sign_record()` 的存储异常降级为警告
- **健壮性修复**：Automation 的 `timer_loop` 无异常隔离，一次异常即让所有 timer 规则永久停摆且无告警。现循环体内部捕获异常继续轮询，并给 `create_task` 加完成回调记录异常退出
- **健壮性修复**：`_call_telegram_api()` 的 FloodWait 退避在 `async with lock` 内部等待，而 FloodWait 常见数百秒，会把同一个 client 的所有任务（包括其它 chat 的签到）串行阻塞。现把退避移出锁外；限流间隔的等待仍留在锁内，保证并发调用继续被串行化
- **健壮性修复**：大模型输出异常击穿签到主循环。`choose_option_by_image()` 遇到非 JSON / 缺 `option` 字段 / `option` 非整数 / 空 `content` 时抛 `KeyError`/`TypeError`，`get_reply()` 可能返回 `None`，两者都会打死整个任务。现分别收敛为 `-1` 与 `""`，并把 `sign_once()` 的异常捕获从 `errors.RPCError` 放宽为「单个 chat 失败只跳过该 chat」
- **安全修复**：`*.session_string` 与 `.openai_config.json` 未收紧权限。两者默认按进程 umask 落盘（POSIX 下常见 0644），同机其他用户可直接读到账号凭据与 API Key。现新增 `restrict_file_permissions()`，在 `save_session_string()` 与 `OpenAIConfigManager.save_config()` 落盘后把文件收紧为 `0600`。刻意做成 best-effort：非 POSIX 平台与 `chmod` 失败都只返回 `False`，不让登录 / 保存失败
- **安全修复**：硬编码的共享 `api_id` / `api_hash` 被所有未设环境变量的用户共用（同一应用配额、风控关联）。现内置值为默认回退并**明确 warning 一次**。未改成 fail-fast，否则会直接打断所有既有部署的启动
- **安全修复**：自动化规则的 `text_value` 模板可借 `str.format_map` 的属性链逃逸取值（如 `{message.__class__.__mro__}`）。现改用 `_SafeTemplateFormatter`，拒绝下标访问、属性链深度 > 2、以及任何以 `_` 开头或为空的字段段
- **安全修复**：自动化规则里的正则无长度与形态约束，灾难性回溯会卡死事件循环（CPython 的 `re` 在回溯期间不释放 GIL，线程超时也打不断）。现新增 `safe_regex_search()`：pattern 上限 512、subject 上限 8KB（超长截断而非拒绝），并用「star height ≥ 2」形状检查挡掉「量词套量词」。判别性实证：朴素 `re.search(r"(a+)+$", "a"*24 + "!")` 需 1.98s，新护栏 0.0000s 抛 `ValueError`；正则非法 / 超长时三处调用点统一降级为「不匹配」，不打断整条规则链
- **安全修复**：WebUI 子进程的代理凭据原先经 `--proxy` 进 argv，同机可被 `ps` / 任务管理器读到。现改为通过 `TG_PROXY` 环境变量传递（CLI 本就有该 `envvar`，无需改 CLI）
- **健壮性修复**：WebUI 登录会话无过期。每账号一个 daemon 线程 + 独立 event loop + 一个 Client，用户 `send_code` 后直接关页面就会永久驻留。现加 10 分钟 TTL 并由 `send_login_code` / `complete_login` 入口顺手回收
- **健壮性修复**：`get_ai_tools()` 每条消息新建一个 `AITools`，每次都泄漏一个 httpx 连接池且从不 `close()`。现改为惰性创建后缓存复用
- **健壮性修复**：`Client.__aenter__` 抛非 `ConnectionError` 异常时 `_CLIENT_REFS` 已 +1 却不回滚，引用计数永久漂移。现补 `except BaseException` 回滚后再 `raise`（保留「连接失败仍算可用」的既有语义）
- **健壮性修复**：编辑消息的忙等可永久自旋。`wait_for()` 里的 action 若抛异常，`sign_a_chat` 中的 `waiting_message = None` 不会执行，该消息的编辑事件此后永远自旋。现把复位动作放进 `finally`
- **健壮性修复**：`sign_once` 闭包捕获外层循环的 `now`，跨轮次会串值；`_validate_sign_at()` 返回 `Optional[str]`，非法时会把 `None` 传进 `croniter` 抛 `TypeError`（且不在被捕获集合内）。现 `sign_at` 提前求值并在不可用时明确报错，`now` 改为参数传入
- **健壮性修复**：WebUI 多处模块级可变状态被 FastAPI 线程池并发读写。`runner.py` 的进程 / 锁 / 任务名字典、`server.py` 的鉴权失败计数、`data.py` 的 logger 配置、`account.py` 的登录会话注册表现已各自加锁；其中鉴权「判断锁定 + 记一次失败」收进同一把锁，此前读-改-写分离可被并发绕过「连续 5 次锁定 60 秒」
- **健壮性修复**：子进程日志路径不一致。此前只传 `--log-dir`，子进程按 CLI 的默认相对 `--log-file` 另建 `logs/`，且多个子进程的 `RotatingFileHandler` 并发轮转同一 `warn.log` / `error.log` 会互相截断。现显式传 `--log-file <workdir>/logs/<kind>-<account>/tg-signer.log`，每个子进程独立目录
- **健壮性修复**：`data.sqlite3` 每次读写都漏关连接。`sqlite3.Connection` 的上下文管理器只提交/回滚事务、**不关闭连接**，而被沿用的 7 处 `with self._connect() as conn:` 都依赖它收尾，连接只能等 gc 兜底才释放（实测 30 次 `upsert_record()` 后仍有 30 个连接存活，`gc.collect()` 才归零）。单次调用看不出问题，多账号并发时会同时压着大量已打开的库与 WAL / `-shm` 句柄。现新增 `SignRecordStore._connection()` 把「事务 + 关闭」收敛为唯一入口（`finally: conn.close()`，事务语义与原先一致；`_connect()` 本身行为不变，仍返回裸连接），7 处调用点一并切换
- **行为变更**：配置 `version` 字段现在真正参与分发，配置文件中也会写入它。此前 `version` 是 `ClassVar`，既不参与 `model_dump`（磁盘上从来没有版本号）也无一处被读取，导致校验失败时只能报**当前**版本的字段错误 —— 一份缺 `sign_text` 的 V1 配置会被告知「缺 `chats`」，让人去补一个完全不相干的字段。现在 `to_jsonable()` 会写入 `version`，`load_checked()` 在配置声明了版本时优先按声明的版本校验并迁移（例如 chats 里同时有 `sign_text` 与 `actions` 时按 V2 迁移、用 `sign_text` 重建动作，而不是当成 V3 接受），全部失败时改报声明版本的字段错误。**写错的 `version` 不会拒掉原本能读的配置**：声明分支走不通时仍会回落到原有的 `olds` 回溯链
- **健壮性修复**：WebUI 关闭登录会话时跨模块、无锁地直接 pop `tg_core` 的私有容器（`_CLIENT_INSTANCES` / `_CLIENT_REFS`）。现新增 `core.forget_client()` 作为模块外回收 client 状态的唯一入口，顺带回收 `_API_LAST_CALL_AT`（限流时间戳，引用归零后已无意义）；`Client.__aexit__` 在引用归零时也一并回收。刻意**不清理** `_CLIENT_ASYNC_LOCKS` / `_LOGIN_ASYNC_LOCKS` / `_API_ASYNC_LOCKS`：它们是同一个 key 互斥的唯一凭据，清掉之后并发的 `__aenter__` 会各自新建一把锁、同时进入临界区
- **可维护性**：自动化引擎与 `config.TriggerConfig` 各写了一份触发器类型清单（`"startup"` / `"timer"` / `"message"`），config 新增类型而引擎没跟上就会变成「配置合法、规则永不触发」。现引擎侧收敛为 `SUPPORTED_TRIGGER_TYPES` 单一清单，三处重复的 `trigger.type != "..."` 过滤收敛为 `_iter_triggers()`（同时保留原下标，`trigger_id` 依赖它作为 `state.json` 的键），并新增 CI 漂移守卫测试 —— 从 `TriggerConfig` 的 union 反解出全部 `Literal` 类型后与引擎清单比对，任一侧漏改即失败
- **可维护性**：WebUI 的配置类型元数据原先散在两张表里 —— `CONFIG_META` 管「目录名 + 配置类」、`NAME_PREFIXES` 管「随机名前缀」，而 `automation` 只存在于后者。新增一种配置类型必须记得同时改两张表，漏一张就是运行期 KeyError。现合并为 `CONFIG_KINDS: dict[NameGenKind, ConfigKindMeta]`（`cfg_cls` / `name_prefix` / `dir_name`），并新增 `uses_dir_layout()` 把「走 `signs/` 目录布局」与「在表里」两件事区分开 —— 合并后这两个判据不再等价，`server.py` 的 4 处「不支持的配置类型」守卫必须用前者，否则 `automation` 会被放行到一个不存在的目录上
- **界面体验**：WebUI 的 LLM 配置把服务端回显的密钥掩码（如 `****1234`）当作值回填进密码框，用户无法分辨「已配置」与「这是真实密钥」，点开 `show-password` 还会露出一串形如坏掉的 `****1234`。现改为留空 + 占位符说明（已配置时显示「已配置（****1234），留空表示不修改」），仅在用户真的输入新密钥时才提交该字段；服务端本就把空值视为「不修改已有密钥」，无需改动。此改动需一并重建随仓库分发的 `webui/static/` 产物，并新增 `test_llm_config_ui_leaves_the_stored_key_blank` 守卫「源码改了但产物未重建」
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
