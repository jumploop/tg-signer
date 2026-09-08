"""Tests for tg_signer.webui.data module."""

from tg_signer.webui import data


def test_log_file_name_matches_runner():
    # 与 tg_signer.webui.runner.DEFAULT_LOG_FILE_NAME 一致
    assert data.LOG_FILE_NAME == "tg-signer.log"
    assert data.DEFAULT_LOG_FILE.name == data.LOG_FILE_NAME


def test_list_log_files_returns_empty_when_dir_missing(tmp_path):
    missing = tmp_path / "no_logs_dir"
    assert data.list_log_files(missing) == []


def test_list_log_files_finds_all_logs(tmp_path):
    (tmp_path / "a.log").write_text("a", encoding="utf-8")
    (tmp_path / "b.log").write_text("b", encoding="utf-8")
    (tmp_path / "c.txt").write_text("c", encoding="utf-8")
    found = data.list_log_files(tmp_path)
    names = sorted(p.name for p in found)
    assert names == ["a.log", "b.log"]
