"""Error paths of cmcc_app/api.py with a mocked transport."""
import asyncio, importlib.util, json, pathlib, time
spec = importlib.util.spec_from_file_location("cmcc_api", pathlib.Path(__file__).resolve().parent.parent / "custom_components/cmcc_app/api.py")
api = importlib.util.module_from_spec(spec); spec.loader.exec_module(api)
ENV = json.dumps({"tel": "13900001234", "xk": "k", "t": "x"}, separators=(",", ":"))


def raises(exc, fn):
    try:
        fn()
    except exc:
        return True
    raise AssertionError(f"{fn} did not raise {exc.__name__}")


def transport(login, biz, cookies=("JSESSIONID=S; Path=/",)):
    async def post(self, host, path, headers, body):
        if path.endswith("autoLogin"):
            return api.encrypt(json.dumps(login), *api.LOGIN_KEYS[1:]), list(cookies)
        out = biz(path)
        return (api.encrypt(json.dumps(out), *api.BIZ_KEYS[1:]) if isinstance(out, dict) else out), []
    return post


for junk in ["", "hello", "{\"no\": \"tel\"}", api.encrypt("not json", api.LOGIN_KEYS[0], api.LOGIN_KEYS[2])]:
    raises(api.CmccAuthError, lambda j=junk: api.parse_capture(j))
assert api.phone_of(api.parse_capture(api.encrypt(ENV, api.LOGIN_KEYS[0], api.LOGIN_KEYS[2]))) == "13900001234"

api.LOGIN_SPACING = 0
client = api.CmccClient(None, ENV)
api.CmccClient._post = transport({"retCode": "100001", "retDesc": "登录失效"}, lambda p: {})
raises(api.CmccAuthError, lambda: asyncio.run(client.refresh()))

# Rate limiting is temporary: not an auth error, so Home Assistant retries instead of asking to re-capture.
for login in [{"retCode": "233031", "retDesc": ""}, {"retCode": "299999", "retDesc": "操作过于频繁，请稍后再试"}]:
    api.CmccClient._post = transport(login, lambda p: {})
    try:
        asyncio.run(client.refresh())
        raise AssertionError("no error")
    except api.CmccAuthError:
        raise AssertionError(f"{login} treated as auth error")
    except api.CmccRateLimitError:
        pass

# Logins of several numbers are serialised and spaced.
stamps = []
async def stamped(self, host, path, headers, body):
    stamps.append(time.monotonic())
    return api.encrypt(json.dumps({"retCode": "000000"}), *api.LOGIN_KEYS[1:]), ["JSESSIONID=S; Path=/"]
async def three_numbers():
    await asyncio.gather(*(api.CmccClient(None, ENV).refresh() for _ in range(3)))
api.CmccClient._post = stamped
api.LOGIN_SPACING = 0.2
asyncio.run(three_numbers())
gaps = [b - a for a, b in zip(stamps, stamps[1:])]
assert len(stamps) == 3 and min(gaps) >= 0.19, gaps
api.LOGIN_SPACING = 0

api.CmccClient._post = transport({"retCode": "000000"}, lambda p: {}, cookies=())
raises(api.CmccError, lambda: asyncio.run(client.refresh()))

api.CmccClient._post = transport({"retCode": "000000"}, lambda p: {"retCode": "410000"})
raises(api.CmccError, lambda: asyncio.run(client.query("fee", "JSESSIONID=S")))

def partial(path):
    if "payFees" in path:
        return {"retCode": "000000", "rspBody": {"balance": "8.5", "payAmount": "1"}}
    if "Score" in path:
        return "<html>403</html>"
    return {"retCode": "999999", "retDesc": "系统繁忙"}
api.CmccClient._post = transport({"retCode": "000000"}, partial)
data = asyncio.run(client.fetch())
assert data["balance"] == 8.5 and data["consumed"] == 1.0, data
assert data["points"] is None and data["flow"] is None and data["user"] is None
assert set(data["errors"]) == {"points", "flow", "user"}, data["errors"]
print("error paths ok:", data["errors"])
