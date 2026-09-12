## v0.9.17

### 中文

- 修复 WebUI 删除配置后配置仍残留的问题:配置目录里遗留的旧版签到记录文件会让「配置」继续显示;现在列表只显示真正含 `config.json` 的配置,删除配置会连同遗留记录目录一并移除(SQLite 主存储的签到记录不受影响)

### English

- Fix deleted configs still showing in the WebUI: leftover legacy record files under a config directory kept the "config" listed. The picker now lists only directories that actually contain `config.json`, and deleting a config removes its whole directory (SQLite-backed sign records are unaffected)
