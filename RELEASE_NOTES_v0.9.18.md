## v0.9.18

### 中文

- WebUI「配置管理」页新增「大模型」子页签:配置 OpenAI 兼容大模型 API（API Key / Base URL / Model），保存到 `<workdir>/.openai_config.json`，与 CLI `llm-config` 一致，运行时以环境变量优先
- 代码清理:`clean_schema` 就地修改,删除 `schema.copy()`

### English

- Added an "LLM" tab to the WebUI config management page to configure OpenAI-compatible APIs (API key / base URL / model), saved to `<workdir>/.openai_config.json` with the same behavior as the CLI `llm-config` (environment variables take priority at runtime)
- Code cleanup: `clean_schema` now mutates the passed schema in place (dropped `schema.copy()`)
