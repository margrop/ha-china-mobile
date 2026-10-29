// Run the upstream cmcc.data.js with fixed time/nonce and a mock transport; print requests + result.
// Regenerate js_out.json: CMCC_DATA_JS=/path/to/paperclip/app/cmcc/cmcc.data.js node tests/js_reference.js tests/fixtures.json > tests/js_out.json
const fs = require("fs"), vm = require("vm"), path = require("path");
const src = fs.readFileSync(process.env.CMCC_DATA_JS || path.join(__dirname, "cmcc.data.js"), "utf8")
  .replace("return { getAccountData, refresh };", "return { getAccountData, refresh, encB64, decStr };");
const ctx = { module: { exports: {} }, globalThis: {}, Date: { now: () => 1761450000000 },
              Math: Object.assign(Object.create(Math), { random: () => 0.35 }), JSON, String, Number, Object, Array, Uint8Array, DataView, Error, RegExp, Promise, encodeURIComponent };
vm.runInNewContext(src, ctx);
const m = ctx.module.exports;
const fixtures = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const LSK = "RYV0hCV1lV25KYVJ", LIV = "VjFSQ1ZtVkQxRTlQ", BSK = "GS7VelkJl5IT1uwQ", BIV = "9791027341711819";
const requests = [];
async function request(req) {
  requests.push(req);
  const p = new URL(req.url).pathname;
  if (p.endsWith("autoLogin")) return { status: 200, headers: { "set-cookie": fixtures.setCookie }, body: m.encB64(JSON.stringify(fixtures.login), LSK, LIV) };
  const key = Object.keys(fixtures.biz).find(k => p.includes(k));
  return { status: 200, headers: {}, body: m.encB64(JSON.stringify(fixtures.biz[key]), BSK, BIV) };
}
const loginEnvelope = JSON.stringify(fixtures.envelope);
m.getAccountData({ loginEnvelope, request }).then(d => {
  delete d.raw;
  console.log(JSON.stringify({ requests, result: d, captured: m.encB64(loginEnvelope, "tVkdaRWRY0ZkV1Vr", LIV) }));
});
