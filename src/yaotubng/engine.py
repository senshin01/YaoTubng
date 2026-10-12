"""yt-dlp integration. Authentication lives only inside this local process."""

from contextlib import contextmanager
from pathlib import Path
import shutil
import tempfile
import time
from typing import Callable

from .core import AppError, Auth, normalize_url, publish_file, safe_filename, validate_format

Emit = Callable[[dict], None]


class QuietLogger:
    def debug(self, message):
        pass

    def warning(self, message):
        pass

    def error(self, message):
        pass


@contextmanager
def options(auth: Auth, scratch: str | Path | None = None):
    auth.validate()
    with tempfile.TemporaryDirectory(prefix="auth-", dir=scratch) as temporary:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "logger": QuietLogger(),
            "noplaylist": True,
            "cachedir": False,
            "socket_timeout": 20,
            "retries": 0,
            "fragment_retries": 0,
            "extractor_retries": 0,
            "concurrent_fragment_downloads": 1,
            "sleep_interval_requests": 2,
            "sleep_interval": 3,
            "max_sleep_interval": 3,
            "overwrites": False,
            "windowsfilenames": True,
        }
        node = shutil.which("node")
        deno = shutil.which("deno")
        if deno:
            opts["js_runtimes"] = {"deno": {"path": deno}}
        elif node:
            opts["js_runtimes"] = {"node": {"path": node}}
        if auth.mode == "file":
            # yt-dlp may update its cookie jar. Preserve the user's original file.
            local_cookie = Path(temporary) / "cookies.txt"
            shutil.copyfile(auth.cookie_file, local_cookie)
            local_cookie.chmod(0o600)
            opts["cookiefile"] = str(local_cookie)
        elif auth.mode != "none":
            opts["cookiesfrombrowser"] = (auth.mode,)
        yield opts


def audio_formats(info: dict) -> list[dict]:
    result = []
    for fmt in info.get("formats", []):
        if fmt.get("vcodec") != "none" or fmt.get("acodec") in (None, "none") or fmt.get("has_drm"):
            continue
        identifier = str(fmt.get("format_id", ""))
        try:
            validate_format(identifier)
        except AppError:
            continue
        # Deliberately omit stream URLs, request headers, and cookies.
        result.append({
            "id": identifier,
            "ext": fmt.get("ext"),
            "codec": fmt.get("acodec"),
            "abr": fmt.get("abr"),
            "sample_rate": fmt.get("asr"),
            "size": fmt.get("filesize") or fmt.get("filesize_approx"),
            "note": fmt.get("format_note") or "",
        })
    return result


def inspect(url: str, auth: Auth, emit: Emit, factory=None, scratch=None) -> dict:
    from yt_dlp import YoutubeDL

    url = normalize_url(url)
    with options(auth, scratch) as opts, (factory or YoutubeDL)(opts) as ydl:
        emit({"type": "status", "message": "音声形式を確認しています…"})
        info = ydl.extract_info(url, download=False)
        formats = audio_formats(info)
        if not formats:
            raise AppError("取得可能な音声専用形式がありません。認証や yt-dlp の対応状況を確認してください。")
        return {"type": "inspection", "id": info["id"], "title": info.get("title", "audio"),
                "duration": info.get("duration"), "formats": formats, "authenticated": auth.mode != "none"}


def download(url: str, auth: Auth, format_id: str, destination: str, stage: str, emit: Emit, factory=None) -> dict:
    from yt_dlp import YoutubeDL

    url = normalize_url(url)
    validate_format(format_id)
    directory = Path(destination).resolve(strict=True)
    staging = Path(stage).resolve(strict=True)
    if not directory.is_dir() or not staging.is_dir() or staging.parent != directory or not staging.name.startswith(".yaotubng-"):
        raise AppError("保存先または一時フォルダーが不正です。")
    if not shutil.which("ffmpeg"):
        raise AppError("FFmpeg が見つかりません。インストール後にアプリを再起動してください。")
    last_emit = 0.0

    def progress(data):
        nonlocal last_emit
        now = time.monotonic()
        if data["status"] == "downloading" and now - last_emit >= 0.2:
            last_emit = now
            emit({"type": "progress", "downloaded": data.get("downloaded_bytes", 0),
                  "total": data.get("total_bytes") or data.get("total_bytes_estimate"),
                  "speed": data.get("speed"), "eta": data.get("eta")})
        elif data["status"] == "finished":
            emit({"type": "status", "message": "音声ファイルを確認しています…"})

    with options(auth, staging) as opts:
        opts.update({
            "format": "bestaudio[vcodec=none]" if format_id == "best" else f"{format_id}[vcodec=none][acodec!=none]",
            "outtmpl": str(staging / "audio.%(ext)s"),
            "progress_hooks": [progress],
            # No lossy conversion, metadata sidecars, or thumbnail downloads.
            "postprocessors": [],
        })
        emit({"type": "status", "message": "音声を取得しています…"})
        with (factory or YoutubeDL)(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        files = [p for p in staging.iterdir() if p.is_file() and p.stem == "audio" and p.suffix not in {".part", ".ytdl", ".temp"}]
        if len(files) != 1:
            raise AppError("完成した音声ファイルを一意に確認できませんでした。")
        source = files[0]
        name = safe_filename(info.get("title", "audio"), info["id"], source.suffix[1:])
        target = publish_file(source, directory, name)
        return {"type": "complete", "path": str(target), "title": info.get("title", "audio")}
