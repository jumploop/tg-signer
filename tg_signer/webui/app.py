import asyncio
import copy
import json
import os
import secrets
from pathlib import Path
from typing import Callable, Dict, List, Tuple

from nicegui import app, ui
from pydantic import TypeAdapter

from tg_signer.webui import runner
from tg_signer.webui.account import (
    cancel_login,
    complete_login,
    is_account_authorized,
    list_accounts,
    logout_account,
    refresh_dialogs,
    send_login_code,
)
from tg_signer.webui.auth import (
    AUTH_ATTEMPTS_KEY,
    AUTH_MAX_ATTEMPTS,
    auth_lock_remaining,
    clear_auth_failures,
    record_auth_failure,
)
from tg_signer.webui.data import (
    CONFIG_META,
    DEFAULT_LOG_FILE,
    DEFAULT_WORKDIR,
    LOG_DIR,
    ConfigKind,
    UIState,
    _setup_webui_logger,
    delete_config,
    list_log_files,
    list_task_names,
    load_config,
    load_group_chats,
    load_logs,
    load_sign_records,
    load_user_infos,
    save_config,
)
from tg_signer.webui.interactive import InteractiveSignerConfig
from tg_signer.webui.schema_utils import clean_schema

SIGNER_TEMPLATE: Dict[str, object] = {
    "chats": [
        {
            "chat_id": "@channel_or_user",
            "message_thread_id": None,
            "name": "示例任务",
            "delete_after": None,
            "actions": [{"action": 1, "text": "签到"}],
            "action_interval": 1,
        }
    ],
    "sign_at": "0 6 * * *",
    "random_seconds": 0,
    "sign_interval": 1,
}

MONITOR_TEMPLATE: Dict[str, object] = {
    "match_cfgs": [
        {
            "chat_id": "@channel_or_user",
            "rule": "contains",
            "rule_value": "关键词",
            "from_user_ids": None,
            "always_ignore_me": False,
            "default_send_text": "自动回复",
            "ai_reply": False,
            "ai_prompt": None,
            "send_text_search_regex": None,
            "send_text_template": None,
            "delete_after": None,
            "ignore_case": True,
            "forward_to_chat_id": None,
            "external_forwards": None,
            "push_via_server_chan": False,
            "server_chan_send_key": None,
        }
    ]
}


AUTH_CODE_ENV = "TG_SIGNER_GUI_AUTHCODE"
AUTH_STORAGE_KEY = "tg_signer_gui_auth_code"


state = UIState()


def pretty_json(data: Dict[str, object]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def notify_error(exc: Exception) -> None:
    ui.notify(f"{exc}", type="negative")


class BaseConfigBlock:
    def __init__(
        self,
        kind: ConfigKind,
        template: Dict[str, object],
    ):
        self.kind = kind
        self.template = template
        self.title = "签到配置 (signer)" if kind == "signer" else "监控配置 (monitor)"
        self.root_dir, self.cfg_cls = CONFIG_META[kind]
        with ui.card().classes("w-full shadow-md"):
            ui.label(self.title).classes("text-lg font-semibold")
            ui.label(f"目录: {self.root_dir}/<name>/config.json").classes(
                "text-sm text-gray-500"
            )
            with ui.row().classes("items-end w-full gap-3"):
                self.select = ui.select(
                    label="选择配置",
                    options=[],
                    with_input=True,
                    on_change=self.load_current,
                ).classes("min-w-[240px]")
                ui.button("重置", on_click=self.clear_selection).props("outline")
                self.name_input = ui.input(
                    label="保存为/新建名称",
                    placeholder="my_task",
                ).classes("min-w-[200px]")
                ui.button("使用示例", on_click=self.fill_template)
                self.setup_toolbar()

            # MonitorConfig schema causes json_editor to fail rendering due to "format": "uri" etc.
            # We need to clean the schema before passing it to the editor.
            schema = TypeAdapter(self.cfg_cls | None).json_schema()
            if self.kind == "monitor":
                schema = clean_schema(schema)

            def on_change(e):
                self.editor.properties["content"] = e.content

            self.editor = ui.json_editor(
                {"content": {"json": None}},
                schema=schema,
                on_change=on_change,
            )
            self.selected_name: dict[str, str] = {"value": ""}

            with ui.row().classes("gap-2 items-center"):
                ui.button("刷新列表", on_click=self.refresh_options)
                ui.button("加载", on_click=self.load_current)
                ui.button("保存", color="primary", on_click=self.save_current)
                ui.button("删除", color="negative", on_click=self.delete_current)
            self.setup_footer()

    def clear_selection(self) -> None:
        self.select.value = None
        self.name_input.value = ""
        self.fill_template()
        self.selected_name["value"] = ""

    def setup_toolbar(self):
        """Override to add more buttons to the top toolbar"""
        pass

    def setup_footer(self):
        """Override to add more buttons to the bottom footer"""
        pass

    def __call__(self, *args, **kwargs):
        self.refresh_options()

    def refresh_options(self) -> None:
        options = list_task_names(self.kind, state.workdir)
        self.select.options = options
        self.select.update()

    def load_current(self) -> None:
        target = self.select.value
        if not target:
            return
        try:
            entry = load_config(self.kind, target, workdir=state.workdir)
            self.editor.properties["content"]["json"] = entry.payload
            self.name_input.value = entry.name
            self.editor.update()
            self.name_input.update()
            self.editor.run_editor_method(":expand", "[]", "path => true")
            self.selected_name["value"] = target
            self.on_loaded(target)
        except Exception as exc:  # noqa: BLE001
            notify_error(exc)

    def on_loaded(self, target: str):
        """Hook called after config is loaded"""
        pass

    def save_current(self) -> None:
        target = (self.name_input.value or self.select.value or "").strip()
        if not target:
            ui.notify("请先填写配置名称", type="warning")
            return
        try:
            save_config(
                self.kind,
                target,
                self.editor.properties["content"]["json"] or "{}",
                workdir=state.workdir,
            )
            self.refresh_options()
            self.select.value = target
            self.select.update()
            self.selected_name["value"] = target
            self.on_loaded(target)
            ui.notify("保存成功", type="positive")
        except Exception as exc:  # noqa: BLE001
            notify_error(exc)

    def fill_template(self) -> None:
        self.editor.properties["content"]["json"] = self.template
        self.editor.update()

    def delete_current(self) -> None:
        target = (self.select.value or "").strip() or (
            self.name_input.value or ""
        ).strip()
        if not target:
            ui.notify("请选择要删除的配置", type="warning")
            return

        with ui.dialog() as dialog, ui.card().classes("p-4 min-w-[320px]"):
            ui.label(f"确认删除配置: {target}？").classes("text-lg font-semibold")
            ui.label("删除后不可恢复。").classes("text-sm text-gray-500")
            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                ui.button("取消", on_click=dialog.close).props("flat")
                ui.button(
                    "删除",
                    color="negative",
                    on_click=lambda: (dialog.close(), self._do_delete(target)),
                )
        dialog.open()

    def _do_delete(self, target: str) -> None:
        try:
            delete_config(self.kind, target, workdir=state.workdir)
            self.refresh_options()
            if self.select.value == target:
                self.select.value = None
                self.select.update()
            self.selected_name["value"] = ""
            ui.notify("已删除配置", type="positive")
        except Exception as exc:  # noqa: BLE001
            notify_error(exc)


class SignerBlock(BaseConfigBlock):
    def __init__(
        self,
        template: Dict[str, object],
        *,
        goto_records: Callable[[str], None] = lambda _task: None,
    ):
        self.record_btn = None
        self.record_hint = None
        self._goto_records = goto_records
        super().__init__("signer", template)

    def setup_toolbar(self):
        ui.button("交互式配置", on_click=self.open_interactive).props("outline")

    def setup_footer(self):
        self.record_hint = ui.label("").classes("text-sm text-primary")
        self.record_btn = ui.button(
            "查看签到记录",
            color="primary",
            on_click=self.goto_records,
        ).classes("min-w-[120px]")
        self.record_btn.disable()

    def on_loaded(self, target: str):
        records = load_sign_records(state.workdir)
        has_record = any(r.task == target for r in records)
        if has_record:
            self.record_btn.enable()
            self.record_hint.text = f"发现签到记录: {target}"
        else:
            self.record_btn.disable()
            self.record_hint.text = "无签到记录"
        self.record_hint.update()
        self.record_btn.update()

    def goto_records(self):
        self._goto_records(self.selected_name["value"])

    def apply_chat(self, chat: Dict[str, object]) -> None:
        content = self.editor.properties["content"].get("json")
        if not isinstance(content, dict) or not isinstance(content.get("chats"), list):
            content = copy.deepcopy(SIGNER_TEMPLATE)
        content.setdefault("sign_at", SIGNER_TEMPLATE["sign_at"])
        content.setdefault("random_seconds", SIGNER_TEMPLATE["random_seconds"])
        content.setdefault("sign_interval", SIGNER_TEMPLATE["sign_interval"])
        chats = content["chats"]
        if not chats:
            chats.append(copy.deepcopy(SIGNER_TEMPLATE["chats"][0]))
        chat_item = chats[0]
        chat_item["chat_id"] = chat.get("id")
        chat_item["name"] = str(chat.get("title") or chat.get("username") or "")
        self.editor.properties["content"]["json"] = content
        self.editor.update()
        self.editor.run_editor_method(":expand", "[]", "path => true")
        ui.notify(
            f"已填入签到配置: {chat_item['name'] or chat.get('id')}",
            type="positive",
        )

    def open_interactive(self):
        def on_complete():
            self.refresh_options()
            # If the user saved a config with the same name as currently selected, reload it
            if self.select.value:
                self.load_current()

        initial_config = self.editor.properties["content"].get("json")
        initial_name = self.name_input.value or self.select.value or ""

        wizard = InteractiveSignerConfig(
            state.workdir,
            on_complete=on_complete,
            initial_config=initial_config,
            initial_name=initial_name,
        )
        wizard.open()


class MonitorBlock(BaseConfigBlock):
    def __init__(self, template: Dict[str, object]):
        super().__init__("monitor", template)

    def apply_chat(self, chat: Dict[str, object]) -> None:
        content = self.editor.properties["content"].get("json")
        if not isinstance(content, dict) or not isinstance(
            content.get("match_cfgs"), list
        ):
            content = copy.deepcopy(MONITOR_TEMPLATE)
        match_cfgs = content["match_cfgs"]
        if not match_cfgs:
            match_cfgs.append(copy.deepcopy(MONITOR_TEMPLATE["match_cfgs"][0]))
        match_cfg = match_cfgs[0]
        match_cfg["chat_id"] = chat.get("id")
        self.editor.properties["content"]["json"] = content
        self.editor.update()
        self.editor.run_editor_method(":expand", "[]", "path => true")
        ui.notify(f"已填入监控配置: {chat.get('id')}", type="positive")


def user_info_block() -> Callable[[], None]:
    container = ui.column().classes("w-full gap-2")

    def refresh() -> None:
        container.clear()
        entries = load_user_infos(state.workdir)
        with container:
            if not entries:
                ui.label("未找到用户信息").classes("text-gray-500")
                return
            for entry in entries:
                name = entry.data.get("first_name") or ""
                header = f"{entry.user_id} {name}".strip()
                with ui.expansion(header, icon="person"):
                    ui.label(f"文件: {entry.path}")
                    ui.code(pretty_json(entry.data), language="json").classes("w-full")

                    if entry.latest_chats:
                        ui.separator().classes("my-2")
                        ui.label(f"最近聊天 ({len(entry.latest_chats)})").classes(
                            "font-semibold"
                        )

                        chat_rows = []
                        for chat in entry.latest_chats:
                            chat_rows.append(
                                {
                                    "id": chat.get("id"),
                                    "title": chat.get("title")
                                    or chat.get("first_name")
                                    or "N/A",
                                    "type": chat.get("type"),
                                    "username": chat.get("username") or "",
                                }
                            )

                        ui.table(
                            columns=[
                                {
                                    "name": "id",
                                    "label": "ID",
                                    "field": "id",
                                    "align": "left",
                                },
                                {
                                    "name": "title",
                                    "label": "名称",
                                    "field": "title",
                                    "align": "left",
                                },
                                {
                                    "name": "type",
                                    "label": "类型",
                                    "field": "type",
                                    "align": "left",
                                },
                                {
                                    "name": "username",
                                    "label": "用户名",
                                    "field": "username",
                                    "align": "left",
                                },
                            ],
                            rows=chat_rows,
                            pagination=10,
                        ).classes("w-full").props("flat dense")
                    else:
                        ui.label("未找到最近聊天记录").classes(
                            "text-gray-500 text-sm mt-2"
                        )

    return refresh


class SignRecordBlock:
    def __init__(self):
        self.container = ui.column().classes("w-full gap-3")
        with ui.row().classes("items-end gap-3"):
            self.filter_input = ui.input(
                label="筛选任务/用户",
                placeholder="输入任务名或用户ID过滤",
                value=state.record_filter,
                on_change=lambda e: self._update_filter(e.value),
            ).classes("w-full")
            ui.button("清除筛选", on_click=lambda: self._update_filter("")).props(
                "outline"
            )
        self.status = ui.label("").classes("text-sm text-gray-500")

    def _update_filter(self, value: str) -> None:
        state.record_filter = value or ""
        self.refresh()

    def refresh(
        self,
    ) -> None:
        self.container.clear()
        records = load_sign_records(state.workdir)
        keyword = (state.record_filter or "").lower().strip()
        if keyword:
            records = [
                r
                for r in records
                if keyword in r.task.lower()
                or (r.user_id and keyword in str(r.user_id).lower())
            ]
        with self.container:
            if not records:
                self.status.text = "未找到匹配的签到记录" if keyword else "尚无签到记录"
                self.status.update()
                return
            self.status.text = f"共 {len(records)} 组记录"
            self.status.update()
            for record in records:
                user_text = record.user_id or "默认"
                header = f"{record.task} / {user_text}（{len(record.records)}条）"
                with ui.expansion(header, icon="event").classes("shadow-sm"):
                    ui.label(f"来源: {record.path}").classes("text-gray-500")
                    if not record.records:
                        ui.label("暂无记录").classes("text-gray-500")
                        continue
                    rows = [{"日期": k, "时间": v} for k, v in record.records]
                    ui.table(
                        columns=[
                            {"name": "日期", "label": "日期", "field": "日期"},
                            {"name": "时间", "label": "时间", "field": "时间"},
                        ],
                        rows=rows,
                    ).classes("w-full").props("flat dense")

    def __call__(self, *args, **kwargs):
        return self.refresh()


def log_block() -> Callable[[], None]:
    with ui.card().classes("w-full shadow-sm"):
        ui.label("日志查看").classes("text-md font-semibold")
        ui.label("查看最新日志行，可自定义文件路径和行数。").classes(
            "text-sm text-gray-500 mb-1"
        )

        with ui.row().classes("items-end w-full gap-3 flex-wrap"):
            limit_input = ui.number(
                label="日志行数",
                value=state.log_limit,
                min=10,
                max=2000,
                format="%d",
            ).classes("w-32")
            log_select = ui.select(
                label="选择日志文件（logs/ 或 <workdir>/logs/）",
                options=[],
                on_change=lambda e: select_log_file(e.value),
            ).classes("min-w-[220px]")
            log_path_input = ui.input(
                label="日志路径（可自定义）", value=str(state.log_path)
            ).classes("w-full")
        log_area = ui.scroll_area().classes(
            "w-full bg-gray-50 rounded-lg border border-gray-200"
        )
        log_area.style("max-height: 420px")
        with log_area:
            log_list = (
                ui.column()
                .classes("w-full gap-0 p-3 font-mono text-sm")
                .style("white-space: pre;")
            )

        def classify_line(line: str) -> str:
            upper = line.upper()
            if "ERROR" in upper:
                return "text-red-700"
            if "WARN" in upper:
                return "text-amber-700"
            if "INFO" in upper:
                return "text-blue-700"
            return "text-gray-800"

        def refresh_log_options() -> None:
            seen: dict[str, str] = {}
            # 优先扫 workdir/logs,统一的主日志;再 fallback 到旧 LOG_DIR 兼容旧部署
            for base in (state.workdir / "logs", LOG_DIR):
                if not base.is_dir():
                    continue
                for log_file in list_log_files(base):
                    seen[str(log_file)] = str(log_file)
            options = list(seen)

            workdir_default = str(state.workdir / "logs" / DEFAULT_LOG_FILE.name)
            if Path(workdir_default).is_file():
                resolved_default = workdir_default
            elif Path(DEFAULT_LOG_FILE).is_file():
                resolved_default = str(DEFAULT_LOG_FILE)
            else:
                resolved_default = workdir_default

            current_path = str(log_path_input.value or state.log_path)
            # After switching workdir, keep the user's custom path, otherwise auto-switch
            # to an existing log file under the new workdir (or the CWD default).
            if current_path == str(DEFAULT_LOG_FILE) and resolved_default != str(
                DEFAULT_LOG_FILE
            ):
                current_path = resolved_default
                log_path_input.value = resolved_default
                log_path_input.update()
            if current_path and current_path not in options:
                options.insert(0, current_path)
            log_select.options = options
            log_select.value = current_path
            log_select.update()

        def select_log_file(path_value: str | None) -> None:
            if not path_value:
                return
            log_path_input.value = path_value
            log_path_input.update()
            refresh()

        def refresh() -> None:
            refresh_log_options()
            try:
                state.log_limit = int(limit_input.value or state.log_limit)
            except ValueError:
                state.log_limit = 200
            state.set_log_path(log_path_input.value or str(DEFAULT_LOG_FILE))
            path, lines = load_logs(state.log_limit, log_path_input.value)
            log_list.clear()
            if not lines:
                with log_list:
                    ui.label(
                        f"未找到日志文件: {path}（可检查 logs/ 与 <workdir>/logs/）"
                    ).classes("text-gray-500 text-sm")
                log_list.update()
                refresh_status(f"未找到日志文件: {path}（logs/ 或 <workdir>/logs/）")
                return

            with log_list:
                for line in lines:
                    color = classify_line(line)
                    ui.label(line).classes(f"w-full {color}").style("white-space: pre;")
            log_list.update()
            refresh_status(f"文件: {path} | 显示最新 {len(lines)} 行")

        with ui.row().classes("gap-2 mt-2 items-center justify-between"):
            with ui.row().classes("gap-2 items-center"):
                ui.button("刷新日志", on_click=refresh)
                auto_refresh = ui.checkbox("自动刷新（5秒）", value=False)
            log_status = ui.label("").classes("text-xs text-gray-500")

        log_timer = ui.timer(5.0, refresh, active=False)

        def toggle_auto_refresh(e) -> None:
            log_timer.active = bool(e.value)

        auto_refresh.on_value_change(toggle_auto_refresh)

        def refresh_status(text: str) -> None:
            log_status.text = text
            log_status.update()

        refresh_log_options()

    return refresh


def group_chat_block(
    on_pick: Callable[[Dict[str, object], str], None],
) -> Callable[[], None]:
    container = ui.column().classes("w-full gap-2")
    filter_input = ui.input(
        label="筛选群组",
        placeholder="名称 / 用户名 / ID",
    ).classes("w-full")
    with ui.row().classes("items-center w-full gap-3"):
        account_select = ui.select(
            options=[],
            value=None,
            label="账号",
        ).classes("w-56")
        refresh_btn = ui.button(
            "刷新最近 50 个对话",
            color="primary",
            on_click=lambda: refresh_async(),
        ).props("dense")
        status_label = ui.label("").classes("text-sm text-gray-500")

    def sync_accounts() -> None:
        names = [
            item["account"]
            for item in list_accounts(state.workdir)
            if "session" in item["kind"]
        ]
        if names != account_select.options:
            account_select.options = names
            if account_select.value not in names:
                account_select.value = names[0] if names else None
            account_select.update()

    async def refresh_async() -> None:
        account = account_select.value
        if not account:
            ui.notify("请先选择一个账号（需先在“账号管理”登录）", type="warning")
            return
        refresh_btn.disable()
        status_label.text = "正在获取最近对话..."
        status_label.update()
        try:
            ok, message = await refresh_dialogs(str(account), state.workdir, 50)
        except Exception as exc:  # noqa: BLE001
            ok, message = False, str(exc)
        status_label.text = ""
        status_label.update()
        refresh_btn.enable()
        ui.notify(message, type="positive" if ok else "negative")
        refresh_with_filter()

    def refresh(filter_text: str = "") -> None:
        sync_accounts()
        container.clear()
        keyword = (filter_text or "").strip().lower()
        chats = [
            chat
            for chat in load_group_chats(state.workdir)
            if not keyword
            or keyword in str(chat.get("title") or "").lower()
            or keyword in str(chat.get("username") or "").lower()
            or keyword in str(chat.get("id") or "")
        ]
        with container:
            if not chats:
                ui.label(
                    "未找到群组/频道信息，请先运行 tg-signer login 或 run 生成 "
                    "users/*/latest_chats.json"
                ).classes("text-gray-500")
                return
            for chat in chats:
                title = chat.get("title") or chat.get("first_name") or "未命名"
                username = f"@{chat['username']}" if chat.get("username") else "-"
                with ui.card().classes("w-full p-3"):
                    with ui.row().classes("w-full items-center gap-3"):
                        with ui.column().classes("flex-grow gap-0"):
                            ui.label(str(title)).classes("font-medium")
                            ui.label(
                                f"{chat.get('type')} | {username} "
                                f"| ID: {chat.get('id')} | 账号: {chat.get('account') or '-'}"
                            ).classes("text-sm text-gray-500")
                        ui.button(
                            "填入签到配置",
                            on_click=lambda c=chat: on_pick(c, "signer"),
                        ).props("outline dense")
                        ui.button(
                            "填入监控配置",
                            on_click=lambda c=chat: on_pick(c, "monitor"),
                        ).props("outline dense")

    def refresh_with_filter() -> None:
        refresh(filter_input.value)

    filter_input.on_value_change(lambda _e: refresh_with_filter())
    refresh()
    return refresh_with_filter


def account_block() -> Callable[[], None]:
    container = ui.column().classes("w-full gap-2")

    def logout_confirm(account: str) -> None:
        with ui.dialog() as dialog, ui.card().classes("p-4 min-w-[320px]"):
            ui.label(f"确认登出 {account}？").classes("text-lg font-semibold")
            ui.label(
                "将调用 Telegram 登出并删除 <account>.session / .session_string 文件。"
            ).classes("text-sm text-gray-500")
            status = ui.label("").classes("text-sm text-gray-500")

            async def do_logout() -> None:
                ok_btn.disable()
                cancel_btn.disable()
                status.text = "正在登出..."
                status.update()
                try:
                    message = await logout_account(account, state.workdir)
                except Exception as exc:  # noqa: BLE001
                    status.text = str(exc)
                    status.update()
                    ok_btn.enable()
                    cancel_btn.enable()
                    return
                dialog.close()
                ui.notify(message, type="positive")
                refresh()

            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                cancel_btn = ui.button("取消", on_click=dialog.close).props("flat")
                ok_btn = ui.button("确认登出", color="negative", on_click=do_logout)
        dialog.open()

    def open_login_dialog() -> None:
        state_cell = {"account": "", "phase": "phone"}

        with ui.dialog() as dialog, ui.card().classes("w-full max-w-xl"):
            ui.label("登录 Telegram 账号").classes("text-lg font-bold")
            account_input = ui.input(
                label="账号名称（session 文件名）", value="my_account"
            ).classes("w-full")
            phone_input = ui.input(label="手机号（含区号，如 +8613800138000）").classes(
                "w-full"
            )
            code_input = ui.input(label="验证码").classes("w-full")
            password_input = ui.input(
                label="两步验证密码（如启用）",
                placeholder="仅需要时填写",
                password=True,
                password_toggle_button=True,
            ).classes("w-full")
            status = ui.label("").classes("text-sm text-gray-600")

            code_input.disable()
            password_input.disable()

            def cancel() -> None:
                if state_cell["phase"] == "code":
                    cancel_login(state_cell["account"])
                dialog.close()

            async def send_code() -> None:
                account = (account_input.value or "").strip()
                phone = (phone_input.value or "").strip()
                if not account or not phone:
                    status.text = "请填写账号名称和手机号"
                    status.update()
                    return
                state_cell["account"] = account
                send_btn.disable()
                status.text = "正在发送验证码..."
                status.update()
                result, message = await asyncio.to_thread(
                    send_login_code, account, phone, state.workdir
                )
                if result == "already":
                    cancel_login(account)
                    status.text = message
                    status.update()
                    ui.notify(message, type="positive")
                    dialog.close()
                    refresh()
                    return
                if result == "ok":
                    state_cell["phase"] = "code"
                    code_input.enable()
                    password_input.enable()
                    complete_btn.enable()
                    status.text = message
                else:
                    send_btn.enable()
                    cancel_login(account)
                    status.text = message
                status.update()

            async def do_complete() -> None:
                code = (code_input.value or "").strip()
                if not code:
                    status.text = "请填写验证码"
                    status.update()
                    return
                complete_btn.disable()
                status.text = "正在登录..."
                status.update()
                result, message = await asyncio.to_thread(
                    complete_login,
                    state_cell["account"],
                    code,
                    (password_input.value or "").strip() or None,
                )
                if result == "password_needed":
                    status.text = "需要两步验证密码，请填写后再次点击完成登录"
                    complete_btn.enable()
                elif result == "ok":
                    status.text = message
                    status.update()
                    dialog.close()
                    refresh()
                    return
                else:
                    status.text = message
                    complete_btn.enable()
                status.update()

            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("取消", on_click=cancel).props("flat")
                send_btn = ui.button("发送验证码", on_click=send_code)
                complete_btn = ui.button("完成登录", on_click=do_complete)
                complete_btn.disable()

        dialog.open()

    def refresh() -> None:
        container.clear()
        accounts = list_accounts(state.workdir)
        with container:
            with ui.row().classes("w-full items-center justify-between"):
                ui.label(f"已发现 {len(accounts)} 个账号").classes(
                    "text-sm text-gray-500"
                )
                ui.button(
                    "登录新账号",
                    icon="person_add",
                    on_click=open_login_dialog,
                )
            if not accounts:
                ui.label(
                    "未找到 session 文件。登录后会在工作目录生成 <account>.session。"
                ).classes("text-gray-500")
                return
            for info in accounts:
                with ui.card().classes("w-full p-3"):
                    with ui.row().classes("w-full items-center gap-3"):
                        with ui.column().classes("flex-grow gap-0"):
                            ui.label(info["account"]).classes("font-medium")
                            ui.label(
                                f"{', '.join(info['kind'])} "
                                f"| {info.get('session_file') or '-'}"
                            ).classes("text-sm text-gray-500")
                        ui.button(
                            "登出并删除Session",
                            color="negative",
                            on_click=lambda a=info["account"]: logout_confirm(a),
                        ).props("outline")

    refresh()
    return refresh


def top_controls(on_refresh: Callable[[], None]) -> None:
    with ui.card().classes("w-full"):
        ui.label("基础设置").classes("text-lg font-semibold")
        with ui.row().classes("items-end w-full"):
            workdir_input = ui.input(
                label="工作目录",
                value=str(state.workdir),
                placeholder=".signer",
            ).classes("w-full")
            ui.button(
                "应用并刷新",
                color="primary",
                on_click=lambda: _apply_paths(workdir_input, on_refresh),
            )


def _apply_paths(workdir_input, on_refresh: Callable[[], None]) -> None:
    try:
        state.set_workdir(workdir_input.value or str(DEFAULT_WORKDIR))
        ui.notify(f"已切换工作目录: {state.workdir}", type="positive")
    except Exception as exc:  # noqa: BLE001
        notify_error(exc)
        return
    on_refresh()


def run_block() -> Callable[[], None]:
    """ "统一运行"页面：选择账号后一键启动/停止持续运行进程。

    一个账号同 kind 的多个任务共享一个子进程(共享 pyrogram Client),
    避免多进程抢 SQLite session 文件触发 ``database is locked``;
    跨 WebUI 实例的并发启动由账号级文件锁兜底拒绝。
    """
    with ui.card().classes("w-full"):
        ui.label("统一运行（持续监控）").classes("text-lg font-semibold")
        ui.label(
            "以独立 CLI 进程持续运行所选类型/账号的全部任务，多个任务共享同一进程与 "
            "Client（避免 SQLite session 文件锁冲突）。日志写入 "
            "<workdir>/logs/，可在“日志”页查看；WebUI 服务重启后进程不再受管理。"
        ).classes("text-sm text-gray-500")
        with ui.row().classes("items-end w-full"):
            kind_select = ui.select(
                options=["signer", "monitor"],
                value="signer",
                label="运行类型",
            ).classes("w-44")
            account_select = ui.select(
                options=[],
                value=None,
                label="账号（session）",
            ).classes("w-60")
            ui.button("启动全部", color="primary", on_click=lambda: start_all())
            ui.button("刷新状态", on_click=lambda: refresh())
        status_list = ui.column().classes("w-full gap-1")
        _last_snapshot = None

        def notify_result(ok: bool, msg: str) -> None:
            ui.notify(msg, type="positive" if ok else "warning")

        def sync_accounts() -> None:
            names = [
                item["account"]
                for item in list_accounts(state.workdir)
                if "session" in item["kind"]
            ]
            if names != account_select.options:
                account_select.options = names
                if account_select.value not in names:
                    account_select.value = names[0] if names else None
                account_select.update()

        def stop_process(kind: str, account: str) -> None:
            ok, msg = runner.stop(kind, account)
            notify_result(ok, msg)
            refresh(force=True)

        async def start_all() -> None:
            kind = kind_select.value
            account = account_select.value
            if not account:
                ui.notify("请先选择一个账号（需先在“账号管理”登录）", type="warning")
                return
            ok_auth, auth_msg = await is_account_authorized(str(account), state.workdir)
            if not ok_auth:
                ui.notify(auth_msg, type="negative")
                return
            tasks = list_task_names(kind, state.workdir)
            if not tasks:
                ui.notify(f"当前工作目录没有 {kind} 任务配置", type="warning")
                return
            # 关键改动: 多个任务合并到一个子进程,共享 pyrogram Client / 同一份
            # SQLite session 文件,避免多进程抢锁导致 "database is locked"。
            # runner.start 内部 time.sleep 1.5s,仍丢线程池避免冻结事件循环。
            ok, msg = await asyncio.to_thread(
                runner.start, kind, tasks, state.workdir, str(account)
            )
            notify_result(ok, msg)
            if not ok:
                refresh(force=True)
                return
            # 早期失败探测: 子进程启动后立即退出会被这里捕获
            await asyncio.sleep(1.5)
            if not runner.status(kind, str(account)):
                notify_result(
                    False,
                    f"账号 {account} 的 {kind} 任务启动后立即退出,请到“日志”页查看",
                )
            refresh(force=True)

        def refresh(force: bool = False) -> None:
            nonlocal _last_snapshot
            sync_accounts()
            # 行维度从 (kind, task) 改为 (kind, account): 一个进程跑同 kind/account
            # 的所有任务,UI 上展示「正在运行哪些账号的哪些类型任务」,以及任务数。
            entries: List[Tuple[str, str, int]] = []
            for kind in ("signer", "monitor"):
                tasks = list_task_names(kind, state.workdir)
                accounts = {
                    item["account"]
                    for item in list_accounts(state.workdir)
                    if "session" in item["kind"]
                }
                for account in sorted(accounts):
                    entries.append((kind, account, len(tasks)))
            running = runner.running_tasks()
            snapshot = (
                tuple(entries),
                frozenset(k for k, v in running.items() if v),
            )
            if not force and snapshot == _last_snapshot:
                return
            _last_snapshot = snapshot
            status_list.clear()
            if not entries:
                with status_list:
                    ui.label(
                        "当前工作目录没有签到/监控任务配置,或没有已登录的账号。"
                    ).classes("text-gray-500")
                return
            with status_list:
                for kind, account, task_count in entries:
                    is_run = running.get(runner.process_key(kind, account), False)
                    label = f"{kind} · {account} ({task_count} 个任务)"
                    with ui.row().classes("items-center w-full gap-3"):
                        ui.label(label).classes("w-80")
                        ui.badge(
                            "运行中" if is_run else "已停止",
                            color="positive" if is_run else "default",
                        ).props("outline")
                        if is_run:
                            ui.button(
                                "停止",
                                on_click=lambda k=kind, a=account: stop_process(k, a),
                            ).props("dense flat")

        ui.timer(5.0, refresh, active=True)
    return refresh


def _build_dashboard(container) -> None:
    with container:
        ui.label("TG Signer Web 控制台").classes(
            "text-2xl font-semibold tracking-wide mb-2"
        )
        refreshers: list[Callable[[], None]] = []
        refresh_records: "SignRecordBlock"

        def refresh_all() -> None:
            for refresh in refreshers:
                refresh()

        top_controls(refresh_all)

        with ui.tabs().classes("w-full") as tabs:
            tab_configs = ui.tab("配置管理")
            tab_run = ui.tab("统一运行")
            tab_accounts = ui.tab("账号管理")
            tab_users = ui.tab("用户信息")
            tab_records = ui.tab("签到记录")
            tab_logs = ui.tab("日志")

        sub_tabs = None
        signer_block = None
        monitor_block = None

        def pick_group(chat: Dict[str, object], kind: str) -> None:
            if kind == "signer" and signer_block is not None:
                signer_block.apply_chat(chat)
                target_panel = tab_signer
            elif kind == "monitor" and monitor_block is not None:
                monitor_block.apply_chat(chat)
                target_panel = tab_monitor
            else:
                return
            sub_tabs.value = target_panel
            sub_tabs.update()

        def goto_records(task_name: str) -> None:
            tabs.value = tab_records
            tabs.update()
            refresh_records.filter_input.set_value(task_name)

        with ui.tab_panels(tabs, value=tab_configs).classes("w-full"):
            with ui.tab_panel(tab_configs):
                ui.label(
                    "管理 signer 和 monitor 的配置文件，右侧可快速选择群组填入配置。"
                ).classes("text-gray-600")
                with ui.row().classes("w-full items-start gap-4"):
                    with ui.column().classes("flex-1 min-w-0"):
                        with ui.tabs().classes("w-full") as sub_tabs:
                            tab_signer = ui.tab("Signer")
                            tab_monitor = ui.tab("Monitor")
                        with ui.tab_panels(sub_tabs, value=tab_signer).classes(
                            "w-full"
                        ):
                            with ui.tab_panel(tab_signer):
                                signer_block = SignerBlock(
                                    SIGNER_TEMPLATE, goto_records=goto_records
                                )
                                refreshers.append(signer_block)
                            with ui.tab_panel(tab_monitor):
                                monitor_block = MonitorBlock(MONITOR_TEMPLATE)
                                refreshers.append(monitor_block)
                    with ui.column().classes("w-96 shrink-0"):
                        ui.label("群组 / 频道").classes("text-lg font-semibold")
                        ui.label(
                            "从已登录账号缓存 (users/*/latest_chats.json) 列出群组/"
                            "频道，点击即可填入左侧配置。"
                        ).classes("text-sm text-gray-500 mb-2")
                        refreshers.append(group_chat_block(pick_group))

            with ui.tab_panel(tab_run):
                ui.label(
                    "选择账号后一键启动/停止全部签到或监控持续进程，日志写入 <workdir>/logs/。"
                ).classes("text-gray-600")
                refreshers.append(run_block())

            with ui.tab_panel(tab_accounts):
                ui.label(
                    "登录账号以获取 session，并管理已有账号（登出会删除 session 文件）。"
                ).classes("text-gray-600")
                refreshers.append(account_block())

            with ui.tab_panel(tab_users):
                ui.label("查看当前已登录账户信息 (users/*/me.json)。").classes(
                    "text-gray-600"
                )
                refreshers.append(user_info_block())

            with ui.tab_panel(tab_records):
                ui.label(
                    "签到记录（优先读取 SQLite，兼容旧 sign_record.json）"
                ).classes("text-gray-600")
                refresh_records = SignRecordBlock()
                refreshers.append(refresh_records)

            with ui.tab_panel(tab_logs):
                ui.label("查看日志文件的最新行。").classes("text-gray-600")
                refreshers.append(log_block())

        refresh_all()


def _auth_gate(container, auth_code: str, on_success: Callable[[], None]) -> None:
    with container:
        ui.label("TG Signer Web 控制台").classes(
            "text-2xl font-semibold tracking-wide mb-2"
        )
        ui.label("已启用访问控制，请输入 Auth Code 继续使用 Web 控制台。").classes(
            "text-gray-600"
        )
        with ui.column().classes("w-full items-center"):
            with ui.card().classes("w-full max-w-xl shadow-md"):
                ui.label("Auth Code 验证").classes("text-lg font-semibold")
                ui.label("检测到auth_code环境变量已配置，首次访问需验证。").classes(
                    "text-sm text-gray-500"
                )
                code_input = ui.input(
                    label="Auth Code",
                    placeholder="请输入授权码",
                    password=True,
                    password_toggle_button=True,
                ).classes("w-full")
                status = ui.label("").classes("text-sm text-negative")

                def verify() -> None:
                    storage = app.storage.user
                    lock_remaining = auth_lock_remaining(storage)
                    if lock_remaining > 0:
                        seconds = int(lock_remaining) + 1
                        status.text = f"尝试过于频繁，请在 {seconds} 秒后重试"
                        status.update()
                        return
                    code = (code_input.value or "").strip()
                    if not code:
                        ui.notify("请输入授权码", type="warning")
                        return
                    if not secrets.compare_digest(
                        code.encode("utf-8"), auth_code.encode("utf-8")
                    ):
                        locked_for = record_auth_failure(storage)
                        if locked_for:
                            status.text = f"失败次数过多，已锁定 {int(locked_for)} 秒"
                        else:
                            remaining = AUTH_MAX_ATTEMPTS - int(
                                storage.get(AUTH_ATTEMPTS_KEY, 0)
                            )
                            status.text = f"授权码错误，请重试（剩余 {remaining} 次）"
                        status.update()
                        code_input.set_value("")
                        ui.notify("认证失败", type="negative")
                        return
                    clear_auth_failures(storage)
                    storage[AUTH_STORAGE_KEY] = auth_code
                    ui.notify("认证成功", type="positive")
                    container.clear()
                    on_success()

                ui.button("验证并进入", color="primary", on_click=verify).classes(
                    "w-full mt-2"
                )


def build_ui(auth_code: str = None) -> None:
    ui.page_title("TG Signer Web 控制台")
    root = ui.column().classes("w-full gap-3")

    def render_dashboard() -> None:
        root.clear()
        _build_dashboard(root)

    auth_code = auth_code or (os.environ.get(AUTH_CODE_ENV) or "").strip()
    if not auth_code:
        render_dashboard()
        return

    if app.storage.user.get(AUTH_STORAGE_KEY) == auth_code:
        render_dashboard()
        return

    root.clear()
    _auth_gate(root, auth_code, render_dashboard)


def main(host: str = None, port: int = None, storage_secret: str = None) -> None:
    # WebUI 自身也写文件日志,与子进程共享 <workdir>/logs/tg-signer.log
    _setup_webui_logger(DEFAULT_WORKDIR)
    # WebUI 退出时主动清理 runner 跟踪的子进程,避免孤儿进程
    app.on_shutdown(runner.shutdown_all)
    ui.run(
        build_ui,
        title="TG Signer WebUI",
        favicon="⚙️",
        reload=False,
        host=host,
        port=port,
        show=False,
        storage_secret=storage_secret or os.urandom(10).hex(),
    )
