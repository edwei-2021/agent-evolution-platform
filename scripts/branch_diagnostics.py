"""Bounded branch-location diagnostics; no raw arguments, payloads or error bodies."""
from functools import wraps
from pathlib import Path
import time
import traceback


def record(root, phase, branch, outcome, *, identifier=None, error=None, **facts):
    try:
        return _record(root, phase, branch, outcome, identifier=identifier, error=error, **facts)
    except Exception:
        # Diagnostics are supplementary; preserve the business result/original exception.
        return False


def _record(root, phase, branch, outcome, *, identifier=None, error=None, **facts):
    from diagnostic_log import DiagnosticLog
    safe = {k: v for k, v in facts.items() if isinstance(v, (bool, int, float)) or v is None}
    if error is not None:
        safe.update(exceptionType=type(error).__name__,
                    frames=[{'file': Path(f.filename).name, 'line': f.lineno, 'function': f.name}
                            for f in traceback.extract_tb(error.__traceback__)[-8:]])
    return DiagnosticLog(root).write('workflows', 'branch.decision',
        level='ERROR' if outcome == 'failed' else 'INFO', correlation_id=identifier,
        phase=phase, branch=branch, outcome=outcome, **safe)


def diagnosed(phase, branch):
    """Instrument mutations without changing exceptions, persistence or results."""
    def decorate(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            owner = args[0] if args else None
            root = getattr(owner, 'root', None)
            if root is None and hasattr(owner, 'store'):
                root = owner.store.path.parent.parent.parent if owner.store.path.parent.name=='m' else owner.store.path.parent
            if root is None and hasattr(owner, 'path'):
                root = owner.path.parent.parent.parent if owner.path.parent.name=='m' else owner.path.parent
            if root is None and isinstance(owner, Path):
                root = owner.parents[2] if owner.parent.name=='runs' and owner.parent.parent.name=='.local' else owner
            identifier = None
            if len(args) > 1 and isinstance(args[1], dict):
                identifier = args[1].get('id')
            elif len(args) > 1 and isinstance(args[1], str) and args[1].startswith(('MRUN-', 'RUN-')):
                identifier = args[1]
            start = time.monotonic()
            record(root, phase, branch, 'started', identifier=identifier)
            try:
                result = fn(*args, **kwargs)
            except BaseException as exc:
                record(root, phase, branch, 'failed', identifier=identifier, error=exc,
                       elapsedMs=round((time.monotonic()-start)*1000, 3))
                raise
            record(root, phase, branch, 'completed', identifier=identifier,
                   elapsedMs=round((time.monotonic()-start)*1000, 3), empty=result is None)
            return result
        return wrapped
    return decorate
