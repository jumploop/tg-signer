## Telegram Daily Auto Check-in / Personal, Group, and Channel Message Monitoring with Auto Reply

[简体中文](./README.md)

### Features

- Daily scheduled check-ins with random time deviation
- Click keyboard buttons based on configured text
- Use AI for image recognition and click the matching keyboard button
- Monitor personal, group, and channel messages, then forward or auto-reply
- Execute action flows based on configuration

  **...**

### Installation

Requires Python 3.10 or above.

```sh
pip install -U tg-signer
```

Or install the performance extras:

```sh
pip install "tg-signer[speedup]"
```

#### WebUI

`tg-signer` also ships with a WebUI. Install it with:

```sh
pip install "tg-signer[gui]"
```

![webgui](./assets/webui.jpeg)

The WebUI includes account management (login/logout), config management (Signer / Automation config editing, including LLM API config and the interactive config wizard), group selection, user info, sign records and log pages. The account page can log in to obtain a session and log out to delete session files; the group selection page lists cached groups/channels and can quickly fill them into signer or automation configs.
The WebUI uses a front-end/back-end separated architecture: the backend is FastAPI (REST API + static file hosting) and the frontend is Vue 3 (source in `tg_signer/webui/frontend/`). You do not need to build the frontend yourself - the package installed via `pip install "tg-signer[gui]"` already contains the built assets. To modify the frontend, run `npm install && npm run build` inside `tg_signer/webui/frontend/`; the output goes to `tg_signer/webui/static/`.

### Docker

#### GitHub Container Registry

Two prebuilt images are published on GitHub Container Registry:
`ghcr.io/amchii/tg-signer:<tag>` (CLI) and
`ghcr.io/amchii/tg-signer:<tag>-webui` (CLI + WebUI).

#### Local

If you want to build the image yourself, the local build flow is still available.
See the Dockerfiles in the [docker](./docker) directory and its
[README](./docker/README.md).

### Usage

```text
Usage: tg-signer [OPTIONS] COMMAND [ARGS]...

  Use <subcommand> --help for usage instructions

Subcommand aliases:
  run_once -> run-once
  send_text -> send-text

Options:
  -l, --log-level [debug|info|warn|error]
                                  Log level: `debug`, `info`, `warn`, `error`
                                  [default: info]
  --log-file PATH                 Log file path, can be relative  [default: logs/tg-
                                  signer.log]
  --log-dir PATH                  Log directory, can be relative  [default: logs]
  -p, --proxy TEXT                Proxy address, for example:
                                  socks5://127.0.0.1:1080. Overrides the
                                  `TG_PROXY` environment variable  [env var:
                                  TG_PROXY]
  --session_dir PATH              Directory used to store TG sessions, can be
                                  relative  [default: .]
  -a, --account TEXT              Custom account name. The session file will be
                                  named <account>.session  [env var: TG_ACCOUNT;
                                  default: my_account]
  -w, --workdir PATH              tg-signer working directory, used to store
                                  configs and check-in records  [default: .signer]
  --session-string TEXT           Telegram Session String. Overrides the
                                  `TG_SESSION_STRING` environment variable
                                  [env var: TG_SESSION_STRING]
  --in-memory                     Store the session in memory instead of a file
  --help                          Show this message and exit.

Commands:
  export                  Export configuration, defaults to stdout
  import                  Import configuration, defaults to stdin
  list                    List existing configurations
  list-members            List chat members (groups or channels; channels require
                          admin permissions)
  list-folders            List regular Telegram chat folders
  list-sign-records       List the latest N check-in records
  list-topics             List group topic IDs (`message_thread_id`)
  list-schedule-messages  Show configured scheduled messages
  llm-config              Configure the LLM API
  login                   Log in to an account (used to obtain a session)
  migrate-sign-records    Migrate check-in records from JSON to SQLite (keeps the
                          original files by default)
  logout                  Log out and delete the session file
  multi-run               Run multiple accounts with a shared configuration
  reconfig                Reconfigure
  run                     Run check-in tasks based on task configuration
  run-once                Run a check-in task once, even if it has already run
                          today
  schedule-messages       Batch configure Telegram's built-in scheduled messages
  send-dice               Send one DICE message. Make sure the current session has
                          already "seen" this `chat_id`
  send-text               Send one text message. Make sure the current session has
                          already "seen" this `chat_id`
  version                 Show version
  webgui                  Start the WebGUI (requires
                          `pip install "tg-signer[gui]"`)
```

Examples:

```sh
tg-signer run
tg-signer run my_sign  # Run the 'my_sign' task directly, without prompting
tg-signer run-once my_sign  # Run the 'my_sign' task once directly
tg-signer list-folders  # List regular Telegram folders and their explicit chat counts
tg-signer login --from-folder Sign  # Log in and discover chats from the Sign folder
tg-signer run --from-folder Sign my_sign  # Discover chats from Sign before running the task
tg-signer list-sign-records linuxdo -n 5  # View the latest 5 check-in records for task linuxdo
tg-signer migrate-sign-records  # Migrate check-in records under .signer/signs to SQLite
tg-signer send-text 8671234001 /test  # Send '/test' to chat_id '8671234001'
tg-signer send-text @neo /test  # Send '/test' to username '@neo'
tg-signer send-text --message-thread-id 1 -- -1003763902761 checkin  # Send to a group topic (message_thread_id=1)
tg-signer send-text -- -10006758812 water  # For negative numbers, use POSIX style and add '--' before '-'
tg-signer send-text --delete-after 1 8671234001 /test  # Send '/test' to chat_id '8671234001' and delete it after 1 second
tg-signer list-members --chat_id -1001680975844 --admin  # List channel admins
tg-signer list-topics --chat_id -1003763902761 --limit 50  # List group topics and message_thread_id
tg-signer schedule-messages --crontab '0 0 * * *' --next-times 10 -- -1001680975844 hello  # Send a message to '-1001680975844' at 00:00 for the next 10 days
tg-signer schedule-messages --crontab '0 0 * * *' --next-times 3 --message-thread-id 1 -- -1003763902761 hello  # Configure scheduled messages for a group topic
tg-signer multi-run -a account_a -a account_b same_task  # Run 'account_a' and 'account_b' using the same 'same_task' config
tg-signer webgui --auth-code averycomplexcode  # Start the WebGUI
```

When `--auth-code` is set, 5 consecutive wrong attempts lock the login for 60 seconds.

### Configure a Proxy (Optional)

`tg-signer` does not read the system proxy. Use the `TG_PROXY` environment
variable or the `--proxy` argument instead.

For example:

```sh
export TG_PROXY=socks5://127.0.0.1:7890
```

### Login

```sh
tg-signer login
```

Follow the prompts to enter your phone number and verification code. The command
will print your recent chats, so make sure the chat you want to use for
check-ins is included.

Running tasks (`run` / `run-once` / `multi-run` / `automation run`) reuses an existing valid session file directly, so no re-login is required.
You only need to log in (via `tg-signer login` or the WebUI "Account" page) when
the session is missing or invalid.

Signer `chat_id` also supports integer IDs and `@`-prefixed usernames such as
`@neo`.

For forum-style groups, the login output also prints each topic's
`message_thread_id`, which can be used directly with `--message-thread-id`.

If a target chat is not in the recent list, create a regular Telegram folder and
manually add the target chats. You can then load it by name or ID:

```sh
tg-signer list-folders
tg-signer login --from-folder Sign
# Use the ID when multiple folders have the same name
tg-signer login --from-folder 2
```

`--from-folder` discovers chats from the folder and is also available on `run`,
`run-once`, `multi-run`, and `automation run`. When specified,
all manually included or pinned chats in the folder are loaded and
`--num-of-dialogs` is ignored. Folders whose membership is generated from
dynamic rules such as contacts, bots, groups, or channels are not supported;
use a regular folder containing only manually added chats.

### Time Zone

Scheduling-related commands such as `run` and `schedule-messages` resolve the
time zone in the following order:

1. the `TZ` environment variable
2. the local time zone recognized by Python
3. `Asia/Shanghai` as the final fallback

If you need schedules to follow a specific time zone, set `TZ` before starting
the process.

### Get Group Topic IDs

```sh
tg-signer list-topics --chat_id -1003763902761
```

This prints the visible topics in the forum group, including each
`message_thread_id`, title, and status, which makes topic-based configuration
much easier.

### Send a Message Once

```sh
tg-signer send-text 8671234001 hello  # Send 'hello' to chat_id '8671234001'
tg-signer send-text @neo hello  # Send 'hello' to username '@neo'
```

### Run a Check-in Task

```sh
tg-signer run
```

Or specify the task name in advance:

```sh
tg-signer run linuxdo
```

Then follow the prompts to configure it.

#### Example

```text
Start configuring task <linuxdo>
Check-in 1
1. Chat ID (from recent chats during login or @username): 7661096533
2. Chat name (optional): jerry bot
3. Send to a topic (`message_thread_id`)? (y/N): y
4. message_thread_id: 1
5. Start configuring <actions>. Please configure them in the real check-in order.
  1: Send plain text
  2: Send a Dice emoji
  3: Click a keyboard button based on text
  4: Select an option based on an image
  5: Reply to a math question

Action 1:
1. Enter the number of the action: 1
2. Enter the text to send: checkin
3. Continue adding actions? (y/N): y
Action 2:
1. Enter the number of the action: 3
2. Enter the keyboard button text to click: Check in
3. Continue adding actions? (y/N): y
Action 3:
1. Enter the number of the action: 4
Image recognition uses the configured LLM. Make sure your model supports image input.
2. Continue adding actions? (y/N): y
Action 4:
1. Enter the number of the action: 5
Math questions are answered by the configured LLM.
2. Continue adding actions? (y/N): y
Action 5:
1. Enter the number of the action: 2
2. Enter the dice emoji to send (for example 🎲, 🎯): 🎲
3. Continue adding actions? (y/N): n
Before running, set `OPENAI_API_KEY` and `OPENAI_BASE_URL` correctly via environment variables.
The default model is "gpt-4o", and can be changed with `OPENAI_MODEL`.
6. Delete the check-in message after N seconds (wait N seconds after sending before deleting; enter '0' for immediate deletion, or press Enter to keep it), N: 10
╔════════════════════════════════════════════════╗
║ Chat ID: 7661096533                            ║
║ Name: jerry bot                                ║
║ Message Thread ID: 1                           ║
║ Delete After: 10                               ║
╟────────────────────────────────────────────────╢
║ Actions Flow:                                  ║
║ 1. [Send plain text] Text: checkin             ║
║ 2. [Click by text] Click: Check in             ║
║ 3. [Select by image]                           ║
║ 4. [Reply to math question]                    ║
║ 5. [Send Dice emoji] Dice: 🎲                  ║
╚════════════════════════════════════════════════╝
Check-in 1 configured successfully

Continue configuring check-ins? (y/N): n
Daily check-in time (time or crontab expression, such as '06:00:00' or '0 6 * * *'):
Random time deviation in seconds (default is 0): 300
```

### Monitoring Has Been Removed

`tg-signer monitor` and `<workdir>/monitors/` are gone. Use `tg-signer automation`
for message monitoring, forwarding, and auto reply:

```sh
tg-signer automation init my_auto
# Edit .signer/automations/my_auto/config.json
tg-signer automation run my_auto
```

Migration map:

| Old monitor concept | automation equivalent |
| --- | --- |
| Monitor item `chat_id` + matching rule | `message` trigger + `filters` (`text_rule` / `text_value` / `from_user_ids`) |
| Default reply text | `send_text` handler |
| AI reply | `ai_reply` handler |
| Regex extraction of reply text | `send_text` handler `search_regex` + `template` |
| Forward to a chat | `forward` handler |
| Forward to an external target (UDP / HTTP) | `external_forward` handler |
| ServerChan push | `server_chan` handler |

See [docs/automation_usage.md](docs/automation_usage.md) for details.

### Changelog

The changelog has moved to [CHANGELOG.md](CHANGELOG.md#changelog).

### Configuration and Data Storage

Data and configuration are stored in the `.signer` directory by default. If you
run `tree .signer`, you will see:

```text
.signer
├── .openai_config.json  # Optional LLM configuration
├── data.sqlite3  # SQLite check-in record database
├── users
│   └── 123456789
│       ├── latest_chats.json  # Recently fetched chats
│       └── me.json  # Personal profile
└── signs  # Check-in tasks
    └── linuxdo  # Check-in task name
        ├── config.json  # Check-in configuration
        ├── 123456789
        │   └── sign_record.json  # Legacy JSON check-in records (still supported for migration)
        └── sign_record.json  # Even older JSON path (still supported for migration)

5 directories, 6 files
```

After migrating to SQLite, new check-in records are written only to
`data.sqlite3`, but old `sign_record.json` files can still be read. If legacy
JSON is detected while running a task, the program prints a notice and tries to
import that task's historical records into SQLite automatically.
