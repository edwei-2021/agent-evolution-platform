"""Browser-triggered matrix dispatch, persistence, cancellation and archive access."""
from functools import partial
from http.server import ThreadingHTTPServer
import io
import json
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import zipfile

from scripts.matrix_service import MatrixService
from scripts.serve_gui import GuiHandler, DIST
from scripts.runtime_service import RuntimeService


def fixture_command(output):
    code = '''import json,sys,time,zipfile
from pathlib import Path
p=Path(sys.argv[1]);p.mkdir(parents=True)
(p/'events.jsonl').write_text('{"kind":"matrix.started"}\\n')
print('matrix worker started',flush=True)
time.sleep(0.2)
(p/'summary.json').write_text(json.dumps({'status':'passed','coverage':{'flowPasses':{'configurations':3,'components':3,'acceptance':3}}}))
with zipfile.ZipFile(p/'support.zip','w') as z:z.write(p/'summary.json','summary.json')
'''
    return [sys.executable, '-u', '-c', code, str(output)]


def wait_terminal(service, identifier):
    for _ in range(100):
        result = service.snapshot(identifier)
        if result['status'] in ('completed', 'failed', 'cancelled'):
            return result
        time.sleep(0.03)
    raise AssertionError('Matrix worker did not finish')


def test_matrix_supervisor_rejects_overlap_and_preserves_archive(tmp_path):
    service = MatrixService(tmp_path, fixture_command)
    try:
        job = service.start()
        try:
            service.start()
        except RuntimeError as exc:
            assert 'already running' in str(exc)
        else:
            raise AssertionError('An overlapping matrix was accepted')
        done = wait_terminal(service, job['id'])
        assert done['status'] == 'completed'
        assert done['archiveReady']
        assert done['summary']['coverage']['flowPasses']['acceptance'] == 3
        with zipfile.ZipFile(service.archive(job['id'])) as archive:
            assert json.loads(archive.read('summary.json'))['status'] == 'passed'
        assert 'matrix worker started' in done['logTail']
        assert MatrixService(tmp_path, fixture_command).snapshot(job['id'])['status'] == 'completed'
    finally:
        service.close()


def test_matrix_cancel_stops_process_group(tmp_path):
    service = MatrixService(tmp_path, lambda output: [sys.executable, '-c', 'import time;time.sleep(60)'])
    try:
        job = service.start()
        for _ in range(100):
            if service.snapshot(job['id'])['status'] == 'running':
                break
            time.sleep(0.01)
        service.cancel(job['id'])
        done = wait_terminal(service, job['id'])
        assert done['status'] == 'cancelled'
        assert done['archiveReady']
    finally:
        service.close()


def test_missing_environment_still_returns_downloadable_failure(tmp_path):
    service = MatrixService(tmp_path)
    try:
        job = service.start()
        done = wait_terminal(service, job['id'])
        assert done['status'] == 'failed'
        assert done['archiveReady']
        assert len(done['summary']['coverage']['unexecuted']) == 12
        with zipfile.ZipFile(service.archive(job['id'])) as archive:
            assert {'job.json', 'runner.log', 'summary.json'} <= set(archive.namelist())
    finally:
        service.close()


def test_matrix_http_requires_session_token_and_downloads_job_archive(tmp_path):
    service = MatrixService(tmp_path, fixture_command)
    runtime = RuntimeService(tmp_path)
    runtime.matrix = service
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(GuiHandler, directory=str(DIST)))
    server.runtime = runtime
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'

    def request(path, *, token=None, body=None):
        headers = {'Content-Type': 'application/json'} if body is not None else {}
        if token:
            headers['X-Lab-Token'] = token
        with urlopen(Request(base+path, data=json.dumps(body).encode() if body is not None else None,
                             headers=headers), timeout=5) as result:
            return result.status, result.read()

    try:
        try:
            request('/api/v1/tests/matrix', body={})
        except HTTPError as exc:
            assert exc.code == 403
        else:
            raise AssertionError('A cross-session POST was accepted')
        status, raw = request('/api/v1/tests/matrix', token=runtime.csrf_token, body={})
        assert status == 202
        identifier = json.loads(raw)['id']
        assert wait_terminal(service, identifier)['status'] == 'completed'
        status, raw = request('/api/v1/tests/matrix/'+identifier)
        assert status == 200 and json.loads(raw)['archiveReady']
        _, raw = request('/api/v1/tests/matrix/'+identifier+'/support')
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            assert archive.namelist() == ['summary.json']
        try:
            request('/api/v1/tests/matrix/'+identifier+'/support/../support')
        except HTTPError as exc:
            assert exc.code == 404
        else:
            raise AssertionError('Unexpected archive path was accepted')
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5);service.close();runtime.close()
