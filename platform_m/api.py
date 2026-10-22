"""Loopback-only FastAPI control API. Optional same-origin legacy compatibility proxy."""
import asyncio
import hmac
import json
from pathlib import Path
import re
import secrets
import time
import uuid
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from .store import Store
from .evidence import Artifacts, atomic_write
from .releases import Releases, signing_key_path
from scripts.branch_diagnostics import record

def create_app(root, token, role='operator', legacy_port=None):
    root = Path(root).resolve()
    store = Store(root/'.local/m/control.sqlite3')
    artifacts = Artifacts(root/'.local/m/artifacts')
    releases = Releases(store, artifacts, signing_key_path(root),
                        git_root=root if (root/'.git').exists() else None)
    app = FastAPI(title='Agent Evolution Platform M', version='0.8.0')
    app.state.store, app.state.artifacts, app.state.releases = store, artifacts, releases

    @app.on_event('startup')
    def reconcile_release_startup():
        if releases.git is not None:
            try:
                releases.reconcile_git()
            except (RuntimeError, ValueError) as exc:
                record(root, 'M6', 'release.git-startup', 'failed', error=exc)

    @app.middleware('http')
    async def boundary(request: Request, call_next):
        request_id = request.headers.get('X-Request-ID', '')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', request_id):
            request_id = uuid.uuid4().hex
        request.state.correlation_id = request_id
        from urllib.parse import urlsplit
        host = request.headers.get('host', '')
        parsed = urlsplit('http://'+host)
        if parsed.hostname not in ('localhost', '127.0.0.1', 'testserver') or parsed.username or parsed.password:
            return JSONResponse({'error': 'Local Host required'}, status_code=403)
        if request.headers.get('origin') not in (None, 'http://'+host):
            return JSONResponse({'error': 'Cross-origin access denied'}, status_code=403)
        if request.headers.get('sec-fetch-site') not in (None, 'same-origin', 'none'):
            return JSONResponse({'error': 'Cross-site access denied'}, status_code=403)
        if request.url.path.startswith('/api/m/') and request.url.path != '/api/m/health':
            if not hmac.compare_digest(request.headers.get('authorization', ''), 'Bearer '+token):
                return JSONResponse({'error': 'Local operator token required'}, status_code=401)
        try:
            size = int(request.headers.get('content-length', '0') or '0')
        except ValueError:
            return JSONResponse({'error': 'Invalid Content-Length'}, status_code=400)
        if size < 0 or size > 1000000:
            return JSONResponse({'error': 'Request too large'}, status_code=413)
        try:
            store.event(request_id, 'api.request', {'method': request.method, 'path': request.url.path}, request_id)
            response = await call_next(request)
            store.event(request_id, 'api.response', {'status': response.status_code}, request_id)
        except Exception as exc:
            record(root,'M7','api.authoritative-request','failed',identifier=request_id,error=exc)
            raise
        route=getattr(request.scope.get('route'),'name','unknown')
        record(root,'M7','api.'+route,'failed' if response.status_code>=500 else 'withheld' if response.status_code>=400 else 'completed',
               identifier=request_id,status=response.status_code)
        response.headers['X-Request-ID'] = request_id
        return response

    @app.exception_handler(ValueError)
    async def invalid(request, error):
        record(root,'M7','api.validation','withheld',identifier=request.state.correlation_id,error=error)
        return JSONResponse({'error': str(error), 'request_id': request.state.correlation_id}, status_code=400)

    @app.exception_handler(PermissionError)
    async def forbidden(request, error):
        record(root,'M7','api.permission','withheld',identifier=request.state.correlation_id,error=error)
        return JSONResponse({'error': str(error)}, status_code=403)

    @app.exception_handler(KeyError)
    async def missing(request, error):
        return JSONResponse({'error': 'Record not found'}, status_code=404)

    @app.exception_handler(RuntimeError)
    async def conflict(request, error):
        record(root,'M7','api.conflict','withheld',identifier=request.state.correlation_id,error=error)
        return JSONResponse({'error': str(error)}, status_code=409)

    @app.get('/api/m/health')
    def health():
        with store.db() as db:
            revision = db.execute('PRAGMA user_version').fetchone()[0]
            db.execute('SELECT COUNT(*) FROM events').fetchone()
        return {'status': 'healthy', 'schema_version': revision, 'mode': 'local', 'at': time.time()}

    @app.post('/api/m/jobs', status_code=202)
    async def submit(request: Request):
        payload = await request.json()
        if set(payload) != {'task', 'release', 'environment'} or payload['environment'].get('adapter') != 'mock':
            raise ValueError('Canonical queue currently accepts explicit mock jobs only; use verified nanobot runner separately')
        from .contracts import Task
        Task.model_validate(payload['task'])
        if 'skill_hash' not in payload['release']:
            raise ValueError('Frozen Skill snapshot required')
        identifier = store.submit(request.headers.get('Idempotency-Key'), payload, request.state.correlation_id)
        return {'id': identifier, 'state': store.get(identifier)['state']}

    @app.get('/api/m/jobs/{identifier}')
    def job(identifier: str):
        row = store.get(identifier)
        with store.db() as db:
            result = db.execute('SELECT data FROM results WHERE job_id=?', (identifier,)).fetchone()
        return {'id': identifier, 'state': row['state'], 'request_hash': row['request_hash'],
                'result': json.loads(result[0]) if result else None}

    @app.post('/api/m/nanobot/jobs',status_code=202)
    async def submit_nanobot(request: Request):
        spec=await request.json()
        fields={'task_id','skill_body','label','repetition','calls','seconds','experiment'}
        if not isinstance(spec,dict) or set(spec)!=fields:
            raise ValueError('Supply exactly the native task, Skill and bounded execution fields')
        key=request.headers.get('Idempotency-Key')
        if not isinstance(key,str) or not 1<=len(key)<=112:
            raise ValueError('Idempotency-Key must contain 1..112 characters')
        key='nanobot:'+key
        with store.db() as db:
            prior=db.execute('SELECT id,payload FROM jobs WHERE idem=?',(key,)).fetchone()
        if prior:
            frozen=json.loads(prior['payload'])
            if frozen.get('submission')!=spec:
                raise ValueError('Idempotency key reused with different native input')
            if store.get(prior['id'])['state']=='queued':
                store.configure(prior['id'],frozen['configuration_hash'])
            return {'id':prior['id'],'state':store.get(prior['id'])['state']}
        from scripts.run_m_repair import prepare
        # Explicit POST only: dependency/model/data freezing stays out of reads.
        _,_,config,payload=await asyncio.to_thread(prepare,root,image='aep-evaluator:m',**spec)
        payload['submission']=spec
        payload['configuration_hash']=artifacts.put(config)
        identifier=store.submit(key,payload,request.state.correlation_id)
        store.configure(identifier,payload['configuration_hash'])
        return {'id':identifier,'state':store.get(identifier)['state']}

    @app.post('/api/m/jobs/{identifier}/cancel')
    def cancel(identifier: str):
        return {'id': identifier, 'state': store.request_cancel(identifier)}

    @app.post('/api/m/jobs/{identifier}/resume')
    async def resume(identifier: str, request: Request):
        body = await request.json()
        if set(body) != {'request_hash'}:
            raise ValueError('Resume snapshot required')
        store.resume(identifier, body['request_hash'])
        return {'id': identifier, 'state': 'queued'}

    @app.get('/api/m/jobs/{identifier}/events')
    async def events(identifier: str, request: Request, after: int = 0, follow: bool = False):
        store.get(identifier)
        if after < 0:
            raise ValueError('Invalid replay sequence')
        async def replay():
            cursor = after
            while True:
                rows = store.events(identifier, cursor)
                for row in rows:
                    cursor = row['seq']
                    yield f'id: {cursor}\ndata: {json.dumps(row)}\n\n'
                if not follow or store.get(identifier)['state'] in ('completed','failed','cancelled','interrupted'):
                    break
                if await request.is_disconnected():
                    break
                if not rows:
                    yield ': heartbeat\n\n'
                    await asyncio.sleep(.5)
        return StreamingResponse(replay(), media_type='text/event-stream')

    @app.get('/api/m/checks')
    def checks():
        with store.db() as db:
            return {'checks': [json.loads(r[0]) for r in db.execute('SELECT data FROM checks ORDER BY rowid DESC LIMIT 100')]}

    @app.get('/api/m/releases/active')
    def active():
        return releases.active()

    @app.get('/api/m/releases/git')
    def release_git_status():
        return releases.git_status()

    @app.post('/api/m/releases/reconcile')
    async def reconcile_release(request: Request):
        if role != 'approver':
            raise PermissionError('Only approver may reconcile a release')
        body = await request.json()
        if not isinstance(body, dict) or set(body) != {'expected_revision'} or type(body['expected_revision']) is not int:
            raise ValueError('Expected active revision required')
        return releases.reconcile_git(expected={**releases.active(), 'revision': body['expected_revision']})

    @app.post('/api/m/releases/{identifier}/approve')
    async def approve(identifier: str, request: Request):
        body = await request.json()
        if set(body) != {'rationale'}:
            raise ValueError('Supply rationale only; identity/role is server-controlled')
        releases.approve(identifier, 'local-owner', role, body['rationale'])
        return {'hash': identifier, 'approved': True}

    @app.post('/api/m/releases/{identifier}/activate')
    async def activate(identifier: str, request: Request):
        body = await request.json()
        if set(body) != {'expected_revision', 'rollback'} or type(body['rollback']) is not bool:
            raise ValueError('Activation revision and rollback flag required')
        return releases.activate(identifier, body['expected_revision'], 'local-owner', role, body['rollback'])

    if legacy_port is not None:
        if type(legacy_port) is not int or not 1024 <= legacy_port <= 65535:
            raise ValueError('Invalid legacy loopback port')
        @app.api_route('/api/v1/{path:path}', methods=['GET', 'POST'])
        async def legacy(path: str, request: Request):
            import httpx
            from starlette.responses import Response
            # Never forward user-selected hosts, Origin or credentials to another service.
            headers = {'content-type': request.headers.get('content-type', 'application/json')}
            if request.headers.get('X-Lab-Token'):
                headers['X-Lab-Token'] = request.headers['X-Lab-Token']
            url = f'http://127.0.0.1:{legacy_port}/api/v1/'+path
            async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=125) as client:
                response = await client.request(request.method, url, params=request.query_params,
                                                headers=headers, content=await request.body())
            return Response(response.content, status_code=response.status_code,
                            media_type=response.headers.get('content-type', 'application/json'))
    from fastapi.staticfiles import StaticFiles
    if (root/'dist').is_dir():
        app.mount('/', StaticFiles(directory=root/'dist', html=True), name='legacy-gui')
    return app

def operator_token(root):
    path = Path(root)/'.local/m/operator.token'
    if not path.exists():
        atomic_write(path, secrets.token_urlsafe(32).encode())
    if path.is_symlink() or path.stat().st_mode & 0o077:
        raise RuntimeError('Local operator token must have mode 600')
    return path.read_text().strip()
