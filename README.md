## Telegram每日自动签到/个人、群组、频道消息监控与自动回复

[English](./README_EN.md)

### 功能

- 每日定时和随机误差时间签到
- 根据配置的文本点击键盘
- 调用AI进行图片识别并点击键盘
- 个人、群组、频道消息监控、转发与自动回复
- 根据配置执行动作流
- 自动化规则引擎（message/timer/startup 触发 + handler 链）

  **...**

### 安装

需要Python3.10及以上

```sh
pip install -U tg-signer
```

或者为了提升程序速度：

```sh
pip install "tg-signer[speedup]"
```

启用 YAML 配置支持：

```sh
pip install "tg-signer[yaml]"
```
#### WebUI
tg-signer附带了一个WebUI，安装命令:
```sh
pip install "tg-signer[gui]"
```

![webgui](./assets/webui.jpeg)

WebUI 包含账号管理（登录/登出）、配置管理（Signer / Automation 配置编辑，含大模型 API 配置与交互式配置向导）、群组配置、用户信息、签到记录和日志页面；账号管理页可登录账号获取 session 并登出删除 session 文件，群组配置页可列出账号缓存的群组/频道并快速填入签到或自动化配置。
前后端分离架构：后端为 FastAPI（提供 REST API 并托管前端静态产物），前端为 Vue 3（源码位于 `tg_signer/webui/frontend/`）。正常使用无需自行构建前端，`pip install "tg-signer[gui]"` 安装的包内已含构建产物；如需修改前端，在 `tg_signer/webui/frontend/` 下执行 `npm install && npm run build`，产物会输出到 `tg_signer/webui/static/`。

### Docker

#### GitHub Container Registry
在 GitHub Container Registry 提供了两种预构建镜像：`ghcr.io/amchii/tg-signer:<tag>`（CLI）和 `ghcr.io/amchii/tg-signer:<tag>-webui`（CLI + WebUI）。

#### 本地
如果需要自行构建镜像，本地 build 方式仍然保留，见 [docker](./docker) 目录下的 Dockerfile 和 [README](./docker/README.md) 。

### 使用方法

```
Usage: tg-signer [OPTIONS] COMMAND [ARGS]...

  使用<子命令> --help查看使用说明

子命令别名:
  run_once -> run-once
  send_text -> send-text

Options:
  -l, --log-level [debug|info|warn|error]
                                  日志等级, `debug`, `info`, `warn`, `error`
                                  [default: info]
  --log-file PATH                 日志文件路径, 可以是相对路径  [default: logs/tg-
                                  signer.log]
  --log-dir PATH                  日志文件目录, 可以是相对路径  [default: logs]
  -p, --proxy TEXT                代理地址, 例如: socks5://127.0.0.1:1080,
                                  会覆盖环境变量`TG_PROXY`的值  [env var: TG_PROXY]
  --session_dir PATH              存储TG Sessions的目录, 可以是相对路径  [default: .]
  -a, --account TEXT              自定义账号名称，对应session文件名为<account>.session  [env
                                  var: TG_ACCOUNT; default: my_account]
  -w, --workdir PATH              tg-signer工作目录，用于存储配置和签到记录等  [default:
                                  .signer]
  --session-string TEXT           Telegram Session String,
                                  会覆盖环境变量`TG_SESSION_STRING`的值  [env var:
                                  TG_SESSION_STRING]
  --in-memory                     是否将session存储在内存中，默认为False，存储在文件
  --help                          Show this message and exit.

Commands:
  export                  导出配置，默认为输出到终端。
  import                  导入配置，默认为从终端读取。
  list                    列出已有配置
  list-members            查询聊天（群或频道）的成员, 频道需要管理员权限
  list-folders            列出 Telegram 普通对话 Folder
  list-sign-records       列出最近N条签到记录
  list-topics             列出群组话题ID（message_thread_id）
  list-schedule-messages  显示已配置的定时消息
  llm-config              配置大模型API
  login                   登录账号（用于获取session）
  migrate-sign-records    将签到记录从 JSON 迁移到 SQLite（默认保留原...
  logout                  登出账号并删除session文件
  automation              配置和运行自动化规则
  multi-run               使用一套配置同时运行多个账号
  reconfig                重新配置
  run                     根据任务配置运行签到
  run-once                运行一次签到任务，即使该签到任务今日已执行过
  schedule-messages       批量配置Telegram自带的定时发送消息功能
  send-dice               发送一次DICE消息, 请确保当前会话已经"见过"该`chat_id`。...
  send-text               发送一次文本消息, 请确保当前会话已经"见过"该`chat_id`
  version                 Show version
  webgui                  启动一个WebGUI（需要通过`pip install "tg-signer[gui]"`安装相关依赖）

```

例如:

```sh
tg-signer run
tg-signer run my_sign  # 不询问，直接运行'my_sign'任务
tg-signer run-once my_sign  # 直接运行一次'my_sign'任务
tg-signer list-folders  # 列出 Telegram 普通 Folder 的 ID、名称和显式对话数量
tg-signer login --from-folder Sign  # 登录账号并从 Sign Folder 发现对话
tg-signer run --from-folder Sign my_sign  # 从 Sign Folder 发现对话后运行任务
tg-signer list-sign-records linuxdo -n 5  # 查看任务 linuxdo 最近 5 条签到记录
tg-signer migrate-sign-records  # 将.signer/signs 下的签到记录迁移到 SQLite
tg-signer send-text 8671234001 /test  # 向chat_id为'8671234001'的聊天发送'/test'文本
tg-signer send-text @neo /test  # 向username为'@neo'的聊天发送'/test'文本
tg-signer send-text --message-thread-id 1 -- -1003763902761 checkin  # 发送到群组话题(message_thread_id=1)
tg-signer send-text -- -10006758812 浇水  # 对于负数需要使用POSIX风格，在短横线'-'前方加上'--'
tg-signer send-text --delete-after 1 8671234001 /test  # 向chat_id为'8671234001'的聊天发送'/test'文本, 并在1秒后删除发送的消息
tg-signer list-members --chat_id -1001680975844 --admin  # 列出频道的管理员
tg-signer list-topics --chat_id -1003763902761 --limit 50  # 列出群组话题及message_thread_id
tg-signer schedule-messages --crontab '0 0 * * *' --next-times 10 -- -1001680975844 你好  # 在未来10天的每天0点向'-1001680975844'发送消息
tg-signer schedule-messages --crontab '0 0 * * *' --next-times 3 --message-thread-id 1 -- -1003763902761 你好  # 配置群组话题的定时消息
tg-signer automation init my_auto  # 初始化自动化模板
tg-signer automation run my_auto  # 运行自动化任务
tg-signer multi-run -a account_a -a account_b same_task  # 使用'same_task'的配置同时运行'account_a'和'account_b'两个账号
tg-signer webgui --auth-code averycomplexcode  # 启动一个WebGUI
```

启用 `--auth-code` 后，连续输错 5 次授权码会锁定 60 秒。

### 自动化规则（automation）

使用 `tg-signer automation` 统一管理消息监控、转发与自动回复等自动化规则。

```sh
tg-signer automation init my_auto
# 编辑 .signer/automations/my_auto/config.json
tg-signer automation run my_auto
```

更多详细使用说明与示例见：`docs/automation_usage.md`

### 配置代理（如有需要）

`tg-signer`不读取系统代理，可以使用环境变量 `TG_PROXY`或命令参数`--proxy`进行配置

例如：

```sh
export TG_PROXY=socks5://127.0.0.1:7890
```

### 登录

```sh
tg-signer login
```

根据提示输入手机号码和验证码进行登录并获取最近的聊天列表，确保你想要签到的聊天在列表内。
运行任务（`run` / `run-once` / `multi-run` / `automation run`）时，若已存在有效 session 文件会直接复用，无需重复登录；仅当 session 缺失或失效时才需要先执行 `tg-signer login` 或到 WebUI「账号管理」页登录。
签到任务里的`chat_id`同时支持整数ID和以`@`开头的username，例如`@neo`。
对于论坛群组，登录输出中会额外打印每个话题的 `message_thread_id`，可直接用于 `--message-thread-id`。

如果目标对话不在最近列表中，可以在 Telegram 新建一个普通 Folder，手动把目标对话加入其中，然后按名称或 ID 加载：

```sh
tg-signer list-folders
tg-signer login --from-folder Sign
# 名称重复时使用 ID
tg-signer login --from-folder 2
```

`--from-folder` 表示“从 Folder 发现对话”，也适用于 `run`、`run-once`、`multi-run` 和 `automation run`。指定后会加载 Folder 中所有手动加入或置顶的对话，`--num-of-dialogs` 不再生效。当前不支持按联系人、非联系人、机器人、群组或频道等动态规则生成成员的 Folder；请使用只包含手动添加对话的普通 Folder。

### 时区

调度相关命令（如 `run` 和 `schedule-messages`）会按以下顺序解析时区：

1. 环境变量 `TZ`
2. Python 识别到的本地时区
3. 默认回退到 `Asia/Shanghai`

如果你需要按特定时区计算下次执行时间，直接在运行前设置 `TZ` 即可。

### 获取群组话题 ID

```sh
tg-signer list-topics --chat_id -1003763902761
```

会输出该论坛群组可见话题的 `message_thread_id`、标题及状态，便于配置签到到指定话题。

### 发送一次消息

```sh
tg-signer send-text 8671234001 hello  # 向chat_id为'8671234001'的聊天发送'hello'文本
tg-signer send-text @neo hello  # 向username为'@neo'的聊天发送'hello'文本
```

### 运行签到任务

```sh
tg-signer run
```

或预先执行任务名：

```sh
tg-signer run linuxdo
```

根据提示进行配置即可。

#### 示例：

```
开始配置任务<linuxdo>
第1个签到
一. Chat ID（登录时最近对话输出中的ID或@username）: 7661096533
二. Chat名称（可选）: jerry bot
三. 是否发送到话题（message_thread_id）？(y/N)：y
四. message_thread_id: 1
五. 开始配置<动作>，请按照实际签到顺序配置。
  1: 发送普通文本
  2: 发送Dice类型的emoji
  3: 根据文本点击键盘
  4: 根据图片选择选项
  5: 回复计算题

第1个动作:
1. 输入对应的数字选择动作: 1
2. 输入要发送的文本: checkin
3. 是否继续添加动作？(y/N)：y
第2个动作:
1. 输入对应的数字选择动作: 3
2. 键盘中需要点击的按钮文本: 签到
3. 是否继续添加动作？(y/N)：y
第3个动作:
1. 输入对应的数字选择动作: 4
图片识别将使用大模型回答，请确保大模型支持图片识别。
2. 是否继续添加动作？(y/N)：y
第4个动作:
1. 输入对应的数字选择动作: 5
计算题将使用大模型回答。
2. 是否继续添加动作？(y/N)：y
第5个动作:
1. 输入对应的数字选择动作: 2
2. 输入要发送的骰子（如 🎲, 🎯）: 🎲
3. 是否继续添加动作？(y/N)：n
在运行前请通过环境变量正确设置`OPENAI_API_KEY`, `OPENAI_BASE_URL`。默认模型为"gpt-4o", 可通过环境变量`OPENAI_MODEL`更改。
六. 等待N秒后删除签到消息（发送消息后等待进行删除, '0'表示立即删除, 不需要删除直接回车）, N: 10
╔════════════════════════════════════════════════╗
║ Chat ID: 7661096533                            ║
║ Name: jerry bot                                ║
║ Message Thread ID: 1                           ║
║ Delete After: 10                               ║
╟────────────────────────────────────────────────╢
║ Actions Flow:                                  ║
║ 1. [发送普通文本] Text: checkin                ║
║ 2. [根据文本点击键盘] Click: 签到              ║
║ 3. [根据图片选择选项]                          ║
║ 4. [回复计算题]                                ║
║ 5. [发送Dice类型的emoji] Dice: 🎲              ║
╚════════════════════════════════════════════════╝
第1个签到配置成功

继续配置签到？(y/N)：n
每日签到时间（time或crontab表达式，如'06:00:00'或'0 6 * * *'）:
签到时间误差随机秒数（默认为0）: 300
```

### 监控功能已下线

`tg-signer monitor` 与 `<workdir>/monitors/` 已移除。消息监控、转发与自动回复请统一使用 `tg-signer automation`：

```sh
tg-signer automation init my_auto
# 编辑 .signer/automations/my_auto/config.json
tg-signer automation run my_auto
```

迁移对照：

| 旧 monitor 概念 | automation 对应 |
| --- | --- |
| 监控项 `chat_id` + 匹配规则 | 触发器 `message` + `filters`（`text_rule` / `text_value` / `from_user_ids`） |
| 默认发送文本 | handler `send_text` |
| AI 回复 | handler `ai_reply` |
| 正则提取发送文本 | handler `send_text` 的 `search_regex` + `template` |
| 转发到聊天 | handler `forward` |
| 转发到外部（UDP / Http） | handler `external_forward` |
| Server酱推送 | handler `server_chan` |

详见 [docs/automation_usage.md](docs/automation_usage.md)。

### 版本变动日志

版本变动日志已移至 [CHANGELOG.md](CHANGELOG.md#版本变动日志)。

### 配置与数据存储位置

数据和配置默认保存在 `.signer` 目录中。然后运行 `tree .signer`，你将看到：

```
.signer
├── .openai_config.json  # 可选，大模型配置
├── data.sqlite3  # SQLite 签到记录库
├── users
│   └── 123456789
│       ├── latest_chats.json  # 获取的最近对话
│       └── me.json  # 个人信息
├── automations  # 自动化规则
│   ├── my_auto  # 自动化任务名
│       ├── config.json  # 自动化配置
│       └── state.json  # 运行状态
└── signs  # 签到任务
    └── linuxdo  # 签到任务名
        ├── config.json  # 签到配置
        ├── 123456789
        │   └── sign_record.json  # 旧版 JSON 签到记录（兼容迁移）
        └── sign_record.json  # 更旧版 JSON 路径（兼容迁移）

```

迁移到 SQLite 后，新的签到记录只写入 `data.sqlite3`，但仍兼容读取旧
`sign_record.json`。当运行任务时如果检测到旧 JSON，程序会输出提示并尝试将该任务
的历史记录自动导入 SQLite。
