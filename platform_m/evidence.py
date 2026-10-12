"""Canonical serialization, verified CAS, redacted support data."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()

def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()

def redact(value):
    if isinstance(value, dict):
        return {k: "[REDACTED]" if re.search(r"secret|token|password|authorization|api.?key", k, re.I)
                else redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r"(?i)(bearer\s+)[^\s\"']+", r"\1[REDACTED]", value)
        value = re.sub(r"(?i)((?:token|password|secret|api[_-]?key)\s*[=:]\s*)[^\s,;\"']+",
                       r"\1[REDACTED]", value)
        return re.sub(r"https?://[^\s/@]+:[^\s/@]+@", "https://[REDACTED]@", value)
    return value

def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

class Artifacts:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
    def path(self, identifier):
        if not re.fullmatch(r"[a-f0-9]{64}", identifier):
            raise ValueError("Invalid artifact hash")
        target = self.root / identifier[:2] / identifier
        if target.is_symlink() or target.parent.is_symlink():
            raise ValueError("Artifact symlinks are forbidden")
        return target
    def put(self, value):
        raw = canonical(value)
        identifier = hashlib.sha256(raw).hexdigest()
        target = self.path(identifier)
        if target.exists():
            self.get(identifier)
        else:
            atomic_write(target, raw)
        return identifier
    def get(self, identifier):
        raw = self.path(identifier).read_bytes()
        if hashlib.sha256(raw).hexdigest() != identifier:
            raise ValueError("Artifact integrity failure")
        return json.loads(raw)
