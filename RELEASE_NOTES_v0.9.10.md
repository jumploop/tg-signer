## v0.9.10

### 中文

- 修复无 `nicegui` 依赖环境下 `import tg_signer.webui` 失败的问题:`webui/__init__.py` 改用 PEP 562 模块级懒加载,`data` / `runner` / `account` / `auth` / `schema_utils` 等轻量子模块在未安装 `tg-signer[gui]` 时也可正常导入,`AUTH_CODE_ENV` / `build_ui` / `main` 保持按需懒加载,向后兼容
- 新增 6 个测试覆盖无 `nicegui` 环境下的懒加载导入行为(CI 默认 runner 不再需要额外安装 GUI 依赖即可跑完整测试)

### English

- WebUI package no longer requires NiceGUI at import time: `tg_signer/webui/__init__.py` uses a PEP 562 lazy module-level `__getattr__`, so the lightweight submodules (`data`, `runner`, `account`, `auth`, `schema_utils`) import cleanly without the `tg-signer[gui]` extra, while `AUTH_CODE_ENV` / `build_ui` / `main` remain lazily loaded for backward compatibility
- Add 6 tests covering lazy-import behavior in environments without NiceGUI (CI default runners can now run the full suite without the GUI extra)
