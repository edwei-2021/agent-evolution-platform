"""Transactional local queue, fenced leases, immutable evidence and StepChecks."""
from contextlib import contextmanager
import json
from pathlib import Path
import secrets
import sqlite3
import time
import uuid
from .contracts import Event, StepCheck, Evaluation
from .evidence import canonical, digest, redact

from scripts.branch_diagnostics import diagnosed

HEAD = 1
TERMINAL = {"completed", "failed", "cancelled", "interrupted"}
TRANSITIONS = {"draft": {"queued", "cancelled"}, "queued": {"running", "cancelled"},
               "running": {"evaluating", "failed", "cancelling", "cancelled", "interrupted"},
               "evaluating": {"completed", "failed", "cancelling", "cancelled", "interrupted"},
               "cancelling": {"cancelled", "failed", "interrupted"}}

SCHEMA = """
CREATE TABLE jobs(id TEXT PRIMARY KEY, idem TEXT UNIQUE NOT NULL, request_hash TEXT NOT NULL,
 payload TEXT NOT NULL, state TEXT NOT NULL, owner TEXT, lease REAL, fence INTEGER NOT NULL DEFAULT 0);
CREATE TABLE events(seq INTEGER PRIMARY KEY AUTOINCREMENT, aggregate_id TEXT NOT NULL,
 correlation_id TEXT NOT NULL, type TEXT NOT NULL, at REAL NOT NULL, payload TEXT NOT NULL);
CREATE TABLE evaluations(id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE results(job_id TEXT PRIMARY KEY REFERENCES jobs(id), fence INTEGER NOT NULL, data TEXT NOT NULL);
CREATE TABLE checkpoints(job_id TEXT NOT NULL REFERENCES jobs(id), ordinal INTEGER NOT NULL,
 hash TEXT NOT NULL, PRIMARY KEY(job_id,ordinal));
CREATE TABLE checks(id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE releases(hash TEXT PRIMARY KEY, data TEXT NOT NULL, comparison_hash TEXT NOT NULL);
CREATE TABLE approvals(hash TEXT PRIMARY KEY REFERENCES releases(hash), actor TEXT NOT NULL, at REAL NOT NULL,
 rationale TEXT NOT NULL, signature TEXT NOT NULL, public_key TEXT NOT NULL);
CREATE TABLE active(singleton INTEGER PRIMARY KEY CHECK(singleton=1), hash TEXT REFERENCES releases(hash), revision INTEGER NOT NULL);
INSERT INTO active VALUES(1,NULL,0);
"""

class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()
    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=15000")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()
    @diagnosed('M3','ledger.migrate')
    def migrate(self):
        import fcntl
        stream = self.path.with_suffix(self.path.suffix+'.migration.lock').open('a+')
        try:
            fcntl.flock(stream,fcntl.LOCK_EX)
            self._migrate_locked()
        finally:
            stream.close()
    def _migrate_locked(self):
        with self.db() as db:
            current = db.execute("PRAGMA user_version").fetchone()[0]
            if current not in (0, HEAD):
                raise RuntimeError("DBG-M-003 migration head mismatch")
            if current == 0:
                db.executescript("BEGIN IMMEDIATE;" + SCHEMA)
                for table in ("events", "evaluations", "results", "checkpoints", "checks", "releases", "approvals"):
                    for action in ("UPDATE", "DELETE"):
                        db.execute(f"CREATE TRIGGER {table}_{action.lower()} BEFORE {action} ON {table} "
                                   "BEGIN SELECT RAISE(ABORT,'immutable evidence'); END")
                db.execute(f"PRAGMA user_version={HEAD}")
    def _event(self, db, identifier, kind, payload, correlation=None):
        db.execute("INSERT INTO events(aggregate_id,correlation_id,type,at,payload) VALUES(?,?,?,?,?)",
                   (identifier, correlation or identifier, kind, time.time(), canonical(redact(payload)).decode()))
    def event(self, identifier, kind, payload, correlation=None):
        with self.db() as db:
            self._event(db, identifier, kind, payload, correlation)
    def events(self, identifier, after=0, limit=200):
        if not 0 <= after or not 1 <= limit <= 500:
            raise ValueError("Invalid event page")
        with self.db() as db:
            rows = db.execute("SELECT * FROM events WHERE aggregate_id=? AND seq>? ORDER BY seq LIMIT ?",
                              (identifier, after, limit)).fetchall()
        return [Event(seq=r['seq'], aggregate_id=r['aggregate_id'], correlation_id=r['correlation_id'],
                      type=r['type'], at=r['at'], payload=json.loads(r['payload'])).model_dump() for r in rows]
    @diagnosed('M3','ledger.submit')
    def submit(self, key, payload, correlation=None):
        if not isinstance(key, str) or not 1 <= len(key) <= 120:
            raise ValueError("Idempotency key required")
        request_hash = digest(payload)
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT id,request_hash FROM jobs WHERE idem=?", (key,)).fetchone()
            if existing:
                if existing['request_hash'] != request_hash:
                    raise ValueError("Idempotency key reused with different input")
                return existing['id']
            identifier = 'MRUN-' + uuid.uuid4().hex
            db.execute("INSERT INTO jobs(id,idem,request_hash,payload,state) VALUES(?,?,?,?,?)",
                       (identifier, key, request_hash, canonical(payload).decode(), "queued"))
            self._event(db, identifier, "queued", {"request_hash": request_hash}, correlation)
        return identifier
    def get(self, identifier):
        with self.db() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (identifier,)).fetchone()
        if not row:
            raise KeyError(identifier)
        return {**dict(row), 'payload': json.loads(row['payload'])}
    @diagnosed('M3','ledger.configure')
    def configure(self, identifier, config_hash):
        if not isinstance(config_hash,str) or len(config_hash)!=64 or any(c not in '0123456789abcdef' for c in config_hash):
            raise ValueError('Immutable configuration hash required')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT state,payload FROM jobs WHERE id=?',(identifier,)).fetchone()
            if not row or row['state']!='queued' or json.loads(row['payload']).get('environment',{}).get('adapter')!='nanobot':
                raise ValueError('Only a queued native task can be configured')
            old=db.execute('SELECT hash FROM checkpoints WHERE job_id=? AND ordinal=-1',(identifier,)).fetchone()
            if old:return old[0]
            db.execute('INSERT INTO checkpoints VALUES(?,-1,?)',(identifier,config_hash))
            self._event(db,identifier,'configuration.frozen',{'config_hash':config_hash})
            return config_hash
    @diagnosed('M3','ledger.claim-id')
    def claim_id(self, identifier, owner, seconds=30):
        if type(seconds) is not int or not 1<=seconds<=3600:
            raise ValueError('Invalid lease')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM jobs WHERE id=? AND state=\'queued\'',(identifier,)).fetchone()
            if not row:return None
            if json.loads(row['payload']).get('environment',{}).get('adapter')=='nanobot' and not db.execute(
                    'SELECT 1 FROM checkpoints WHERE job_id=? AND ordinal=-1',(identifier,)).fetchone():
                raise ValueError('Native configuration must be frozen before dispatch')
            token=owner+':'+secrets.token_hex(8)
            db.execute('UPDATE jobs SET state=\'running\',owner=?,lease=?,fence=fence+1 WHERE id=?',
                       (token,time.time()+seconds,identifier))
            self._event(db,identifier,'running',{'owner':owner,'fence':row['fence']+1})
            return {**dict(row),'payload':json.loads(row['payload']),'owner':token,'fence':row['fence']+1}
    @diagnosed('M3','ledger.claim')
    def claim(self, owner, seconds=30, adapter=None):
        if not 1 <= seconds <= 3600:
            raise ValueError("Invalid lease")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM jobs WHERE state='queued' AND (? IS NULL OR "
                             "json_extract(payload,'$.environment.adapter')=?) ORDER BY rowid LIMIT 1",
                             (adapter,adapter)).fetchone()
            if not row:
                return None
            token = owner + ':' + secrets.token_hex(8)
            db.execute("UPDATE jobs SET state='running',owner=?,lease=?,fence=fence+1 WHERE id=?",
                       (token, time.time()+seconds, row['id']))
            self._event(db, row['id'], "running", {"owner": owner, "fence": row['fence']+1})
            return {**dict(row), 'payload': json.loads(row['payload']), 'owner': token, 'fence': row['fence']+1}
    def _owned(self, db, identifier, owner, fence):
        row = db.execute("SELECT * FROM jobs WHERE id=?", (identifier,)).fetchone()
        if not row or row['owner'] != owner or row['fence'] != fence or row['state'] in TERMINAL or row['lease'] < time.time():
            raise RuntimeError("Stale worker lease or cancelled job")
        return row
    def heartbeat(self, job, seconds=30):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._owned(db, job['id'], job['owner'], job['fence'])
            db.execute("UPDATE jobs SET lease=? WHERE id=?", (time.time()+seconds, job['id']))
    @diagnosed('M3','ledger.transition')
    def transition(self, identifier, state, job=None):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM jobs WHERE id=?", (identifier,)).fetchone()
            if not row:
                raise KeyError(identifier)
            if state not in TRANSITIONS.get(row['state'], set()):
                raise ValueError("Invalid lifecycle transition")
            if state!='cancelled' or row['state'] not in ('draft','queued'):
                if job is None:
                    raise ValueError("Worker lease required")
                self._owned(db, identifier, job['owner'], job['fence'])
            db.execute("UPDATE jobs SET state=? WHERE id=?", (state, identifier))
            self._event(db, identifier, state, {})
    @diagnosed('M3','ledger.cancel-request')
    def request_cancel(self, identifier):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT state FROM jobs WHERE id=?',(identifier,)).fetchone()
            if not row:raise KeyError(identifier)
            if row['state'] in TERMINAL or row['state']=='cancelling':return row['state']
            state='cancelled' if row['state'] in ('draft','queued') else 'cancelling'
            db.execute('UPDATE jobs SET state=? WHERE id=?',(state,identifier))
            self._event(db,identifier,'cancel.requested',{'state':state,'cleanup_pending':state=='cancelling'})
            if state=='cancelled':self._event(db,identifier,'cancelled',{'dispatched':False})
            return state
    @diagnosed('M3','ledger.gui-restart')
    def interrupt_gui(self, identifier, fence, run_id):
        """Called only by the GUI supervisor holding the exclusive runtime lock."""
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM jobs WHERE id=?',(identifier,)).fetchone()
            if not row:raise KeyError(identifier)
            payload=json.loads(row['payload'])
            if (payload.get('environment',{}).get('adapter')!='gepa' or payload.get('run_id')!=run_id or
                    row['fence']!=fence or row['state'] not in ('running','evaluating','cancelling')):
                raise ValueError('GUI recovery identity/fence mismatch')
            db.execute("UPDATE jobs SET state='interrupted',fence=fence+1 WHERE id=?",(identifier,))
            self._event(db,identifier,'interrupted',{'reason':'exclusive GUI supervisor restarted; no external-call replay'})
    @diagnosed('M3','ledger.complete')
    def complete(self, job, result):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._owned(db, job['id'], job['owner'], job['fence'])
            if row['state'] != 'evaluating':
                raise ValueError("Evaluate before completion")
            db.execute("INSERT INTO results VALUES(?,?,?)", (job['id'], job['fence'], canonical(result).decode()))
            db.execute("UPDATE jobs SET state='completed' WHERE id=?", (job['id'],))
            self._event(db, job['id'], "completed", {"result_hash": digest(result)})
    @diagnosed('M3','ledger.reconcile')
    def reconcile(self):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("SELECT id FROM jobs WHERE state IN ('running','evaluating','cancelling') AND lease<?",
                              (time.time(),)).fetchall()
            for row in rows:
                db.execute("UPDATE jobs SET state='interrupted',fence=fence+1 WHERE id=?", (row['id'],))
                self._event(db, row['id'], "interrupted", {"reason": "expired lease; no automatic model retry"})
        return len(rows)
    @diagnosed('M3','ledger.resume')
    def resume(self, identifier, expected_hash):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM jobs WHERE id=?", (identifier,)).fetchone()
            if not row or row['state'] != 'interrupted' or row['request_hash'] != expected_hash:
                raise ValueError("Resume requires same snapshot and interrupted state")
            if json.loads(row['payload']).get('environment',{}).get('adapter') in ('nanobot','gepa'):
                raise ValueError('Native interrupted request requires evidence review; automatic model replay is forbidden')
            db.execute("UPDATE jobs SET state='queued',owner=NULL,lease=NULL,fence=fence+1 WHERE id=?", (identifier,))
            self._event(db, identifier, "resumed", {"external_call_may_repeat": True})
    @diagnosed('M3','ledger.checkpoint')
    def checkpoint(self, job, ordinal, identifier):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._owned(db, job['id'], job['owner'], job['fence'])
            row = db.execute("SELECT hash FROM checkpoints WHERE job_id=? AND ordinal=?", (job['id'], ordinal)).fetchone()
            if row:
                if row[0] != identifier:
                    raise ValueError("Checkpoint changed")
                return
            db.execute("INSERT INTO checkpoints VALUES(?,?,?)", (job['id'], ordinal, identifier))
    @diagnosed('M3','ledger.evaluation')
    def evaluation(self, value):
        value = Evaluation.model_validate(value).model_dump()
        with self.db() as db:
            db.execute("INSERT INTO evaluations VALUES(?,?)", (value['id'], canonical(value).decode()))
    @diagnosed('M3','ledger.check')
    def check(self, value):
        value = StepCheck.model_validate(value).model_dump()
        with self.db() as db:
            db.execute("INSERT INTO checks VALUES(?,?)", (value['id'], canonical(value).decode()))
    @diagnosed('M3','ledger.backup')
    def backup(self, destination):
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db, sqlite3.connect(destination) as target:
            db.backup(target)
        with sqlite3.connect(destination) as check:
            if check.execute("PRAGMA integrity_check").fetchone()[0] != 'ok':
                raise RuntimeError("Backup integrity failure")
