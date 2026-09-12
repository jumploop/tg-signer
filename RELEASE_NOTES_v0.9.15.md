## v0.9.15

### 中文

- 修复群组/频道下拉显示 `[object Object]` 的问题:root cause 是 NiceGUI `ui.select` 不支持 Quasar 原生 `[{"label","value"}]` dict 列表格式,改用 `{value: label}` dict 映射后正常显示群组名称

### English

- Fix the group/channel picker showing `[object Object]`: the root cause was NiceGUI `ui.select` not supporting Quasar's native `[{"label","value"}]` list-of-dicts format; switching to a `{value: label}` dict mapping makes channel names display correctly
