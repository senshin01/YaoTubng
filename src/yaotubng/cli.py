"""Local format inspection and single-track download without the desktop UI."""

import argparse
from importlib.metadata import version
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from .core import Auth, error_message
from .engine import download, inspect


def emit(event):
    print(json.dumps(event, ensure_ascii=True), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="YaoTubng: local audio tools")
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("doctor", help="Check installed tools without accessing YouTube")
    for command in ("inspect", "download"):
        sub = commands.add_parser(command)
        sub.add_argument("url")
        sub.add_argument("--browser", choices=["edge", "chrome", "firefox"])
        sub.add_argument("--cookies", type=Path, help="Local Netscape cookie file; never share this file")
        if command == "download":
            sub.add_argument("--output", type=Path, required=True)
            sub.add_argument("--format", default="best")
    args = parser.parse_args(argv)
    if args.action == "doctor":
        ready = True
        for package in ("yaotubng", "yt-dlp", "yt-dlp-ejs", "PySide6"):
            try:
                print(f"{package}: {version(package)}")
            except Exception:
                print(f"{package}: not installed")
                ready = False
        for tool in ("ffmpeg", "node"):
            path = shutil.which(tool)
            if path:
                result = subprocess.run([path, "-version" if tool == "ffmpeg" else "--version"], capture_output=True, text=True)
                print(f"{tool}: {result.stdout.splitlines()[0] if result.stdout else 'cannot execute'}")
                ready = ready and result.returncode == 0
                if tool == "node":
                    try:
                        ready = ready and int(result.stdout.strip().lstrip("v").split(".")[0]) >= 22
                    except ValueError:
                        ready = False
            else:
                print(f"{tool}: not installed")
                ready = False
        return 0 if ready else 1
    if args.browser and args.cookies:
        parser.error("--browser and --cookies cannot be combined")
    auth = Auth("file" if args.cookies else args.browser or "none", str(args.cookies or ""))
    try:
        if args.action == "inspect":
            with tempfile.TemporaryDirectory(prefix="yaotubng-cli-") as scratch:
                emit(inspect(args.url, auth, emit, scratch=scratch))
        else:
            args.output.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix=".yaotubng-", dir=args.output) as stage:
                emit(download(args.url, auth, args.format, str(args.output), stage, emit))
        return 0
    except KeyboardInterrupt:
        emit({"type": "cancelled"})
        return 130
    except Exception as exc:
        emit({"type": "error", "message": error_message(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
