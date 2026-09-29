import pathlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest

import tg_signer.utils as utils


def require_zoneinfo(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        pytest.skip(f"zoneinfo data for {name} is unavailable in this environment")


def get_test_tzfile_source() -> pathlib.Path:
    for path_str in ("/etc/localtime", "/usr/share/zoneinfo/UTC"):
        path = pathlib.Path(path_str)
        if path.is_file():
            return path
    pytest.skip("no system tzfile is available for this test")


def test_get_timezone_prefers_tz_environment(monkeypatch):
    import tg_signer.utils as utils

    expected = require_zoneinfo("America/New_York")
    monkeypatch.setenv("TZ", "America/New_York")
    monkeypatch.setattr(utils, "_get_local_timezone", lambda: timezone.utc)

    tz = utils.get_timezone()

    assert getattr(tz, "key", None) == expected.key


def test_get_timezone_supports_posix_prefixed_tz_name(monkeypatch):
    import tg_signer.utils as utils

    expected = require_zoneinfo("America/New_York")
    monkeypatch.setenv("TZ", ":America/New_York")
    monkeypatch.setattr(utils, "_get_local_timezone", lambda: timezone.utc)

    tz = utils.get_timezone()

    assert getattr(tz, "key", None) == expected.key


def test_get_timezone_supports_tzfile_path_in_tz_environment(monkeypatch, tmp_path):
    import tg_signer.utils as utils

    tzfile = tmp_path / "localtime"
    tzfile.write_bytes(get_test_tzfile_source().read_bytes())
    expected = utils._load_timezone_from_file(tzfile)
    assert expected is not None

    monkeypatch.setenv("TZ", f":{tzfile}")
    monkeypatch.setattr(utils, "_get_local_timezone", lambda: timezone.utc)

    tz = utils.get_timezone()
    sample = datetime(2026, 4, 14, 12, 0)

    assert (
        sample.replace(tzinfo=tz).utcoffset()
        == sample.replace(tzinfo=expected).utcoffset()
    )


def test_get_timezone_uses_local_timezone_when_tz_missing(monkeypatch):
    import tg_signer.utils as utils

    monkeypatch.delenv("TZ", raising=False)
    monkeypatch.setattr(utils, "_get_local_timezone", lambda: timezone.utc)

    tz = utils.get_timezone()

    assert tz is timezone.utc


def test_get_timezone_falls_back_to_local_timezone_when_tz_is_invalid(monkeypatch):
    import tg_signer.utils as utils

    monkeypatch.setenv("TZ", "Invalid/Zone")
    monkeypatch.setattr(utils, "_get_local_timezone", lambda: timezone.utc)

    tz = utils.get_timezone()

    assert tz is timezone.utc


def test_get_timezone_falls_back_to_asia_shanghai(monkeypatch):
    import tg_signer.utils as utils

    monkeypatch.delenv("TZ", raising=False)
    monkeypatch.setattr(utils, "_get_local_timezone", lambda: None)

    tz = utils.get_timezone()
    sample = datetime(2026, 1, 1, 12, 0)

    assert sample.replace(tzinfo=tz).utcoffset() == timedelta(hours=8)


def test_get_local_timezone_uses_python_local_timezone(monkeypatch):
    import tg_signer.utils as utils

    expected = timezone.utc

    class FakeDateTime:
        @staticmethod
        def now(tz=None):
            assert tz is None
            return SimpleNamespace(astimezone=lambda: SimpleNamespace(tzinfo=expected))

    monkeypatch.setattr(utils, "datetime", FakeDateTime)

    assert utils._get_local_timezone() is expected


# ---------------------------------------------------------------------------
# resolve_under / resolve_within：外部字符串 → 受限路径的唯一入口
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "..",
        ".",
        "",
        "a/b",
        r"a\b",
        "sub/../..",
        "../x",
        ".. ",
        "...",
        "../..",
        "nul\x00byte",
    ],
)
def test_resolve_under_rejects_non_component_names(tmp_path, name):
    with pytest.raises(ValueError):
        utils.resolve_under(tmp_path, name)


def test_resolve_under_rejects_absolute_and_drive_paths(tmp_path):
    for name in (str(tmp_path / "x"), "/etc/passwd", r"C:\Windows"):
        with pytest.raises(ValueError):
            utils.resolve_under(tmp_path, name)


@pytest.mark.parametrize("name", ["acc", "签到任务", "task with space", "a.b-c_d"])
def test_resolve_under_accepts_ordinary_names(tmp_path, name):
    assert utils.resolve_under(tmp_path, name) == tmp_path / name


def test_resolve_under_appends_suffix(tmp_path):
    assert utils.resolve_under(tmp_path, "acc", suffix=".lock") == tmp_path / "acc.lock"


def test_resolve_within_accepts_paths_inside_root(tmp_path):
    root = tmp_path / "logs"
    root.mkdir()
    (root / "a.log").write_text("x", encoding="utf-8")

    assert utils.resolve_within(root, root / "a.log") == (root / "a.log").resolve()
    # 相对路径按 root 解析，不是按当前工作目录
    assert utils.resolve_within(root, "a.log") == (root / "a.log").resolve()


@pytest.mark.parametrize(
    "relative",
    ["../x.log", "..", ".", "sub/../../x.log", ""],
)
def test_resolve_within_rejects_paths_outside_root(tmp_path, relative):
    root = tmp_path / "logs"
    root.mkdir()
    with pytest.raises(ValueError):
        utils.resolve_within(root, relative)


def test_resolve_within_rejects_symlink_escape(tmp_path):
    """root 内指向外部的软链同样必须被拒（resolve 会展开软链）。"""
    root = tmp_path / "logs"
    root.mkdir()
    outside = tmp_path / "outside.log"
    outside.write_text("SECRET", encoding="utf-8")
    link = root / "link.log"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("当前环境不允许创建符号链接")

    with pytest.raises(ValueError):
        utils.resolve_within(root, link)
