# Garmin <-> Coros Sync Tool

当前仓库只保留 Garmin 国际区 <-> Coros 双向同步能力。

## 支持范围

- Garmin 国际区 -> Coros
- Coros -> Garmin 国际区

## 配置

支持的配置项：

- `GARMIN_EMAIL`
- `GARMIN_PASSWORD`
- `GARMIN_TOKEN_DATA`
- `GARMIN_TOKENSTORE`
- `COROS_EMAIL`
- `COROS_PASSWORD`
- `GARMIN_NEWEST_NUM`

配置优先级：
1. 命令行参数
2. 环境变量
3. 项目根目录 `.env`

## 运行

安装依赖：

```bash
pip install -r requirements.txt
```

全量双向运行：

```bash
python sync.py
```

仅 Garmin -> Coros：

```bash
python sync.py --garmin-only
```

仅 Coros -> Garmin：

```bash
python sync.py --coros-only
```

仅预演：

```bash
python sync.py --dry-run
```

只预演最新 3 条 Garmin 记录：

```bash
python sync.py --dry-run --garmin-only --newest 3 --coros-email "..." --coros-password "..."
```

## 当前结论

- Garmin 国际区支持 tokenstore 优先复用
- Garmin token / tokenstore 失效时，如果同时配置了账号密码，会自动回退账号密码并重新写入 tokenstore
- Garmin token / tokenstore 失效会被单独识别并输出更明确的日志，便于判断是否需要刷新 token
- 提供 `scripts/refresh_garmin_token.py`，可单独刷新或获取 Garmin tokenstore / token JSON
- `--newest` 现在同时限制抓取和同步阶段的候选数量
- `--dry-run` 现在只预演将要同步的活动，不再下载 FIT 文件
- Coros 双向主流程保留
- 当前仓库默认只公开运行所需说明；开发计划、验收、交接等过程文档建议保留在本地，不随公开仓库提交
- 项目目标是支持无交互自动化运行，适用于服务器定时任务和 GitHub Actions
- 对启用 2FA 的 Garmin 账号，长期目标是通过 tokenstore 刷新/更新维持运行，而不是反复人工输入验证码

## 常见问题

### Garmin 登录失败

优先检查：
- 是否已有可复用的 `garmin_tokens.json`
- `GARMIN_TOKEN_DATA` / `GARMIN_TOKENSTORE` 是否配置正确
- 账号密码是否有效

如果账号启用了 2FA，推荐长期使用 tokenstore 路线。项目后续目标是：
- token 失效后优先刷新或更新 tokenstore
- 仅在确实无法刷新时才需要一次人工重新认证
- 重新认证成功后继续持久化新 token，恢复无交互运行

当前已实现的过渡行为：
- token / tokenstore 登录失败时，如果配置了 `GARMIN_EMAIL` + `GARMIN_PASSWORD`
- 程序会自动回退到账号密码登录
- 登录成功后会重新写入 tokenstore

### 如何单独刷新 Garmin token

本地一次性更新 tokenstore：

```bash
python scripts/refresh_garmin_token.py --garmin-email you@example.com --garmin-password your-password --garmin-tokenstore ~/.garminconnect/default/garmin_tokens.json
```

如果需要把 token JSON 放进 GitHub Secrets：

```bash
python scripts/refresh_garmin_token.py --garmin-email you@example.com --garmin-password your-password --print-token-data
```

### Coros 登录失败

检查：
- `COROS_EMAIL`
- `COROS_PASSWORD`

### 如何查看同步结果

运行结束后会输出：
- Garmin stats
- Coros stats
- Direction summary
