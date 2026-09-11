## v0.9.14

### 中文

- WebUI 配置管理:「选择配置」与群组/频道下拉双向联动 —— 加载某配置后右侧自动高亮其绑定的聊天(`chats[0].chat_id` / `match_cfgs[0].chat_id`),支持按 int chat.id 或 `@username` 匹配;填入聊天后下拉框即时同步到该群组,目标聊天不在缓存时保持用户选择
- 优化 `generate_random_config_name`:新增本会话去重缓存与磁盘配置名缓存,连续/批量生成不再撞生日悖论(1000 次调用从分钟级降到约 0.5s),并补充缓存清理 fixture 与测试
- 新增 `resolve_chat_id_for_selector` 与相关参数化测试(18 个断言场景)
- 修复群组/频道下拉显示 `[object Object]` 的问题:root cause 是 NiceGUI `ui.select` 不支持 Quasar 原生 `[{"label","value"}]` dict 列表格式,改用 `{value: label}` dict 映射后正常显示群组名称

### English

- WebUI config page: two-way sync between the "select config" dropdown and the group/channel picker — loading a config auto-highlights its bound chat (`chats[0].chat_id` / `match_cfgs[0].chat_id`), matching by int chat.id or `@username`; picking a group immediately syncs the picker, and an unknown chat keeps the user's selection
- Optimize `generate_random_config_name` with an in-session dedup cache and a disk-name cache: bulk generation no longer hits the birthday paradox (1000 calls dropped from minutes to ~0.5s), plus cache-reset fixtures and tests
- Add `resolve_chat_id_for_selector` with parametrized tests (18 assertion scenarios)
- Fix the group/channel picker showing `[object Object]`: the root cause was NiceGUI `ui.select` not supporting Quasar's native `[{"label","value"}]` list-of-dicts format; switching to a `{value: label}` dict mapping makes channel names display correctly
