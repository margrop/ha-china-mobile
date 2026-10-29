# 中国移动 Home Assistant 集成（App 凭证）

[![hacs](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/docs/faq/custom_repositories)
[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

中文 | [English](README.en.md)

用“中国移动”App 自己的接口，把号码的话费余额、本月消费、套餐流量和积分接入 Home Assistant。

- **只读**：只查询，不签到、不办理业务、不修改任何账号数据。
- **免短信**：在 App 冷启动时抓一次 `autoLogin` 请求体，之后由集成定期重放来刷新会话。
- **多号码**：每个号码一个配置条目，多个号码的登录会串行执行，并相互间隔 2 秒，避免触发“登录过于频繁”。

> 使用前请阅读 [免责声明](DISCLAIMER.md)。本项目与中国移动无关，接口随时可能失效。

## 实体

每个号码会生成一个设备，实体 ID 形如 `sensor.cmcc_<尾号>_<项目>`：

| 实体 | 说明 | 单位 |
|---|---|---|
| `balance` 话费余额 | 属性 `as_of` 为运营商给出的数据时间 | CNY |
| `consumed` 本月消费 | | CNY |
| `flow_remaining` 剩余流量 | 属性 `packages` 列出每个流量包的总量、已用、剩余 | MB（界面默认显示 GB） |
| `flow_used` 已用流量 | 第一个流量包 | MB |
| `flow_total` 流量总量 | 第一个流量包 | MB |
| `points` 积分 | | |
| `updated` 更新时间 | 诊断实体；部分项目读取失败时，属性 `errors` 会写明原因 | |

## 安装

### HACS（推荐）

1. HACS → 右上角菜单 →「自定义存储库」，地址填 `https://github.com/margrop/ha-china-mobile`，类别选「Integration」。
2. 搜索并下载「中国移动（App 凭证）」，然后重启 Home Assistant。

### 手动安装

把 `custom_components/cmcc_app` 复制到 Home Assistant 配置目录下的 `custom_components/`，然后重启。

集成只用到 Home Assistant 自带的 `aiohttp`、`cryptography`、`certifi`，不需要额外安装 Python 依赖。

## 抓取凭证

你需要一个能解密 HTTPS 的抓包工具，比如 iOS 上的 Stream、Surge、Loon、Quantumult X，或电脑上的 Charles、mitmproxy。

1. 在抓包工具里开启 HTTPS 解密，并把 `client.app.coc.10086.cn` 加入解密域名（MitM 主机名）。
2. **彻底关闭“中国移动”App**（从后台划掉），开始抓包后再打开 App。
3. 找到这条请求：
   `POST https://client.app.coc.10086.cn/biz-orange/LN/uamrandcodelogin/autoLogin`
   （有的版本是 `…/uamonekeylogin/autoLogin`）
4. 复制它的**请求体**，也就是一长串 base64 文本。如果你的工具已经把它解密成 JSON，复制 JSON 也可以。
5. 抓完后关闭 HTTPS 解密。

> 这份请求体相当于一份长期有效、不需要短信的登录凭证，**请像对待密码一样保管它**，不要发到群里或 issue 里。

## 配置

「设置 → 设备与服务 → 添加集成」，搜索「中国移动」，把请求体粘贴进去。集成会先试登录一次，成功后以 `中国移动 138****1234` 的名称创建条目。

- **更新间隔**：在集成的「配置」里设置，默认 60 分钟，范围 15–720 分钟。每次更新都会重放一次登录，间隔不要设得太短。
- **凭证失效**：中国移动拒绝凭证时，Home Assistant 会提示「重新认证」。按上面的步骤重新抓一次，粘贴进去即可，实体和历史数据都会保留。
- **登录过于频繁**：返回码 `233031`，或者错误描述里有“频繁 / 繁忙 / 稍后”等字样时，按临时错误处理，Home Assistant 会自动重试，不会要求重新抓包。

## 常见问题

| 现象 | 原因与处理 |
|---|---|
| 配置时提示“这不是 autoLogin 的请求体” | 复制的是别的请求，或者只复制了一部分。请确认是 `autoLogin` 的**请求体**，而不是响应体 |
| 配置时提示“登录过于频繁” | 短时间内登录次数太多，过半小时到几小时再试 |
| 日志里有 `some items could not be read` | 部分查询失败（比如接口繁忙），其余数据照常更新，下次更新会再试 |
| 连接报 SSL 错误 | `client.app.coc.10086.cn` 需要旧式 TLS 重协商，集成只对它的会话单独放开，证书仍照常校验。如果仍然报错，请附上 Home Assistant 和 OpenSSL 版本提 issue |

提 issue 时请把日志里的手机号、`JSESSIONID`、请求体等内容打码。

## 开发

```bash
# 与上游 JS 实现逐请求对比（固定时间和随机数），以及错误路径测试
uv run --no-project --with aiohttp --with cryptography --with certifi python tests/test_against_js.py
uv run --no-project --with aiohttp --with cryptography --with certifi python tests/test_errors.py
```

`tests/js_out.json` 是上游 `cmcc.data.js` 在同样输入下的输出，重新生成的方法写在 `tests/js_reference.js` 开头。更多约定见 [AGENTS.md](AGENTS.md)。

## 致谢

协议实现移植自 [MaYIHEI/paperclip](https://github.com/MaYIHEI/paperclip) 中的 `app/cmcc/cmcc.data.js`（MIT），详见 [NOTICE.md](NOTICE.md)。

## 许可证

[MIT](LICENSE)
