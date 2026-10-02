"""配置校验：字段明细透出 + sign_at cron 合法性。"""

import pytest
from pydantic import ValidationError

from tg_signer.config import (
    AutomationConfig,
    FilterConfig,
    HandlerConfig,
    MessageTriggerConfig,
    RuleConfig,
    SignConfigV3,
    TimerTriggerConfig,
    format_validation_error,
    normalize_sign_at,
)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("06:00:00", "0 6 * * *"),
        ("06:30", "30 6 * * *"),
        ("06：00：00", "0 6 * * *"),  # 全角冒号
        ("  0 6 * * *  ", "0 6 * * *"),
        ("*/5 * * * *", "*/5 * * * *"),
    ],
)
def test_normalize_sign_at_accepts_time_and_cron(value, expected):
    assert normalize_sign_at(value) == expected


def test_normalize_sign_at_preserves_seconds():
    """带秒的时间不能被静默截断成整分（回归：曾返回 "0 6 * * *" 丢掉 30 秒）。"""
    assert normalize_sign_at("06:00:30") == "0 6 * * * 30"
    assert normalize_sign_at("23:59:59") == "59 23 * * * 59"


def test_normalize_sign_at_with_seconds_schedules_at_the_right_instant():
    """归一化结果必须真的把秒带上，而不是只满足字符串相等。"""
    from datetime import datetime, timezone

    from croniter import croniter

    now = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    expr = normalize_sign_at("06:00:30")
    assert croniter(expr, now).next(datetime) == datetime(
        2024, 1, 1, 6, 0, 30, tzinfo=timezone.utc
    )


@pytest.mark.parametrize("value", ["", "   ", "不是 cron", "每晚六点", "60 6 * * *"])
def test_normalize_sign_at_rejects_garbage(value):
    with pytest.raises(ValueError):
        normalize_sign_at(value)


def test_sign_config_v3_rejects_bad_sign_at():
    with pytest.raises(ValueError):
        SignConfigV3.model_validate(
            {"chats": [{"chat_id": 1, "actions": []}], "sign_at": "不是 cron"}
        )


def test_sign_config_v3_keeps_original_sign_at_text():
    """只校验不改写，避免存量配置被静默重写。"""
    cfg = SignConfigV3.model_validate(
        {"chats": [{"chat_id": 1, "actions": []}], "sign_at": "06:00:00"}
    )
    assert cfg.sign_at == "06:00:00"


def test_load_checked_reports_field_details():
    cfg, migrated, err = SignConfigV3.load_checked(
        {"chats": [{"chat_id": 1, "actions": "not-a-list"}], "sign_at": "0 6 * * *"}
    )
    assert cfg is None
    assert migrated is False
    assert "chats.0.actions" in err


def test_load_checked_surfaces_sign_at_error():
    cfg, _migrated, err = SignConfigV3.load_checked(
        {"chats": [{"chat_id": 1, "actions": []}], "sign_at": "不是 cron"}
    )
    assert cfg is None
    assert "sign_at" in err


def test_load_checked_ok_returns_no_error():
    cfg, migrated, err = SignConfigV3.load_checked(
        {"chats": [{"chat_id": 1, "actions": []}], "sign_at": "0 6 * * *"}
    )
    assert cfg is not None
    assert migrated is False
    assert err is None


def test_load_still_returns_none_for_invalid():
    assert SignConfigV3.load({"chats": "nope"}) is None


def test_format_validation_error_truncates():
    payload = {"chats": [{"chat_id": i, "actions": "bad"} for i in range(12)]}
    _cfg, _migrated, err = SignConfigV3.load_checked(payload)
    assert err.count("chats.") <= 8
    assert "等" in err


def test_format_validation_error_on_non_pydantic_error():
    assert format_validation_error(ValueError("boom")) == "boom"


# ---------------------------------------------------------------------------
# V1/V2 迁移链必须能穿过 V3 到达（olds 只查一层是历史 bug）
# ---------------------------------------------------------------------------


def test_v2_config_migrates_through_v3():
    payload = {
        "chats": [{"chat_id": 123, "sign_text": "签到", "delete_after": None}],
        "sign_at": "06:00:00",
        "random_seconds": 0,
    }
    cfg, migrated, err = SignConfigV3.load_checked(payload)
    assert cfg is not None
    assert migrated is True
    assert err is None
    assert cfg.chats[0].chat_id == 123


def test_v1_config_migrates_all_the_way_to_v3():
    payload = {
        "chat_id": 123,
        "sign_text": "老配置",
        "sign_at": "06:00:00",
        "random_seconds": 30,
    }
    cfg, migrated, err = SignConfigV3.load_checked(payload)
    assert err is None
    assert migrated is True
    assert cfg is not None
    assert cfg.sign_at == "06:00:00"
    assert cfg.random_seconds == 30
    assert len(cfg.chats) == 1
    assert cfg.chats[0].chat_id == 123
    assert cfg.chats[0].actions[0].text == "老配置"


# ---------------------------------------------------------------------------
# version 必须真正参与分发：写入配置 + 读取时以声明版本为准
# ---------------------------------------------------------------------------


def test_to_jsonable_writes_the_version():
    """`version` 是 ClassVar，不显式补进 payload 的话磁盘上永远没有版本号。"""
    cfg = SignConfigV3(chats=[{"chat_id": 1, "actions": []}], sign_at="0 6 * * *")
    assert cfg.to_jsonable()["version"] == 3


def test_written_config_roundtrips_without_being_seen_as_migrated():
    cfg = SignConfigV3(chats=[{"chat_id": 1, "actions": []}], sign_at="0 6 * * *")
    reloaded, migrated, err = SignConfigV3.load_checked(cfg.to_jsonable())
    assert err is None
    assert migrated is False
    assert reloaded == cfg


def test_declared_version_wins_over_merely_compatible_fields():
    """字段同时兼容 V2/V3 时，声明了版本就必须按声明版本迁移。

    判别性：这份配置的 chats 既有 sign_text（V2 特征）又有 actions（V3 特征）。
    不声明版本时会被当成 V3 直接接受、保留手写的 actions；声明 version=2 后应当
    走 V2 -> V3 迁移，用 sign_text 重建 actions。修复前两者结果相同。
    """
    payload = {
        "chats": [
            {
                "chat_id": 123,
                "sign_text": "签到",
                "actions": [{"action": 1, "text": "手写的"}],
            }
        ],
        "sign_at": "06:00:00",
    }

    cfg, migrated, _err = SignConfigV3.load_checked(payload)
    assert migrated is False
    assert cfg.chats[0].actions[0].text == "手写的"

    cfg, migrated, _err = SignConfigV3.load_checked({**payload, "version": 2})
    assert migrated is True
    assert cfg.chats[0].actions[0].text == "签到"


def test_declared_version_error_points_at_the_right_version():
    """缺字段的 V1 配置应当报 V1 的错误，而不是「V3 缺 chats」。"""
    broken_v1 = {"chat_id": 111, "sign_at": "06:00:00", "random_seconds": 5}

    _cfg, _migrated, err = SignConfigV3.load_checked(dict(broken_v1))
    assert "chats" in err

    _cfg, _migrated, err = SignConfigV3.load_checked({**broken_v1, "version": 1})
    assert "sign_text" in err
    assert "chats" not in err


@pytest.mark.parametrize("declared", [2, 99, "3", None])
def test_declared_version_never_rejects_a_previously_valid_config(declared):
    """写错的 version 不能让以前能读的配置变成读不了。"""
    payload = {"chats": [{"chat_id": 1, "actions": []}], "sign_at": "0 6 * * *"}
    if declared is not None:
        payload["version"] = declared

    cfg, migrated, err = SignConfigV3.load_checked(payload)
    assert err is None
    assert cfg is not None
    assert migrated is False


def test_declared_v1_version_still_migrates_through_the_whole_chain():
    payload = {
        "version": 1,
        "chat_id": 123,
        "sign_text": "老配置",
        "sign_at": "06:00:00",
        "random_seconds": 30,
    }
    cfg, migrated, err = SignConfigV3.load_checked(payload)
    assert err is None
    assert migrated is True
    assert cfg.chats[0].actions[0].text == "老配置"


# ---------------------------------------------------------------------------
# automation：数字字符串 chat_id 必须归一化成 int，否则 _match_chat 永不命中
# ---------------------------------------------------------------------------


def test_trigger_numeric_string_chat_id_becomes_int():
    trigger = MessageTriggerConfig(type="message", params={"chat_id": "-1001234567890"})
    assert trigger.params.chat_id == -1001234567890
    assert isinstance(trigger.params.chat_id, int)


def test_trigger_username_stays_string():
    trigger = MessageTriggerConfig(type="message", params={"chat_id": "@neo"})
    assert trigger.params.chat_id == "@neo"


def test_trigger_chat_ids_list_normalized():
    trigger = MessageTriggerConfig(
        type="message", params={"chat_ids": ["123", "@neo", 456]}
    )
    assert trigger.params.chat_ids == [123, "@neo", 456]


def test_filter_numeric_string_chat_id_becomes_int():
    assert FilterConfig(chat_id="-1001234567890").chat_id == -1001234567890
    assert FilterConfig(chat_id="@neo").chat_id == "@neo"
    assert FilterConfig(chat_ids=["1", "@a"]).chat_ids == [1, "@a"]


# ---------------------------------------------------------------------------
# 负数随机秒：运行期会炸 random.randint(0, n)，必须在配置层拦住
# ---------------------------------------------------------------------------


def test_sign_config_v3_rejects_negative_random_seconds():
    with pytest.raises(ValidationError):
        SignConfigV3(chats=[], sign_at="0 6 * * *", random_seconds=-1)


def test_timer_trigger_rejects_negative_random_seconds():
    with pytest.raises(ValidationError):
        TimerTriggerConfig(
            type="timer",
            params={"interval_seconds": 60, "random_seconds": -5},
        )


def test_sign_config_v3_accepts_zero_and_positive_random_seconds():
    assert SignConfigV3(chats=[], sign_at="0 6 * * *").random_seconds == 0
    assert (
        SignConfigV3(chats=[], sign_at="0 6 * * *", random_seconds=30).random_seconds
        == 30
    )


# ---------------------------------------------------------------------------
# automation：rule id / trigger id 必须唯一，否则 state 桶与 next_run_at 互相覆盖
# ---------------------------------------------------------------------------


def _rule(rule_id: str, triggers=None) -> RuleConfig:
    return RuleConfig(
        id=rule_id,
        triggers=triggers or [MessageTriggerConfig(type="message", params={})],
        handlers=[HandlerConfig(handler="send_text", params={"text": "x"})],
    )


def test_automation_config_rejects_duplicate_rule_ids():
    with pytest.raises(ValidationError, match="重复的 rule id"):
        AutomationConfig(rules=[_rule("dup"), _rule("dup")])


def test_automation_config_rejects_duplicate_trigger_ids():
    triggers = [
        MessageTriggerConfig(type="message", params={}, id="t1"),
        MessageTriggerConfig(type="message", params={}, id="t1"),
    ]
    with pytest.raises(ValidationError, match="重复的 trigger id"):
        AutomationConfig(rules=[_rule("r1", triggers)])


def test_automation_config_accepts_distinct_ids():
    AutomationConfig(rules=[_rule("a"), _rule("b")])
