import os
import pathlib
import re
import time
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
    if not link.is_symlink():
        # 部分 Windows 环境（缺少 SeCreateSymbolicLinkPrivilege / 被安全软件拦截）
        # 不会抛错，而是静默退化成普通文件，此时本用例没有可验证的对象。
        pytest.skip("当前环境把符号链接静默降级为普通文件，无法验证软链逃逸")

    with pytest.raises(ValueError):
        utils.resolve_within(root, link)


# ---------------------------------------------------------------------------
# restrict_file_permissions：凭据文件权限收紧
# ---------------------------------------------------------------------------


def test_restrict_file_permissions_chmods_on_posix(tmp_path, monkeypatch):
    target = tmp_path / "acc.session_string"
    target.write_text("secret", encoding="utf-8")
    recorded = []

    def fake_chmod(path, mode):
        # 不要在此处 pathlib.Path(path) 重新包装：本用例把全局 os.name 改成了
        # "posix"，pathlib 会据此构造 PosixPath，与 WindowsPath 的 target 不相等。
        recorded.append((path, mode))

    monkeypatch.setattr(utils.os, "name", "posix")
    monkeypatch.setattr(utils.os, "chmod", fake_chmod)

    assert utils.restrict_file_permissions(target) is True
    assert recorded == [(target, 0o600)]


def test_restrict_file_permissions_is_noop_off_posix(tmp_path, monkeypatch):
    """Windows 的 chmod 只影响只读位,不做无意义的调用。"""
    called = []

    def fake_chmod(*args):
        called.append(args)

    monkeypatch.setattr(utils.os, "name", "nt")
    monkeypatch.setattr(utils.os, "chmod", fake_chmod)

    assert utils.restrict_file_permissions(tmp_path / "x") is False
    assert called == []


def test_restrict_file_permissions_swallows_oserror(tmp_path, monkeypatch):
    """权限位写不进去不能让登录 / 保存流程失败。"""

    def boom(*_args):
        raise OSError("not permitted")

    monkeypatch.setattr(utils.os, "name", "posix")
    monkeypatch.setattr(utils.os, "chmod", boom)

    assert utils.restrict_file_permissions(tmp_path / "x") is False


def test_restrict_file_permissions_real_mode_on_posix(tmp_path):
    """POSIX 上验证真实落在磁盘上的 mode。"""
    if os.name != "posix":
        pytest.skip("chmod 的权限位语义只在 POSIX 上可用")
    target = tmp_path / "acc.session_string"
    target.write_text("secret", encoding="utf-8")
    os.chmod(target, 0o644)

    assert utils.restrict_file_permissions(target) is True
    assert os.stat(target).st_mode & 0o777 == 0o600


# ---------------------------------------------------------------------------
# safe_regex_search：配置正则的边界护栏
# ---------------------------------------------------------------------------


def test_safe_regex_search_matches_like_re_search():
    match = utils.safe_regex_search(r"code:(\d+)", "your code:42 ok")
    assert match is not None
    assert match.group(1) == "42"
    assert utils.safe_regex_search("nope", "text") is None
    assert utils.safe_regex_search("ABC", "abc", flags=re.IGNORECASE) is not None


def test_safe_regex_search_rejects_invalid_pattern():
    with pytest.raises(ValueError):
        utils.safe_regex_search("(unclosed", "text")


def test_safe_regex_search_rejects_non_string_pattern():
    with pytest.raises(ValueError):
        utils.safe_regex_search(None, "text")


def test_safe_regex_search_rejects_oversized_pattern():
    too_long = "a" * (utils.MAX_REGEX_PATTERN_LENGTH + 1)
    with pytest.raises(ValueError):
        utils.safe_regex_search(too_long, "aaaa")


def test_safe_regex_search_truncates_oversized_subject():
    """超长文本截断而非拒绝:上限内的匹配仍然生效,上限外的不参与。"""
    inside = "x" * 10 + "marker" + "y" * (utils.MAX_REGEX_SUBJECT_LENGTH * 2)
    assert utils.safe_regex_search("marker", inside) is not None

    beyond = "x" * utils.MAX_REGEX_SUBJECT_LENGTH + "marker"
    assert utils.safe_regex_search("marker", beyond) is None


def test_safe_regex_search_rejects_none_subject():
    """None 不该把 TypeError 抛给调用方。"""
    assert utils.safe_regex_search(r"\d", None) is None


@pytest.mark.parametrize(
    "pattern",
    [
        r"(a+)+$",
        r"(\d*)*",
        r"(a+b)+",
        r"(?:x+)*",
        r"(a+)*",
        r"((a+)+)+",
    ],
)
def test_safe_regex_search_rejects_nested_unbounded_quantifiers(pattern):
    """「量词套量词」是指数级回溯的形态,必须被挡掉而不是真的去匹配。"""
    with pytest.raises(ValueError):
        utils.safe_regex_search(pattern, "a" * 2000 + "!")


@pytest.mark.parametrize(
    "pattern",
    [
        r"\d+",
        r"(ab)*c",
        r"(a|b)+",
        r"[a+]+",
        r"(\d{2,4})+",
        r"(a+)?",
        r"(a+){2}",
        r"(?:\d{1,3}\.){3}\d{1,3}",
        r"(foo|ba+r)?",
        r"^a+$",
        r"a\+b",
    ],
)
def test_safe_regex_search_allows_benign_quantifiers(pattern):
    """形状检查不能误伤常见写法(有上限量词、字符类里的量词等)。"""
    utils.safe_regex_search(pattern, "abc 12.34.56.78")


def test_safe_regex_search_guard_is_fast_on_hostile_pattern():
    """朴素 re.search 在 n=24 就要约 2 秒(指数级),护栏必须立刻返回。"""
    start = time.perf_counter()
    with pytest.raises(ValueError):
        utils.safe_regex_search(r"(a+)+$", "a" * 2400 + "!")
    assert time.perf_counter() - start < 1.0
