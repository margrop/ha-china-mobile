# China Mobile for Home Assistant (app credential)

[![hacs](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/docs/faq/custom_repositories)
[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[中文](README.md) | English

Brings the balance, spending this month, data plan usage and points of China Mobile (中国移动, 10086) numbers into Home Assistant, using the API of the official China Mobile app.

- **Read-only**: it only queries. No check-ins, no orders, no changes to the account.
- **No SMS codes**: capture the app's `autoLogin` request body once while the app cold-starts; the integration replays it periodically to refresh the session.
- **Several numbers**: one config entry per number. Their logins run one at a time, 2 seconds apart, so that several numbers do not trip the "logging in too often" limit.

> Read the [disclaimer](DISCLAIMER.md) (Chinese) before use. This project is not affiliated with China Mobile, and the API may stop working at any time.

## Entities

Each number becomes a device; entity IDs look like `sensor.cmcc_<last 4 digits>_<item>`:

| Entity | Description | Unit |
|---|---|---|
| `balance` Balance | Attribute `as_of` is the carrier's timestamp for the figure | CNY |
| `consumed` Spent this month | | CNY |
| `flow_remaining` Data remaining | Attribute `packages` lists total, used and remaining data of every package | MB (shown as GB by default) |
| `flow_used` Data used | First package | MB |
| `flow_total` Data total | First package | MB |
| `points` Points | | |
| `updated` Last update | Diagnostic; when some items could not be read, attribute `errors` says why | |

## Installation

### HACS (recommended)

1. HACS → top-right menu → "Custom repositories", enter `https://github.com/margrop/ha-china-mobile`, category "Integration".
2. Search for and download "中国移动（App 凭证）", then restart Home Assistant.

### Manual

Copy `custom_components/cmcc_app` into `custom_components/` of your Home Assistant configuration directory and restart.

The integration only uses `aiohttp`, `cryptography` and `certifi`, which ship with Home Assistant; no extra Python packages are installed.

## Capturing the credential

You need a proxy that can decrypt HTTPS, such as Stream, Surge, Loon or Quantumult X on iOS, or Charles or mitmproxy on a computer.

1. Enable HTTPS decryption (MitM) in the proxy and add `client.app.coc.10086.cn` to the decrypted hosts.
2. **Fully close the China Mobile app** (swipe it away), start capturing, then open the app.
3. Find this request:
   `POST https://client.app.coc.10086.cn/biz-orange/LN/uamrandcodelogin/autoLogin`
   (some app versions use `…/uamonekeylogin/autoLogin`)
4. Copy its **request body**, a long base64 string. If your proxy already shows it decrypted as JSON, the JSON works too.
5. Turn HTTPS decryption off when you are done.

> The request body is a long-lived login credential that needs no SMS code. **Treat it like a password**: do not post it in chats or issues.

## Configuration

"Settings → Devices & services → Add integration", search for "China Mobile" or "中国移动", and paste the request body. The integration tries one login first; on success it creates an entry named like `中国移动 138****1234`.

- **Update interval**: set it under the integration's "Configure", 60 minutes by default, 15–720 minutes allowed. Every update replays a login, so do not make it too short.
- **Rejected credential**: when China Mobile rejects the credential, Home Assistant asks you to re-authenticate. Capture it again as above and paste it; entities and history are kept.
- **Logging in too often**: return code `233031`, or a description containing words such as "频繁 / 繁忙 / 稍后" (too frequent / busy / later), is treated as a temporary error. Home Assistant retries by itself and does not ask for a new capture.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| "This is not an autoLogin request body" during setup | You copied another request or only part of it. Make sure it is the **request body** of `autoLogin`, not the response |
| "Logging in too often" during setup | Too many logins in a short time. Try again after half an hour to a few hours |
| `some items could not be read` in the log | Some queries failed (for example the API was busy); the other values still update, and the next update tries again |
| SSL errors | `client.app.coc.10086.cn` still needs legacy TLS renegotiation; the integration allows it only for its own session and still verifies certificates. If it keeps failing, open an issue with your Home Assistant and OpenSSL versions |

Mask phone numbers, `JSESSIONID` values and request bodies in logs before posting an issue.

## Development

```bash
# Request-by-request comparison with the upstream JS implementation (fixed time and nonce), and error paths
uv run --no-project --with aiohttp --with cryptography --with certifi python tests/test_against_js.py
uv run --no-project --with aiohttp --with cryptography --with certifi python tests/test_errors.py
```

`tests/js_out.json` is the output of the upstream `cmcc.data.js` on the same inputs; how to regenerate it is described at the top of `tests/js_reference.js`. See [AGENTS.md](AGENTS.md) (Chinese) for contribution rules.

## Credits

The protocol is ported from `app/cmcc/cmcc.data.js` in [MaYIHEI/paperclip](https://github.com/MaYIHEI/paperclip) (MIT); see [NOTICE.md](NOTICE.md).

## License

[MIT](LICENSE)
