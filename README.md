# Telegram Media Archiver

### YouTube, Bilibili, TikTok, Douyin & Xiaohongshu/RedNote Downloader for Telegram and NAS

**Self-hosted Telegram bot for downloading and archiving social media videos, audio, thumbnails, descriptions, and metadata to local storage or a NAS. Includes yt-dlp platforms today, with dedicated Douyin Downloader and Xiaohongshu/RedNote Downloader adapters on the roadmap.**

把 Telegram 变成私人媒体收件箱：发送一个社交媒体链接，自动下载媒体与元数据到自己的电脑或 NAS，再通过聊天按钮分类归档。

## Why / 为什么做这个项目

收藏链接并不等于保存内容。原帖可能被删除、平台可能失效，普通下载 Bot 又往往只把文件发回聊天，无法形成长期素材库。

Telegram Media Archiver 提供一条简单、可迁移的工作流：

```text
Telegram link → yt-dlp → local/NAS folder → archive button
```

所有内容都是普通文件，不依赖专有数据库；即使停止运行本项目，已归档内容仍可直接访问。

## Features / 功能

- Telegram-first inbox：手机转发链接即可保存
- 基于 `yt-dlp`，覆盖 YouTube、Bilibili、TikTok、Instagram、X、Reddit 等站点
- 为 Douyin Downloader 与 Xiaohongshu/RedNote Downloader 保留明确适配方向
- 保存媒体、缩略图、简介、完整元数据和原始链接
- 每条内容使用独立文件夹，按日期归档
- Telegram 内分类按钮与失败重试
- 下载完成后可点击 **Send to Telegram**，将媒体发送回当前 Telegram 对话供手机预览
- 可配置用户白名单，阻止陌生人消耗服务器流量
- 拒绝私有网络 URL，降低 SSRF 风险
- 单个 Docker 容器，无数据库、无 Web 管理后台
- `amd64` 与 `arm64` 镜像，适用于服务器、NAS、树莓派、macOS 和 Windows
- GitHub Actions 自动测试并发布 GHCR 镜像

## Supported platforms / 平台支持

| Platform | Status | Notes |
|---|---:|---|
| YouTube / YouTube Shorts | ✅ | Video, audio, thumbnail and metadata |
| Bilibili | ✅ | Availability depends on region and login requirements |
| TikTok Downloader | ✅ | Platform changes may require a newer `yt-dlp` |
| Instagram | ✅ | Private or restricted posts may require cookies |
| X / Twitter | ✅ | Public media posts |
| Reddit, Vimeo, SoundCloud | ✅ | Handled by `yt-dlp` |
| Other `yt-dlp` sites | 🟡 | Best effort |
| Douyin Downloader | 🟡 | Dedicated cookie-aware adapter planned; not claimed stable yet |
| Xiaohongshu / RedNote Downloader | 🟡 | Dedicated cookie-aware adapter planned; not claimed stable yet |

平台经常调整接口；遇到下载失败时，首先拉取最新镜像并确认该链接可公开访问。

## Quick start / 快速开始

### 1. Create a Telegram bot

1. Open [@BotFather](https://t.me/BotFather).
2. Run `/newbot` and copy the token.
3. Do not paste that token into source code or commit it to Git.

### 2. Configure

```bash
git clone https://github.com/zz1994125/telegram-media-archiver.git
cd telegram-media-archiver
cp .env.example .env
```

Edit `.env`:

```dotenv
TELEGRAM_BOT_TOKEN=replace-with-your-new-token
TELEGRAM_ALLOWED_USERS=123456789
ARCHIVER_CATEGORIES=favorites,reference,projects,archive
ARCHIVER_HOST_DATA=./data
PUID=1000
PGID=1000
```

`TELEGRAM_ALLOWED_USERS` accepts comma-separated numeric Telegram user IDs. You can temporarily leave it empty while checking your ID, but configure it before exposing the Bot.

### 3. Run

```bash
docker compose up -d --build
docker compose logs -f
```

Send a supported URL to the Bot. Downloads appear in `./data` by default.

```bash
docker compose ps
docker compose down
```

## Deploy a prebuilt GHCR image / 使用预构建镜像

After this repository is published, GitHub Actions builds both `linux/amd64` and `linux/arm64` images:

```bash
docker run -d \
  --name telegram-media-archiver \
  --restart unless-stopped \
  --env-file .env \
  -v /path/to/archive:/data \
  ghcr.io/zz1994125/telegram-media-archiver:latest
```

Make the container package public under the repository's **Packages** settings after the first successful build.

## Device deployment / 各类设备部署

| Device | Recommended method |
|---|---|
| Ubuntu / Debian / VPS | Docker Compose |
| Synology / QNAP / Unraid | Container Manager with `/data` mapped to a shared folder |
| Raspberry Pi 4/5 | GHCR `arm64` image |
| macOS | Docker Desktop or OrbStack |
| Windows | Docker Desktop; use a shared path such as `D:/TelegramArchive` |

For Linux and NAS devices, run `id` and set `PUID`/`PGID` to the owner of the archive folder. This prevents permission errors on bind mounts.

GitHub Pages cannot run a Telegram Bot, GitHub Actions is not a permanent server, and Codespaces can stop or be deleted. GitHub should host the source and container image; the Bot itself must run on an always-on device or hosting provider.

## Storage layout / 文件结构

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
│   └── 2026-08-10/Example video/
└── .telegram-media-archiver-state.json
```

The Bot first saves content to `inbox`, then moves the complete folder when an archive button is selected.

After a download, tap **Send to Telegram** to upload the saved media back into the current Telegram conversation. MP4 files are sent as streamable videos and fall back to documents when Telegram rejects the codec; image-only posts are sent image by image. The default Telegram Bot API accepts videos and general files up to 50 MB, so larger files stay safely in local storage and the Bot reports that they were skipped.

## Configuration / 配置

| Variable | Required | Default | Description |
|---|---:|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | — | Token created by BotFather |
| `TELEGRAM_ALLOWED_USERS` | Recommended | empty | Comma-separated Telegram numeric user IDs; empty allows anyone who knows the Bot |
| `ARCHIVER_CATEGORIES` | No | `favorites,reference,projects,archive` | Telegram archive buttons |
| `ARCHIVER_DOWNLOAD_TIMEOUT` | No | `900` | Per-link timeout in seconds |
| `ARCHIVER_HOST_DATA` | No | `./data` | Host folder mounted at `/data` by Compose |
| `PUID` / `PGID` | Linux/NAS | `1000` | Container process user and group |

## Update / 更新

Source build:

```bash
git pull
docker compose up -d --build
```

GHCR image:

```bash
docker pull ghcr.io/zz1994125/telegram-media-archiver:latest
docker rm -f telegram-media-archiver
# Run the docker command from the deployment section again.
```

Downloaded files remain intact because they live in the mounted host folder.

## Troubleshooting / 故障排查

### Permission denied under `/data`

Confirm that `ARCHIVER_HOST_DATA` exists and is writable by `PUID:PGID`.

### The Bot does not respond

```bash
docker compose ps
docker compose logs --tail=100
```

Check the Bot token, outbound internet access, and `TELEGRAM_ALLOWED_USERS`.

### A platform stopped downloading

Pull or rebuild the latest image. If the post requires login, age confirmation, CAPTCHA, or a private account, the public edition may not be able to access it.

### Download succeeds but archiving fails

Verify that the host data folder is mounted at `/data` and has not been moved manually while the Bot is running.

### Send to Telegram says the file is too large

The public Telegram Bot API currently limits uploaded videos and general files to 50 MB. The original file remains in the archive. A self-hosted Local Bot API Server can raise this ceiling, but it is intentionally outside the one-container default setup.

## Security

- Never commit `.env`, cookies, downloaded media or logs.
- Revoke a Telegram token immediately if it ever appears in source code or Git history.
- Configure `TELEGRAM_ALLOWED_USERS` before sharing the Bot username.
- Keep the container and `yt-dlp` current.
- Only download content you own or are authorized to archive.

## Development

No application dependencies are required for unit tests:

```bash
python -m unittest -v
python -m py_compile app.py
```

Docker provides `yt-dlp` and FFmpeg at runtime.

## Contributing

Bug reports should include the platform, a public example URL when possible, the container version, and sanitized logs. Never post tokens or cookies in an issue.

The most useful contributions are small platform fixes, reproducible failing links, documentation improvements, and deployment reports from different NAS devices.

## Repository metadata / 建议的 GitHub 信息

**Description**

> Self-hosted Telegram media downloader and NAS archiver for YouTube, Bilibili, TikTok, Douyin and Xiaohongshu/RedNote.

**Topics**

`telegram-bot`, `media-downloader`, `social-media-downloader`, `media-archiver`, `yt-dlp`, `self-hosted`, `nas`, `docker`, `video-downloader`, `bilibili-downloader`, `tiktok-downloader`, `douyin-downloader`, `xiaohongshu-downloader`, `rednote-downloader`

## License

[MIT](LICENSE)
