#!/usr/bin/env python3
"""Telegram Media Archiver: save chat links into ordinary local folders."""

from __future__ import annotations

import ipaddress
import json
import mimetypes
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path


DATA_DIR = Path(os.getenv("ARCHIVER_DATA_DIR", "/data")).resolve()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ALLOWED_USERS = {
    int(value) for value in os.getenv("TELEGRAM_ALLOWED_USERS", "").split(",")
    if value.strip().isdigit()
}
CATEGORIES = [
    value.strip() for value in os.getenv(
        "ARCHIVER_CATEGORIES", "favorites,reference,projects,archive"
    ).split(",") if value.strip()
]
DOWNLOAD_TIMEOUT = int(os.getenv("ARCHIVER_DOWNLOAD_TIMEOUT", "900"))
MCP_HOST = os.getenv("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.getenv("MCP_PORT", "8000"))
MCP_TRANSPORT = os.getenv("MCP_TRANSPORT", "streamable-http")
MAX_UPLOAD_BYTES = 50_000_000
MAX_PHOTO_BYTES = 10_000_000
STATE_FILE = DATA_DIR / ".telegram-media-archiver-state.json"
URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)
DOWNLOAD_LOCK = threading.Lock()

PLATFORMS = {
    "douyin.com": "douyin",
    "youtube.com": "youtube", "youtu.be": "youtube",
    "bilibili.com": "bilibili", "b23.tv": "bilibili",
    "tiktok.com": "tiktok", "instagram.com": "instagram",
    "twitter.com": "x", "x.com": "x", "reddit.com": "reddit",
    "vimeo.com": "video", "soundcloud.com": "audio",
}


def sanitize(value: str, fallback: str = "untitled") -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", value).strip().strip(".")
    value = re.sub(r"\s+", " ", value)
    return value[:100] or fallback


def extract_urls(text: str) -> list[str]:
    return list(dict.fromkeys(match.rstrip(".,;:!?)]}") for match in URL_RE.findall(text or "")))


def platform_for(url: str) -> str:
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    for domain, platform in PLATFORMS.items():
        if host == domain or host.endswith("." + domain):
            return platform
    return "media"


def validate_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only public HTTP(S) URLs are accepted")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or 443)}
    except socket.gaierror as error:
        raise ValueError("Host name could not be resolved") from error
    if any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError("Private and local network URLs are blocked")


def load_state() -> dict:
    try:
        value = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # ponytail: last 200 actions are enough for chat buttons; use SQLite if multi-user history matters.
    state = dict(list(state.items())[-200:])
    temp = STATE_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(STATE_FILE)


class Telegram:
    def __init__(self, token: str):
        self.base = f"https://api.telegram.org/bot{token}/"

    def call(self, method: str, **params):
        encoded = {}
        for key, value in params.items():
            encoded[key] = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
        request = urllib.request.Request(
            self.base + method,
            data=urllib.parse.urlencode(encoded).encode(),
        )
        with urllib.request.urlopen(request, timeout=65) as response:
            payload = json.load(response)
        if not payload.get("ok"):
            raise RuntimeError(payload.get("description", "Telegram API error"))
        return payload.get("result")

    def send(self, chat_id: int, text: str, keyboard=None):
        params = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
        if keyboard:
            params["reply_markup"] = {"inline_keyboard": keyboard}
        return self.call("sendMessage", **params)

    def send_file(self, chat_id: int, path: Path, method: str, field: str):
        boundary = "----TelegramMediaArchiver" + secrets.token_hex(12)
        body = bytearray()

        def add_value(name: str, value: str) -> None:
            body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())

        add_value("chat_id", str(chat_id))
        add_value("caption", path.name[:1024])
        if method == "sendVideo":
            add_value("supports_streaming", "true")
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        filename = path.name.replace('"', "'")
        body.extend(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{filename}\"\r\nContent-Type: {mime}\r\n\r\n".encode()
        )
        body.extend(path.read_bytes())
        body.extend(f"\r\n--{boundary}--\r\n".encode())
        request = urllib.request.Request(
            self.base + method,
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = json.load(response)
        if not payload.get("ok"):
            raise RuntimeError(payload.get("description", "Telegram upload error"))
        return payload.get("result")


def archive_keyboard(token: str):
    rows = [[{"text": "📲 Send to Telegram", "callback_data": f"send:{token}"}]]
    for index in range(0, len(CATEGORIES), 2):
        rows.append([
            {"text": name, "callback_data": f"move:{token}:{offset}"}
            for offset, name in enumerate(CATEGORIES[index:index + 2], start=index)
        ])
    return rows


def retry_keyboard(token: str):
    return [[{"text": "Retry", "callback_data": f"retry:{token}"}]]


def media_files(path_text: str) -> list[Path]:
    folder = Path(path_text).resolve()
    if not folder.is_relative_to(DATA_DIR) or not folder.is_dir():
        raise ValueError("Saved folder is missing or outside the data directory")
    video_audio = {".mp4", ".mov", ".mkv", ".webm", ".mp3", ".m4a", ".ogg", ".wav", ".flac"}
    images = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    files = sorted(item for item in folder.iterdir() if item.is_file())
    primary = [item for item in files if item.suffix.lower() in video_audio]
    return primary or [item for item in files if item.suffix.lower() in images]


def send_saved_media(bot: Telegram, chat_id: int, path_text: str) -> tuple[int, list[str]]:
    files = media_files(path_text)
    if not files:
        raise ValueError("No viewable media files found")
    sent = 0
    skipped = []
    for path in files:
        size = path.stat().st_size
        if size > MAX_UPLOAD_BYTES:
            skipped.append(f"{path.name} ({size / 1024 / 1024:.1f} MB, limit 50 MB)")
            continue
        suffix = path.suffix.lower()
        if suffix == ".mp4":
            method, field = "sendVideo", "video"
        elif suffix in {".jpg", ".jpeg", ".png"} and size <= MAX_PHOTO_BYTES:
            method, field = "sendPhoto", "photo"
        elif suffix in {".mp3", ".m4a"}:
            method, field = "sendAudio", "audio"
        else:
            method, field = "sendDocument", "document"
        try:
            bot.send_file(chat_id, path, method, field)
        except Exception:
            if method != "sendVideo":
                raise
            bot.send_file(chat_id, path, "sendDocument", "document")
        sent += 1
    return sent, skipped


def run_download(url: str) -> Path:
    validate_url(url)
    day = datetime.now().strftime("%Y-%m-%d")
    inbox = DATA_DIR / "inbox" / day
    inbox.mkdir(parents=True, exist_ok=True)
    temp_root = DATA_DIR / ".tmp"
    temp_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=temp_root) as temp_name:
        temp = Path(temp_name)
        if platform_for(url) == "douyin":
            adapter = Path(__file__).with_name("douyin_adapter.py")
            command = [sys.executable, str(adapter), url, "--download-dir", str(temp)]
        else:
            command = [
            "yt-dlp", "--no-playlist", "--no-progress", "--newline",
            "--write-info-json", "--write-description", "--write-thumbnail",
            "--merge-output-format", "mp4",
            "--output", str(temp / "%(title).120B [%(id)s].%(ext)s"), url,
            ]
        result = subprocess.run(
            command, text=True, capture_output=True, timeout=DOWNLOAD_TIMEOUT,
            env={**os.environ, "TMPDIR": str(temp), "TMP": str(temp), "TEMP": str(temp)},
        )
        media = [path for path in temp.iterdir() if path.is_file() and not path.name.endswith((".json", ".description", ".part", ".ytdl"))]
        if result.returncode or not media:
            message = (result.stderr or result.stdout or "No media file produced").strip()
            raise RuntimeError(message[-1000:])

        info_files = list(temp.glob("*.info.json"))
        info = json.loads(info_files[0].read_text(encoding="utf-8")) if info_files else {}
        title = sanitize(str(info.get("title") or media[0].stem))
        item_dir = inbox / title
        suffix = 2
        while item_dir.exists():
            item_dir = inbox / f"{title} {suffix}"
            suffix += 1
        item_dir.mkdir()
        for path in temp.iterdir():
            if path.is_file() and not path.name.endswith((".part", ".ytdl")):
                shutil.move(str(path), item_dir / path.name)
        (item_dir / "source.url").write_text(url + "\n", encoding="utf-8")
        return item_dir


def move_item(path_text: str, category: str) -> Path:
    source = Path(path_text).resolve()
    if not source.is_relative_to(DATA_DIR) or not source.is_dir():
        raise ValueError("Saved folder is missing or outside the data directory")
    date = source.parent.name if re.fullmatch(r"\d{4}-\d{2}-\d{2}", source.parent.name) else datetime.now().strftime("%Y-%m-%d")
    destination_root = DATA_DIR / sanitize(category, "archive") / date
    destination_root.mkdir(parents=True, exist_ok=True)
    destination = destination_root / source.name
    suffix = 2
    while destination.exists():
        destination = destination_root / f"{source.name} {suffix}"
        suffix += 1
    return Path(shutil.move(str(source), destination))


def data_path(path_text: str) -> Path:
    path = Path(path_text)
    resolved = (path if path.is_absolute() else DATA_DIR / path).resolve()
    if not resolved.is_relative_to(DATA_DIR):
        raise ValueError("Path must stay inside the data directory")
    return resolved


def mcp_download_media(url: str) -> dict[str, str]:
    """Download one public media URL into the archive inbox."""
    # ponytail: serialize downloads for small NAS installs; add a queue if throughput matters.
    with DOWNLOAD_LOCK:
        path = run_download(url)
    return {
        "status": "saved",
        "platform": platform_for(url),
        "path": str(path.relative_to(DATA_DIR)),
    }


def mcp_list_archive(category: str = "", limit: int = 20) -> list[dict[str, str]]:
    """List recently saved archive items, optionally under one category."""
    root = data_path(category) if category else DATA_DIR
    if not root.exists():
        return []
    limit = max(1, min(limit, 100))
    source_files = sorted(
        root.rglob("source.url"), key=lambda item: item.stat().st_mtime, reverse=True
    )[:limit]
    items = []
    for source_file in source_files:
        folder = source_file.parent
        relative = folder.relative_to(DATA_DIR)
        lines = source_file.read_text(encoding="utf-8").splitlines()
        items.append({
            "title": folder.name,
            "category": relative.parts[0] if relative.parts else "",
            "path": str(relative),
            "source_url": lines[0] if lines else "",
        })
    return items


def mcp_archive_media(path: str, category: str) -> dict[str, str]:
    """Move one saved item into a configured archive category."""
    if category not in CATEGORIES:
        raise ValueError(f"Category must be one of: {', '.join(CATEGORIES)}")
    destination = move_item(str(data_path(path)), category)
    return {"status": "archived", "path": str(destination.relative_to(DATA_DIR))}


def create_mcp_server():
    try:
        from mcp.server import MCPServer
    except ImportError as error:
        raise SystemExit("MCP support requires the 'mcp' package") from error

    server = MCPServer(
        "telegram-media-archiver",
        description="Download and organize public media links in a local or NAS archive.",
    )
    server.tool(name="download_media")(mcp_download_media)
    server.tool(name="list_archive")(mcp_list_archive)
    server.tool(name="archive_media")(mcp_archive_media)
    return server


def run_mcp() -> None:
    server = create_mcp_server()

    if MCP_TRANSPORT == "stdio":
        server.run("stdio")
    elif MCP_TRANSPORT == "streamable-http":
        server.run(
            "streamable-http",
            host=MCP_HOST,
            port=MCP_PORT,
            stateless_http=True,
            json_response=True,
        )
    else:
        raise SystemExit("MCP_TRANSPORT must be 'stdio' or 'streamable-http'")


def authorized(user_id: int) -> bool:
    return not ALLOWED_USERS or user_id in ALLOWED_USERS


def handle_url(bot: Telegram, state: dict, chat_id: int, url: str) -> None:
    token = f"{int(time.time() * 1000):x}"[-12:]
    try:
        bot.send(chat_id, f"Downloading {platform_for(url)}…")
        path = run_download(url)
        state[token] = {"url": url, "path": str(path), "status": "saved"}
        save_state(state)
        bot.send(chat_id, f"Saved\n{path.relative_to(DATA_DIR)}", archive_keyboard(token))
    except Exception as error:
        state[token] = {"url": url, "status": "failed"}
        save_state(state)
        bot.send(chat_id, f"Download failed\n{str(error)[-700:]}", retry_keyboard(token))


def handle_update(bot: Telegram, state: dict, update: dict) -> None:
    if "message" in update:
        message = update["message"]
        chat_id = message["chat"]["id"]
        user_id = message.get("from", {}).get("id", 0)
        if not authorized(user_id):
            bot.send(chat_id, "This bot is private.")
            return
        urls = extract_urls(message.get("text") or message.get("caption") or "")
        if not urls:
            bot.send(chat_id, "Send me a supported media URL.")
            return
        # ponytail: one download at a time avoids corrupting small NAS installs; add a queue when throughput matters.
        for url in urls:
            handle_url(bot, state, chat_id, url)
        return

    callback = update.get("callback_query")
    if not callback:
        return
    user_id = callback.get("from", {}).get("id", 0)
    if not authorized(user_id):
        bot.call("answerCallbackQuery", callback_query_id=callback["id"], text="Not allowed")
        return
    chat_id = callback["message"]["chat"]["id"]
    parts = callback.get("data", "").split(":")
    action, token = (parts + ["", ""])[:2]
    task = state.get(token)
    if not task:
        bot.call("answerCallbackQuery", callback_query_id=callback["id"], text="Action expired")
        return
    try:
        if action == "retry":
            bot.call("answerCallbackQuery", callback_query_id=callback["id"], text="Retrying")
            handle_url(bot, state, chat_id, task["url"])
        elif action == "send":
            bot.call("answerCallbackQuery", callback_query_id=callback["id"], text="Sending to chat")
            sent, skipped = send_saved_media(bot, chat_id, task["path"])
            summary = f"Sent {sent} file(s)."
            if skipped:
                summary += "\nToo large for Telegram:\n" + "\n".join(skipped)
            bot.send(chat_id, summary)
        elif action == "move" and len(parts) == 3:
            category = CATEGORIES[int(parts[2])]
            destination = move_item(task["path"], category)
            task.update(path=str(destination), status="archived")
            save_state(state)
            bot.call("answerCallbackQuery", callback_query_id=callback["id"], text=f"Moved to {category}")
            bot.send(chat_id, f"Archived\n{destination.relative_to(DATA_DIR)}")
    except Exception as error:
        bot.call("answerCallbackQuery", callback_query_id=callback["id"], text=str(error)[-150:], show_alert=True)


def main() -> None:
    if not TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN is required")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    bot = Telegram(TOKEN)
    state = load_state()
    offset = 0
    print("Telegram Media Archiver is running", flush=True)
    while True:
        try:
            updates = bot.call("getUpdates", timeout=50, offset=offset, allowed_updates=["message", "callback_query"])
            for update in updates:
                offset = update["update_id"] + 1
                handle_update(bot, state, update)
        except (urllib.error.URLError, TimeoutError, RuntimeError) as error:
            print(f"Telegram error: {error}", flush=True)
            time.sleep(3)


if __name__ == "__main__":
    run_mcp() if sys.argv[1:] == ["mcp"] else main()
