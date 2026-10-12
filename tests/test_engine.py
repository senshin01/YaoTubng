from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import hashlib
import io
import json
import subprocess
import sys
import threading
import wave

import pytest
from yt_dlp import YoutubeDL

from yaotubng.core import AppError, Auth
from yaotubng.engine import audio_formats, download, inspect, options


def test_only_audio_formats_and_no_private_data():
    result = audio_formats({'formats': [
        {'format_id': '140', 'vcodec': 'none', 'acodec': 'aac', 'ext': 'm4a', 'url': 'SECRET', 'http_headers': {'Cookie': 'PRIVATE'}},
        {'format_id': '137', 'vcodec': 'avc1', 'acodec': 'none'},
        {'format_id': '18', 'vcodec': 'avc1', 'acodec': 'aac'},
        {'format_id': 'drm', 'vcodec': 'none', 'acodec': 'aac', 'has_drm': True},
    ]})
    assert [f['id'] for f in result] == ['140']
    assert 'SECRET' not in json.dumps(result) and 'PRIVATE' not in json.dumps(result)


def test_cookie_copy_is_cleaned_and_original_unchanged(tmp_path):
    original = tmp_path / 'my-cookies.txt'
    original.write_text('# Netscape HTTP Cookie File\n')
    with options(Auth('file', str(original)), tmp_path) as opts:
        copied = Path(opts['cookiefile'])
        assert copied != original and copied.read_bytes() == original.read_bytes()
        copied.write_text('modified by engine')
        assert opts['retries'] == opts['fragment_retries'] == 0
        assert opts['concurrent_fragment_downloads'] == 1
        assert opts['cachedir'] is False
    assert not copied.exists()
    assert original.read_text() == '# Netscape HTTP Cookie File\n'


def test_inspect_emits_only_metadata(tmp_path):
    class FakeYDL:
        def __init__(self, opts):
            assert opts['noplaylist'] is True
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def extract_info(self, url, download):
            assert download is False and '&list=' not in url
            return {'id': 'BaW_jenozKc', 'title': '曲', 'formats': [
                {'format_id': '140', 'vcodec': 'none', 'acodec': 'aac', 'url': 'PRIVATE'}]}
    result = inspect('https://music.youtube.com/watch?v=BaW_jenozKc&list=PL', Auth(), lambda _: None, FakeYDL, tmp_path)
    assert result['title'] == '曲' and result['authenticated'] is False
    assert 'PRIVATE' not in json.dumps(result)


@contextmanager
def audio_server():
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8000)
        stream.writeframes(b'\x00\x00' * 8000)
    body = buffer.getvalue()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Type', 'audio/wav')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *_):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/audio.wav', body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_real_ytdlp_download_and_no_overwrite(tmp_path):
    stage = tmp_path / '.yaotubng-test'
    stage.mkdir()
    events = []
    with audio_server() as (stream_url, expected):
        class FixtureYDL(YoutubeDL):
            # Substitute only YouTube extraction. Transfer and postprocessing use real yt-dlp.
            def extract_info(self, url, download=True, **kwargs):
                return self.process_ie_result({
                    'id': 'BaW_jenozKc', 'title': '試作テスト', 'extractor': 'fixture',
                    'extractor_key': 'Fixture', 'webpage_url': url,
                    'formats': [{'format_id': 'test', 'url': stream_url, 'ext': 'wav',
                                 'acodec': 'pcm_s16le', 'vcodec': 'none'}],
                }, download=download)
        result = download('https://youtube.com/watch?v=BaW_jenozKc', Auth(), 'best', str(tmp_path), str(stage), events.append, FixtureYDL)
        actual = Path(result['path']).read_bytes()
        assert hashlib.sha256(actual).digest() == hashlib.sha256(expected).digest()
        assert any(event['type'] == 'progress' for event in events)
        assert result['type'] == 'complete'
        with pytest.raises(AppError, match='上書き'):
            download('https://youtube.com/watch?v=BaW_jenozKc', Auth(), 'test', str(tmp_path), str(stage), events.append, FixtureYDL)
        assert Path(result['path']).read_bytes() == expected


def test_worker_invalid_url_returns_failure_without_private_details(tmp_path):
    payload = {'action': 'inspect', 'url': 'https://attacker.example/?token=SECRET', 'stage': str(tmp_path)}
    result = subprocess.run([sys.executable, '-m', 'yaotubng.worker'], input=json.dumps(payload) + '\n', capture_output=True, text=True, timeout=10)
    assert result.returncode == 1
    event = json.loads(result.stdout)
    assert event['type'] == 'error' and 'SECRET' not in result.stdout
