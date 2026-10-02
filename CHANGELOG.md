# Changelog / 版本变动日志

## 版本变动日志
### 未发布
- **fix: `migrate-sign-records` 中途失败会同时丢掉 JSON 和数据库里的记录（最严重的一处）**：`unlink()` 排在遍历循环里、`commit()` 排在循环之后，而 `with conn` 异常时回滚。于是「第一个文件已删 → 处理后面某个文件时抛 `PermissionError`」的结果是源文件已被删除、刚写入的行又被回滚 —— 记录两边都不存在，且没有备份。Windows 上文件被 WebUI/编辑器/杀软短暂占用是家常便饭，实测 3 个文件的迁移能一次丢 2 个。现改为两阶段：先把全部行写入并 `commit()`，**再**删源文件；删不掉的文件如实报告（`undeleted_files`），不影响已经落库的记录
- **fix: `tg-signer run` 只有第一天能正常签到**：`normal_run` 把 `add_handler` 写在 `while True` **之前**，而 pyrogram 的 `Client.__aexit__` 在引用计数归零时会 `stop()`，`stop()` 默认 `clear_handlers=True` → `dispatcher.groups.clear()`。每轮都重新 `async with self.app`，于是第一轮结束后消息回调被清空且再也不会注册回来：第二轮起机器人回复没有任何 handler 接手，所有点击/回复动作只能干等 30s 超时。而 WebUI 起的正是 `run`（`webui/runner.py` 不带 `--in-memory`），两条入口一起中招。现新增幂等的 `_ensure_message_handlers()`，每轮进入 client 后按需补注册（`add_handler` 是无条件 append，重复调用会产出重复回调）
- **fix: 机器人没回复（等满 30s 超时）被当成签到成功并写入记录**：`wait_for` 的超时路径和成功路径都 `return None`，`sign_a_chat` 无条件记「处理完成」，而 `sign_once` 只靠异常判定失败 —— 于是最常见的失败模式（按钮没出现 / 点了没反应）会被记成今日已签到，`run-once` 退出 0、当天不再重试，也让「全部 chat 均失败」的守卫形同虚设。现 `wait_for` / `sign_a_chat` 返回 bool，动作链没走完就中止该 chat 的后续动作并不计入成功
- **fix: 点击被 Telegram 拒绝却报告为点击成功**：`request_callback_answer` 把 `BadRequest` / `TimeoutError` 吞掉只记一条 ERROR 日志并隐式返回 `None`，而三个调用方（`click_keyboard_by_text` / `reply_by_calculation_problem` / `choose_option_by_image`）全部无条件 `return True`。`MESSAGE_ID_INVALID`、`BUTTON_DATA_INVALID`、`QUERY_ID_INVALID`、`MESSAGE_TOO_OLD` 这些「按钮其实没点中」的情况一律被当成成功。现改为返回 bool 并向上传播
- **fix: `delete_after` 删除失败把一次成功的签到判为失败**：`messages.DeleteMessages` 在群里无删除权限时抛 `MESSAGE_DELETE_FORBIDDEN`（很常见），异常冒泡出 `send_message` → `sign_a_chat` → `sign_once` 的 `except`。此时消息已送达、机器人也已登记：`run-once` 退出码 1（cron/监控误报），`run` 则每 60 秒重发一次签到消息刷屏。现删除失败只记告警、不影响签到结果；`delete_after` 写成 `"5"` 这类字符串时原先会在**投递之后**抛 `TypeError`，现统一规整并对无法解析的值告警跳过
- **fix: ReDoS 护栏可被一层多余的括号绕过**：`)` 后没有量词时，`has_superlinear_quantifier` 把「组内已有无上限量词」的标记直接丢弃，于是 `((a+))+$`（与 `(a+)+$` 语义完全相同）不再被拦。CPython 的 `re` 在回溯期间不放 GIL 也无法中断，实测 27 个字符的文本就能卡死事件循环约 24 秒。现把标记继承给父组
- **fix: ReDoS 护栏漏掉「顺序量词」**：`\d+\d+$`、`\w+\w+`、`.*.*` 这类 star height 只有 1，却是二次回溯 —— 实测 `\d+\d+$` 在 2000 字符上要 12.8s，而 Telegram 允许 4096 字符的单条消息（约 53s）。`extract_regex` / `blacklist_filter` 在 async handler 里同步调用 `re.search`，期间整个引擎（所有账号、所有定时器、pyrogram 的 update 分发）全部停摆。现按字符类别判定两个无上限量词是否可能匹配同一段文本：`a+b+`、`\d+\.\d+`、`(\d{1,3}\.){3}\d{1,3}` 这类有字面分隔符的写法仍然放行
- **fix: 自动化状态文件被暂时占用就当损坏处理，counter/余额全部丢失**：`RuleStateStore.load` 把 `OSError` 与「内容损坏」混为一谈 —— `PermissionError`（杀软扫描、云盘按需下载、另一个进程持有句柄、网络盘）几乎都是暂时性的，原实现却先把真实的 `state.json` 改名成 `.corrupt-<ts>`（备份不会自动恢复），再以空状态继续，于是下一次 `save()` 就把空 buckets 写回去，所有 `interval_seconds` 定时器还会立刻重新触发。现 `OSError` 改为短暂重试后抛出并**保留原文件**，只有真正的 JSON/形状错误才备份
- **fix: 模板渲染失败时把未渲染的模板原文发进群里**：`render_template` 的 `except Exception: return text` 不留任何日志，而调用方直接把它 `send_message` 出去。最典型的是文档里的 `{message.chat.title}` 用在 `startup`/`timer` 触发器上（这两类事件 `message is None`，`chat` 也就是 `None`）—— 群里收到一条字面量 `{message.chat.title}`，日志里一条告警都没有。现渲染失败抛 `TemplateRenderError`；变量名写错（`SafeFormatDict.__missing__` 原样返回 `{nope}`）同样能识别。正文里本来就带花括号的（HTTP 回调的 JSON body）仍原样放行
- **fix: `store_state(keys=[...])` 把尚未产生的变量写成 `null`，模板随后发出字符串 "None"**：`ctx.vars.get(k)` 没有默认值，未产生的键被存成 `None`；下一轮 `load_state` 把 `None` 灌回 `ctx.vars` 后该键就「存在」了，`SafeFormatDict.__missing__` 不再兜底，`str(None)` 被渲染并发送。现只持久化已经存在的键
- **fix: `blacklist_filter` 在 `source_var` 写错时静默失效（fail-open）**：`resolve_blacklist_text` 对不存在的变量返回空串，而空串什么都匹配不到 —— 过滤器不拦任何东西，后面的 `send_text` 照样把大模型输出发进群。文档里 `ai_reply(store_var)` → `blacklist_filter(source_var)` → `send_text` 这条链，只要 `store_var` 写错一个字母，「广告/引流」过滤就完全不起作用且没有任何提示。现改为失败关闭：抛 `ValueError` 中止该规则，不发任何内容
- **fix: 切换工作目录后仍存活的登录会话会把登录态写进旧目录**：`prune_login_sessions()` 只回收超过 `LOGIN_SESSION_TTL_SECONDS`（600s）的会话，而「发验证码 → 切目录 → 粘贴验证码」这条最常见的路径里会话只有几秒大。于是 `complete-login` 把 `.session`、`users/<id>/` 缓存和 `webui_accounts.json` 全写进刚切走的旧目录，并如实返回「登录成功」，而当前目录里这个账号根本不存在。现改为回收全部会话
- **fix: `POST /api/state` 的回滚会撤销另一个请求已成功的切换**：`set_state` 是无锁的「快照 → 切换 → 重绑日志」，而它是同步端点、跑在 Starlette 线程池里。A 线程切到 W2 后日志重绑失败，B 线程此时成功切到 W3 并已把 W3 返回给前端，A 再执行 `state.workdir = previous` 就把整个服务打回 W1 —— 前端显示 W3、服务端干的是 W1，之后配置保存、任务启动、日志读取、账号会话全部落在错误目录且不报错。现整段加锁
- **fix: `GET /api/run` 不按工作目录过滤，列出的任务点「停止」永远失败**：`process_key` 已按 `<workdir>|<kind>:<account>` 作用域化，但 `running_tasks()` 返回时把 workdir 剥掉了；`run_stop` 又用**当前** `state.workdir` 去解析 key。切目录后旧目录里仍在跑的任务继续显示为「运行中」，而每一行的「停止」都只回一句「未在运行」。现按 workdir 过滤
- **fix: `DELETE /api/configs/...` 删除失败仍返回 `{"ok": true}`**：`shutil.rmtree(..., ignore_errors=True)` 吞掉 Windows 上「文件被占用」导致的失败，前端于是弹出「已删除」，列表一刷新配置又回来了。现删除失败抛 `OSError`，接口映射为 409 并带上真实原因
- **fix: FastAPI 自动生成的 `/docs`、`/redoc`、`/openapi.json` 不需要访问码**：`docs_url`/`redoc_url`/`openapi_url` 默认公开，且不挂 `require_auth`。设了 `TG_SIGNER_GUI_AUTHCODE` 并 `--host 0.0.0.0` 时，同网段任何人无需任何凭据就能拿到完整 API 端点地图（而且图里连 Bearer 认证方案都没声明）。现全部关闭
- **fix: 授权码的「连错 N 次锁定」对在线猜解几乎无效**：每个请求都是「先比对、后判锁定」，因此正确的那个猜测无论锁定期内外都能通过 —— 攻击者以行速率持续试探，任何一个正确的都被接受（4 位码约 1 万次），锁定反而确认了服务端确实在校验。现给登录端点加最小请求间隔限速（已认证的客户端不会再走这个端点，不影响正常使用）
- **fix: `llm-config` 保存 API Key 不是原子写**：`save_config` 直接 `open(path, "w")` —— 打开即截断，磁盘满/进程被杀/被安全软件打断时用户已保存的 Key 就变成空文件或半截 JSON，且没有备份。WebUI 其它写都走「临时文件 + `os.replace`」，唯独这个存密钥的文件被漏掉。现改为原子写，并在改名**之前**先收紧临时文件权限
- **fix: `sign_at` 里的 UTC 偏移被静默丢弃**：`normalize_sign_at("06:00:30+08:00")` 返回 `"0 6 * * * 30"`，偏移不见了；而调度时刻最终按 `get_now()` 的时区（`TZ` → 本地 → 默认）解释，于是 `TZ=UTC` 的机器上本该 +08:00 的签到会提前 8 小时触发，没有任何提示。现直接拒绝带偏移的写法并说明改用 `TZ`
- **fix: legacy JSON 迁移会覆盖更新鲜的运行期记录**：ON CONFLICT 曾是无条件 DO UPDATE，跑一遍 `migrate-sign-records`（升级后的清理步骤，且默认保留 JSON 文件、用户会反复跑）就把重叠的那些天改写成 JSON 里的旧时间戳、把 `account` 抹成 `NULL`、`source` 从 `runtime` 翻成 `json_migrated`，多账号归属和精确签到时刻都没了。现只有更新的记录才覆盖
- **fix: 迁移计数虚报**：`migrated_records` 返回的是交给 `executemany` 的行数，而不是真正写入的行数 —— 对已迁移过的数据再跑一次仍报「迁移 1 条」。用户没法据此判断「是不是都迁完了」。现返回实际变更行数
- **fix: 损坏的 legacy `sign_record.json` 被静默跳过且不计入 `skipped_files`**：`load_json_records` 对坏文件返回 `{}`，随后直接 `continue` —— CLI 于是打印「迁移文件数 0 / 迁移记录数 0」而没有任何告警，用户以为迁移干净了，这些记录其实永远不会被迁移也永远不会被告知。现计入 `skipped_files`（损坏的文件绝不会被删），并单独报告「已迁移但 JSON 副本删不掉」的文件
- **fix: Server酱通知失败在规则侧完全看不出来**：`sc_send` 直接 `return response.json()`，而 `server_chan` handler 根本不检查返回值 —— SendKey 写错时 Server酱用 HTTP 200 + 非 0 `code` 表示业务失败，规则日志里只有一条 DEBUG，用户根本没收到通知；被网关拦截返回 HTML 时则抛一个看不出原因的 `JSONDecodeError`。现 HTTP 非 2xx、响应非 JSON、响应体带非 0 `code` 三种失败都显式抛异常
- **fix: `get_forum_topics` 在 FloodWait 重试后返回重复 topic**：`topics = []` 建在闭包**外面**，而 `get_forum_topics` 是异步生成器、可能迭代到一半才抛 FloodWait，`_call_telegram_api` 会重新调用闭包，于是结果变成 `1,2,3,1,2,3`（`list-topics` 与登录时的 topic 预览都重复打印）。同文件的 `login` 里等价写法就建在闭包内部。现对齐
- **fix: `Client.__aexit__` 在 `stop()` 抛错时泄漏 client 并打死守护进程**：`except ConnectionError` 抓不到 `sqlite3.OperationalError`（`stop()` → `terminate()` → `storage.save()` → commit，库被占用时抛的正是它），于是两行 pop 被跳过、异常继续冒泡到 `normal_run` 的 `except (OSError, errors.Unauthorized)` 之外。现清理无条件走完
- **fix: `delay: .inf` 永久占死一条规则**：非有限值能通过 `if seconds > 0`，`asyncio.sleep(inf)` 永不返回；而该 task 一直持有 `async with self._rule_lock(rule.id)`，于是这条规则之后的所有触发都排在它后面，规则对进程生命周期而言等于死亡，日志里没有任何错误。现跳过非有限值并对超长等待按上限截断
- **fix: `random_pick` 的 `choices` 写成字符串时发的是单个字符**：YAML `choices: "hello world"` → `list(str)` 把整串拆成字符，于是「随机发一条消息」变成随机发一个字母，而日志看起来完全正常。现字符串按单个选项处理、映射取其值，均记告警
- **fix: 插件在导入时 `sys.exit()` 会带走整个进程的自动化任务**：`load_plugins` 的 `except Exception` 抓不到 `SystemExit`/`KeyboardInterrupt`，异常直接穿过它，而 `UserAutomation.run` 调用它时没有任何保护 —— 一个坏插件文件（残留的顶层 `main()`、import 到会调 `sys.exit` 的库）就能让进程里所有任务一起消失。现按「加载失败」跳过该文件
- **fix: `state.json.tmp` 是固定名，多进程写同一任务目录会互相覆盖**：两个 `automation run` 共写同一个临时文件，一边截断、另一边随后 `os.replace`，会把一个被截断的 `state.json` 装上去（下次 load 直接判损坏并清空）；Windows 上还表现为周期性 `PermissionError`。现临时文件名带 pid 与线程 id
- **fix: Windows 上并发保存 `state.json` 偶发失败（`WinError 5`）**：`os.replace` 要求目标文件当前没有任何未共享删除的打开句柄，而引擎的 `load()` 用的正是 `open(path, "r")`。同一进程里定时器回调与消息 handler 的 `save()`/`load()` 一交错就抛 `PermissionError`，状态这一轮的进度直接丢掉。现补上与 `webui/data.py::_write_json_atomic` 相同的有限次退避重试
- **fix: UDP 转发错误用 `print` 输出，tg-signer 日志文件里看不到**：`print` 只到 stdout，在打包后的 CLI / `multi-run` 下通常没有可见控制台，「转发地址不可达」这类问题彻底无声。现改用 logger
- **fix: WebUI 打开一个旧版配置就把它改写，纯读操作产生写副作用**：`load_config` 在检测到 `from_old` 时会 `save_config(...)` 回写。于是「打开配置」「列表页」这类纯读也会改磁盘 —— 只读挂载或无写权限时明明已经读成功却抛 `OSError`，页面整个 500；而且每次读都把配置文件截断重写一次。这既与同文件的 `load_automation_config` 不一致（那边只标记不回写），也与前端自己的提示文案冲突（文案写的是「保存时将写入新格式」）。现读路径不再回写，迁移落盘交给用户显式保存时完成
- **fix: WebUI 保存配置会让并发读到半个 JSON**：写配置是 `open(path, "w")` —— 打开即截断再流式写，而 WebUI 是 FastAPI 线程池并发的，截断到写完之间的窗口里任何并发读都会读到截断 JSON 并抛 `JSONDecodeError`（表现为「配置损坏」）；进程写入途中被杀则留下同样的残缺文件，而配置是用户唯一的真相。现改为「临时文件 + `os.replace`」
- **fix: Windows 上并发读配置会让保存直接失败（`WinError 5`）**：`os.replace` 要求目标文件当前没有任何未共享删除的打开句柄，而 Python 的 `open(path, "r")` 恰好不共享删除 —— 同一进程里一个正在读配置的线程就能让保存抛 `Access denied`。现配置读写共用 `_CONFIG_LOCK`
- **fix: `os.replace` 对刚写完的文件偶发 `Access denied`**：新建/落盘的临时文件可能被实时扫描或索引器短暂独占，`MoveFileEx` 直接失败（并发保存下实测必现）。现加了有限次退避重试
- **fix: 同账号并发「发送验证码」留下孤儿登录会话**：`send_login_code` 的「弹出旧会话」与「登记新会话」是两次独立加锁，中间夹着 `close()`（要 join 线程，最多 5s）和会话构造（要起线程）两次慢操作。两个并发请求（重复点按钮）各自建一个会话，后登记的直接覆盖先登记的 —— 被覆盖的那个既离开了 `LOGIN_SESSIONS` 又永远不会被 `close()`，线程 / event loop / Telegram 连接三重泄漏；而用户拿到的是第二个验证码，用第一个必然失败。现整段按账号串行（每账号一把锁，不用全局锁以免连累其它账号），并在登记失败时兜底关闭
- **fix: 一条规则对同一条消息最多执行一次 handler 链**：遍历时对每个命中的 trigger 各跑一遍，同一群的 `chat_id` 同时写成 `-100123` 和 `@mychannel` 两种形式就会自动回复两次（第二次往往是用户刚收到的回声）。现每条规则只取第一条命中的 trigger 执行，其余记 DEBUG
- **fix: 规则链里的 `delay` 会阻塞整个账号的更新流**：pyrogram 的 `Dispatcher.handler_worker` 是在**唯一一个** worker 协程里 `await handler.callback(...)`，原来 `on_message` 直接内联 `await` 规则链 —— 一条 `delay: 300` 的规则能让所有群的所有消息停摆 5 分钟（`forward` / `ai_reply` 同理）。现派发到独立 task，退出时统一取消；异常由新增的 done 回调取出并记录（否则会重演「Task exception was never retrieved」式的静默失败）
- **fix: 同一规则的并发执行丢状态更新**：带 `timer` + `message` 触发的规则会被 pyrogram 的各条更新 task 与 `timer_loop` 同时进入，两边各自读到同一份旧 `vars`、`+1` 后回写，counter 只 +1。现每条 rule 一把 `asyncio.Lock`，串行化「读 → 改 → 回写」
- **fix: `run` / `multi-run` 抛裸 traceback，且失败后不取消兄弟任务**：`run_coroutines` 只捕获 `ChatFolderError`，其余异常直接打穿 CLI；`asyncio.gather` 抛第一个异常时其它协程仍在后台跑着，随后 loop 被关闭，它们要么被 `RuntimeWarning` 静默丢弃，要么在半应用状态上继续发消息。现整体 cancel + 回收，异常统一转 `ClickException`；两个调用点补上 `loop.close()`
- **fix: WebUI 并发登录丢失账号映射条目**：`save_account_user` 是无锁的读-改-写，两个账号同时登录完成时都读到同一份旧映射、各自整份写回，后写者抹掉前者的条目（实测 8 个并发只剩 2 个）。现加锁把「读 → 改 → 写」做成临界区，并改为「临时文件 + `os.replace`」原子落盘
- **fix: 每个 WebUI 登录会话泄漏一个未关闭的 event loop**：`close()` 停了线程和 `run_forever`，却没关 loop，反复登录/重登会持续堆积（Windows 上各占一个 select 句柄）。另外 `_AccountLoginSession.__init__` 在 `get_client()` **之前**就启动了线程，client 构造失败时线程与 loop 双重泄漏 —— 现改为构造成功后再启动线程，并在 `close()` 里关闭 loop
- **fix: `stop` 在 kill 后仍 wait 不到时抛裸 `TimeoutExpired`**：账号锁与注册表项都不清理，HTTP 层返回 500 + traceback，而该账号被永久占住、后续 `start()` 一直被拒。现清理后返回一条「未能确认退出，请手动检查该进程」的提示
- **fix: 插件里的同步 handler 被注册进注册表**：`load_plugins` 只校验 `callable`，同步函数直到规则执行到它才在引擎里抛 `object str can't be used in 'await' expression` —— 报错里既没有插件文件名也没有 handler 名。现加载期即拒绝并警告
- **fix: `blacklist_filter` 的非字符串关键词崩溃**：YAML 里不带引号的 `- 123` 解析成 `int`，`kw.lower()` 抛 `AttributeError`，而且发生在 handler 链执行途中（前面的 handler 已经跑过了）。现跳过并告警
- **fix: Server酱 sendkey 区分大小写导致发错主机**：`sctp` 前缀大小写写错会被当成普通 key 发到 `sctapi.ftqq.com`，用户收到一个莫名的 `sendkey` 错误；`sctp` 开头但不含数字段则直接 `raise ValueError`，让整条通知失败。现不区分大小写匹配，无数字段时回落到旧主机
- **fix: `list-schedule-messages` 的日志压制是空操作**：`logging.root.setLevel(WARNING)` 完全无效 —— `configure_logger` 给 `tg-signer` logger 设了 `propagate = False`，它的记录根本不会冒泡到 root。现改为直接设置该 logger 的等级
- **fix: 多群签到时，后面还没轮到的群收到的消息被静默丢弃**：`sign_chats` 原本边处理边登记，只含「正在处理的那个 chat」。在 A 群等待键盘的 30s 里，B 群机器人推来的消息会因为 `sign_chats` 里还没有 B，被 `_on_message` 判成「意料之外的聊天」直接丢弃（handler 已按 `filters.chat(chat_ids)` 放行，不会再有第二次机会）；等真正轮到 B 时那条消息早没了，B 必然等满 timeout 签到失败，日志里只留一行「忽略意料之外的聊天」。现改为本轮开始时先把**所有** chat 的路由解析并登记进 `sign_chats`，再逐个处理
- **fix: `run-once` 全部 chat 失败仍以退出码 0 结束**：`sign_once` 全失败时不落库也不抛异常，`normal_run` 直接 `break`，`run_worker` 又只转换 `ChatFolderError` —— cron/监控只看到「成功」，而当天不会再重试、记录里也查不到，漏签完全无声。现 `normal_run`/`in_memory_run`/`run_once` 返回本轮结果，CLI 在全失败时抛 `ClickException`，退出码非 0
- **fix: 自动化 timer 在规则抛异常后每个 tick 重复触发**：`next_run_at` 的推进语句排在 `await self._run_rule(...)` **之后**，异常一来就永远走不到，调度时间停在过去。配合 YAML 的隐式类型（`yaml.safe_load` 会把 `2024-06-01` 解析成真正的 `datetime`，`json.dump` 抛 `TypeError`）实测一条 `interval_seconds: 3600` 的规则**0.2 秒内发了 12 条消息**。现把推进放进 `finally`，并用 `_json_default` 把非 JSON 原生类型降级成可序列化值（`datetime`→ISO 字符串、set→list），从根上消掉这条崩溃路径
- **fix: 单条规则异常会打断同一配置里其它 timer 规则**：`_tick_timers` 不隔离单条规则，异常冒泡后本轮后面的规则全部不触发。现按规则 try/except（`CancelledError` 仍向上抛），失败只跳过该条并记 ERROR
- **fix: 插件返回 dict/list 时状态变量完全不落盘**：`if result in {"stop", "defer"}` 写在 try 之外，对不可哈希的返回值抛 `TypeError` 并逃出 `_run_rule` —— 后面的 handler 不再执行，规则变量也一并不落盘。现只对 `str` 判停，并把状态持久化移进 `finally`
- **fix: `state.json` 里 `next_run_at` 是数字时，该任务所有 timer 规则静默停摆**：`_validate_shape` 只校验容器、不校验叶子值类型，`datetime.fromisoformat(int)` 抛的是 `TypeError` 而非 `ValueError`，逃出 `get_trigger_next_run` 的捕获后每秒打断一次 `_tick_timers`。现叶子值一并校验（非法即按损坏备份为 `.corrupt-<ts>`），读取处同时兜底捕获 `TypeError`
- **fix: WebUI 切换工作目录后，进程/锁/登录态注册表全部串味**：`process_key()` 是 `kind:account`、不含 workdir，`POST /api/state` 只重绑 `state.workdir` 和日志 handler。切目录后新目录里的同名账号会被旧目录的进程挡住并报「已在运行 (PID ...)」，`/api/run` 把旧目录的任务显示成新目录的；登录更会把 `me.json`/`latest_chats.json`/`webui_accounts.json` 写进**刚切走的旧目录**（用户看到「登录成功」却找不到账号）。现注册表键改为 `<workdir>|<kind>:<account>`（对外仍返回不含 workdir 的展示键），切目录时回收旧登录会话
- **fix: `tzdata` 未声明，`TZ` 环境变量在 Windows 上被静默忽略**：zoneinfo 依赖系统时区库，而 pip 安装不经过 Dockerfile 里的 `apt-get install tzdata`。缺库时 `ZoneInfo("Asia/Shanghai")` 抛 `ZoneInfoNotFoundError`，`get_timezone()` 退回 UTC —— 定时签到与定时发送**整体偏移**（东八区用户差 8h），而 README 明确承诺「直接设置 `TZ` 即可」。CI 只跑 ubuntu，`test_utils` 在缺 zoneinfo 时 skip，永远抓不到。现补 `"tzdata; platform_system == 'Windows'"`
- **fix: `tg-signer llm-config` 在全新目录上崩溃，用户刚输入的 API Key 全丢**：`save_config` 直接往 `<workdir>/.openai_config.json` 写，没有 `mkdir`；默认 workdir `.signer` 在新克隆的仓库里并不存在，异常发生在 `ask_for_config()` **提示用户输完 Key 之后**
- **fix: 损坏的 `.openai_config.json` 让 CLI 崩在裸 `JSONDecodeError`**：WebUI 的 `_safe_llm_config` 早就按「损坏即未配置」兜底，CLI 的 `ensure_ai_cfg()` 没有 —— 一个坏文件就能打死整个签到/自动化任务。现转为带修复指引的 `ValueError`
- **fix: WebUI 登出失败时本地数据仍被清空**：`logout_account` 的本地清理（删 session 文件、`users/<id>` 缓存、账号映射）挂在 `finally` 上无条件执行，任何 Telegram 侧错误都会在 API 返回失败的同时把本地状态删光。现改为登出成功后才清理；session 文件被占用导致的 `PermissionError` 也不再变成 500 traceback
- **fix: 两种 legacy JSON 布局在记录页产生重复行**：`load_sign_records` 的 `existing_keys` 只在遍历 SQLite 分组时填充，JSON 分支只查不加 —— `signs/<task>/sign_record.json` 与 `signs/<task>/<user_id>/sign_record.json` 解析出同一 key 时两条都出现，且各带一半历史。现 JSON 分支同样登记回集合
- **fix: `send-text @ hello` 抛裸 `ValueError` traceback**：`parse_chat_id` 的 `"@"` 分支写在 `try` 之外，而 `parse_chat_id_or_username("@")` 正是抛 `ValueError`。现统一包在一个 `try` 里，转成 Click 用法错误（退出码 2）
- **fix: 错误的 `TZ` 值让每个自动化 tick 崩溃**：`_load_timezone` 只捕获 `ZoneInfoNotFoundError`，而 `..`、绝对路径这类 key 抛的是 `ValueError`。现一并捕获，走文档里的兜底链
- **fix: `sign_at` 的秒被静默丢弃**：`normalize_sign_at("06:00:30")` 返回 `"0 6 * * *"`，实际早签 30 秒，与「返回等价的 crontab 表达式」不符。现秒非 0 时返回 6 段式（croniter 默认把秒放在末尾），秒为 0 时仍返回原有的 5 段式
- **fix: `logout` 在账号未授权时留下 `.session_string`**：`storage.delete()` 只删 pyrogram 的 SQLite session，本项目自己的 `session_string` 登录态文件会残留，WebUI 仍会判定该账号「已登录」。现与 `webui.account.logout_account` 的清理范围保持一致
- **fix: 测试污染 —— `get_now` 被永久钉死在 2024**：`test_timer_schedule_next_override` 直接给模块属性赋值（不经 `monkeypatch`），使整个 `engine` 模块的「现在」在后续所有用例里恒为 `2024-01-01`，让依赖真实时间的用例随机失败。现改用 `monkeypatch.setattr`

### 0.10.14
- **fix: 早于 `sign_at` 启动会当天签到两次**：`need_sign()` 只要「今天还没有签到记录」就立刻签，完全不管当前是否已到计划时刻。于是进程 05:00 启动 + `sign_at=06:00:00` 时，05:00 先补签一次、06:00 到点因为「上次签到(05:00)之后的下一次命中(06:00)不大于当前时间」又签一次 —— 每天定时重启的容器必然如此。现改为先求出「今天第一个计划命中时刻」：未到点就等到点再签；已过点才补签；像 `0 6 * * 1` 这种今天没有命中的非每日 cron 则本次循环不签（旧实现会退化成每天都签一次）。求「今天第一个命中时刻」时锚点必须放在当天 00:00 的**前一秒**：croniter 的 `next()` 严格晚于锚点，锚在 00:00 上会把 `0 0 * * *` 算成明天，于是每天都判「今日无计划时刻」而永不签到（全量测试抓到并已修正）
- **fix: 所有 chat 都失败时仍被记为「今日已签到」，当天不再重试**：`sign_once` 吞掉每个 chat 的异常后无条件 `persist_sign_record`，一次网络抖动就等于整天漏签（实测：唯一 chat 抛异常后 `2026-09-30` 照样落库）。现只有「至少一个 chat 成功」或「配置里没有 chat」才写入记录；全部失败时不落库，并在 `only_once` 之外退避 `_ALL_FAILED_RETRY_SECONDS`（60s）重试本轮。`run-once` 语义不变（不重试、不落库）
- **fix: 较早的消息被编辑后永远不会被重新处理，点击类签到必然超时**：`wait_for` 只比对队尾消息判断「有没有新内容」，而编辑写回的是原 message_id 的位置，队尾没变就被永久忽略（实测：编辑后点击次数 0、一直等到超时）。现改为逐条记录「已处理过的那次消息对象」，对象身份变化（新增或编辑）就重新处理，同时避免同一条消息被反复处理
- **fix: 频道原生帖/服务消息没有 `from_user` 时日志直接抛 AttributeError**：`on_message`/`on_edited_message` 直接取 `message.from_user.username`，频道帖子该字段为 `None`，异常发生在写回调 `_on_message` **之前**，该条消息被整个丢掉。现新增 `_message_sender_label()`，无发送者时退回 `@chat.username` / `chat <id>`
- **fix: 签到记录里的历史 naive 时间戳或被改坏的值会打死整个 run**：`datetime.fromisoformat()` 的结果直接与 aware 的 `now` 比较，naive 值抛 `TypeError`、非法值抛 `ValueError`，两者都不在 `normal_run` 的 `except (OSError, errors.Unauthorized)` 集合内。现解析失败按「今日已签到」处理（警告日志，`run-once` 可强制），naive 值补上当前时区后再比较
- **fix: `random_seconds` 为负数时崩溃**：`random.randint(0, n)` 对负数抛 `ValueError: empty range`。配置层给 `SignConfigV3.random_seconds` 与 `TimerTriggerParams.random_seconds` 加 `ge=0` 约束；`schedule_messages` 的 CLI 入参额外做 `max(0, ...)` 兜底
- **fix: 重复的 rule id / trigger id 被静默接受**：两条规则共用 `rules.<id>.vars` 状态桶、共用同一个 `trigger_id`，`next_run_at` 互相覆盖。现 `AutomationConfig` 增加唯一性校验，重复时在配置校验阶段就报错（`docs/automation_design.md:51` 本就要求 trigger_id 唯一）
- **fix: startup/timer 后台任务在 Client 启动之前就被创建**：`run()` 先 `create_task(run_startup/timer_loop)` 再 `async with self.app`，冷启动时首个 Telegram 调用必然撞上 pyrogram 的 `ConnectionError("Client has not been started yet")`，异常被 `_run_rule` 吞掉并中断 handler 链；timer 还会照常推进 `next_run_at`，于是「已到期」的那次执行被静默消费。现两个任务都在 `async with self.app` 之内创建，并在退出前趁 client 仍存活时取消
- **fix: `automation list` 会建出并列出并不存在的 `my_task`**：`UserAutomation(workdir=...)` 未传任务名 → 兜底 `my_task`，而 `__init__` 里的 `RuleStateStore(self.state_file)` 经 `task_dir`/`make_dirs` 建出 `<workdir>/automations/my_task`。现状态存储改为懒加载，`list` 只枚举真正含配置文件的已有任务目录，不构造 worker、不建任何目录
- **fix: `automation validate <打错的task>` 打印「配置校验通过」并在磁盘上生成模板配置**：`load_config()` 对不存在的文件会走 `reconfig()` → 写模板，于是「校验」变成「创建」，还对着错名报成功。现 validate 先做一次不建目录的存在性检查，缺失则 `ClickException` 退出非 0、不落任何文件
- **fix: YAML 任务的 export→import 往返会把任务改坏**：`export()` 返回的是已解析文件（可能是 YAML）的原文，而基类 `import_()` 一律写 `config.json`，且解析顺序 JSON 优先 —— YAML 文本落进 config.json 后遮蔽 config.yaml，任务再也读不出来（`Expecting value: line 2 column 1`），必须手工删文件才能恢复。现 `import_()` 解析（JSON 优先、YAML 兜底）后按**目标文件格式**序列化，并先经配置校验，非法内容给出明确错误
- **fix: state.json 非「非法 JSON」类损坏会让所有 automation 子命令崩溃**：恢复分支只 catch `(OSError, JSONDecodeError)`，UTF-16 文件抛 `UnicodeDecodeError`，`[]` / `null` / `{"rules": null}` / `{"rules": []}` 则在 `_rule_bucket` 抛 AttributeError/TypeError；而 `RuleStateStore` 是在 `UserAutomation.__init__` 里构造的，于是连 `list`/`validate` 都直接抛裸栈。现扩大捕获范围并新增 `_validate_shape()`（根/`rules`/桶/`vars`/`triggers` 逐层校验），一律走 `.corrupt-<ts>` 备份 + 空状态继续
- **fix: chat `@username` 匹配区分大小写，且 `ignore_case` 是死字段**：`_match_chat` 精确比较用户名，配置写 `@MyChannel`、实际是 `mychannel` 时规则永不触发。现按 `ignore_case`（默认 true）做大小写归一，并把 `MessageTriggerParams.ignore_case` 真正接进匹配
- **fix: `store_state(keys=[...])` 永远不生效**：handler 写下的子集会被规则结束时无条件的 `set_rule_vars(rule.id, ctx.vars)` 覆盖。现通过 `ctx.persist_vars` 声明回写子集，`keys`（数组或单个字符串）非空时只持久化列出的键
- **fix: `external_forward` 单个目标失败会打断后续目标与整条 handler 链**：`await udp_forward/http_api_callback` 不在 try 内。现每个目标单独兜异常、继续执行剩余目标，日志区分 success/failed
- **fix: `blacklist_filter` 的 `keywords` 传裸字符串会逐字符匹配**（`"abcd"` 退化成 4 个单字符关键词，含 `a` 的正常文本被误杀）。现字符串整体作为一个关键词，非列表类型忽略并告警
- **fix: `include_current` 的去重分支永不成立**：`lines.reverse()` 后与 `"[current] 文本"` 比较的是 `"[sender] 文本"`，当前消息在 LLM prompt 里出现两次。现改为比对纯文本，已存在则不追加
- **fix: `_message_cache` 只限单聊消息数、不限聊天数**（长期运行随 chat 数无界增长）。现外层同样按 LRU 淘汰，上限 64 个 chat
- **fix: 只有环境变量提供 Key 时 LLM 配置完全无法保存**：回退分支只认文件里的 `stored_key`，env-only 时恒为空 → 无论留空还是回显掩码都返回 400「API Key 不能为空」，base_url / model 根本存不下去。现回退到 env 感知的有效密钥
- **fix: `.openai_config.json` 损坏时三个 LLM 端点全部 500 且无法从 UI 修复**：`load_file_config()` 的 `JSONDecodeError` / pydantic `ValidationError` 无人兜底，连「重新填一个 Key 保存」这条修复路径也走不通。现统一经 `_safe_llm_config()` 读取（损坏视为未配置 + 告警），POST 仍可覆写修好文件
- **fix: 子进程自行退出后同账号 `start()` 报误导性的「正在被其他进程使用」**：死子进程的 `LockHandle` 仍占着 `<account>.lock`（flock / msvcrt.locking 按打开的文件描述符记账），而 `start()` 从不 `_forget`，只能等 `running_tasks()`/`status()`/`stop()` 顺手清理。现 `start()` 发现进程已退出就先 `_forget` 再抢锁
- **fix: `Popen` 抛 `ValueError` 时账号锁不释放**（任务名含 NUL 等非法参数）：原只 catch `OSError`，锁要等 traceback 被 GC 才回收，违反 `tests/test_account_lock.py` 的「start 失败不留锁」不变量。现该路径关闭日志句柄并释放锁
- **fix: 启动 1.5s 宽限期内 `stop()`/`shutdown_all()` 停不掉正要起的子进程**：子进程在 `time.sleep(_STARTUP_GRACE_SECONDS)` 之后才登记进 `_PROCESSES`，窗口内被拉起的进程会成为孤儿（用户看到「未在运行」，进程却活着）。现提前登记，立即退出时用 `_forget` 清理
- **fix: 日志页 `tail_file` 多出一条伪空行、且少返回一行**：文件以 `\n` 结尾时 `split` 末尾的空串白占一个 limit 名额（`limit=3` 的 3 行文件只回 2 行 + 一条空行）。现只丢弃文件末尾那个空段，中间空行照旧保留，跨块长行/切开的 UTF-8 仍能还原
- **fix: legacy 两段式 `signs/<task>/sign_record.json` 在记录页重复显示**：`_record_target` 给出 `(task, None)`，与迁移到 SQLite 时推断出的 `(task, <user_id>)` 对不上，去重形同虚设。现统一走 `SignRecordStore.resolve_record_target()` 计算去重键
- **fix: `data.sqlite3` 损坏或被长时间锁住时 `/api/records` 返回 500**。现捕获 `sqlite3.Error` 并退化为「只展示 JSON 记录」
- **fix: `/api/logs/files` 会列出 `/api/logs?path=` 必然 400 的日志**（列举是无限递归 `rglob`，读取只允许一层子目录）——即「列得出来、一点就报错」在更深一层目录上的翻版。现列表与读取共用同一套形状规则
- **fix: `users/<id>/me.json` 是 `null` / `[]` 等非对象 JSON 时 `/api/chats` 返回 500**。现跳过非对象条目（与 `latest_chats.json` 的非数组守卫一致）
- **fix: 语法损坏的 `automations/<task>/config.yaml` 返回 500 而非 400**：`yaml.YAMLError` 不是 `ValueError` 子类，绕过了端点的兜底 except。现统一转成 `ValueError`
- **fix: 对不存在的账号调用 `POST /api/accounts/logout` 会发起真实 Telegram 连接**。现 `server.py` 与 `account.py` 两处都先做本地 session 检查，不存在则直接返回「无需登出」，不再外连
- **fix: 两处失效/缺失的工程配置**：`pyproject.toml` 的 `pydantic` 没有下界，而代码用的是 `ConfigDict` / `model_validate` / `model_validator`（均为 v2 API），环境里已装 pydantic v1 时会满足依赖却在 import 阶段直接失败 —— 现改为 `pydantic>=2`；`[tool.pytest_asyncio] auto_mode = true` 不是 pytest-asyncio 认识的配置项（只认 `asyncio_mode`），属于静默失效，现改为 `[tool.pytest.ini_options] asyncio_mode = "auto"`（此前一直没暴露，只因所有 async 用例都显式打了 marker）
- **fix: `tox` 这条跨版本验证路径实际是坏的**：`tox.ini` 的 `deps` 只写了 `pytest`/`pytest-asyncio`，而测试套件会 `import fastapi`（`tests/test_webui_server.py` 模块级）与 `yaml`，于是 tox 环境在**收集阶段**就 `ModuleNotFoundError`（CI 因为执行 `pip install --group dev` 才没暴露这个长期漂移）。现 `tox.ini` 改为 `dependency_groups = dev` 直接复用 pyproject 的 dev 组，从根上避免两份清单再次不同步；同时给 dev 组补上 `pyyaml`（与 fastapi/uvicorn 同理：测试要覆盖可选能力的真实路径，而不是只测到跳过分支）
- **fix: `tests/test_main_entry.py` 在 Windows 上对子进程编码不健壮**：`subprocess.run(..., text=True)` 未指定编码，默认按本地编码（中文 Windows 是 cp936）解码，而 CLI 帮助文本含中文；tox 会给它执行的命令设 `PYTHONIOENCODING=utf-8`（`tox/sets.py`），此时子进程输出 UTF-8、父进程按 cp936 解码 → 读取线程抛 `UnicodeDecodeError`、`proc.stdout` 变成 `None`，用例报 `TypeError`。现显式 `encoding="utf-8", errors="replace"`（断言只涉及 ASCII，两种编码下都稳定）
- `tests/test_cli_folders.py` / `tests/test_automation_engine.py` 里的 yaml 依赖改用 `pytest.importorskip("yaml")`（与 `test_webui_data.py` / `test_webui_server.py` 的既有惯例一致），缺 pyyaml 时是跳过而不是收集期直接崩
- 测试：新增 `test_normal_run_waits_until_today_scheduled_time`、`test_normal_run_catches_up_when_started_after_todays_time`、`test_normal_run_non_daily_cron_only_signs_on_matching_weekday`、`test_normal_run_does_not_record_when_every_chat_fails`、`test_normal_run_records_when_at_least_one_chat_succeeds`、`test_normal_run_tolerates_broken_sign_record_values`（naive/非法两参数）、`test_wait_for_processes_message_edited_later_in_the_list`、`test_on_message_tolerates_messages_without_from_user`、`test_sign_config_v3_rejects_negative_random_seconds`、`test_timer_trigger_rejects_negative_random_seconds`、`test_automation_config_rejects_duplicate_rule_ids`、`test_automation_config_rejects_duplicate_trigger_ids`、`test_normal_run_retries_the_round_when_every_chat_fails`、`test_normal_run_signs_daily_midnight_cron`
- 测试（automation / CLI）：新增 `test_background_tasks_start_after_client_is_started`、`test_background_tasks_are_cancelled_on_exit`、`test_constructing_worker_does_not_create_task_dir`、`test_list_task_names_is_read_only`、`test_yaml_task_export_import_roundtrip_stays_loadable`、`test_json_task_export_import_roundtrip_stays_loadable`、`test_import_yaml_text_into_json_task_converts_format`、`test_import_invalid_text_raises_clear_error`、`test_chat_username_matching_is_case_insensitive_by_default`、`test_store_state_keys_restrict_what_is_persisted`、`test_run_rule_persists_all_vars_without_store_state`、`test_message_cache_bounds_number_of_chats`、`test_external_forward_continues_after_target_failure`、`test_blacklist_filter_string_keyword_is_not_split`、`test_include_current_does_not_duplicate_current_message`、`test_include_current_marks_message_missing_from_history`、`test_rule_state_store_load_damaged_file_backs_up_and_continues`、`test_rule_state_store_load_utf16_encodes_backs_up`、`test_rule_state_store_load_empty_object_is_normalised`、`test_automation_list_on_fresh_workdir_prints_nothing_and_creates_nothing`、`test_automation_list_prints_real_tasks`、`test_automation_validate_missing_config_does_not_create_one`、`test_automation_yaml_export_import_validate_roundtrip`
- 测试（WebUI）：新增 `test_llm_config_saves_with_env_only_key`、`test_llm_config_survives_corrupt_file_and_can_repair_it`、`test_llm_config_test_endpoint_survives_corrupt_file`、`test_start_after_child_exited_by_itself_releases_stale_lock`、`test_start_popen_value_error_releases_account_lock`、`test_stop_during_startup_grace_can_still_stop_child`、`test_shutdown_all_during_startup_grace_stops_child`、`test_tail_file_drops_trailing_newline_artifact`、`test_tail_file_returns_limit_real_lines`、`test_tail_file_keeps_real_blank_lines`、`test_tail_file_without_trailing_newline`、`test_tail_file_handles_empty_file_and_lone_newline`、`test_tail_file_reassembles_long_line_spanning_chunks`、`test_tail_file_keeps_order_across_many_chunks`、`test_tail_file_preserves_utf8_split_across_chunks`、`test_load_sign_records_dedups_two_part_legacy_json_against_sqlite`、`test_load_sign_records_keeps_distinct_user_rows`、`test_load_sign_records_survives_corrupt_sqlite_file`、`test_list_log_files_only_lists_paths_the_reader_accepts`、`test_load_automation_config_reports_invalid_yaml_as_value_error`、`test_load_user_infos_skips_non_object_me_json`、`test_chats_endpoint_survives_non_object_me_json`、`test_records_endpoint_survives_corrupt_sqlite`、`test_automation_config_with_invalid_yaml_returns_400`、`test_logout_missing_session_never_constructs_client`、`test_logout_nonexistent_account_does_not_connect`、`test_logout_existing_account_still_reports_ok`

### 0.10.13
- **chore: 移除 WebUI 启动/切换工作目录时的日志打印**：撤掉 0.10.11 引入的 `server._log_workdir()` 及其两处调用，同时删掉当时的 `import logging` 与配套测试 `test_workdir_is_logged_on_startup_and_switch`。该功能只是 0.10.12 之前的临时排查手段，真正的问题（import 建野目录、切换失败不回滚）已在 0.10.12 修复，不再需要靠日志反推实际目录

### 0.10.12
- **fix: import 模块即在进程 CWD 下凭空创建 `.signer`**：`server.py` 的模块级 `state = data_mod.UIState()` 会在 import 阶段执行，而 `UIState.__init__` -> `get_workdir()` 内含 `mkdir(parents=True)`。于是「仅仅 import 一下」就在 CWD 建出 `.signer`，传了 `--workdir` 也照样建 —— 随后 `main()` 改回真正的 workdir，那个野目录却留在磁盘上。Docker 里 WORKDIR 若是 `/`，用户就会在自己根本没用过的路径下看到残留目录。现 `get_workdir()`/`UIState()` 增 `create` 开关，模块级 state 用 `create=False`，目录改由 `_setup_logger()` 在启动时创建
- **fix: `POST /api/state` 切换失败后状态不回滚**：`set_workdir()` 成功之后本函数已无回滚点，若后续 `_setup_webui_logger()` 失败，会被同一个 `except Exception` 吞掉并返回 400「切换工作目录失败」—— 但后端其实**已经切到新目录在操作**，前端收到失败后保留旧值显示。这正是「基础设置显示的路径和实际不一致」的代码级成因（此前只怀疑部署侧未重启）。现失败时把 `workdir` / `log_path` 与日志 handler 一并退回
- **fix: 子进程 stdout 与主进程 logger 争抢同一个主日志**：`runner.start` 过去把子进程 `stdout/stderr` 重定向到顶层 `<workdir>/logs/tg-signer.log`，而该文件同时被主进程的 `RotatingFileHandler` 独占。轮转时主进程把文件改名为 `.log.1` 并新建，子进程经 `Popen` 继承的裸 fd 仍指向改名前的旧 inode，此后所有输出落进 `.log.1` —— 表现为「任务跑一段时间后主日志突然不再更新」。子进程自己的 logger 本就写在 `<workdir>/logs/<kind>-<account>/`（v0.10.8 已隔离），stdout 再抄一份到主日志属冗余。新增 `runner.child_stdout_log()`，stdout 改落 `<workdir>/logs/<kind>-<account>/stdout.log`，顶层主日志由主进程 handler 独占
- **fix: `latest_chats.json` 内容不是数组时 `/api/chats` 报 500**：文件被手改或截断成 `{}` / `null` 时，`load_user_infos` 原样透传，`load_group_chats` 按 list 迭代抛 `TypeError`。现载入时校验类型，聚合时再逐项跳过非 dict
- **fix: 前端切换工作目录失败不回滚输入框**：`Settings.vue` 的 `apply()` 在 catch 里只弹错误，用户填的无效路径留在框里却未生效。现失败时重新拉取后端真实值
- 测试：新增 `test_switch_workdir_failure_rolls_state_back`、`test_get_workdir_can_resolve_without_creating`、`test_ui_state_create_false_does_not_touch_disk`、`test_load_group_chats_tolerates_malformed_latest_chats`；改写 `test_start_redirects_stdout_stderr_to_child_dir_not_main_log`（含「子进程不得写顶层主日志」判别断言）、`test_child_process_stdout_visible_in_load_logs`、`test_start_creates_log_dir`、`test_start_isolates_child_log_dir`

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
