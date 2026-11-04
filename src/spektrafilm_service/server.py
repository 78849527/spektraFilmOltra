"""本地 HTTP 服务：只绑 127.0.0.1，用每次启动随机生成的令牌鉴权。"""

from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from spektrafilm_service import catalog
from spektrafilm_service.grade_api import GradeApi
from spektrafilm_service.jobs import JobQueue
from spektrafilm_service.library_api import LibraryApi
from spektrafilm_service.session import ServiceSession

_JOB_PATH = re.compile(r'^/v1/jobs/([^/]+)$')
_JOB_CANCEL_PATH = re.compile(r'^/v1/jobs/([^/]+)/cancel$')


class Api:
    def __init__(self) -> None:
        self.queue = JobQueue()
        self.session = ServiceSession(self.queue)
        self.library = LibraryApi()
        self.grade = GradeApi(self.queue, self.session)

    def handle(self, method: str, path: str, body: dict[str, Any] | None) -> tuple[int, dict[str, Any]]:
        body = body or {}
        if method == 'GET' and path == '/v1/health':
            return 200, {'ready': True}

        if method == 'GET' and path == '/v1/bootstrap':
            return 200, catalog.bootstrap()

        if method == 'GET' and path == '/v1/state':
            return 200, {'state': self.session.state_dict()}

        if method == 'POST' and path == '/v1/state':
            self.session.apply_state(body.get('state'))
            return 200, {'state': self.session.state_dict(), **self.session.quick_payload()}

        if method == 'GET' and path == '/v1/quick':
            return 200, self.session.quick_payload()

        if method == 'POST' and path == '/v1/quick/axis':
            return 200, self.session.set_quick_axis(
                str(body.get('axis') or ''),
                float(body.get('value') or 0.0),
            )

        if method == 'POST' and path == '/v1/quick/reset':
            return 200, self.session.reset_quick()

        if method == 'POST' and path == '/v1/reset':
            return 200, self.session.reset_state()

        if method == 'GET' and path == '/v1/photo':
            return 200, {'photo': self.session.photo_dict()}

        if method == 'POST' and path == '/v1/photos/open':
            photo_path = str(body.get('path') or '')
            if not photo_path:
                return 400, {'error': '缺少图片路径'}
            return 200, self.session.open_photo(photo_path, str(body.get('item_id') or ''))

        if method == 'POST' and path == '/v1/preview':
            scale = float(body.get('scale') or 0.5)
            job = self.session.submit_preview(scale)
            return 200, {'job_id': job.id}

        if method == 'POST' and path == '/v1/preview/fast':
            scale = float(body.get('scale') or 0.5)
            if body.get('force_precise'):
                job = self.session.submit_preview(scale)
            else:
                job = self.session.submit_fast_preview(scale)
            return 200, {'job_id': job.id}

        if method == 'POST' and path == '/v1/preview/preflight':
            return 200, self.session.preflight(int(body.get('edge') or 256))

        if method == 'POST' and path == '/v1/preview/cancel':
            self.session.cancel_preview()
            return 200, {'ok': True}

        if method == 'POST' and path == '/v1/export':
            job = self.session.submit_export(body.get('settings'))
            return 200, {'job_id': job.id}

        if method == 'POST' and path == '/v1/handoff':
            job = self.session.submit_handoff()
            return 200, {'job_id': job.id}

        if method == 'GET' and path == '/v1/library':
            return 200, self.library.snapshot()

        if method == 'POST' and path == '/v1/library/scan':
            return 200, self.library.scan(str(body.get('path') or ''))

        if method == 'POST' and path == '/v1/library/photos':
            return 200, self.library.add_photos([str(item) for item in body.get('paths') or []])

        if method == 'POST' and path == '/v1/library/remove':
            return 200, self.library.remove([str(item) for item in body.get('ids') or []])

        if method == 'POST' and path == '/v1/library/mark':
            return 200, self.library.mark(
                str(body.get('id') or ''),
                favorite=body.get('favorite'),
                color=body.get('color'),
            )

        if method == 'POST' and path == '/v1/library/thumb':
            return 200, self.library.thumb(str(body.get('id') or ''))

        if method == 'POST' and path == '/v1/library/state':
            item = self.library.item(str(body.get('id') or ''))
            if item is None:
                return 404, {'error': '照片不在库中'}
            saved = self.library.save_state(
                item.id,
                body.get('state'),
                film_stock=str(body.get('film_stock') or ''),
                print_paper=str(body.get('print_paper') or ''),
            )
            return 200, saved

        if method == 'GET' and path == '/v1/grade/presets':
            return 200, self.grade.preset_payload()

        if method == 'POST' and path == '/v1/grade/presets':
            return 200, self.grade.save_preset(str(body.get('name') or ''), body.get('recipe') or {})

        if method == 'POST' and path == '/v1/grade/presets/rename':
            return 200, self.grade.rename_preset(str(body.get('id') or ''), str(body.get('name') or ''))

        if method == 'POST' and path == '/v1/grade/presets/delete':
            return 200, self.grade.delete_preset(str(body.get('id') or ''))

        if method == 'GET' and path == '/v1/grade/luts':
            return 200, self.grade.luts()

        if method == 'POST' and path == '/v1/grade/luts/import':
            return 200, self.grade.import_lut(str(body.get('path') or ''))

        if method == 'POST' and path == '/v1/grade/luts/remove':
            return 200, self.grade.remove_lut(str(body.get('path') or ''))

        if method == 'POST' and path == '/v1/grade/preview/cancel':
            self.grade.cancel_preview()
            return 200, {'ok': True}

        if method == 'POST' and path == '/v1/grade/preview':
            job = self.grade.submit_preview(
                str(body.get('handoff') or ''),
                body.get('recipe') or {},
                int(body.get('edge') or 1600),
            )
            return 200, {'job_id': job.id}

        if method == 'POST' and path == '/v1/grade/export':
            job = self.grade.submit_export(
                str(body.get('handoff') or ''),
                body.get('recipe') or {},
                body.get('settings') or {},
                str(body.get('name') or ''),
            )
            return 200, {'job_id': job.id}

        match = _JOB_PATH.match(path)
        if method == 'GET' and match:
            job = self.queue.get(match.group(1))
            if job is None:
                return 404, {'error': '任务不存在'}
            return 200, job.to_dict()

        match = _JOB_CANCEL_PATH.match(path)
        if method == 'POST' and match:
            if not self.queue.cancel(match.group(1)):
                return 404, {'error': '任务不存在'}
            return 200, {'ok': True}

        return 404, {'error': f'未知接口：{method} {path}'}


def make_server(*, port: int, token: str) -> tuple[ThreadingHTTPServer, Api]:
    api = Api()

    class Handler(BaseHTTPRequestHandler):
        server_version = 'SpektrafilmService/0.1'

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - 基类签名
            return

        def _send(self, status: int, payload: dict[str, Any]) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Spektra-Token')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.end_headers()
            self.wfile.write(data)

        def do_OPTIONS(self) -> None:  # noqa: N802 - 基类签名
            self._send(204, {})

        def do_GET(self) -> None:  # noqa: N802 - 基类签名
            self._dispatch('GET')

        def do_POST(self) -> None:  # noqa: N802 - 基类签名
            self._dispatch('POST')

        def _dispatch(self, method: str) -> None:
            provided = self.headers.get('X-Spektra-Token', '')
            if provided != token:
                self._send(401, {'error': '令牌无效'})
                return
            length = int(self.headers.get('Content-Length') or 0)
            body: dict[str, Any] | None = None
            if length:
                try:
                    body = json.loads(self.rfile.read(length).decode('utf-8'))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    self._send(400, {'error': '请求体不是合法 JSON'})
                    return
            path = urlparse(self.path).path
            try:
                status, payload = api.handle(method, path, body)
            except (OSError, ValueError, RuntimeError, TypeError) as exc:
                self._send(500, {'error': f'{type(exc).__name__}: {exc}'})
                return
            except Exception as exc:  # noqa: BLE001 - 不让异常打断服务
                self._send(500, {'error': f'{type(exc).__name__}: {exc}'})
                return
            self._send(status, payload)

    server = ThreadingHTTPServer(('127.0.0.1', int(port)), Handler)
    server.daemon_threads = True
    return server, api


__all__ = ['Api', 'make_server']
