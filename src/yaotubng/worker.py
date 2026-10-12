"""Private JSON-lines subprocess protocol; request comes through stdin."""

import json
import os
import sys

from .core import Auth, error_message
from .engine import download, inspect


def emit(event: dict) -> None:
    print(json.dumps(event, ensure_ascii=True), flush=True)


def main() -> int:
    if os.name != "nt":
        os.setsid()
    try:
        payload = json.loads(sys.stdin.readline())
        auth = Auth(payload.get("auth", "none"), payload.get("cookie_file", ""))
        if payload["action"] == "inspect":
            result = inspect(payload["url"], auth, emit, scratch=payload["stage"])
        elif payload["action"] == "download":
            result = download(payload["url"], auth, payload["format"], payload["destination"], payload["stage"], emit)
        else:
            raise ValueError("Unknown action")
        emit(result)
        return 0
    except Exception as exc:
        emit({"type": "error", "message": error_message(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
