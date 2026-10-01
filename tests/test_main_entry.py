"""确保 `python -m tg_signer` 可作为 CLI 入口正常执行。

背景：WebUI 的 runner 通过 `sys.executable -m tg_signer ...` 拉起签到/监控子进程，
但 `tg_signer/__main__.py` 曾缺少 `if __name__ == "__main__"` 入口块，导致子进程
启动后立即退出（exit code 0），"统一运行"页面的启动全部失败。

解码必须显式指定 UTF-8：`text=True` 默认用本地编码（中文 Windows 上是 cp936）
解码子进程输出，而 CLI 的帮助文本含中文；tox 还会给它执行的命令设
`PYTHONIOENCODING=utf-8`（tox/sets.py），此时子进程按 UTF-8 输出、父进程按 cp936
解码 → 读取线程抛 UnicodeDecodeError、`proc.stdout` 变成 None（原实现即在此崩溃）。
下面断言只涉及 ASCII，`errors="replace"` 足以让两种编码下都稳定。
"""

import subprocess
import sys

_SUBPROCESS_TEXT_KWARGS = {
    "capture_output": True,
    "text": True,
    "encoding": "utf-8",
    "errors": "replace",
    # 导入 tg_signer 会拉起 pyrogram/kurigram，本机单次子进程约 8~9s；机器负荷高
    # 或杀软扫描新进程时会更慢 —— 30s 曾在并发跑测试时把整个套件拖红（假失败）。
    # 放宽到 120s：它仍然是「卡死」的守卫，而不是性能断言。
    "timeout": 120,
}


def test_module_entry_runs_version_command():
    proc = subprocess.run(
        [sys.executable, "-m", "tg_signer", "version"],
        **_SUBPROCESS_TEXT_KWARGS,
    )
    assert proc.returncode == 0, proc.stderr
    assert "tg-signer" in proc.stdout


def test_module_entry_runs_help_command():
    proc = subprocess.run(
        [sys.executable, "-m", "tg_signer", "--help"],
        **_SUBPROCESS_TEXT_KWARGS,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Usage" in proc.stdout
