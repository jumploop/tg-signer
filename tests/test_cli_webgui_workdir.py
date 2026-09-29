"""``tg-signer webgui`` 必须尊重全局 ``--workdir``。

历史问题：``webgui`` 子命令只把 host/port 传给 ``main()``，完全没接
``ctx.obj["workdir"]``，于是 WebUI 永远读 CWD 下的 ``.signer``。CLI 明明
指定了工作目录，日志却在别处，页面自然什么都没有。
"""

import pytest
from click.testing import CliRunner

import tg_signer.cli.signer as signer_cli
import tg_signer.webui as webui_pkg


@pytest.fixture
def runner():
    return CliRunner()


def test_webgui_passes_workdir_to_main(runner, monkeypatch, tmp_path):
    captured = {}

    def fake_main(host=None, port=None, workdir=None):
        captured.update(host=host, port=port, workdir=workdir)

    # webgui() 内部是 `from tg_signer.webui import main`，因此要打在包上。
    monkeypatch.setattr(webui_pkg, "main", fake_main, raising=False)

    target = tmp_path / "custom-workdir"
    result = runner.invoke(
        signer_cli.tg_signer,
        ["--workdir", str(target), "webgui", "--port", "8099"],
    )

    assert result.exit_code == 0, result.output
    assert captured["port"] == 8099
    assert captured["workdir"] == str(target)
