import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app
from douyin_adapter import parse_pace_html, resolve


class CoreTests(unittest.TestCase):
    def test_download_keeps_child_temp_files_on_data_volume(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()

            def download(command, **kwargs):
                temp = Path(kwargs["env"]["TMPDIR"])
                self.assertEqual(temp.parent, root / ".tmp")
                self.assertTrue(temp.is_dir())
                self.assertEqual(kwargs["env"]["TMP"], str(temp))
                self.assertEqual(kwargs["env"]["TEMP"], str(temp))
                self.assertEqual(kwargs["env"]["ARCHIVER_TEST_ENV"], "preserved")
                (temp / "clip.mp4").write_bytes(b"video")
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            with patch.object(app, "DATA_DIR", root), patch("app.validate_url"), \
                    patch.dict("app.os.environ", {"ARCHIVER_TEST_ENV": "preserved"}), \
                    patch("app.subprocess.run", side_effect=download):
                folder = app.run_download("https://www.douyin.com/video/123")
            self.assertEqual((folder / "clip.mp4").read_bytes(), b"video")
            self.assertEqual(list((root / ".tmp").iterdir()), [])

    def test_douyin_pace_parser_checks_id_and_preserves_live_photo(self):
        detail = {
            "awemeId": "123", "desc": "caption", "authorInfo": {"nickname": "author"},
            "images": [{"urlList": ["https://img/1.webp", "https://img/1.jpeg"],
                        "video": {"playAddr": [{"src": "https://video/1.mp4"}]}}],
        }
        summary = {"awemeId": "123", "desc": "", "images": [{"urlList": ["https://img/1.webp"]}]}
        payload = ["$", "$L", None, {"awemeId": "123", "aweme": {"detail": summary},
                                      "full": {"awemeId": "123", "aweme": {"detail": detail}}}]
        chunk = "7:" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        script = f"self.__pace_f.push([1,{json.dumps(chunk)}])"
        result = parse_pace_html(f"<script>{script}</script>", "123")
        self.assertEqual(result["author"], "author")
        self.assertEqual(result["images"][0]["url"], "https://img/1.jpeg")
        self.assertEqual(result["images"][0]["live_url"], "https://video/1.mp4")
        with self.assertRaisesRegex(ValueError, "did not match"):
            parse_pace_html(f"<script>{script}</script>", "456")

    def test_douyin_parser_uses_verified_rendered_video_when_pace_has_no_aweme(self):
        html = """
        <html><head>
          <title>Rendered caption - 抖音</title>
          <link rel="canonical" href="https://www.douyin.com/video/123">
        </head><body><video><source src="https://video/123.mp4?a=1&amp;b=2"></video></body></html>
        """
        result = parse_pace_html(html, "123")
        self.assertEqual(result["type"], "video")
        self.assertEqual(result["caption"], "Rendered caption")
        self.assertEqual(result["url"], "https://video/123.mp4?a=1&b=2")
        with self.assertRaisesRegex(ValueError, "did not match"):
            parse_pace_html(html, "456")

    def test_douyin_resolver_retries_with_a_fresh_browser(self):
        first_page = MagicMock()
        first_page.goto.side_effect = RuntimeError("transient load failure")
        second_page = MagicMock(url="https://www.douyin.com/video/123")
        second_page.content.return_value = "<html></html>"
        second_page.evaluate.return_value = ""
        second_page.title.return_value = "caption - 抖音"
        second_page.on.side_effect = lambda event, callback: callback(
            SimpleNamespace(url="https://video.douyinvod.com/file.mp4?__vid=123")
        )
        browsers = []
        for page in (first_page, second_page):
            browser = MagicMock()
            browser.new_page.return_value = page
            browsers.append(browser)
        chromium = MagicMock()
        chromium.launch.side_effect = browsers
        context = MagicMock()
        context.__enter__.return_value = SimpleNamespace(chromium=chromium)
        sync_api = MagicMock()
        sync_api.sync_playwright.return_value = context
        with patch.dict("sys.modules", {"playwright": MagicMock(), "playwright.sync_api": sync_api}):
            self.assertEqual(resolve("https://v.douyin.com/test/")["url"],
                             "https://video.douyinvod.com/file.mp4?__vid=123")
        self.assertEqual(chromium.launch.call_count, 2)

    def test_extract_and_classify(self):
        self.assertEqual(
            app.extract_urls("one https://youtu.be/abc, again https://youtu.be/abc"),
            ["https://youtu.be/abc"],
        )
        self.assertEqual(app.platform_for("https://m.youtube.com/watch?v=1"), "youtube")

    def test_sanitize(self):
        self.assertEqual(app.sanitize('../bad: name?.mp4'), 'bad name.mp4')

    def test_private_url_is_blocked(self):
        with patch("app.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 443))]):
            with self.assertRaisesRegex(ValueError, "Private"):
                app.validate_url("http://localhost/admin")

    def test_move_stays_in_data_dir(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "inbox" / "2026-08-10" / "clip"
            source.mkdir(parents=True)
            with patch.object(app, "DATA_DIR", root):
                moved = app.move_item(str(source), "reference")
            self.assertEqual(moved, root / "reference" / "2026-08-10" / "clip")

    def test_mcp_archive_helpers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            item = root / "inbox" / "2026-08-10" / "Example"
            item.mkdir(parents=True)
            (item / "source.url").write_text("https://example.com/video\n", encoding="utf-8")

            with patch.object(app, "DATA_DIR", root):
                listed = app.mcp_list_archive()
                self.assertEqual(listed[0]["path"], "inbox/2026-08-10/Example")
                moved = app.mcp_archive_media(listed[0]["path"], "favorites")
                self.assertEqual(moved["path"], "favorites/2026-08-10/Example")
                with self.assertRaises(ValueError):
                    app.mcp_archive_media(moved["path"], "private-local-category")

    def test_send_button_and_media_selection(self):
        self.assertEqual(app.archive_keyboard("abc")[0][0]["callback_data"], "send:abc")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            folder = root / "inbox" / "2026-08-10" / "clip"
            folder.mkdir(parents=True)
            video = folder / "clip.mp4"
            video.touch()
            (folder / "thumbnail.webp").touch()
            with patch.object(app, "DATA_DIR", root):
                self.assertEqual(app.media_files(str(folder)), [video])

    def test_images_are_sent_when_no_video_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            folder = root / "inbox" / "2026-08-10" / "post"
            folder.mkdir(parents=True)
            first = folder / "1.jpg"
            second = folder / "2.png"
            first.touch()
            second.touch()
            with patch.object(app, "DATA_DIR", root):
                self.assertEqual(app.media_files(str(folder)), [first, second])

    def test_rejected_streaming_video_falls_back_to_document(self):
        class FakeBot:
            def __init__(self):
                self.calls = []

            def send_file(self, chat_id, path, method, field):
                self.calls.append((method, field))
                if method == "sendVideo":
                    raise RuntimeError("unsupported codec")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            folder = root / "inbox" / "2026-08-10" / "clip"
            folder.mkdir(parents=True)
            (folder / "clip.mp4").write_bytes(b"video")
            bot = FakeBot()
            with patch.object(app, "DATA_DIR", root):
                sent, skipped = app.send_saved_media(bot, 1, str(folder))
            self.assertEqual((sent, skipped), (1, []))
            self.assertEqual(bot.calls, [("sendVideo", "video"), ("sendDocument", "document")])


if __name__ == "__main__":
    unittest.main()
