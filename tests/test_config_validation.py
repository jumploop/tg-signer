"""配置校验：字段明细透出 + sign_at cron 合法性。"""

import pytest

from tg_signer.config import (
    FilterConfig,
    MessageTriggerConfig,
    SignConfigV3,
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
