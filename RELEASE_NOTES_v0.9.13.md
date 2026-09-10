## v0.9.13

### 中文

- WebUI 配置管理页:群组/频道从「筛选框+卡片列表」改为单个可搜索下拉框(支持按标题/类型/用户名/ID 过滤),账号下拉、刷新按钮与「填入签到/监控配置」按钮合并到一个卡片内
- 填入配置时自动生成未占用的随机配置名(如 `sign_<chat>_<hex>`),写入「保存为/新建名称」输入框,不再误覆盖当前选中的已有配置;名称冲突时循环重试,极端情况下使用更长随机后缀
- 新增 `data.generate_random_config_name` 并补充 6 个测试(前缀、slug、冲突、饱和)
- 修复早退测试 flaky,确保子进程退出后被收割
- 配置 ↔ 群组/频道双向联动:加载配置后右侧群组/频道下拉框自动高亮其绑定的聊天,填入配置后即时同步;支持 int chat.id 与 `@username` 匹配

### English

- WebUI config page: the group/channel picker is now a single searchable dropdown (filter by title/type/username/ID) instead of a filter box plus a card list; the account dropdown, refresh button and the "fill signer/monitor config" buttons are merged into one card
- Filling a config now auto-generates an unused random config name (e.g. `sign_<chat>_<hex>`) into the "save as / new name" input, so it never overwrites the currently selected config; it retries on name collisions and falls back to a longer random suffix in the worst case
- Add `data.generate_random_config_name` plus 6 tests (prefix, slug, collision, saturation)
- Fix flaky early-exit tests and ensure child processes are reaped
- Two-way config ↔ chat linkage: loading a config auto-highlights its bound chat in the group/channel dropdown, and filling a chat syncs the dropdown immediately; matches by int chat id or `@username`
