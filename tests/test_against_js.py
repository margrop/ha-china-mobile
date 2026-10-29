"""Compare cmcc_app/api.py with the upstream JS module on identical inputs (fixed time and nonce)."""
import asyncio
import importlib.util
import json
import pathlib
import random
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("cmcc_api", HERE.parent / "custom_components/cmcc_app/api.py")
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)

fixtures = json.loads((HERE / "fixtures.json").read_text())
js = json.loads((HERE / "js_out.json").read_text())

time.time = lambda: 1761450000.0
random.choice = lambda seq: "3"

requests = []


async def fake_post(self, host, path, headers, body):
    requests.append({"url": f"https://{host}{path}", "method": "POST", "headers": headers, "body": body})
    if path.endswith("autoLogin"):
        return api.encrypt(json.dumps(fixtures["login"], ensure_ascii=False), *api.LOGIN_KEYS[1:]), fixtures["setCookie"]
    key = next(k for k in fixtures["biz"] if k in path)
    return api.encrypt(json.dumps(fixtures["biz"][key], ensure_ascii=False), *api.BIZ_KEYS[1:]), []


api.CmccClient._post = fake_post
envelope = api.parse_capture(js["captured"])
assert envelope == json.dumps(fixtures["envelope"], ensure_ascii=False, separators=(",", ":")), envelope
assert api.parse_capture("  " + envelope + "\n") == envelope
data = asyncio.run(api.CmccClient(None, envelope).fetch())

failures = 0
# JS queries in its PATHS order too; compare request by request.
for i, (mine, ref) in enumerate(zip(requests, js["requests"])):
    for field in ("url", "method", "body"):
        if mine[field] != ref[field]:
            failures += 1
            print(f"request {i} {field} differs")
    if mine["headers"] != ref["headers"]:
        failures += 1
        print(f"request {i} headers differ:", {k: (mine["headers"].get(k), ref["headers"].get(k))
                                               for k in set(mine["headers"]) | set(ref["headers"])
                                               if mine["headers"].get(k) != ref["headers"].get(k)})
if len(requests) != len(js["requests"]):
    failures += 1
    print("request count", len(requests), len(js["requests"]))

ref = js["result"]
expect = {
    "balance": ref["fee"]["balance"], "consumed": ref["fee"]["consumed"], "fee_time": ref["fee"]["at"],
    "points": ref["points"], "user": ref["user"],
    "flow_remain_mb": ref["flow"]["remainMB"], "flow_used_mb": 14766, "flow_total_mb": 200704,
    "flow_items": [(x["type"], x["totalMB"], x["usedMB"], x["remainMB"]) for x in ref["flow"]["items"]],
}
got = {
    "balance": data["balance"], "consumed": data["consumed"], "fee_time": data["fee_time"],
    "points": data["points"], "user": data["user"],
    "flow_remain_mb": data["flow"]["remain_mb"], "flow_used_mb": data["flow"]["used_mb"],
    "flow_total_mb": data["flow"]["total_mb"],
    "flow_items": [(x["type"], x["total_mb"], x["used_mb"], x["remain_mb"]) for x in data["flow"]["items"]],
}
for k in expect:
    if expect[k] != got[k]:
        failures += 1
        print("result", k, got[k], "!=", expect[k])
assert data["errors"] == {} and data["phone"] == "13800000000"
print(f"{len(requests)} requests compared, {failures} differences")
sys.exit(1 if failures else 0)
