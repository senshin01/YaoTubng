from pathlib import Path

import pytest

from yaotubng.core import AppError, Auth, error_message, normalize_url, publish_file, safe_filename, validate_format


@pytest.mark.parametrize("url", [
    "https://music.youtube.com/watch?v=BaW_jenozKc&list=PL123",
    "https://youtu.be/BaW_jenozKc?si=anything",
    "https://www.youtube.com/shorts/BaW_jenozKc",
])
def test_url_is_single_video(url):
    assert normalize_url(url) == "https://www.youtube.com/watch?v=BaW_jenozKc"


@pytest.mark.parametrize("url", [
    "http://youtube.com/watch?v=BaW_jenozKc", "https://evil.example/watch?v=BaW_jenozKc",
    "https://youtube.com.evil.example/watch?v=BaW_jenozKc",
    "https://user:password@youtube.com/watch?v=BaW_jenozKc",
    "file:///etc/passwd", "https://www.youtube.com/playlist?list=abc",
    "https://youtube.com:invalid/watch?v=BaW_jenozKc", "--exec calc.exe",
])
def test_unsafe_urls_rejected(url):
    with pytest.raises(AppError):
        normalize_url(url)


def test_windows_filename_and_path_traversal():
    name = safe_filename('../CON:<song>\\foo?*\x00. ', 'BaW_jenozKc', 'm4a')
    assert '/' not in name and '\\' not in name and ':' not in name
    assert name.endswith('[BaW_jenozKc].m4a')
    assert safe_filename('CON', 'BaW_jenozKc', 'webm').startswith('_CON')
    assert len(safe_filename('曲' * 500, 'BaW_jenozKc', 'm4a')) < 100
    with pytest.raises(AppError):
        safe_filename('song', '../bad', 'm4a')


def test_atomic_save_preserves_existing_and_symlink_targets(tmp_path):
    source = tmp_path / 'source.m4a'
    source.write_bytes(b'complete audio')
    target = publish_file(source, tmp_path, 'song.m4a')
    assert target.read_bytes() == b'complete audio'
    source.unlink()
    assert target.read_bytes() == b'complete audio'
    source.write_bytes(b'new audio')
    with pytest.raises(AppError, match='上書き'):
        publish_file(source, tmp_path, 'song.m4a')
    assert target.read_bytes() == b'complete audio'
    link = tmp_path / 'link.m4a'
    try:
        link.symlink_to(target)
    except OSError:
        return  # Windows without symlink privilege; overwrite case still tested.
    with pytest.raises(AppError):
        publish_file(source, tmp_path, link.name)
    assert target.read_bytes() == b'complete audio'


def test_incomplete_file_and_directory_escape_rejected(tmp_path):
    source = tmp_path / 'empty.m4a'
    source.touch()
    with pytest.raises(AppError):
        publish_file(source, tmp_path, 'empty-final.m4a')
    source.write_bytes(b'audio')
    with pytest.raises(AppError):
        publish_file(source, tmp_path, '../escape.m4a')


@pytest.mark.parametrize('value', ['best; calc', '140/bestvideo', '../secret', ''])
def test_format_selector_cannot_be_injected(value):
    with pytest.raises(AppError):
        validate_format(value)


def test_error_does_not_expose_cookie_or_stream_url():
    message = error_message(RuntimeError('403 Cookie=SECRET https://stream.example/?token=PRIVATE'))
    assert 'SECRET' not in message and 'PRIVATE' not in message and 'stream.example' not in message
    assert '停止' in error_message(RuntimeError('HTTP 429 Too Many Requests'))


def test_auth_missing_file(tmp_path):
    with pytest.raises(AppError):
        Auth('file', str(tmp_path / 'missing.txt')).validate()
