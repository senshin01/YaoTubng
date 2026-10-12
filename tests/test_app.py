import json
import os
from pathlib import Path
import time

from PySide6.QtCore import QProcess
import pytest

from yaotubng.app import MainWindow
from yaotubng.controller import JobController
from yaotubng.core import AppError
import yaotubng.controller as controller_module


def wait_for(qapp, predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.005)
    assert predicate(), 'Qt operation did not complete'


def test_window_form_state_and_safe_text(qapp):
    window = MainWindow()
    window.show()
    qapp.processEvents()
    assert not window.download_button.isEnabled()
    window.on_event({'type': 'inspection', 'title': '<b>曲</b>', 'formats': [
        {'id': '140', 'ext': 'm4a', 'codec': 'aac', 'abr': 128}]})
    window.on_busy(False)
    assert window.download_button.isEnabled()
    assert window.title.text() == '<b>曲</b>'
    assert window.formats.itemData(1) == '140'
    window.auth.setCurrentIndex(window.auth.findData('file'))
    assert not window.download_button.isEnabled()
    assert window.cookie_row.isEnabled()
    window.close()


def install_fake_worker(monkeypatch, script):
    class FixtureProcess(QProcess):
        def setArguments(self, args):
            if args == ['-m', 'yaotubng.worker']:
                args = ['-c', script]
            return super().setArguments(args)
    monkeypatch.setattr(controller_module, 'QProcess', FixtureProcess)


def test_job_protocol_and_cleanup(qapp, monkeypatch, tmp_path):
    script = """
import json, pathlib, sys
payload=json.loads(sys.stdin.readline())
pathlib.Path(payload['stage'], 'private-cookie-copy.txt').write_text('test-only')
print(json.dumps({'type':'inspection','title':'fixture','formats':[]}), flush=True)
"""
    install_fake_worker(monkeypatch, script)
    job = JobController()
    events = []
    outcomes = []
    job.event.connect(events.append)
    job.finished.connect(outcomes.append)
    job.start({'action': 'inspect', 'url': 'https://youtube.com/watch?v=BaW_jenozKc'})
    stage = job.stage
    wait_for(qapp, lambda: not job.busy)
    assert outcomes == [True] and events[0]['type'] == 'inspection'
    assert not stage.exists()


@pytest.mark.parametrize('immediate', [False, True])
def test_cancellation_kills_job_and_removes_partial_and_auth(qapp, monkeypatch, tmp_path, immediate):
    script = """
import json, os, pathlib, sys, time
if os.name != 'nt': os.setsid()
payload=json.loads(sys.stdin.readline())
pathlib.Path(payload['stage'], 'audio.m4a.part').write_bytes(b'partial')
pathlib.Path(payload['stage'], 'cookie-copy.txt').write_text('test-only')
print(json.dumps({'type':'status','message':'started'}), flush=True)
time.sleep(30)
"""
    install_fake_worker(monkeypatch, script)
    job = JobController()
    events = []
    job.event.connect(events.append)
    job.start({'action': 'download', 'url': 'https://youtube.com/watch?v=BaW_jenozKc',
               'format': 'best', 'destination': str(tmp_path)})
    stage = job.stage
    if not immediate:
        wait_for(qapp, lambda: any(e.get('message') == 'started' for e in events))
    job.cancel()
    wait_for(qapp, lambda: not job.busy)
    assert not stage.exists()
    assert any(e['type'] == 'cancelled' for e in events)
    assert list(tmp_path.iterdir()) == []


def test_empty_destination_is_rejected_before_start(qapp):
    job = JobController()
    with pytest.raises(AppError, match='保存先'):
        job.start({'action': 'download', 'url': 'https://youtube.com/watch?v=BaW_jenozKc', 'format': 'best', 'destination': ''})
    assert not job.busy


def test_closing_window_cancels_active_job(qapp, monkeypatch):
    script = """
import json, os, sys, time
if os.name != 'nt': os.setsid()
json.loads(sys.stdin.readline())
print(json.dumps({'type':'status','message':'started'}), flush=True)
time.sleep(30)
"""
    install_fake_worker(monkeypatch, script)
    window = MainWindow()
    window.show()
    window.url.setText('https://youtube.com/watch?v=BaW_jenozKc')
    window.start('inspect')
    stage = window.job.stage
    wait_for(qapp, lambda: window.status.text() == 'started')
    window.close()
    wait_for(qapp, lambda: not window.job.busy and not window.isVisible())
    assert not stage.exists()
