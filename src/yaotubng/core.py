"""Validation and filesystem operations shared by the GUI and worker."""

from dataclasses import dataclass
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit


class AppError(Exception):
    """An error safe to display without exposing yt-dlp credentials or logs."""


def normalize_url(value: str) -> str:
    try:
        parsed = urlsplit(value.strip())
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port:
            raise ValueError
        host = (parsed.hostname or "").lower()
        if host == "youtu.be":
            video_id = parsed.path.removeprefix("/")
        elif host in {"youtube.com", "www.youtube.com", "music.youtube.com", "m.youtube.com"}:
            if parsed.path == "/watch":
                ids = parse_qs(parsed.query).get("v", [])
                video_id = ids[0] if len(ids) == 1 else ""
            elif parsed.path.startswith(("/shorts/", "/live/")):
                video_id = parsed.path.split("/")[2]
            else:
                raise ValueError
        else:
            raise ValueError
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            raise ValueError
    except ValueError as exc:
        raise AppError("HTTPS の YouTube / YouTube Music の曲・動画 URL を入力してください。プレイリスト単体は未対応です。") from exc
    return f"https://www.youtube.com/watch?v={video_id}"


@dataclass(frozen=True)
class Auth:
    mode: str = "none"
    cookie_file: str = ""

    def validate(self) -> None:
        if self.mode not in {"none", "edge", "chrome", "firefox", "file"}:
            raise AppError("認証方法が不正です。")
        if self.mode == "file":
            path = Path(self.cookie_file)
            if not path.is_file() or path.is_symlink():
                raise AppError("Cookie ファイルを選択してください。")


def validate_format(value: str) -> str:
    if value != "best" and not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", value):
        raise AppError("音声形式の指定が不正です。")
    return value


def safe_filename(title: str, video_id: str, extension: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise AppError("取得結果の動画 ID が不正です。")
    if not re.fullmatch(r"[A-Za-z0-9]{1,8}", extension):
        raise AppError("取得結果の拡張子が不正です。")
    # Conservative length also limits UTF-16 path length on Windows.
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', "_", title).strip(" .")
    name = "".join(list(name)[:70]).rstrip(" .") or "audio"
    if name.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}:
        name = "_" + name
    return f"{name} [{video_id}].{extension.lower()}"


def publish_file(source: Path, directory: Path, filename: str) -> Path:
    """Atomically create a final name without overwriting any existing file."""
    if Path(filename).name != filename or "/" in filename or "\\" in filename:
        raise AppError("保存ファイル名が不正です。")
    if not source.is_file() or source.is_symlink() or source.stat().st_size == 0:
        raise AppError("完成した音声ファイルを確認できませんでした。")
    directory = directory.resolve(strict=True)
    target = directory / filename
    try:
        target.hardlink_to(source)
    except FileExistsError as exc:
        raise AppError("同名のファイルが存在します。上書きせず停止しました。") from exc
    except OSError as exc:
        raise AppError("保存先がハードリンクに対応していません。Windows の NTFS ドライブ上のフォルダーを選んでください。") from exc
    return target


def error_message(error: Exception) -> str:
    if isinstance(error, AppError):
        return str(error)
    # Never relay arbitrary yt-dlp errors, URLs, paths, or cookie values to UI/logs.
    raw = str(error).lower()
    if any(word in raw for word in ("429", "too many requests", "confirm you", "not a bot", "captcha")):
        return "アクセス制限または認証確認が発生しました。処理を停止しました。時間を置いて確認してください。"
    if "cookie" in raw or "dpapi" in raw:
        return "ブラウザー認証を読み取れませんでした。ブラウザーを閉じて再確認するか、ローカル Cookie ファイルを指定してください。"
    if "403" in raw or "sign in" in raw or "premium" in raw:
        return "この音声へのアクセスが拒否されました。認証状態や取得可能な形式を確認してください。"
    return "取得できませんでした。ネットワーク、認証、yt-dlp の更新状況を確認してください。"
