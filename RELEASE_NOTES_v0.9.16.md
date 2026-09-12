## v0.9.16

### 中文

- WebUI 新增主题与暗色模式:Telegram 风格品牌色与统一 Header,暗色模式开关支持浏览器记忆偏好
- 代码清理(ponytail 审计):随机配置名生成移除模块级缓存,`--num-of-dialogs` 选项 6 处重复定义收敛为装饰器,chat 序列化逻辑合并为 `chat_to_dict`,`TypeAlias` 改用标准库 `typing`

### English

- WebUI now ships a Telegram-style brand theme with a unified header and a dark-mode toggle that remembers the user's preference in browser storage
- Code cleanup (ponytail audit): dropped module-level caches from random config-name generation, consolidated 6 duplicated `--num-of-dialogs` click options into a `dialogs_option` decorator, deduplicated chat serialization into `chat_to_dict`, and switched `TypeAlias` to the standard-library `typing`
