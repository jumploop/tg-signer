## v0.9.19

### 中文

- 运行任务时自动复用已有 session:存在有效 session 文件就直接使用,无需重复登录;只有 session 缺失或失效时才需要登录（`tg-signer login` 或 WebUI「账号管理」）
- session 无效时快速报错,不再触发交互式登录提示挂起子进程

### English

- Running tasks (`run` / `run-once` / `multi-run` / `monitor run` / `automation run` / `send-text`, etc.) now reuses an existing valid session file directly — no re-login needed
- A missing or invalid session fails fast with a clear message instead of hanging on an interactive login prompt (only `tg-signer login` keeps the interactive flow)
