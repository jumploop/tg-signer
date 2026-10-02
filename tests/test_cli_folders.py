import asyncio

import click
import pytest
from click.testing import CliRunner

import tg_signer.cli.automation as automation_cli
import tg_signer.cli.signer as signer_cli
from tg_signer.core import ChatFolderError

# ---------------------------------------------------------------------------
# run_coroutines：异常必须转成 ClickException，且兄弟协程要一起收场
# ---------------------------------------------------------------------------


def test_run_coroutines_converts_arbitrary_error_to_click_exception():
    """非 ChatFolderError 异常不得以裸 traceback 打穿 CLI。"""

    async def boom():
        raise RuntimeError("disk on fire")

    loop = asyncio.new_event_loop()
    try:
        with pytest.raises(click.ClickException) as exc:
            signer_cli.run_coroutines(loop, [boom()])
    finally:
        loop.close()
    assert "disk on fire" in str(exc.value)


def test_run_coroutines_cancels_sibling_tasks_on_failure():
    """一个协程失败时，兄弟协程必须被取消并回收，不能留在后台继续发消息。"""
    state = {"sibling_finished": False, "sibling_cancelled": False}

    async def boom():
        raise RuntimeError("boom")

    async def sibling():
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            state["sibling_cancelled"] = True
            raise
        state["sibling_finished"] = True  # pragma: no cover

    loop = asyncio.new_event_loop()
    try:
        with pytest.raises(click.ClickException):
            signer_cli.run_coroutines(loop, [boom(), sibling()])
    finally:
        loop.close()

    assert state["sibling_cancelled"] is True
    assert state["sibling_finished"] is False


def test_run_coroutines_propagates_cancellation_as_click_exception():
    """CancelledError 不属于 ChatFolderError，必须被转成错误而不是裸抛。"""

    async def boom():
        raise asyncio.CancelledError

    loop = asyncio.new_event_loop()
    try:
        with pytest.raises(click.ClickException):
            signer_cli.run_coroutines(loop, [boom()])
    finally:
        loop.close()


class DummyWorker:
    def __init__(self):
        self.calls = []

    def app_run(self, coroutine=None):
        if coroutine is not None:
            asyncio.run(coroutine)

    async def list_folders(self):
        self.calls.append({"method": "list_folders"})

    async def login(self, num_of_dialogs, folder=None, interactive: bool = False):
        self.calls.append(
            {
                "method": "login",
                "num_of_dialogs": num_of_dialogs,
                "folder": folder,
                "interactive": interactive,
            }
        )

    async def run(self, num_of_dialogs, folder=None):
        self.calls.append(
            {
                "method": "run",
                "num_of_dialogs": num_of_dialogs,
                "folder": folder,
            }
        )

    async def run_once(self, num_of_dialogs, folder=None):
        self.calls.append(
            {
                "method": "run_once",
                "num_of_dialogs": num_of_dialogs,
                "folder": folder,
            }
        )


@pytest.fixture
def runner():
    return CliRunner()


def test_list_folders_command(monkeypatch, runner):
    worker = DummyWorker()
    monkeypatch.setattr(signer_cli, "get_signer", lambda *_args, **_kwargs: worker)

    result = runner.invoke(signer_cli.tg_signer, ["list-folders"])

    assert result.exit_code == 0
    assert worker.calls == [{"method": "list_folders"}]


@pytest.mark.parametrize(
    ("args", "method"),
    [
        (["login", "--from-folder", "Sign"], "login"),
        (["run", "--from-folder", "Sign", "task"], "run"),
        (["run-once", "--from-folder", "Sign", "task"], "run_once"),
        (
            [
                "multi-run",
                "--account",
                "account-a",
                "--from-folder",
                "Sign",
                "task",
            ],
            "run",
        ),
    ],
)
def test_signer_commands_forward_folder(monkeypatch, runner, args, method):
    worker = DummyWorker()
    monkeypatch.setattr(signer_cli, "get_signer", lambda *_args, **_kwargs: worker)

    result = runner.invoke(signer_cli.tg_signer, args)

    assert result.exit_code == 0, result.output
    assert worker.calls[0]["method"] == method
    assert worker.calls[0]["folder"] == "Sign"


@pytest.mark.parametrize(
    ("args", "module", "factory_name"),
    [
        (
            ["automation", "run", "--from-folder", "Sign", "task"],
            automation_cli,
            "get_automation",
        ),
    ],
)
def test_subsystem_run_commands_forward_folder(
    monkeypatch, runner, args, module, factory_name
):
    worker = DummyWorker()
    monkeypatch.setattr(module, factory_name, lambda *_args, **_kwargs: worker)

    result = runner.invoke(signer_cli.tg_signer, args)

    assert result.exit_code == 0, result.output
    assert worker.calls == [{"method": "run", "num_of_dialogs": 20, "folder": "Sign"}]


def test_folder_errors_are_reported_as_click_errors(monkeypatch, runner):
    class ErrorWorker(DummyWorker):
        async def login(self, num_of_dialogs, folder=None, interactive: bool = False):
            del num_of_dialogs, folder, interactive
            raise ChatFolderError("folder error")

    worker = ErrorWorker()
    monkeypatch.setattr(signer_cli, "get_signer", lambda *_args, **_kwargs: worker)

    result = runner.invoke(
        signer_cli.tg_signer,
        ["login", "--from-folder", "Missing"],
    )

    assert result.exit_code == 1
    assert "Error: folder error" in result.output


# ---------------------------------------------------------------------------
# automation list / validate / export→import 往返
# ---------------------------------------------------------------------------

_YAML_CONFIG = """\
version: 1
rules:
  - id: r1
    enabled: true
    triggers:
      - type: timer
        params:
          interval_seconds: 60
    handlers:
      - handler: send_text
        params:
          text: hi
"""


def _invoke(runner, workdir, *args, **kwargs):
    return runner.invoke(
        signer_cli.tg_signer, ["--workdir", str(workdir), "automation", *args], **kwargs
    )


def test_automation_list_on_fresh_workdir_prints_nothing_and_creates_nothing(
    runner, tmp_path
):
    """`automation list` 不得构造默认任务(my_task)并把它建出来。"""
    workdir = tmp_path / "wd"

    result = _invoke(runner, workdir, "list")

    assert result.exit_code == 0, result.output
    assert result.output.strip() == ""
    assert not (workdir / "automations").exists()


def test_automation_list_prints_real_tasks(runner, tmp_path):
    workdir = tmp_path / "wd"
    (workdir / "automations" / "task_a").mkdir(parents=True)
    (workdir / "automations" / "task_b").mkdir(parents=True)

    result = _invoke(runner, workdir, "list")

    assert result.exit_code == 0, result.output
    assert result.output.split() == ["task_a", "task_b"]


def test_automation_validate_missing_config_does_not_create_one(runner, tmp_path):
    """`validate <typo>` 必须报错，而不是写出模板配置并显示「校验通过」。"""
    workdir = tmp_path / "wd"

    result = _invoke(runner, workdir, "validate", "typo_task")

    assert result.exit_code == 1, result.output
    assert "配置不存在" in result.output
    assert not list((workdir / "automations" / "typo_task").glob("config.*"))
    assert not (workdir / "automations" / "typo_task" / "state.json").exists()
    # 连空任务目录都不能留下:否则 `automation list` 会把它当成真实任务列出来
    assert not (workdir / "automations" / "typo_task").exists()
    assert not (workdir / "automations").exists()


def test_automation_yaml_export_import_validate_roundtrip(runner, tmp_path):
    """YAML 任务导出→导入后必须仍可加载，且 validate 通过。"""
    yaml = pytest.importorskip("yaml")
    workdir = tmp_path / "wd"
    task_dir = workdir / "automations" / "my_auto"
    task_dir.mkdir(parents=True)
    (task_dir / "config.yaml").write_text(_YAML_CONFIG, encoding="utf-8")

    exported = _invoke(runner, workdir, "export", "my_auto")
    assert exported.exit_code == 0, exported.output
    assert "rules:" in exported.output

    imported = _invoke(runner, workdir, "import", "my_auto", input=exported.output)
    assert imported.exit_code == 0, imported.output

    # 修复前：YAML 文本落进 config.json，遮蔽 config.yaml 且解析失败。
    assert not (task_dir / "config.json").exists()
    assert yaml.safe_load((task_dir / "config.yaml").read_text(encoding="utf-8"))

    validated = _invoke(runner, workdir, "validate", "my_auto")
    assert validated.exit_code == 0, validated.output
    assert "配置校验通过" in validated.output
