"""Read-only client for the China Mobile app API (client.app.coc.10086.cn / clientaccess.10086.cn).

Ported from cmcc.data.js in https://github.com/MaYIHEI/paperclip (app/cmcc).  The app sends an
AES-encrypted "login envelope" to autoLogin; replaying it yields fresh session cookies, which the
query endpoints accept together with a business envelope built from the same login envelope.
"""

import asyncio
import base64
import hashlib
import json
import random
import re
import ssl
import time

import aiohttp
import certifi
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

HOST_LOGIN = "client.app.coc.10086.cn"
HOST_BIZ = "clientaccess.10086.cn"
PATH_AUTOLOGIN = "/biz-orange/LN/uamrandcodelogin/autoLogin"
PATHS = {
    "points": "/biz-orange/BN/scoreQueryService/getScoreQuery",
    "fee": "/biz-orange/BN/payFeesQuery/getPayFeesQueryInfo",
    "flow": "/biz-orange/BH/newPlanRemainQry/getNewPlanRemainQry",
    "user": "/biz-orange/BN/userInformationService/getUserInformation",
}
USER_AGENT = "ChinaMobile/12.5.5 (iPhone; iOS 26.1; Scale/3.00)"
SALT = "Leadeon/SecurityOrganization"
# (request key, response key, iv) for the login host and the business host, and the x-token key.
LOGIN_KEYS = ("tVkdaRWRY0ZkV1Vr", "RYV0hCV1lV25KYVJ", "VjFSQ1ZtVkQxRTlQ")
BIZ_KEYS = ("bAIgvwAuA4tbDr9d", "GS7VelkJl5IT1uwQ", "9791027341711819")
TOKEN_KEY, TOKEN_IV = "bAIgvwAuA4tbDr9d", "9791027341711819"
OK = "000000"
SESSION_EXPIRED = "410000"
# autoLogin answers that say "not now" rather than "bad credential": 233031 is "logging in too often".
# Codes are not documented, so the description is matched too.
LOGIN_RATE_LIMITED = {"233031"}
LOGIN_TEMPORARY_HINTS = re.compile("频繁|繁忙|稍后|超时|限制|风控")
LOGIN_SPACING = 2.0  # seconds between autoLogin calls of different numbers, as the app's own scripts do
TIMEOUT = aiohttp.ClientTimeout(total=20)

# Every number replays autoLogin on each update; serialise them so several numbers in one Home
# Assistant do not log in at the same instant and trip the rate limit.
_login_lock = asyncio.Lock()
_last_login = 0.0


class CmccError(Exception):
    """The API could not be reached or answered with an error."""


class CmccAuthError(CmccError):
    """The login envelope was rejected; it has to be captured again."""


class CmccRateLimitError(CmccError):
    """autoLogin refused for now (too many logins); the envelope is still good."""


def _ssl_context() -> ssl.SSLContext:
    """Certificates are verified as usual, but client.app.coc.10086.cn still needs legacy
    renegotiation, which OpenSSL 3 refuses by default."""
    context = ssl.create_default_context(cafile=certifi.where())
    context.options |= ssl.OP_LEGACY_SERVER_CONNECT
    return context


# Built at import time (Home Assistant imports integrations in an executor) to keep the
# certificate loading off the event loop.
SSL_CONTEXT = _ssl_context()


def new_session() -> aiohttp.ClientSession:
    """A private session without a cookie jar: the session cookie is passed by hand."""
    return aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar(),
                                 connector=aiohttp.TCPConnector(ssl=SSL_CONTEXT))


def _md5(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def encrypt(plain: str, key: str, iv: str) -> str:
    padder = padding.PKCS7(128).padder()
    data = padder.update(plain.encode()) + padder.finalize()
    enc = Cipher(algorithms.AES(key.encode()), modes.CBC(iv.encode())).encryptor()
    return base64.b64encode(enc.update(data) + enc.finalize()).decode()


def decrypt(text: str, key: str, iv: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9+/]", "", text)
    raw = base64.b64decode(cleaned + "=" * (-len(cleaned) % 4))
    dec = Cipher(algorithms.AES(key.encode()), modes.CBC(iv.encode())).decryptor()
    data = dec.update(raw) + dec.finalize()
    if data and 0 < data[-1] <= 16:
        data = data[: -data[-1]]
    return data.decode("utf-8", "replace")


def parse_capture(text: str) -> str:
    """Return the login envelope (a JSON string) from what the user pasted.

    Accepts the raw autoLogin request body as captured (base64 ciphertext) or the decrypted JSON.
    The text is kept verbatim, as the app sent it, because the signature headers hash it.
    """
    text = (text or "").strip()
    if not text.startswith("{"):
        try:
            text = decrypt(text, LOGIN_KEYS[0], LOGIN_KEYS[2]).strip()
        except ValueError as exc:
            raise CmccAuthError("not an autoLogin request body") from exc
    try:
        envelope = json.loads(text)
    except ValueError as exc:
        raise CmccAuthError("not an autoLogin request body") from exc
    if not isinstance(envelope, dict) or not envelope.get("tel"):
        raise CmccAuthError("the envelope has no phone number")
    return text


def phone_of(envelope: str) -> str:
    return str(json.loads(envelope)["tel"])


def biz_envelope(envelope: str) -> str:
    login = json.loads(envelope)
    return json.dumps({**login, "reqBody": {"cellNum": login["tel"]}}, ensure_ascii=False, separators=(",", ":"))


def signed_headers(host: str, path: str, envelope: str, sid: str, qen: str,
                   now: str | None = None, nonce: str | None = None) -> dict[str, str]:
    now = now or str(int(time.time() * 1000))
    nonce = nonce or "".join(random.choice("0123456789") for _ in range(8))
    xk = json.loads(envelope).get("xk") or ""
    token = encrypt(f"{xk}_{path}_{now}_{nonce}", TOKEN_KEY, TOKEN_IV)
    return {
        "Content-Type": "application/Json",
        "User-Agent": USER_AGENT,
        "x-qen": qen,
        "x-time": now,
        "x-nonce": nonce,
        "xs": _md5(f"https://{host}{path}_{envelope}_{SALT}"),
        "x-token": token,
        "x-sign": _md5(f"{token}_{now}_{nonce}_{sid}"),
    }


def session_cookie(set_cookies: list[str]) -> str:
    raw = "; ".join(set_cookies)
    found = []
    for name in ("JSESSIONID", "UID", "ticketID"):
        match = re.search(name + r"=([^;,\s]+)", raw)
        if match:
            found.append(f"{name}={match.group(1)}")
    return "; ".join(found)


def parse_flow(body: dict | None) -> dict:
    try:
        rows = body["newPlanRemainQryRes"]["planRemianFlowListRes"]["planRemianFlowRes"] or []
    except (KeyError, TypeError):
        rows = []
    items = []
    for row in rows:
        total, used = float(row.get("flowSumNum") or 0), float(row.get("flowUsdNum") or 0)
        items.append({"type": row.get("flowtype"), "total_mb": total, "used_mb": used,
                      "remain_mb": max(0.0, total - used)})
    main = items[0] if items else None
    return {
        "items": items,
        "total_mb": main["total_mb"] if main else None,
        "used_mb": main["used_mb"] if main else None,
        "remain_mb": main["remain_mb"] if main else None,
    }


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class CmccClient:
    def __init__(self, session: aiohttp.ClientSession, envelope: str) -> None:
        self._session = session
        self.envelope = envelope
        self._biz = biz_envelope(envelope)

    async def _post(self, host: str, path: str, headers: dict, body: str) -> tuple[str, list[str]]:
        try:
            async with self._session.post(f"https://{host}{path}", headers=headers, data=body,
                                          timeout=TIMEOUT) as resp:
                text = await resp.text()
                return text, resp.headers.getall("Set-Cookie", [])
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise CmccError(f"{host}: {exc}") from exc

    async def refresh(self) -> str:
        """Replay the login envelope and return the new session cookie."""
        global _last_login
        async with _login_lock:
            wait = _last_login + LOGIN_SPACING - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                headers = signed_headers(HOST_LOGIN, PATH_AUTOLOGIN, self.envelope, "null", "14")
                text, cookies = await self._post(HOST_LOGIN, PATH_AUTOLOGIN, headers,
                                                 encrypt(self.envelope, LOGIN_KEYS[0], LOGIN_KEYS[2]))
            finally:
                _last_login = time.monotonic()
        out = _decode(text, LOGIN_KEYS[1], LOGIN_KEYS[2])
        code, desc = out.get("retCode"), out.get("retDesc") or ""
        if code != OK:
            message = f"autoLogin {code} {desc}".strip()
            if code in LOGIN_RATE_LIMITED or LOGIN_TEMPORARY_HINTS.search(desc):
                raise CmccRateLimitError(message)
            raise CmccAuthError(message)
        cookie = session_cookie(cookies)
        if not cookie:
            raise CmccError("autoLogin returned no session cookie")
        return cookie

    async def query(self, key: str, cookie: str) -> dict:
        path = PATHS[key]
        sid = (re.search(r"JSESSIONID=([^;]+)", cookie) or [None, ""])[1]
        headers = signed_headers(HOST_BIZ, path, self._biz, sid, "2")
        headers["Cookie"] = cookie
        text, _ = await self._post(HOST_BIZ, path, headers, encrypt(self._biz, BIZ_KEYS[0], BIZ_KEYS[2]))
        out = _decode(text, BIZ_KEYS[1], BIZ_KEYS[2])
        if out.get("retCode") == SESSION_EXPIRED:
            raise CmccError(f"{key}: session expired")
        if out.get("retCode") != OK:
            raise CmccError(f"{key}: {out.get('retCode')} {out.get('retDesc') or ''}".strip())
        return out.get("rspBody") or {}

    async def fetch(self) -> dict:
        """Refresh the session and read every item; an item that fails is None and listed in errors."""
        cookie = await self.refresh()
        raw, errors = {}, {}
        for key in PATHS:
            try:
                raw[key] = await self.query(key, cookie)
            except CmccError as exc:
                raw[key], errors[key] = None, str(exc)
        fee, points = raw["fee"] or {}, raw["points"] or {}
        user = raw["user"] or {}
        return {
            "phone": phone_of(self.envelope),
            "balance": _number(fee.get("balance")),
            "consumed": _number(fee.get("payAmount")),
            "fee_time": fee.get("oprTime"),
            "points": _number(points.get("pointValue")),
            "flow": parse_flow(raw["flow"]) if raw["flow"] is not None else None,
            "user": user.get("userInfo", user) if raw["user"] is not None else None,
            "raw": raw,
            "errors": errors,
        }


def _decode(text: str, key: str, iv: str) -> dict:
    try:
        return json.loads(decrypt(text or "", key, iv) or "{}")
    except ValueError as exc:
        raise CmccError(f"unreadable response: {text[:80]!r}") from exc
