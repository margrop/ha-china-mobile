# AGENTS.md

本文件写给在这个仓库里工作的 AI 编程助手和人类贡献者。

## 项目概况

- Home Assistant 自定义集成，domain 为 `cmcc_app`，代码在 `custom_components/cmcc_app/`。
- 通过“中国移动”App 的私有接口**只读**地查询话费余额、本月消费、套餐流量和积分。
- 协议移植自 MaYIHEI/paperclip 的 `app/cmcc/cmcc.data.js`（MIT），见 `NOTICE.md`。

| 文件 | 作用 |
|---|---|
| `api.py` | 协议实现：AES-128-CBC 加解密、签名请求头、autoLogin 重放、各项查询和解析。不依赖 Home Assistant，可以单独测试 |
| `__init__.py` | `DataUpdateCoordinator`：把 `CmccAuthError` 转成 `ConfigEntryAuthFailed`（触发重新认证），其他 `CmccError` 转成 `UpdateFailed`（自动重试） |
| `config_flow.py` | 粘贴抓包内容 → 校验 → 以手机号作为 `unique_id` 建条目；重新认证；更新间隔选项 |
| `sensor.py` | 实体定义 |
| `brand/` | 集成图标，HACS 校验要求必须有 |
| `strings.json`、`translations/` | 界面文案。`en.json` 必须和 `strings.json` 完全一致，`zh-Hans.json` 键名要一一对应 |

## 硬性规则

1. **只读。** 不要加签到、领奖、办理业务、修改账号资料等任何写操作，也不要加相关接口。
2. **不要提交真实数据。** 包括手机号、请求体、Cookie、`xk`/`t` 等令牌、抓包文件、真实接口的完整响应。测试一律使用 `tests/fixtures.json` 里这种明显虚构的值（例如 `13800000000`）。提交前执行下面的“敏感信息检查”。
3. **不要把凭证写进日志。** 日志和异常信息里只能出现返回码和 `retDesc`，不能出现请求体、Cookie 或完整手机号。设备名、条目标题里的号码要打码（`138****1234`）。
4. **错误分类要谨慎。** 只有确认是“凭证失效”的情况才能抛 `CmccAuthError`，因为它会让用户重新抓包。限流、风控、系统繁忙、网络错误都应该是普通的 `CmccError` 或 `CmccRateLimitError`。新增的已知临时返回码加进 `LOGIN_RATE_LIMITED`。
5. **保持请求和上游一致。** `api.py` 发出的 URL、请求头、请求体必须和上游 JS 逐字节一致，`tests/test_against_js.py` 负责检查。要改协议，先改 `tests/fixtures.json` 并重新生成 `tests/js_out.json`（方法见 `tests/js_reference.js` 开头），不要为了让测试通过而去改参考输出。
6. **不增加第三方依赖。** 只用 Home Assistant 自带的 `aiohttp`、`cryptography`、`certifi`，`manifest.json` 的 `requirements` 保持为空。
7. **TLS。** `OP_LEGACY_SERVER_CONNECT` 只用于本集成自己的会话，不要关闭证书校验，也不要改用 Home Assistant 的共享会话。
8. **频率。** 每次更新都会重放一次登录。不要把默认间隔（60 分钟）或最小间隔（15 分钟）调低，也不要去掉多个号码之间的登录间隔（`LOGIN_SPACING`）。

## 测试

```bash
uv run --no-project --with aiohttp --with cryptography --with certifi python tests/test_against_js.py
uv run --no-project --with aiohttp --with cryptography --with certifi python tests/test_errors.py
```

两个测试都必须通过。CI（`.github/workflows/validate.yml`）还会跑 hassfest 和 HACS 校验。

## 敏感信息检查

提交前在仓库根目录执行，除了 `13800000000`、`13900001234` 这类明显虚构的号码，不应该有其他命中：

```bash
git grep -nE '(^|[^0-9])1[3-9][0-9]{9}([^0-9]|$)|JSESSIONID=[A-Za-z0-9]{16,}|192\.168\.|(^|[^0-9.])10\.[0-9]+\.[0-9]+\.[0-9]+'
```

## 发版

1. 修改 `custom_components/cmcc_app/manifest.json` 里的 `version`，并在 `CHANGELOG.md` 里写明改动。
2. 打标签 `vX.Y.Z` 并创建 GitHub Release。HACS 会读取 Release 作为可用版本。

## 风格

- 和现有代码保持一致：注释少而准，函数短，不加多余的抽象。
- 面向用户的文案要同时更新英文和简体中文。
- `strings.json` 里不能直接写 URL（hassfest 会报错），要用 `{占位符}`，并在代码里通过 `description_placeholders` 传入。
- 图标在 `custom_components/cmcc_app/brand/`（256 和 512 像素的 PNG，透明背景）。不要换成中国移动的商标或标志。
