import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
import twitter_adapter as x


class TwitterTests(unittest.TestCase):
    def payload(self, items):
        return {'code': 200, 'tweet': {'id': '123', 'text': 'caption', 'media': {'all': items}}}

    def test_links(self):
        for url in ('https://x.com/u/status/123/photo/1?s=20',
                    'https://mobile.twitter.com/u/status/123', 'https://x.com/i/web/status/123'):
            self.assertEqual(x.post_id(url), '123')
        for url in ('https://x.com/u', 'https://x.com.evil/u/status/123'):
            with self.assertRaises(ValueError):
                x.post_id(url)

    def test_mixed_media_and_best_video(self):
        _, files = x.parse_media(self.payload([
            {'type': 'photo', 'url': 'https://pbs.twimg.com/media/a?format=jpg&name=small'},
            {'type': 'video', 'url': 'https://video.twimg.com/default.mp4', 'formats': [
                {'container': 'mp4', 'bitrate': 1, 'url': 'https://video.twimg.com/low.mp4'},
                {'container': 'mp4', 'bitrate': 2, 'url': 'https://video.twimg.com/high.mp4'}]},
            {'type': 'gif', 'url': 'https://video.twimg.com/loop.mp4'},
        ]), '123')
        self.assertEqual(files, [('https://pbs.twimg.com/media/a?format=jpg&name=orig', 'jpg'),
                                 ('https://video.twimg.com/high.mp4', 'mp4'),
                                 ('https://video.twimg.com/loop.mp4', 'mp4')])

    def test_invalid_responses(self):
        for payload in (self.payload([]), {'code': 404}, self.payload([
                {'type': 'photo', 'url': 'https://127.0.0.1/secret.jpg'}])):
            with self.assertRaises(ValueError):
                x.parse_media(payload, '123')
        with self.assertRaises(ValueError):
            x.parse_media(self.payload([{'type': 'photo', 'url': 'https://pbs.twimg.com/a.jpg'}]), '456')
        for url in ('https://twimg.com.evil/a.jpg', 'http://pbs.twimg.com/a.jpg',
                    'https://pbs.twimg.com:8080/a.jpg'):
            with self.assertRaises(ValueError):
                x.media_url(url)

    def test_download_and_archive_all_photos(self):
        payload = self.payload([{'type': 'photo', 'url': f'https://pbs.twimg.com/{i}.jpg'} for i in range(4)])
        def response(url):
            result = io.BytesIO(json.dumps(payload).encode() if 'api.fxtwitter' in url else b'image')
            result.headers = {'Content-Type': 'image/jpeg'}
            return result
        with tempfile.TemporaryDirectory() as folder, patch.object(x, 'open_url', side_effect=response):
            x.download('https://x.com/u/status/123', folder)
            self.assertEqual(len(list(Path(folder).glob('*.jpg'))), 4)
            self.assertFalse(list(Path(folder).glob('*.part')))

    def test_retry_lookup_and_media_body(self):
        payload = self.payload([{'type': 'photo', 'url': 'https://pbs.twimg.com/a.jpg'}])
        def response(data, headers):
            result = io.BytesIO(data)
            result.headers = headers
            return result
        replies = [
            TimeoutError('lookup timeout'),
            response(json.dumps(payload).encode(), {}),
            response(b'short', {'Content-Type': 'image/jpeg', 'Content-Length': '8'}),
            response(b'complete', {'Content-Type': 'image/jpeg', 'Content-Length': '8'}),
        ]
        with tempfile.TemporaryDirectory() as folder, patch.object(x, 'open_url', side_effect=replies), \
                patch.object(x.time, 'sleep'):
            x.download('https://x.com/u/status/123', folder)
            self.assertEqual((Path(folder) / '123_01.jpg').read_bytes(), b'complete')
            self.assertFalse(list(Path(folder).glob('*.part')))

    def test_transient_http_retry_and_permanent_http_stop(self):
        for code, attempts in ((429, 3), (503, 3), (403, 1), (404, 1)):
            with self.subTest(code=code), patch.object(x, 'open_url', side_effect=lambda _: self.raise_http(code)) as request, patch.object(x.time, 'sleep'), \
                    self.assertRaisesRegex(RuntimeError, 'Post lookup failed'):
                x.fetch('https://api.fxtwitter.com/i/status/123')
            self.assertEqual(request.call_count, attempts)

    @staticmethod
    def raise_http(code):
        import urllib.error
        raise urllib.error.HTTPError('https://api.fxtwitter.com', code, 'failure', {}, None)

    def test_exhausted_media_retry_does_not_finalize(self):
        payload = self.payload([{'type': 'photo', 'url': 'https://pbs.twimg.com/a.jpg'}])
        def response(url):
            if 'api.fxtwitter' not in url:
                raise ConnectionResetError('interrupted')
            result = io.BytesIO(json.dumps(payload).encode())
            result.headers = {}
            return result
        with tempfile.TemporaryDirectory() as folder, patch.object(x, 'open_url', side_effect=response), \
                patch.object(x.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'Media download failed after 3'):
                x.download('https://x.com/u/status/123', folder)
            self.assertFalse(list(Path(folder).glob('*.jpg')))

    def test_app_dispatch(self):
        from types import SimpleNamespace
        def run(command, **kwargs):
            self.assertTrue(command[1].endswith('twitter_adapter.py'))
            (Path(command[-1]) / '123_01.jpg').write_bytes(b'image')
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        with tempfile.TemporaryDirectory() as folder, patch.object(app, 'DATA_DIR', Path(folder)), \
                patch.object(app, 'validate_url'), patch.object(app.subprocess, 'run', side_effect=run):
            result = app.run_download('https://x.com/u/status/123')
            self.assertTrue((result / '123_01.jpg').exists())


if __name__ == '__main__':
    unittest.main()
