"""One cancellable local job at a time; no shell, automatic retries, or saved auth."""

import json
import os
from pathlib import Path
import shutil
import signal
import sys
import tempfile

from PySide6.QtCore import QObject, QProcess, Signal

from .core import AppError, Auth, normalize_url, validate_format


class JobController(QObject):
    event = Signal(dict)
    finished = Signal(bool)
    busy_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None
        self.stage = None
        self.buffer = b""
        self.cancelled = False
        self.result_received = False
        self.error_received = False
        self.killer = None

    @property
    def busy(self):
        return self.process is not None

    def start(self, payload: dict) -> None:
        if self.busy:
            raise AppError("別の処理が実行中です。")
        payload = dict(payload)
        payload["url"] = normalize_url(payload["url"])
        Auth(payload.get("auth", "none"), payload.get("cookie_file", "")).validate()
        if payload["action"] == "download":
            validate_format(payload["format"])
            if not payload["destination"].strip():
                raise AppError("保存先を指定してください。")
            destination = Path(payload["destination"]).expanduser()
            if os.name == "nt" and len(str(destination.absolute())) > 130:
                raise AppError("保存先のパスが長すぎます。短いパスのフォルダーを選んでください。")
            destination.mkdir(parents=True, exist_ok=True)
            destination = destination.resolve()
            payload["destination"] = str(destination)
            self.stage = Path(tempfile.mkdtemp(prefix=".yaotubng-", dir=destination))
        elif payload["action"] == "inspect":
            self.stage = Path(tempfile.mkdtemp(prefix="yaotubng-job-"))
        else:
            raise AppError("不正な操作です。")
        payload["stage"] = str(self.stage)
        self.cancelled = self.result_received = self.error_received = False
        self.buffer = b""
        process = QProcess(self)
        self.process = process
        process.setProgram(sys.executable)
        process.setArguments(["-m", "yaotubng.worker"])
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        process.readyReadStandardOutput.connect(self._read)
        # Discard raw diagnostics: they may contain URLs or authentication paths.
        process.readyReadStandardError.connect(lambda: process.readAllStandardError())
        process.started.connect(lambda: self._started(payload))
        process.finished.connect(self._finished)
        process.errorOccurred.connect(self._process_error)
        self.busy_changed.emit(True)
        process.start()

    def _started(self, payload):
        if not self.process:
            return
        if self.cancelled:
            # Cancellation can arrive while QProcess is still starting.
            self.cancelled = False
            self.cancel()
        else:
            self.process.write(json.dumps(payload).encode() + b"\n")
            self.process.closeWriteChannel()

    def _read(self):
        if not self.process:
            return
        self.buffer += bytes(self.process.readAllStandardOutput())
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            try:
                event = json.loads(line)
                if not isinstance(event, dict) or "type" not in event:
                    continue
            except (ValueError, UnicodeDecodeError):
                continue
            if event["type"] in {"inspection", "complete"}:
                self.result_received = True
            if event["type"] == "error":
                self.error_received = True
            self.event.emit(event)

    def cancel(self):
        if not self.process or self.result_received or self.cancelled:
            return
        self.cancelled = True
        self.event.emit({"type": "status", "message": "キャンセルしています…"})
        pid = int(self.process.processId())
        if not pid:
            self.process.kill()
        elif os.name == "nt":
            # Kill FFmpeg children as well; don't block the GUI thread.
            self.killer = QProcess(self)
            self.killer.setProgram(str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "taskkill.exe"))
            self.killer.setArguments(["/PID", str(pid), "/T", "/F"])
            self.killer.finished.connect(lambda *_: self._kill_fallback())
            self.killer.errorOccurred.connect(lambda *_: self._kill_fallback())
            self.killer.start()
        else:
            try:
                if os.getpgid(pid) == pid:
                    os.killpg(pid, signal.SIGKILL)
                else:
                    self.process.kill()
            except ProcessLookupError:
                pass

    def _kill_fallback(self):
        if self.process and self.cancelled:
            self.process.kill()

    def _process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.error_received = True
            self.event.emit({"type": "error", "message": "取得プロセスを起動できませんでした。仮想環境から起動してください。"})
            self._finished(1, QProcess.ExitStatus.CrashExit)

    def _finished(self, code, exit_status):
        if not self.process:
            return
        self._read()
        success = self.result_received and code == 0 and exit_status == QProcess.ExitStatus.NormalExit
        if self.cancelled and not self.result_received:
            self.event.emit({"type": "cancelled"})
        elif not success and not self.error_received and not self.result_received:
            self.event.emit({"type": "error", "message": "取得プロセスが終了しました。依存関係とネットワークを確認してください。"})
        cleanup_failed = False
        if self.stage:
            try:
                shutil.rmtree(self.stage)
            except OSError:
                cleanup_failed = True
            self.stage = None
        self.process.deleteLater()
        self.process = None
        if self.killer:
            if self.killer.state() == QProcess.ProcessState.NotRunning:
                self.killer.deleteLater()
            else:
                self.killer.finished.connect(self.killer.deleteLater)
            self.killer = None
        if cleanup_failed:
            self.event.emit({"type": "warning", "message": "一時フォルダーを削除できませんでした。保存先または OS の一時フォルダーを確認してください。"})
        self.busy_changed.emit(False)
        self.finished.emit(success)
