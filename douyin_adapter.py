#!/usr/bin/env python3
"""Resolve public Douyin video, image, and live-photo posts with Playwright."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path


class _Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.current = None
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.current = []

    def handle_data(self, data):
        if self.current is not None:
            self.current.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.current is not None:
            self.scripts.append("".join(self.current))
            self.current = None


class _RenderedVideo(HTMLParser):
    def __init__(self):
        super().__init__()
        self.canonical = ""
        self.in_title = False
        self.in_video = False
        self.title = []
        self.sources = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "link" and "canonical" in attrs.get("rel", "").split():
            self.canonical = attrs.get("href", "")
        elif tag == "title":
            self.in_title = True
        elif tag == "video":
            self.in_video = True
            if source := _src(attrs.get("src")):
                self.sources.append(source)
        elif tag == "source" and self.in_video:
            if source := _src(attrs.get("src")):
                self.sources.append(source)

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        elif tag == "video":
            self.in_video = False


def _src(value) -> str:
    if isinstance(value, str):
        return value if value.startswith(("http://", "https://")) else ""
    if isinstance(value, dict):
        for key in ("src", "url"):
            if result := _src(value.get(key)):
                return result
    if isinstance(value, list):
        for item in value:
            if result := _src(item):
                return result
    return ""


def _image_src(value) -> str:
    urls = value if isinstance(value, list) else []
    return next((url for url in urls if isinstance(url, str) and "jpeg" in url), "") or _src(urls)


def _find_details(value, expected_id: str):
    results = []
    if isinstance(value, dict):
        aweme = value.get("aweme") or {}
        detail = aweme.get("detail") if isinstance(aweme, dict) else None
        if str(value.get("awemeId", "")) == expected_id and isinstance(detail, dict):
            results.append(detail)
        for child in value.values():
            results.extend(_find_details(child, expected_id))
    elif isinstance(value, list):
        for child in value:
            results.extend(_find_details(child, expected_id))
    return results


def parse_pace_html(html: str, expected_id: str) -> dict:
    parser = _Scripts()
    parser.feed(html)
    details = []
    for script in parser.scripts:
        match = re.fullmatch(r"\s*self\.__pace_f\.push\(\[1,(.*)\]\)\s*;?\s*", script, re.S)
        if not match:
            continue
        try:
            chunk = json.loads(match.group(1))
            payload = json.loads(chunk.split(":", 1)[1])
        except (json.JSONDecodeError, IndexError, AttributeError):
            continue
        details.extend(_find_details(payload, expected_id))

    def media_score(detail):
        images = detail.get("images") or []
        return len(images) + sum(bool(_src((image.get("video") or {}).get("playAddr"))) for image in images)

    detail = max(details, key=media_score) if details else None

    if not detail:
        rendered = _RenderedVideo()
        rendered.feed(html)
        if not re.search(rf"/(?:video|note)/{re.escape(expected_id)}(?:\D|$)", rendered.canonical):
            raise ValueError(f"page data did not match Douyin work {expected_id}")
        video_url = next((source for source in rendered.sources if ".mp3" not in source), "")
        if not video_url:
            raise ValueError("page data contained no downloadable media")
        caption = "".join(rendered.title).removesuffix(" - 抖音").strip() or f"douyin_{expected_id}"
        return {"status": "success", "type": "video", "video_id": expected_id,
                "title": caption, "caption": caption, "author": "", "url": video_url}

    if str(detail.get("awemeId", "")) != expected_id:
        raise ValueError(f"page data did not match Douyin work {expected_id}")

    caption = detail.get("desc") or detail.get("itemTitle") or detail.get("caption") or f"douyin_{expected_id}"
    author = (detail.get("authorInfo") or {}).get("nickname", "")
    images = []
    for image in detail.get("images") or []:
        url = _image_src(image.get("urlList"))
        if not url:
            continue
        item = {"url": url, "width": image.get("width"), "height": image.get("height")}
        if live_url := _src((image.get("video") or {}).get("playAddr")):
            item["live_url"] = live_url
        images.append(item)

    if images:
        return {"status": "success", "type": "image", "note_id": expected_id,
                "title": caption, "caption": caption, "author": author, "images": images}

    video_url = _src((detail.get("video") or {}).get("playAddr"))
    if not video_url or ".mp3" in video_url:
        raise ValueError("page data contained no downloadable media")
    return {"status": "success", "type": "video", "video_id": expected_id,
            "title": caption, "caption": caption, "author": author, "url": video_url}


def resolve(url: str) -> dict:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        for attempt in range(2):
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            media_urls = []
            page.on("response", lambda response: media_urls.append(response.url)
                    if "douyinvod" in response.url or "/aweme/v1/play/" in response.url else None)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_selector("script", state="attached", timeout=30_000)
                page.wait_for_timeout(3_000)
                match = re.search(r"/(?:note|video)/(\d+)", page.url)
                if not match:
                    raise ValueError(f"unexpected Douyin destination: {page.url}")
                try:
                    return parse_pace_html(page.content(), match.group(1))
                except ValueError as error:
                    if "/video/" not in page.url:
                        raise error
                    video_url = ""
                    for _ in range(45):
                        video_url = next((candidate for candidate in media_urls
                                          if re.search(rf"[?&]__vid={re.escape(match.group(1))}(?:&|$)", candidate)), "")
                        if not video_url:
                            video_url = page.evaluate("""() => {
                            const element = document.querySelector("[data-e2e='player-container'] video")
                                || document.querySelector("video");
                            if (!element) return '';
                            const url = [...element.querySelectorAll('source')].map(source => source.src)
                                .find(value => value.startsWith('http')) || element.currentSrc || element.src;
                            return url.startsWith('http') ? url : '';
                        }""")
                        if _src(video_url):
                            break
                        page.wait_for_timeout(1_000)
                    if not _src(video_url) or ".mp3" in video_url:
                        raise error
                    caption = page.title().removesuffix(" - 抖音").strip() or f"douyin_{match.group(1)}"
                    return {"status": "success", "type": "video", "video_id": match.group(1),
                            "title": caption, "caption": caption, "author": "", "url": video_url}
            except Exception:
                if attempt == 1:
                    raise
            finally:
                browser.close()


def download(result: dict, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)

    def fetch(url: str, path: Path) -> None:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.douyin.com/"})
        with urllib.request.urlopen(request, timeout=120) as response, path.open("wb") as output:
            shutil.copyfileobj(response, output)

    if result["type"] == "video":
        fetch(result["url"], destination / "video.mp4")
    else:
        for index, image in enumerate(result["images"], 1):
            source_image = destination / f".image_{index:02d}.source"
            target_image = destination / f"image_{index:02d}.jpg"
            fetch(image["url"], source_image)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", source_image, target_image], check=True)
            source_image.unlink()
            if live_url := image.get("live_url"):
                source = destination / f".live_{index:02d}.mp4"
                target = destination / f"live_{index:02d}.mov"
                fetch(live_url, source)
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", source, "-c", "copy", target], check=True)
                source.unlink()
    (destination / "description.txt").write_text(
        f"Author: {result.get('author', '')}\n\n{result.get('caption', '')}\n", encoding="utf-8"
    )
    (destination / "douyin.info.json").write_text(
        json.dumps({"id": result.get("note_id") or result.get("video_id"),
                    "title": result.get("caption"), "uploader": result.get("author")}, ensure_ascii=False),
        encoding="utf-8",
    )


def main() -> None:
    try:
        result = resolve(sys.argv[1])
        if len(sys.argv) == 4 and sys.argv[2] == "--download-dir":
            download(result, Path(sys.argv[3]))
        print(json.dumps(result, ensure_ascii=False))
    except Exception as error:
        print(json.dumps({"status": "error", "error": str(error)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
