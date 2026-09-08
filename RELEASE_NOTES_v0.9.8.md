## v0.9.8

### 中文

- 修复 `tg_signer/__main__.py` 缺少 `if __name__ == "__main__"` 入口块,导致 WebUI「统一运行」页面用 `python -m tg_signer` 拉起子进程时立即退出、启动全部失败

### English

- Fix `tg_signer/__main__.py` missing the `if __name__ == "__main__"` entry block, which made the WebUI "Unified Run" page spawn child processes via `python -m tg_signer` that exited immediately, failing every start
