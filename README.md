<div align="center">

# Telegram Media Archiver

### Telegram 媒体下载与 NAS 归档机器人

[![Container](https://github.com/zz1994125/telegram-media-archiver/actions/workflows/container.yml/badge.svg)](https://github.com/zz1994125/telegram-media-archiver/actions/workflows/container.yml)
[![License](https://img.shields.io/github/license/zz1994125/telegram-media-archiver?style=flat-square)](LICENSE)
[![Stars](https://img.shields.io/github/stars/zz1994125/telegram-media-archiver?style=flat-square&color=fda7df)](https://github.com/zz1994125/telegram-media-archiver/stargazers)
[![Forks](https://img.shields.io/github/forks/zz1994125/telegram-media-archiver?style=flat-square&color=55efc4)](https://github.com/zz1994125/telegram-media-archiver/forks)
[![Docker](https://img.shields.io/badge/Docker-amd64%20%7C%20arm64-2496ED?style=flat-square&logo=docker&logoColor=white)](https://github.com/zz1994125/telegram-media-archiver/pkgs/container/telegram-media-archiver)
[![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=flat-square&logo=python&logoColor=white)](Dockerfile)

**把 Telegram 变成私人媒体收件箱：发送一个链接，自动下载到电脑或 NAS，再通过聊天按钮预览、分类和归档。**

YouTube · Bilibili · TikTok · Douyin · Xiaohongshu / RedNote · Instagram · X / Twitter

</div>

---

## 📖 项目介绍

收藏链接不等于保存内容。原帖可能删除、失效或变成不可访问，普通下载 Bot 又通常只把文件发回聊天，无法沉淀为长期素材库。

Telegram Media Archiver 提供一条简单、可迁移的工作流：

```text
Telegram 链接 → yt-dlp 下载 → 本地 / NAS 保存 → Telegram 按钮预览与分类
```

所有内容都保存为普通文件，不依赖数据库或专有格式。即使以后停止运行本项目，已有媒体和元数据仍可直接访问。

## 📑 项目功能

<details open>
<summary><strong>点击展开或收起功能清单</strong></summary>

- ✅ 在 Telegram 中发送一个或多个媒体链接
- ✅ 自动保存视频、音频、缩略图、简介、完整元数据和原始链接
- ✅ 每条内容使用独立文件夹，并按日期整理
- ✅ Telegram 内自定义分类按钮，一键移动完整内容文件夹
- ✅ 下载完成后点击 **📲 Send to Telegram**，直接发送到当前聊天供手机查看
- ✅ MP4 优先以流媒体视频发送，不兼容时自动改为文件发送
- ✅ 图文内容逐张发送，超过 Telegram 限制的文件保留在本地
- ✅ 下载失败后可在 Telegram 中一键重试
- ✅ 支持 Telegram 用户白名单，防止陌生人消耗服务器资源
- ✅ 拒绝私有网络和本地网络 URL，降低 SSRF 风险
- ✅ 基于 `yt-dlp`，兼容其支持的大量公开媒体网站
- ✅ 可选 MCP Server，让 Codex、Claude 等 AI 客户端调用下载与归档工具
- ✅ 单容器部署，无数据库、无 Web 后台
- ✅ GitHub Actions 自动测试并构建 `amd64` / `arm64` 镜像
- ✅ 适用于 Linux、VPS、NAS、树莓派、macOS 和 Windows

</details>

## 🔗 支持链接

| 平台 | 状态 | 示例 |
|---|:---:|---|
| YouTube / Shorts | ✅ | `youtube.com/watch?...`、`youtu.be/...` |
| Bilibili | ✅ | `bilibili.com/video/...`、`b23.tv/...` |
| TikTok Downloader | ✅ | `tiktok.com/@user/video/...` |
| Instagram | ✅ | 公开 Reels、视频和帖子 |
| X / Twitter | ✅ | 公开媒体帖子 |
| Reddit / Vimeo / SoundCloud | ✅ | 由 `yt-dlp` 处理 |
| 其他 `yt-dlp` 网站 | 🟡 | 尽力兼容，以 `yt-dlp` 实际支持为准 |
| Douyin Downloader | 🧪 | 平台限制较多，公开链接可尝试，暂不保证稳定 |
| Xiaohongshu / RedNote Downloader | 🧪 | 平台限制较多，公开链接可尝试，暂不保证稳定 |

> 平台接口会变化。下载失败时，请先更新镜像并确认链接无需登录、验证码、年龄验证或私有账号权限。

## 🥣 快速开始

### 1. 创建 Telegram Bot

1. 打开 [@BotFather](https://t.me/BotFather)。
2. 发送 `/newbot` 并按提示创建机器人。
3. 保存 Bot Token，不要把它提交到 GitHub。

### 2. 下载并配置

```bash
git clone https://github.com/zz1994125/telegram-media-archiver.git
cd telegram-media-archiver
cp .env.example .env
```

编辑 `.env`：

```dotenv
TELEGRAM_BOT_TOKEN=replace-with-your-new-token
TELEGRAM_ALLOWED_USERS=123456789
ARCHIVER_CATEGORIES=favorites,reference,projects,archive
ARCHIVER_HOST_DATA=./data
PUID=1000
PGID=1000
```

`TELEGRAM_ALLOWED_USERS` 填写 Telegram 数字用户 ID；多个 ID 使用英文逗号分隔。留空代表任何知道 Bot 用户名的人都能使用，公开部署时不建议留空。

### 3. 一键启动

```bash
docker compose up -d --build
```

查看状态和日志：

```bash
docker compose ps
docker compose logs -f
```

现在向 Bot 发送受支持的链接，文件默认保存到 `./data`。

## 🐳 使用预构建镜像

无需下载源码，直接运行 GitHub Container Registry 镜像：

```bash
docker run -d \
  --name telegram-media-archiver \
  --restart unless-stopped \
  --env-file .env \
  -v /path/to/archive:/data \
  ghcr.io/zz1994125/telegram-media-archiver:latest
```

镜像支持：

- `linux/amd64`：常见电脑、服务器和 NAS
- `linux/arm64`：树莓派、Apple Silicon 和 ARM NAS

## 💻 各类设备部署

| 设备 | 推荐方式 | 数据目录示例 |
|---|---|---|
| Ubuntu / Debian / VPS | Docker Compose | `/srv/telegram-archive` |
| 群晖 Synology | Container Manager | 映射共享文件夹到 `/data` |
| QNAP / Unraid | Docker / Apps | 映射媒体共享目录到 `/data` |
| Raspberry Pi 4 / 5 | GHCR `arm64` 镜像 | `/mnt/archive` |
| macOS | Docker Desktop / OrbStack | `./data` 或外接硬盘目录 |
| Windows | Docker Desktop | `D:/TelegramArchive` |

Linux 和 NAS 用户可运行 `id` 查看当前用户的 UID / GID，再写入 `.env` 的 `PUID` 和 `PGID`，避免挂载目录出现权限错误。

> GitHub Pages 只能托管静态网页，不能持续运行 Telegram Bot。GitHub 在本项目中负责托管源码、自动测试和容器镜像；Bot 需要部署到持续在线的电脑、NAS、树莓派或服务器。

## 🤖 MCP Server

项目提供可选的 MCP Server，可让支持 Model Context Protocol 的 AI 客户端操作同一个媒体归档目录。

### 可用工具

| MCP Tool | 功能 |
|---|---|
| `download_media` | 下载一个公开媒体链接到 `inbox` |
| `list_archive` | 查看最近保存的内容，可按分类筛选 |
| `archive_media` | 把指定内容移动到 `.env` 中允许的分类 |

### Streamable HTTP（推荐部署方式）

启动独立 MCP 服务：

```bash
docker compose --profile mcp up -d telegram-media-mcp
```

客户端连接地址：

```text
http://127.0.0.1:8000/mcp
```

该端口在 Compose 中只绑定主机回环地址，不会直接暴露到局域网。若需要远程访问，请先使用具备身份验证和 HTTPS 的反向代理，不要把无认证 MCP 端点直接开放到互联网。

### stdio（本机客户端）

支持 stdio 的客户端可直接启动容器：

```json
{
  "mcpServers": {
    "telegram-media-archiver": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-e", "MCP_TRANSPORT=stdio",
        "-v", "/path/to/archive:/data",
        "ghcr.io/zz1994125/telegram-media-archiver:latest",
        "python", "-u", "/app/app.py", "mcp"
      ]
    }
  }
}
```

把 `/path/to/archive` 改成真实归档目录。MCP 模式不需要 Telegram Bot Token。

## 📲 Telegram 操作流程

1. 向 Bot 发送媒体链接。
2. Bot 下载内容并回复保存位置。
3. 点击 **📲 Send to Telegram**，在手机上直接查看媒体。
4. 点击分类按钮，将完整内容文件夹移动到对应分类。
5. 下载失败时点击 **Retry** 重新尝试。

Telegram 公共 Bot API 对视频和普通文件的默认上传上限为 50 MB。超过限制的文件不会丢失，仍会保留在本地或 NAS 中。

## 📁 文件结构

```text
data/
├── inbox/
│   └── 2026-08-10/
│       └── Example video/
│           ├── Example video [id].mp4
│           ├── Example video [id].info.json
│           ├── Example video [id].description
│           ├── Example video [id].webp
│           └── source.url
├── reference/
│   └── 2026-08-10/
│       └── Example video/
└── .telegram-media-archiver-state.json
```

新下载内容先进入 `inbox`。选择分类后，媒体、缩略图、描述、元数据和来源链接会作为一个完整文件夹一起移动。

## ⚙️ 配置说明

| 环境变量 | 必需 | 默认值 | 说明 |
|---|:---:|---|---|
| `TELEGRAM_BOT_TOKEN` | 是 | — | BotFather 创建的 Bot Token |
| `TELEGRAM_ALLOWED_USERS` | 推荐 | 空 | 允许使用 Bot 的 Telegram 数字用户 ID |
| `ARCHIVER_CATEGORIES` | 否 | `favorites,reference,projects,archive` | Telegram 中显示的归档分类按钮 |
| `ARCHIVER_DOWNLOAD_TIMEOUT` | 否 | `900` | 单个链接的下载超时秒数 |
| `MCP_TRANSPORT` | MCP | `streamable-http` | `streamable-http` 或 `stdio` |
| `MCP_HOST` | MCP | `127.0.0.1` | HTTP 监听地址；容器服务会覆盖为 `0.0.0.0` |
| `MCP_PORT` | MCP | `8000` | Streamable HTTP 端口 |
| `ARCHIVER_HOST_DATA` | 否 | `./data` | 主机上保存媒体的目录 |
| `PUID` / `PGID` | Linux / NAS | `1000` | 容器进程使用的用户和用户组 |

自定义分类示例：

```dotenv
ARCHIVER_CATEGORIES=稍后看,学习资料,项目素材,长期归档
```

这些名称只保存在你自己的 `.env` 中，不需要修改源码，也不会被提交到 GitHub。

## 🔄 更新项目

### 从源码构建

```bash
git pull
docker compose up -d --build
```

### 使用 GHCR 镜像

```bash
docker pull ghcr.io/zz1994125/telegram-media-archiver:latest
docker rm -f telegram-media-archiver
# 再次执行上方 docker run 命令
```

媒体文件保存在主机挂载目录中，更新或重建容器不会删除已归档内容。

## 🧰 常见问题

<details>
<summary><strong>Bot 没有响应</strong></summary>

```bash
docker compose ps
docker compose logs --tail=100
```

检查 Bot Token、服务器外网连接和 `TELEGRAM_ALLOWED_USERS`。

</details>

<details>
<summary><strong>/data 出现 Permission denied</strong></summary>

确认 `ARCHIVER_HOST_DATA` 已存在，并且 `PUID:PGID` 对该目录拥有读写权限。

</details>

<details>
<summary><strong>某个平台突然无法下载</strong></summary>

先拉取或构建最新镜像。若链接需要登录、Cookie、验证码、年龄确认或私有账号权限，当前公开版可能无法访问。

</details>

<details>
<summary><strong>Send to Telegram 提示文件太大</strong></summary>

文件仍安全保存在归档目录中。默认实现遵守 Telegram 公共 Bot API 的 50 MB 上传限制。

</details>

<details>
<summary><strong>下载时报 no space left on device</strong></summary>

下载器及解析浏览器的临时文件会放在 `ARCHIVER_DATA_DIR/.tmp` 中，随任务结束自动清理。使用外置盘或 NAS 时，请确认归档目录或 Docker 的 `/data` 挂载指向该存储，并有足够空间；仅将成品放到外置盘不能解决系统临时目录满的问题。

</details>

<details>
<summary><strong>为什么不能部署到 GitHub Pages</strong></summary>

Telegram Bot 需要长期运行并持续接收消息，而 GitHub Pages 只能提供静态网页。请使用 NAS、树莓派、VPS 或常开电脑运行容器。

</details>

## 🔐 安全与使用说明

- 不要提交 `.env`、Bot Token、Cookie、下载文件或运行日志。
- 如果 Token 曾出现在代码或 Git 历史中，请立即通过 BotFather 撤销并重新生成。
- 对外分享 Bot 用户名前，请配置 `TELEGRAM_ALLOWED_USERS`。
- 仅下载自己拥有或已获授权保存的内容，并遵守目标平台条款和当地法律。
- 本项目不提供平台限制绕过、付费内容破解或私有账号访问功能。

## 🛠 开发与测试

项目测试不需要安装额外 Python 依赖：

```bash
python -m unittest -v
python -m py_compile app.py
```

Docker 镜像在运行时提供 `yt-dlp` 和 FFmpeg。

## 🤝 参与贡献

欢迎提交 Issue 和 Pull Request。反馈下载问题时，请提供：

- 平台名称和公开示例链接
- 使用的镜像或提交版本
- 已删除 Token、Cookie、用户名和本地路径的日志

最有价值的贡献包括：可复现的平台兼容修复、不同 NAS / 设备的部署反馈、文档改进和小而清晰的功能修复。

## 🙏 致谢

Telegram Media Archiver 的早期本地工作流由多个开源项目组合、验证并逐步重构而来。感谢这些项目及其维护者：

**当前开源版直接依赖**

- [yt-dlp](https://github.com/yt-dlp/yt-dlp)：跨平台媒体下载与元数据提取
- [FFmpeg](https://github.com/FFmpeg/FFmpeg)：音视频合并与格式处理
- [Model Context Protocol Python SDK](https://github.com/modelcontextprotocol/python-sdk)：MCP Server 与 Streamable HTTP 支持

**早期本地工作流集成与参考**

- [XHS-Downloader](https://github.com/JoeanAmier/XHS-Downloader)：小红书内容解析、下载与动态资源补充
- [wanyi-watermark](https://github.com/Ryan7t/wanyi-watermark)：早期抖音与小红书解析链路
- [douyin-mcp-server](https://github.com/yzfly/douyin-mcp-server)：`wanyi-watermark` 标明的上游基础项目

当前公开版没有直接复制这些项目的私有配置或本地定制代码；具体依赖和许可证以各项目仓库为准。

## 📄 开源许可

本项目采用 [MIT License](LICENSE)。
