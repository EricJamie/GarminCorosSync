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

Garmin 推荐优先使用 token 方式：

- `GARMIN_TOKEN_DATA`
  直接提供完整的 token JSON 字符串，也就是 `garmin_tokens.json` 文件里的内容本身。
  适合放在 GitHub Secrets 或环境变量中。
- `GARMIN_TOKENSTORE`
  提供本地 `garmin_tokens.json` 文件路径。
  适合本地运行或服务器定时任务。

如果两者都没有，再回退到：

- `GARMIN_EMAIL`
- `GARMIN_PASSWORD`

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

## 使用建议

- 日常运行建议优先使用 `GARMIN_TOKENSTORE` 或 `GARMIN_TOKEN_DATA`
- 对启用 2FA 的 Garmin 账号，建议先用 `scripts/refresh_garmin_token.py` 获取或更新 token
- 首次同步记录很多时，建议先配合 `--newest` 和 `--dry-run` 小范围验证
- `--dry-run` 只预演将要同步的活动，不会真正上传到目标平台

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

两者关系：

- `GARMIN_TOKENSTORE` 是磁盘上的 `garmin_tokens.json` 文件路径
- `GARMIN_TOKEN_DATA` 是这个 `garmin_tokens.json` 文件内容本身的 JSON 字符串形式

可以简单理解为：

- 本地/服务器更适合 `GARMIN_TOKENSTORE`
- GitHub Actions 更适合 `GARMIN_TOKEN_DATA`

示例：

```env
GARMIN_TOKENSTORE=C:\Users\yourname\.garminconnect\default\garmin_tokens.json
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
