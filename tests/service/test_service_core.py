from __future__ import annotations

import json
import threading
import time
import urllib.request

import numpy as np
import pytest

from spektrafilm.utils.io import save_image_oiio
from spektrafilm_service.jobs import JobQueue
from spektrafilm_service.server import Api, make_server


def _wait(queue: JobQueue, job_id: str, timeout: float = 120.0) -> object:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = queue.get(job_id)
        if job is not None and job.state in {'done', 'failed', 'cancelled'}:
            return job
        time.sleep(0.05)
    raise TimeoutError(job_id)


def _make_image(path) -> None:
    rng = np.random.default_rng(0)
    image = (rng.random((48, 64, 3)) * 0.6).astype(np.float32)
    save_image_oiio(str(path), image, bit_depth=16, color_space='sRGB', cctf_encoding=True)


def test_job_queue_supersedes_queued_preview() -> None:
    queue = JobQueue()
    release = threading.Event()
    started = threading.Event()

    def slow(_job) -> dict:
        started.set()
        release.wait(2.0)
        return {'ok': True}

    first = queue.submit('preview', slow)
    assert started.wait(5.0)

    second = queue.submit('preview', lambda job: {'ok': True}, supersede_kind='preview')
    third = queue.submit('preview', lambda job: {'ok': True}, supersede_kind='preview')
    release.set()

    _wait(queue, first.id)
    _wait(queue, second.id)
    _wait(queue, third.id)

    # 新的预览会连正在跑的旧预览一起作废，只保留最后一组参数。
    assert first.state == 'cancelled'
    assert second.state == 'cancelled'
    assert third.state == 'done'


def test_supersede_cancels_running_preview() -> None:
    queue = JobQueue()
    started = threading.Event()
    release = threading.Event()

    def slow(_job) -> dict:
        started.set()
        release.wait(2.0)
        return {'ok': True}

    first = queue.submit('preview', slow)
    assert started.wait(5.0)
    queue.submit('preview', lambda job: {'ok': True}, supersede_kind='preview')
    assert queue.is_cancelled(first)
    release.set()
    _wait(queue, first.id)
    assert first.state == 'cancelled'


def test_pipeline_cancels_between_nodes() -> None:
    from spektrafilm.runtime.topology import PipelineCancelled, run_topology, Node

    fired: list[str] = []

    def first(_image: object) -> object:
        fired.append('first')
        return 1

    def second(value: object) -> object:
        fired.append('second')
        return value

    topology = [
        Node(('in',), ('a',), first, 'first'),
        Node(('a',), ('out',), second, 'second'),
    ]
    with pytest.raises(PipelineCancelled):
        run_topology(topology, 'in', 'out', 0, cancel=lambda: True)
    assert fired == []


def test_export_is_not_cancelled_by_new_preview() -> None:
    queue = JobQueue()
    export = queue.submit('export', lambda job: {'ok': 'export'})
    queue.submit('preview', lambda job: {'ok': 'preview'}, supersede_kind='preview')
    _wait(queue, export.id)
    assert export.state == 'done'
    assert export.result == {'ok': 'export'}


def test_bootstrap_catalog_has_all_profiles() -> None:
    api = Api()
    status, payload = api.handle('GET', '/v1/bootstrap', None)
    assert status == 200
    assert len(payload['films']) == 20
    assert len(payload['papers']) == 8
    assert payload['quick_layout']
    assert 'state' in payload and 'export_settings' in payload


def test_preview_then_export_roundtrip(tmp_path) -> None:
    source = tmp_path / 'input.png'
    _make_image(source)
    api = Api()

    opened = api.session.open_photo(str(source))
    assert opened['width'] == 64 and opened['height'] == 48

    preview = api.session.submit_preview(0.5)
    preview_job = _wait(api.queue, preview.id)
    assert preview_job.state == 'done', preview_job.error
    image_path = preview_job.result['image_path']
    assert __import__('pathlib').Path(image_path).is_file()

    export = api.session.submit_export({
        'format': 'PNG',
        'bit_depth': 8,
        'long_edge': 0,
        'directory': str(tmp_path),
        'filename_template': '{name}_test',
    })
    export_job = _wait(api.queue, export.id)
    assert export_job.state == 'done', export_job.error
    assert __import__('pathlib').Path(export_job.result['path']).is_file()


def test_http_requires_token() -> None:
    server, api = make_server(port=0, token='secret')
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    base = f'http://{host}:{port}'
    try:
        request = urllib.request.Request(f'{base}/v1/health', headers={'X-Spektra-Token': 'secret'})
        with urllib.request.urlopen(request, timeout=5) as response:
            assert json.loads(response.read())['ready'] is True

        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(f'{base}/v1/health', timeout=5)
        assert error.value.code == 401
        del api
    finally:
        server.shutdown()
