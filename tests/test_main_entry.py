"""确保 `python -m tg_signer` 可作为 CLI 入口正常执行。

背景：WebUI 的 runner 通过 `sys.executable -m tg_signer ...` 拉起签到/监控子进程，
但 `tg_signer/__main__.py` 曾缺少 `if __name__ == "__main__"` 入口块，导致子进程
启动后立即退出（exit code 0），"统一运行"页面的启动全部失败。
"""

import subprocess
import sys


def test_module_entry_runs_version_command():
    proc = subprocess.run(
        [sys.executable, "-m", "tg_signer", "version"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert "tg-signer" in proc.stdout


def test_module_entry_runs_help_command():
    proc = subprocess.run(
        [sys.executable, "-m", "tg_signer", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Usage" in proc.stdout
