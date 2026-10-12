"""Bounded, local, cross-process debug journal. Never records HTTP bodies/headers."""
from datetime import datetime, timezone
from contextlib import contextmanager
import json
from pathlib import Path
import re
import sqlite3

MODULES = ('api', 'gui', 'runtime', 'ollama', 'llm', 'skills', 'nanobot','gepa',
           'coordinator', 'worker', 'reflector', 'evaluator', 'reviewer')
LEVELS = ('DEBUG', 'INFO', 'WARNING', 'ERROR')
RETENTION = 10000


def redact(value):
    text = str(value)
    text = re.sub(r'(?i)(bearer\s+)[^\s"\',;]+', r'\1[REDACTED]', text)
    text = re.sub(r'(?i)((?:api[_-]?key|token|password|secret|authorization|x-lab-token)["\']?\s*[:=]\s*["\']?)[^\s"\',;}]+', r'\1[REDACTED]', text)
    return text


def safe_details(value, depth=0):
    if depth > 4: return '[DEPTH LIMIT]'
    if isinstance(value, dict):
        return {str(k)[:80]: '[REDACTED]' if re.search(r'(?i)token|secret|password|authorization|api.?key|^(prompt|content|reasoning|reasoning_content|messages)$', str(k))
                else safe_details(v, depth + 1) for k, v in list(value.items())[:30]}
    if isinstance(value, list): return [safe_details(v, depth + 1) for v in value[:30]]
    if value is None or isinstance(value, (bool, int, float)): return value
    return redact(value)[:1000]


class DebugLog:
    def __init__(self, root, retention=RETENTION):
        self.path = Path(root) / '.local/debug.sqlite3'
        self.retention = retention
        self.available = True
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.connect() as db:
                db.execute('PRAGMA journal_mode=WAL')
                db.execute('CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, module TEXT NOT NULL, level TEXT NOT NULL, run_id TEXT, message TEXT NOT NULL, details TEXT NOT NULL)')
                db.execute('CREATE INDEX IF NOT EXISTS logs_module ON logs(module, id)')
                db.execute('CREATE INDEX IF NOT EXISTS logs_run ON logs(run_id, id)')
        except (OSError, sqlite3.Error): self.available = False

    @contextmanager
    def connect(self):
        db = None
        try:
            db = sqlite3.connect(self.path, timeout=5)
            with db: yield db
        except sqlite3.Error as exc: raise OSError('Debug journal storage failed: ' + str(exc)) from exc
        finally:
            if db is not None: db.close()

    def append(self, module, level, message, run_id=None, details=None):
        if module not in MODULES or level not in LEVELS:
            raise ValueError('Unknown log module or level')
        if not self.available: return False
        encoded = json.dumps(safe_details(details or {}), ensure_ascii=False)
        if len(encoded) > 4096: encoded = json.dumps({'truncated': True, 'preview': encoded[:3500]}, ensure_ascii=False)
        try:
            with self.connect() as db:
                db.execute('INSERT INTO logs(at,module,level,run_id,message,details) VALUES (?,?,?,?,?,?)',
                    (datetime.now(timezone.utc).isoformat(), module, level, run_id, redact(message)[:2048], encoded))
                db.execute('DELETE FROM logs WHERE id <= COALESCE((SELECT id FROM logs ORDER BY id DESC LIMIT 1 OFFSET ?), 0)', (self.retention,))
        except (OSError, sqlite3.Error):
            # Debugging storage must not change model scoring or dispatch behavior.
            return False
        return True

    def list(self, module='', level='', run_id='', query='', before=None, limit=100):
        if not self.available: raise OSError('Local debug journal is unavailable; inspect disk permissions and free space')
        if module and module not in MODULES or level and level not in LEVELS:
            raise ValueError('Unknown log filter')
        if type(limit) is not int or not 1 <= limit <= 500 or before is not None and (type(before) is not int or before < 1):
            raise ValueError('Invalid log page size or cursor')
        if not isinstance(query, str) or len(query) > 200 or not isinstance(run_id, str) or len(run_id) > 80:
            raise ValueError('Log query/run ID is too long')
        clauses, args = [], []
        for column, value in [('module', module), ('level', level), ('run_id', run_id)]:
            if value: clauses.append(column + '=?'); args.append(value)
        if query:
            clauses.append('instr(lower(message || details || COALESCE(run_id,\'\')),lower(?))>0'); args.append(query)
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        with self.connect() as db:
            matched = db.execute('SELECT COUNT(*) FROM logs' + where, args).fetchone()[0]
            retained, oldest, newest = db.execute('SELECT COUNT(*),MIN(id),MAX(id) FROM logs').fetchone()
            if before is not None: clauses.append('id<?'); args.append(before)
            page_where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
            rows = db.execute('SELECT id,at,module,level,run_id,message,details FROM logs' + page_where + ' ORDER BY id DESC LIMIT ?', [*args, limit + 1]).fetchall()
        records = [dict(zip(('id','at','module','level','runId','message','details'), row)) for row in rows[:limit]]
        for record in records: record['details'] = json.loads(record['details'])
        return {'schemaVersion': 1, 'records': records, 'matched': matched, 'retained': retained,
                'retentionLimit': self.retention, 'oldestId': oldest, 'newestId': newest,
                'nextBefore': records[-1]['id'] if len(rows) > limit else None,
                'modules': list(MODULES), 'levels': list(LEVELS),
                'serverTime': datetime.now(timezone.utc).isoformat()}
