"""Server酱通知：只测 URL 构造与失败判定，不发真实请求。"""

import json as _json

import pytest

from tg_signer.notification import server_chan


class _FakeResponse:
    def __init__(self, payload=None, status=200, text=None):
        self._payload = payload
        self.status_code = status
        self.text = text if text is not None else _json.dumps(payload or {})

    def json(self):
        if self._payload is None:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self._payload


class _FakeClient:
    """记录 post() 收到的 URL，替换 httpx.AsyncClient。"""

    calls: list = []
    response = _FakeResponse({"code": 0, "message": ""})

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None):
        _FakeClient.calls.append(url)
        return _FakeClient.response


@pytest.fixture(autouse=True)
def _fake_http(monkeypatch):
    _FakeClient.calls = []
    _FakeClient.response = _FakeResponse({"code": 0, "message": ""})
    monkeypatch.setattr(server_chan, "AsyncClient", _FakeClient)
    return _FakeClient


# ---------------------------------------------------------------------------
# URL 构造
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sctp_sendkey_routes_to_push_host():
    await server_chan.sc_send("sctp123t", "标题", "内容")
    assert _FakeClient.calls == ["https://123.push.ft07.com/send/sctp123t.send"]


@pytest.mark.asyncio
async def test_sctp_sendkey_is_case_insensitive():
    """SendKey 只与大小写无关地匹配 sctp：大小写混写曾被当成普通 key 发错主机。"""
    await server_chan.sc_send("SCTP456T", "标题")
    assert _FakeClient.calls == ["https://456.push.ft07.com/send/SCTP456T.send"]


@pytest.mark.asyncio
async def test_plain_sendkey_uses_legacy_host():
    await server_chan.sc_send("SCT123abc", "标题")
    assert _FakeClient.calls == ["https://sctapi.ftqq.com/SCT123abc.send"]


@pytest.mark.asyncio
async def test_sct_prefix_without_number_uses_legacy_host():
    """``sctpabc`` 不含数字段。以前会直接 raise ValueError，让整条通知失败。"""
    await server_chan.sc_send("sctpabc", "标题")
    assert _FakeClient.calls == ["https://sctapi.ftqq.com/sctpabc.send"]


# ---------------------------------------------------------------------------
# 失败必须显式抛异常：调用方（server_chan handler）根本不检查返回值
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_business_error_code_raises():
    """Server酱用 HTTP 200 + 非 0 code 表示业务失败。

    回归：原实现 ``return response.json()``，而 automation 的 server_chan
    handler 不检查返回值 —— SendKey 写错时规则日志里只有一条 DEBUG，
    用户根本收不到通知，而规则看起来一切正常。
    """
    _FakeClient.response = _FakeResponse({"code": 40001, "message": "bad sendkey"})

    with pytest.raises(RuntimeError, match="40001"):
        await server_chan.sc_send("SCT123abc", "标题")


@pytest.mark.asyncio
async def test_http_error_status_raises():
    _FakeClient.response = _FakeResponse(None, status=502, text="<html>bad gw</html>")

    with pytest.raises(RuntimeError, match="502"):
        await server_chan.sc_send("SCT123abc", "标题")


@pytest.mark.asyncio
async def test_non_json_response_raises_readable_error():
    """被网关/代理拦截返回 HTML 时，报错要能看出真实原因。"""
    _FakeClient.response = _FakeResponse(None, status=200, text="<html>403</html>")

    with pytest.raises(RuntimeError, match="不是 JSON"):
        await server_chan.sc_send("SCT123abc", "标题")


@pytest.mark.asyncio
async def test_success_returns_payload():
    payload = {"code": 0, "message": "", "data": {"sent": 1}}
    _FakeClient.response = _FakeResponse(payload)

    assert await server_chan.sc_send("SCT123abc", "标题") == payload


@pytest.mark.asyncio
async def test_response_without_code_field_is_not_treated_as_error():
    """响应体没有 code 字段时不要臆断为失败（不误伤其它形状）。"""
    _FakeClient.response = _FakeResponse({"result": "ok"})

    assert await server_chan.sc_send("SCT123abc", "标题") == {"result": "ok"}
