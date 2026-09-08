#!/usr/bin/env python3
"""Loopback-only project-health host with fixed, bounded CLI endpoints."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from project_health_knowledge import CONFIG, safe_file, write_json, validate_config, load_config

RUNTIME_HOST_TIMEOUT_SECONDS = 3690


def handler_factory(root: Path):
    token = secrets.token_urlsafe(32)
    operation = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def send(self, data, code=200, content_type='application/json; charset=utf-8'):
            body = data.encode('utf-8') if isinstance(data, str) else json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            inline = " 'unsafe-inline'" if urlsplit(self.path).path in ('/', '/latest.html') else ''
            self.send_header('Content-Security-Policy', f"default-src 'self'; script-src 'self'{inline}; style-src 'self'{inline}; object-src 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def allowed_host(self):
            return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

        def cli(self, action, args=(), request=None):
            if not operation.acquire(blocking=False):
                self.send({'reason': 'Another operation is running'}, 409)
                return
            try:
                script = 'project_health_runtime.py' if action == 'runtime' else 'project_health_knowledge.py'
                cmd = [sys.executable, str(Path(__file__).with_name(script)), '--repo-root', str(root), *args]
                if action != 'runtime':
                    cmd.insert(2, action)
                host_timeout = RUNTIME_HOST_TIMEOUT_SECONDS if action == 'runtime' else 240
                proc = subprocess.run(cmd, input=json.dumps(request) if request is not None else None,
                                      capture_output=True, text=True, encoding='utf-8', timeout=host_timeout)
                try:
                    payload = json.loads(proc.stdout)
                except ValueError:
                    payload = {'status': 'failed', 'reason': proc.stderr[-2000:] or 'Invalid CLI response'}
                self.send(payload, 200 if proc.returncode == 0 else 422)
            finally:
                operation.release()

        def do_GET(self):
            if not self.allowed_host():
                self.send({'reason': 'Invalid Host'}, 403)
                return
            parsed = urlsplit(self.path)
            params = parse_qs(parsed.query)
            try:
                if parsed.path == '/api/knowledge/session':
                    self.send({'token': token, 'service': 'project-health-knowledge-v1'})
                elif parsed.path == '/api/knowledge/status':
                    self.cli('status')
                elif parsed.path == '/api/knowledge/config':
                    self.send(load_config(root))
                elif parsed.path == '/api/knowledge/tasks':
                    self.cli('tasks', ['--page', params.get('page', ['1'])[0]])
                elif parsed.path == '/api/knowledge/task':
                    self.cli('task', ['--task-id', params.get('id', [''])[0]])
                elif parsed.path == '/api/knowledge/source':
                    self.cli('source', ['--path', params.get('path', [''])[0]])
                elif parsed.path in ('/knowledge', '/knowledge/'):
                    self.send(Path(__file__).with_name('project_health_knowledge.html').read_text(encoding='utf-8'),
                              content_type='text/html; charset=utf-8')
                elif parsed.path in ('/knowledge/app.js', '/knowledge/style.css'):
                    suffix = 'js' if parsed.path.endswith('.js') else 'css'
                    text = Path(__file__).with_name('project_health_knowledge.' + suffix).read_text(encoding='utf-8')
                    self.send(text, content_type='text/javascript' if suffix == 'js' else 'text/css')
                elif parsed.path in ('/', '/latest.html'):
                    # The existing dashboard has inline scripts/styles; retain its rendering behavior.
                    self.send((root / 'logs/ci/project-health/latest.html').read_text(encoding='utf-8'),
                              content_type='text/html; charset=utf-8')
                elif parsed.path.startswith('/api/'):
                    self.send({'reason': 'Not found'}, 404)
                else:
                    # Keep report JSON/Markdown links, but never serve private snapshots or directories.
                    relative = parsed.path.lstrip('/')
                    path = safe_file(root / 'logs/ci/project-health', relative)
                    if path.suffix not in ('.json', '.md', '.txt') or not path.is_file():
                        self.send({'reason': 'Not found'}, 404)
                    else:
                        self.send(path.read_text(encoding='utf-8'), content_type='text/plain; charset=utf-8')
            except Exception as exc:
                self.send({'status': 'failed', 'reason': str(exc)}, 422)

        def do_POST(self):
            origin = f'http://127.0.0.1:{self.server.server_port}'
            if (not self.allowed_host() or self.headers.get('Origin') != origin
                    or not secrets.compare_digest(self.headers.get('X-Project-Health-Token', ''), token)):
                self.send({'reason': 'Same-origin session token required'}, 403)
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 65536 or self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    raise ValueError('Expected bounded JSON request')
                request = json.loads(self.rfile.read(size))
                if not isinstance(request, dict):
                    raise ValueError('Expected JSON object')
                path = urlsplit(self.path).path
                if path == '/api/knowledge/scan':
                    self.cli('scan')
                elif path == '/api/knowledge/runtime':
                    godot_bin = os.environ.get('GODOT_BIN')
                    if not godot_bin:
                        raise ValueError('GODOT_BIN is required for runtime verification')
                    args = ['--godot-bin', godot_bin]
                    if request.get('task_id') is not None:
                        args.extend(['--task-id', str(request['task_id'])])
                    self.cli('runtime', args)
                elif path == '/api/knowledge/query':
                    self.cli('query', request=request)
                elif path == '/api/knowledge/config':
                    if not operation.acquire(blocking=False):
                        self.send({'reason': 'Another operation is running'}, 409)
                        return
                    try:
                        config = validate_config(root, request)
                        write_json(safe_file(root, CONFIG), config)
                        self.send({'status': 'saved', 'next_step': 'Scan main to apply the configuration'})
                    finally:
                        operation.release()
                else:
                    self.send({'reason': 'Not found'}, 404)
            except Exception as exc:
                self.send({'status': 'failed', 'reason': str(exc)}, 422)

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--port', type=int, required=True)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler_factory(args.repo_root.resolve()))
    server.serve_forever()


if __name__ == '__main__':
    main()
