"""Windows-oriented desktop UI. Credentials and URLs are not persisted."""

from pathlib import Path
import sys

from PySide6.QtCore import QStandardPaths, QTimer, Qt
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QPushButton, QProgressBar, QTextEdit, QVBoxLayout, QWidget,
)

from .controller import JobController
from .core import AppError


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YaoTubng — 音声ダウンローダー")
        self.resize(790, 650)
        self.inspection = None
        self.close_pending = False
        self.job = JobController(self)
        self.job.event.connect(self.on_event)
        self.job.busy_changed.connect(self.on_busy)
        self.job.finished.connect(self.on_finished)
        content = QWidget()
        self.setCentralWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)
        heading = QLabel("YaoTubng")
        heading.setObjectName("heading")
        layout.addWidget(heading)
        subtitle = QLabel("YouTube / YouTube Music の音声を、元の形式で保存")
        layout.addWidget(subtitle)
        form = QFormLayout()
        form.setSpacing(12)
        layout.addLayout(form)
        self.url = QLineEdit()
        self.url.setPlaceholderText("https://music.youtube.com/watch?v=…")
        self.url.textChanged.connect(self.invalidate)
        form.addRow("曲・動画 URL", self.url)
        self.auth = QComboBox()
        for label, key in [("ログインなし", "none"), ("Edge のログイン状態", "edge"),
                           ("Chrome のログイン状態", "chrome"), ("Firefox のログイン状態", "firefox"),
                           ("Cookie ファイル（ローカル）", "file")]:
            self.auth.addItem(label, key)
        self.auth.currentIndexChanged.connect(self.auth_changed)
        form.addRow("認証", self.auth)
        self.cookie = QLineEdit()
        self.cookie.setPlaceholderText("Netscape 形式の Cookie ファイル")
        self.cookie.textChanged.connect(self.invalidate)
        self.cookie_button = QPushButton("選択")
        self.cookie_button.clicked.connect(self.choose_cookie)
        self.cookie_row = QWidget()
        cookie_layout = QHBoxLayout(self.cookie_row)
        cookie_layout.setContentsMargins(0, 0, 0, 0)
        cookie_layout.addWidget(self.cookie)
        cookie_layout.addWidget(self.cookie_button)
        self.cookie_row.setEnabled(False)
        form.addRow("Cookie ファイル", self.cookie_row)
        auth_note = QLabel("認証情報はこの PC 上で使用します。Premium 音声の取得可否は曲と yt-dlp の対応状況によります。")
        auth_note.setWordWrap(True)
        layout.addWidget(auth_note)
        self.title = QLabel("URL を入力し、「形式を確認」を押してください。")
        self.title.setWordWrap(True)
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.title)
        self.formats = QComboBox()
        self.formats.addItem("形式確認後に選択できます", "best")
        self.formats.setEnabled(False)
        form.addRow("音声形式", self.formats)
        self.destination = QLineEdit()
        music = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MusicLocation)
        self.destination.setText(str(Path(music or str(Path.home() / "Music")) / "YaoTubng"))
        self.destination_button = QPushButton("選択")
        self.destination_button.clicked.connect(self.choose_destination)
        destination_row = QWidget()
        destination_layout = QHBoxLayout(destination_row)
        destination_layout.setContentsMargins(0, 0, 0, 0)
        destination_layout.addWidget(self.destination)
        destination_layout.addWidget(self.destination_button)
        form.addRow("保存先", destination_row)
        buttons = QHBoxLayout()
        self.inspect_button = QPushButton("形式を確認")
        self.inspect_button.clicked.connect(lambda: self.start("inspect"))
        self.download_button = QPushButton("音声を保存")
        self.download_button.setObjectName("primary")
        self.download_button.setEnabled(False)
        self.download_button.clicked.connect(lambda: self.start("download"))
        self.cancel_button = QPushButton("キャンセル")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.job.cancel)
        for button in (self.inspect_button, self.download_button, self.cancel_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.progress = QProgressBar()
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.status = QLabel("待機中")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.document().setMaximumBlockCount(80)
        layout.addWidget(self.log, 1)
        footer = QLabel("１曲ずつ取得します。再エンコード・自動再試行・プレイリスト一括取得は行いません。")
        footer.setWordWrap(True)
        layout.addWidget(footer)
        self.setStyleSheet("""
            QMainWindow { background: #f6f8fc; }
            QLabel { color: #26334d; }
            QLabel#heading { font-size: 28px; font-weight: 700; }
            QLineEdit, QComboBox, QTextEdit { background: white; color: #18243a;
                border: 1px solid #cbd4e2; border-radius: 6px; padding: 8px; }
            QPushButton { padding: 10px 15px; border: 1px solid #cbd4e2; border-radius: 6px;
                background: white; color: #243550; }
            QPushButton#primary { background: #315fcb; color: white; border: none; }
            QPushButton:disabled { background: #e8edf4; color: #8793a6; }
            QPushButton#primary:disabled { background: #e8edf4; color: #8793a6; }
            QProgressBar { border: 1px solid #cbd4e2; border-radius: 5px; text-align: center; height: 18px; }
            QProgressBar::chunk { background: #315fcb; }
        """)

    def invalidate(self, *_):
        self.inspection = None
        self.formats.clear()
        self.formats.addItem("形式確認後に選択できます", "best")
        self.formats.setEnabled(False)
        self.download_button.setEnabled(False)
        self.title.setText("URL を入力し、「形式を確認」を押してください。")

    def auth_changed(self, *_):
        self.cookie_row.setEnabled(self.auth.currentData() == "file")
        self.invalidate()

    def choose_cookie(self):
        path, _ = QFileDialog.getOpenFileName(self, "Cookie ファイル", "", "Text files (*.txt);;All files (*)")
        if path:
            self.cookie.setText(path)

    def choose_destination(self):
        path = QFileDialog.getExistingDirectory(self, "保存先", self.destination.text())
        if path:
            self.destination.setText(path)

    def start(self, action):
        if action == "inspect":
            self.invalidate()
        elif not self.inspection:
            return
        payload = {"action": action, "url": self.url.text(), "auth": self.auth.currentData(),
                   "cookie_file": self.cookie.text() if self.auth.currentData() == "file" else ""}
        if action == "download":
            payload.update(format=self.formats.currentData(), destination=self.destination.text())
        self.progress.setRange(0, 0)
        try:
            self.job.start(payload)
        except (AppError, OSError) as exc:
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self.on_event({"type": "error", "message": str(exc) if isinstance(exc, AppError) else "保存先を準備できませんでした。フォルダーとアクセス権を確認してください。"})

    def on_busy(self, busy):
        for widget in (self.url, self.auth, self.destination, self.destination_button, self.inspect_button):
            widget.setEnabled(not busy)
        self.cookie_row.setEnabled(not busy and self.auth.currentData() == "file")
        self.formats.setEnabled(not busy and self.inspection is not None)
        self.download_button.setEnabled(not busy and self.inspection is not None)
        self.cancel_button.setEnabled(busy)

    def on_event(self, event):
        kind = event["type"]
        if kind == "inspection":
            self.inspection = event
            self.title.setText(event["title"])
            self.formats.clear()
            self.formats.addItem("自動選択（yt-dlp が最良と判断する音声）", "best")
            for fmt in event["formats"]:
                bitrate = f"{fmt['abr']:.0f} kbps" if fmt.get("abr") else "ビットレート不明"
                label = f"{fmt['id']} / {fmt['ext']} / {fmt['codec']} / {bitrate}"
                self.formats.addItem(label, fmt["id"])
            message = f"音声形式を {len(event['formats'])} 件確認しました。"
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
        elif kind == "progress":
            total = event.get("total")
            if total:
                self.progress.setRange(0, 100)
                self.progress.setValue(min(100, int(event["downloaded"] * 100 / total)))
            message = f"取得中: {event['downloaded'] / 1048576:.1f} MiB"
            if event.get("eta") is not None:
                message += f" / 残り約 {event['eta']:.0f} 秒"
            self.status.setText(message)
            return
        elif kind == "complete":
            self.progress.setRange(0, 100)
            self.progress.setValue(100)
            self.cancel_button.setEnabled(False)
            message = f"保存しました: {event['path']}"
        elif kind == "cancelled":
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            message = "キャンセルしました。"
        else:
            message = event.get("message", "")
            if kind == "error":
                self.progress.setRange(0, 100)
                self.progress.setValue(0)
        self.status.setText(message)
        self.log.insertPlainText(message + "\n")
        self.log.ensureCursorVisible()

    def on_finished(self, success):
        if self.progress.maximum() == 0:
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
        if self.close_pending:
            QTimer.singleShot(0, self.close)

    def closeEvent(self, event):
        if self.job.busy:
            self.close_pending = True
            self.job.cancel()
            event.ignore()
        else:
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("YaoTubng")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
