"""全局 ``--log-dir`` 改变时，默认日志文件必须跟着走。

历史问题：``--log-file`` 曾把 ``logs/tg-signer.log`` 写死为默认值，
``configure_logger`` 的 ``log_file or log_dir / "tg-signer.log"`` 永远
走不到，于是 ``--log-dir /tmp/x`` 的日志仍落回 CWD 下的 ``logs/``。
"""

import tg_signer.cli.signer as signer_cli
import tg_signer.webui as webui_pkg


def test_default_log_file_follows_log_dir(runner, monkeypatch, tmp_path):
    captured = {}

    def fake_main(host=None, port=None, workdir=None):
        pass

    def fake_configure_logger(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(webui_pkg, "main", fake_main, raising=False)
    monkeypatch.setattr(
        "tg_signer.logger.configure_logger", fake_configure_logger, raising=False
    )

    log_dir = tmp_path / "elsewhere"
    result = runner.invoke(signer_cli.tg_signer, ["--log-dir", str(log_dir), "webgui"])

    assert result.exit_code == 0, result.output
    assert captured["log_dir"] == str(log_dir)
    assert captured["log_file"] is None
