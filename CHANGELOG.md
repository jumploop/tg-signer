# Changelog / 版本变动日志

## 版本变动日志

### 0.9.2

基于 [amchii/tg-signer](https://github.com/amchii/tg-signer) 的 `0.9.2`（`cc05ae9`）
构建；此前全部本地改动已合并为一次提交。上游 0.9.2 的修复（Kurigram 2.2.27
适配、`ForumTopic.name`、登出前 `initialize()`、代理默认端口、带引号答案匹配
按钮）全部包含在内。

**WebUI（`tg-signer webgui`）**
- 账号管理：验证码登录、二维码扫码登录、登出并删除 session
- 配置管理：Signer / Automation 配置的增删改查、模板与交互式向导
- 运行控制：按账号启动 / 停止任务并查看状态
- 日志、签到记录、对话列表、大模型连接配置
- 访问码鉴权（`TG_SIGNER_GUI_AUTHCODE`）与工作目录切换

**自动化**
- 规则引擎、内置处理器、模板渲染、插件加载与状态存储
- 支持 `config.json` / `config.yaml` / `config.yml`

**签到**
- SQLite 记录存储与迁移（`<workdir>/data.sqlite3`），保留旧 JSON 兼容读取
- FloodWait 重试、账号级文件锁、话题（`message_thread_id`）支持

**修复**
- 登录验证码投递方式提示与重新发送，账号名已有 session 时不再误报
- 扫码登录（`tg://login`，令牌过期自动重建，支持两步验证）
- 登录会话占用 session 导致的 `database is locked`
- WebUI 登出报 `Client is already terminated`（`log_out()` 前需 `initialize()`）
- 兼容 Kurigram 2.2.27 的事件循环变化
