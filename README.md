# Garmin ⇄ Coros 双向同步工具

> **说明**：本工具目前仅支持 **Garmin 国际区**。
> Garmin 中国区尚未支持，如有需要可后续扩展。

自动同步 Garmin（国际区）和 Coros（高驰）之间的运动记录。

## 功能说明

| 同步方向 | 说明 |
|---------|------|
| **Garmin → Coros** | 将 Garmin 的运动记录同步到 Coros |
| **Coros → Garmin** | 将 Coros 的运动记录同步到 Garmin |

- 支持双向同步，不会出现重复记录
- 同步状态保存在本地数据库，断电重启不丢失进度
- 支持服务器部署和 GitHub Actions 自动化

---

## 准备工作

### 1. 安装 Python

**Windows**：
1. 访问 https://www.python.org/downloads/
2. 下载 Python 3.10 或更高版本
3. 运行安装程序，**记得勾选"Add Python to PATH"**
4. 打开命令提示符（CMD），验证安装：

```cmd
python --version
pip --version
```

**Linux（Ubuntu/Debian）**：
```bash
sudo apt update
sudo apt install python3 python3-pip
```

**Mac**：
```bash
# 如果没有 brew，先安装 brew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 安装 Python
brew install python3
```

### 2. 安装依赖库

```bash
pip install garminconnect oss2 urllib3 certifi
```

---

## 配置说明

本工具需要配置以下账号信息：

| 变量 | 必须 | 说明 |
|------|------|------|
| `COROS_EMAIL` | ✅ | Coros 账号邮箱 |
| `COROS_PASSWORD` | ✅ | Coros 账号密码 |
| `GARMIN_EMAIL` | ⚠️ | Garmin 账号邮箱（无 2FA 时必须） |
| `GARMIN_PASSWORD` | ⚠️ | Garmin 账号密码（无 2FA 时必须） |
| `GARMIN_TOKEN_DATA` | ⚠️ | Garmin Token（2FA 用户或用 Token 登录时必须） |
| `GARMIN_TOKEN_DIR` | ⚠️ | Garmin Token 目录（可选） |

### 认证方式（根据你的情况选择一种）

#### 方式一：Garmin 账号密码登录（无 2FA 用户推荐）

直接填入 Garmin 账号和密码即可。

#### 方式二：Garmin Token 登录（2FA 用户 或 遇到 429 的用户）

1. 在本地电脑上运行一次同步脚本，让程序自动登录并获取 Token
2. 找到 Token 文件：
   - **Windows**: `C:\Users\你的用户名\.garminconnect\数字\garmin_tokens.json`
   - **Mac/Linux**: `~/.garminconnect/数字/garmin_tokens.json`
3. 打开文件，复制全部内容
4. 把复制的内容作为 `GARMIN_TOKEN_DATA` 的值

---

## 本地运行

### 第一步：创建配置文件

在项目目录下创建 `.env` 文件：

**Windows 创建命令**：
```cmd
cd 项目目录
echo COROS_EMAIL=你的Coros邮箱 > .env
echo COROS_PASSWORD=你的Coros密码 >> .env
echo GARMIN_EMAIL=你的Garmin邮箱 >> .env
echo GARMIN_PASSWORD=你的Garmin密码 >> .env
```

或者直接用文本编辑器创建 `.env` 文件，内容示例：

```
COROS_EMAIL=example@outlook.com
COROS_PASSWORD=yourpassword
GARMIN_EMAIL=yourgarmin@email.com
GARMIN_PASSWORD=yourgarminpassword
```

### 第二步：运行同步

```bash
python sync.py
```

### 命令行参数说明

| 参数 | 说明 |
|------|------|
| `--dry-run` | 预览模式，不实际上传 |
| `--garmin-only` | 仅同步 Garmin → Coros |
| `--coros-only` | 仅同步 Coros → Garmin |
| `--force-fetch-garmin` | 重新拉取 Garmin 活动列表 |
| `--force-fetch-coros` | 重新拉取 Coros 活动列表 |
| `--newest 数量` | 拉取最近多少条活动（默认 1000） |

**示例**：
```bash
# 预览模式（看看会同步什么，不实际上传）
python sync.py --dry-run

# 只同步 Garmin 到 Coros
python sync.py --garmin-only

# 只同步 Coros 到 Garmin
python sync.py --coros-only
```

---

## 服务器部署（定时自动运行）

### Windows 服务器 - 使用任务计划程序

#### 第一步：配置环境变量

1. 右键"此电脑" → 属性 → 高级系统设置 → 环境变量
2. 在"用户变量"中新建：
   - `COROS_EMAIL` = 你的 Coros 邮箱
   - `COROS_PASSWORD` = 你的 Coros 密码
   - `GARMIN_EMAIL` = 你的 Garmin 邮箱
   - `GARMIN_PASSWORD` = 你的 Garmin 密码

#### 第二步：创建批处理文件

用文本编辑器创建 `sync.bat` 文件：

```batch
@echo off
cd /d 项目完整路径
python sync.py >> logs/sync.log 2>&1
```

#### 第三步：设置定时任务

1. 打开"任务计划程序"
2. 创建基本任务
3. 名称填写"Garmin Coros Sync"
4. 触发器选择"每天"，时间设置如 07:00
5. 操作选择"启动程序"，程序选择刚才创建的 `sync.bat`
6. 完成

---

### Linux/Mac 服务器 - 使用 Cron

#### 第一步：创建运行脚本

```bash
#!/bin/bash
cd /path/to/sync_garmin_coros
python sync.py >> logs/sync.log 2>&1
```

保存为 `run_sync.sh`，然后添加执行权限：

```bash
chmod +x run_sync.sh
```

#### 第二步：设置环境变量

```bash
export COROS_EMAIL="your@email.com"
export COROS_PASSWORD="yourpassword"
export GARMIN_EMAIL="garmin@email.com"
export GARMIN_PASSWORD="garminpassword"
```

#### 第三步：设置定时任务

```bash
crontab -e
```

添加一行（每天早上 7:30 执行）：

```cron
30 7 * * * /path/to/run_sync.sh
```

保存退出即可。

**常用 Cron 时间格式**：
- `0 * * * *` - 每小时
- `30 7 * * *` - 每天 7:30
- `0 7 * * 0` - 每周日 7:00
- `0 7 * * *` - 每天 7:00

---

## GitHub Actions 部署

### 前提条件

需要一个 GitHub 账号

### 第一步：Fork 项目

1. 访问 https://github.com/EricJamie/GarminCorosSync
2. 点击右上角 "Fork"
3. 选择你的账号

### 第二步：配置 Secrets

1. 进入你的 Fork 仓库
2. 点击 Settings → Secrets and variables → Actions
3. 点击 "New repository secret"

需要添加以下 Secrets：

| Secret 名称 | 值 |
|------------|-----|
| `COROS_EMAIL` | 你的 Coros 邮箱 |
| `COROS_PASSWORD` | 你的 Coros 密码 |
| `GARMIN_EMAIL` | 你的 Garmin 邮箱 |
| `GARMIN_PASSWORD` | 你的 Garmin 密码（无 2FA 用户） |
| `GARMIN_TOKEN_DATA` | Garmin Token 内容（2FA 用户或遇到 429 用户） |

**获取 GARMIN_TOKEN_DATA 的方法**：
1. 在本地电脑上找到文件：
   - Windows: `C:\Users\你的用户名\.garminconnect\数字\garmin_tokens.json`
   - Mac/Linux: `~/.garminconnect/数字/garmin_tokens.json`
2. 用文本编辑器打开，复制全部内容
3. 粘贴到 GitHub Secret 的值框中

### 第三步：启用 Actions

1. 进入仓库的 Actions 页面
2. 如果看到提示，点击 "I understand my workflows, go ahead and enable them"

### 第四步：手动运行

1. 进入 Actions 页面
2. 点击左侧 "Garmin ⇄ Coros Sync"
3. 点击 "Run workflow"
4. 选择方向（both/garmin-to-coros/coros-to-garmin）
5. 点击 "Run workflow"

### 第五步：查看运行日志

1. 进入 Actions 页面
2. 点击最新的运行记录
3. 点击 "sync" 任务
4. 展开查看日志

### 第六步：设置定时自动运行

仓库的 Actions 已经配置好每天 07:30（北京时间）自动运行。

如果需要修改时间，编辑 `.github/workflows/sync.yml` 文件：

```yaml
on:
  schedule:
    - cron: '30 7 * * *'  # 修改这里的时间
```

Cron 格式说明：`分 时 日 月 周`
- `30 7 * * *` = 每天 7:30
- `0 */2 * * *` = 每 2 小时
- `0 7 * * 0` = 每周日 7:00

---

## 常见问题

### Q: 提示 "Garmin login failed"

**原因**：Garmin 登录失败，可能是 2FA 或 429 限流。

**解决方法**：
1. 使用 Token 方式登录
2. 在本地先运行一次脚本获取 Token
3. 把 Token 内容填入 `GARMIN_TOKEN_DATA`

### Q: 提示 "Coros login failed"

**原因**：Coros 账号或密码错误。

**解决方法**：检查 `COROS_EMAIL` 和 `COROS_PASSWORD` 是否正确。

### Q: 活动重复同步了

**原因**：数据库记录丢失或损坏。

**解决方法**：删除数据库文件重新开始：
- Windows: `data\db\sync_garmin_coros.db`
- Mac/Linux: `data/db/sync_garmin_coros.db`

### Q: GitHub Actions 运行时很久卡住了

**原因**：可能是 Garmin 或 Coros 服务器响应慢。

**解决方法**：在 Actions 页面手动取消，然后重试。

### Q: 如何查看同步了多少条记录？

查看日志输出，或者查看数据库状态：
- Windows: `data\db\sync_garmin_coros.db`
- 使用 SQLite 工具打开查看

---

## 数据流向说明

```
┌─────────────┐     Garmin → Coros      ┌─────────────┐
│   Garmin    │ ──────────────────────→  │    Coros    │
│  Connect    │                          │   (高驰)    │
└─────────────┘                          └─────────────┘
       ↑                                        │
       │                                        │
       │         Coros → Garmin                │
       └──────────────────────────────────────┘

每个方向独立追踪，不会出现循环同步的问题。
```

---

## 技术支持

如果遇到问题：
1. 查看日志输出
2. 检查环境变量配置
3. 确认网络连接正常
4. 查看 GitHub Actions 日志（如果使用云端部署）

---

**版本**：1.0.0
**最后更新**：2026-04-11
