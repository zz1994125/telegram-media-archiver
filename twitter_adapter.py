"""Download public X posts through the FxTwitter media API, without cookies."""

import argparse
import http.client
import json
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Unexpected redirect from media service")


def open_url(url):
    return urllib.request.build_opener(NoRedirect()).open(
        urllib.request.Request(url, headers={"User-Agent": "TelegramMediaArchiver/1.0"}),
        timeout=45,
    )


def curl_media(url, target):
    # Some local TLS routes silently truncate urllib responses; curl checks transfer length.
    result = subprocess.run([
        "curl", "--http1.1", "--silent", "--show-error", "--fail",
        "--proto", "=https", "--retry", "2", "--retry-all-errors",
        "--retry-delay", "1", "--connect-timeout", "20", "--max-time", "45",
        "--retry-max-time", "90", "--output", str(target),
        "--write-out", "%{http_code} %{content_type}", url,
    ], capture_output=True, text=True, timeout=140)
    status, _, content_type = result.stdout.strip().partition(" ")
    if result.returncode or status != "200":
        raise RuntimeError(f"Media download failed: curl exit {result.returncode}, HTTP {status}")
    if not content_type.startswith(("image/", "video/", "application/octet-stream")):
        raise ValueError("Media service returned a non-media response")
    if not target.is_file() or not target.stat().st_size:
        raise ValueError("Empty media file")


def fetch(url, target=None):
    """Retry the complete request, including interrupted response bodies."""
    stage = "Media download" if target is not None else "Post lookup"
    for attempt in range(3):
        try:
            with open_url(url) as response:
                if target is None:
                    return json.load(response)
                content_type = response.headers.get("Content-Type", "").split(";")[0]
                if not content_type.startswith(("image/", "video/", "application/octet-stream")):
                    raise ValueError("Media service returned a non-media response")
                with target.open("wb") as output:
                    shutil.copyfileobj(response, output)
                size = target.stat().st_size
                expected = response.headers.get("Content-Length")
                if not size or (expected is not None and size != int(expected)):
                    raise http.client.IncompleteRead(b"", int(expected or 1))
                return
        except (urllib.error.URLError, TimeoutError, ConnectionError,
                http.client.IncompleteRead, json.JSONDecodeError) as error:
            if isinstance(error, urllib.error.HTTPError):
                error.close()
                if error.code not in {408, 429, 500, 502, 503, 504}:
                    raise RuntimeError(f"{stage} failed: HTTP {error.code}") from error
            if target is not None and isinstance(error, http.client.IncompleteRead):
                return curl_media(url, target)
            if attempt == 2:
                if target is not None:
                    return curl_media(url, target)
                raise RuntimeError(f"{stage} failed after 3 attempts: {error}") from error
            time.sleep(attempt + 1)


def post_id(url):
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not any(
        host == domain or host.endswith("." + domain) for domain in ("x.com", "twitter.com")
    ):
        raise ValueError("Expected an X / Twitter post URL")
    match = re.fullmatch(r"/(?:[^/]+/status|i/web/status)/(\d+)(?:/(?:photo|video)/\d+)?/?", parsed.path)
    if not match:
        raise ValueError("Please send a post link, not a profile or timeline")
    return match[1]


def media_url(url):
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    if (parsed.scheme != "https" or parsed.username or parsed.password
            or parsed.port not in (None, 443)
            or not (host == "twimg.com" or host.endswith(".twimg.com"))):
        raise ValueError("Unexpected X media host")
    return url


def parse_media(payload, expected_id):
    tweet = payload.get("tweet") or payload.get("status") or {}
    if payload.get("code") != 200 or str(tweet.get("id")) != expected_id:
        raise ValueError("Post unavailable or media response did not match the requested post")
    media = tweet.get("media") or {}
    items = media.get("all") or (media.get("photos", []) + media.get("videos", []))
    downloads = []
    for item in items:
        kind = item.get("type")
        if kind == "photo":
            parsed = urllib.parse.urlparse(media_url(item["url"]))
            query = dict(urllib.parse.parse_qsl(parsed.query))
            ext = query.get("format") or Path(parsed.path).suffix.lstrip(".") or "jpg"
            if ext.lower() not in {"jpg", "jpeg", "png", "webp"}:
                raise ValueError("Unsupported photo format")
            query["name"] = "orig"
            url = urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query)))
        elif kind in {"video", "gif"}:
            variants = [v for v in item.get("formats", [])
                        if v.get("container") == "mp4" or urllib.parse.urlparse(v.get("url", "")).path.endswith(".mp4")]
            best = max(variants, key=lambda v: v.get("bitrate") or 0) if variants else item
            url, ext = media_url(best["url"]), "mp4"
        else:
            raise ValueError("Unsupported media type in this post")
        downloads.append((media_url(url), ext))
    if not downloads:
        raise ValueError("This post has no downloadable photos or videos")
    return tweet, downloads


def download(url, directory):
    identifier = post_id(url)
    payload = fetch(f"https://api.fxtwitter.com/i/status/{identifier}")
    tweet, downloads = parse_media(payload, identifier)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for index, (source, ext) in enumerate(downloads, 1):
        target = directory / f"{identifier}_{index:02d}.{ext}"
        partial = target.with_suffix(target.suffix + ".part")
        fetch(source, partial)
        partial.replace(target)
    title = (tweet.get("text") or f"X {identifier}").strip()
    (directory / f"{identifier}.info.json").write_text(
        json.dumps({"id": identifier, "title": title, "webpage_url": url}, ensure_ascii=False), encoding="utf-8")
    (directory / f"{identifier}.description").write_text(title, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--download-dir", required=True)
    args = parser.parse_args()
    download(args.url, args.download_dir)
