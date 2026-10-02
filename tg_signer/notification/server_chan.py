import re

from httpx import AsyncClient


def _build_url(sendkey: str) -> str:
    """SendKey 只与大小写无关地匹配 'sctp'：Server酱本身按小写分派，
    用户写成 'SCTP1234t...' 或 'sctp1234T...' 都会被当成普通 key 发到
    sctapi.ftqq.com，然后收到一个莫名其妙的 400/sendkey 错误。
    """
    match = re.match(r"sctp(\d+)t", sendkey, re.IGNORECASE)
    if match:
        num = match.group(1)
        return f"https://{num}.push.ft07.com/send/{sendkey}.send"
    return f"https://sctapi.ftqq.com/{sendkey}.send"


async def sc_send(sendkey, title, desp="", options=None):
    """发送 Server酱通知，失败时抛异常。

    原来直接 ``return response.json()``，把结果原样丢给调用方，而调用方
    （automation 的 server_chan handler）根本不检查返回值。于是**通知失败在
    规则侧完全看不出来**：

    - SendKey 写错 / 已过期：Server酱用 HTTP 200 + ``{"code": <非0>, "message": ...}``
      表示业务失败，httpx 不抛异常，规则日志里只有一条 DEBUG「发送通知」，
      看上去一切正常 —— 而用户根本没收到任何通知；
    - 被代理/网关拦截返回 HTML 错误页时，``response.json()`` 抛
      JSONDecodeError，报错里看不出真实原因。

    现在三种失败都显式抛异常：HTTP 非 2xx、响应体不是 JSON、以及响应体里带
    非 0 的数字 ``code``。引擎会把 handler 异常记成 ERROR 并中断后续 handler，
    失败因此在日志里可见。
    """
    if options is None:
        options = {}
    url = _build_url(sendkey)
    params = {"title": title, "desp": desp, **options}
    headers = {"Content-Type": "application/json;charset=utf-8"}
    async with AsyncClient(headers=headers) as client:
        response = await client.post(url, json=params)
        status = response.status_code
        body = response.text
        try:
            result = response.json()
        except ValueError as exc:
            raise RuntimeError(
                f"Server酱响应不是 JSON（HTTP {status}）: {body[:200]}"
            ) from exc
    if not 200 <= status < 300:
        raise RuntimeError(f"Server酱返回 HTTP {status}: {body[:200]}")
    # Server酱把业务错误放在响应体的 code 字段里，且 HTTP 仍是 200。
    # 只在 code 是数字时才判定，避免误伤其它形状的响应。
    code = result.get("code") if isinstance(result, dict) else None
    if isinstance(code, int) and not isinstance(code, bool) and code != 0:
        message = result.get("message", "") if isinstance(result, dict) else ""
        raise RuntimeError(f"Server酱返回错误 code={code}: {message or '无说明'}")
    return result
