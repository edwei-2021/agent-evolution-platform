#!/usr/bin/env python3
"""Serve only the public dist directory, without traversing external symlinks."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import argparse
import sys
import tempfile

DIST = Path(__file__).resolve().parents[1] / 'dist'


class GuiHandler(SimpleHTTPRequestHandler):
    def send_head(self):
        target = Path(self.translate_path(self.path)).resolve()
        if not target.is_relative_to(Path(self.directory).resolve()):
            self.send_error(404)
            return None
        # Avoid public directory listings; ordinary static assets remain accessible.
        if target.is_dir():
            index = (target / 'index.html').resolve()
            if not index.is_relative_to(Path(self.directory).resolve()) or not index.is_file():
                self.send_error(404)
                return None
        return super().send_head()

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        super().end_headers()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8080)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error('--port must be between 1 and 65535')
    if sys.version_info < (3, 11):
        parser.error('Python 3.11+ required')
    if not (DIST / 'index.html').is_file():
        parser.error('dist/index.html is missing')
    try:
        server = ThreadingHTTPServer(('127.0.0.1', args.port), partial(GuiHandler, directory=str(DIST)))
    except OSError as exc:
        print(f'Cannot start GUI on port {args.port}: {exc}. Try --port 8081.', file=sys.stderr)
        return 1
    print(f'nanobot GEPA MVP — GUI demo\nWorkspace: {Path.cwd()}\nTemp: {tempfile.gettempdir()}\nOpen http://localhost:{args.port}\nPress Ctrl+C to stop. No model calls; records are browser-local.', flush=True)
    with server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
