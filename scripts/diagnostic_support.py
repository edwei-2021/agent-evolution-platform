"""Python-level snapshots; no periodic native faulthandler watchdog."""
from contextlib import contextmanager
import faulthandler
import json
from pathlib import Path
import platform
import signal
import sqlite3
import sys
import threading
import traceback
from debug_log import redact


def termination(code):
    if code >= 0:
        return {'kind': 'exit', 'exitCode': code}
    number = -code
    try: name = signal.Signals(number).name
    except ValueError: name = 'UNKNOWN'
    return {'kind': 'signal', 'signalNumber': number, 'signalName': name, 'returnCode': code}


def environment():
    return {'python': sys.executable, 'pythonVersion': sys.version,
            'pythonImplementation': platform.python_implementation(),
            'sqliteVersion': sqlite3.sqlite_version, 'platform': platform.platform(),
            'diagnosticPolicy': 'Python stack snapshots; fatal-signal handler; no native watchdog timer'}


class PythonSnapshots:
    def __init__(self, directory, capture=None, interval=5):
        self.directory = Path(directory)
        self.capture = capture
        self.interval = interval
        self.stop = threading.Event()
        self.thread = None

    def sample(self):
        pieces = []
        for identifier, frame in sys._current_frames().items():
            pieces.append(f'Thread {identifier}\n' + ''.join(traceback.format_stack(frame)))
        target = self.directory / 'threads.log'
        temporary = target.with_suffix('.tmp')
        temporary.write_text(redact('\n'.join(pieces)))
        temporary.replace(target)
        if self.capture:
            self.capture()

    def run(self):
        while not self.stop.wait(self.interval):
            try: self.sample()
            except (OSError, ValueError, RuntimeError) as exc:
                (self.directory / 'snapshot-error.log').write_text(redact(str(exc)))

    def __enter__(self):
        self.sample()
        self.thread = threading.Thread(target=self.run, daemon=True, name='python-diagnostic-snapshots')
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.stop.set()
        self.thread.join(timeout=10)


@contextmanager
def fatal_diagnostics(directory):
    directory = Path(directory)
    (directory / 'environment.json').write_text(json.dumps(environment(), indent=2))
    with (directory / 'fatal.log').open('w') as stream:
        faulthandler.enable(file=stream, all_threads=True)
        try: yield
        finally: faulthandler.disable()
