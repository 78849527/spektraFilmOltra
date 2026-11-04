from __future__ import annotations

import numpy as np
import pytest
from scipy.ndimage import map_coordinates

from spektrafilm_service import lut_preview


def _scipy_lookup(image, lut):
    height, width, _ = image.shape
    flat = image.reshape(-1, 3)
    out = np.empty_like(flat)
    n = lut.shape[0]
    coords = np.clip(flat, 0.0, 1.0) * (n - 1)
    for channel in range(3):
        out[:, channel] = map_coordinates(
            lut[..., channel], coords.T, order=1, mode="nearest"
        )
    return out.reshape(height, width, 3)


def test_apply_lut_matches_scipy_trilinear():
    rng = np.random.default_rng(3)
    lut = rng.random((17, 17, 17, 3), dtype=np.float32)
    image = rng.random((24, 32, 3), dtype=np.float32)

    expected = _scipy_lookup(image, lut)
    got = lut_preview.apply_lut(image, lut)

    assert got.dtype == np.float32
    np.testing.assert_allclose(got, expected, atol=1e-5)


def test_fused_shaper_matches_two_pass():
    rng = np.random.default_rng(5)
    lut = rng.random((17, 17, 17, 3), dtype=np.float32)
    image = (rng.random((20, 24, 3)) * 2.0).astype(np.float32)

    expected = lut_preview.apply_lut(lut_preview.shaper_encode(image), lut)
    got = lut_preview._apply_lut_shaped(image, lut)

    np.testing.assert_allclose(got, expected, atol=1e-5)


def test_shaper_encode_clamps_and_is_monotonic():
    values = np.array(
        [0.0, 1e-9, 2.0 ** lut_preview.SHAPER_LO_EV, 0.18, 1.0, 4.0,
         2.0 ** lut_preview.SHAPER_HI_EV, 1e6],
        dtype=np.float32,
    )
    image = np.repeat(values[None, :, None], 3, axis=2)
    encoded = lut_preview.shaper_encode(image)[0, :, 0]

    assert np.all(encoded >= 0.0) and np.all(encoded <= 1.0)
    assert np.all(np.diff(encoded) >= -1e-6)


def test_apply_lut_rejects_bad_shapes():
    with pytest.raises(ValueError):
        lut_preview.apply_lut(np.zeros((2, 2)), np.zeros((2, 2, 2, 3)))
    with pytest.raises(ValueError):
        lut_preview.apply_lut(np.zeros((2, 2, 3)), np.zeros((2, 3, 4, 3)))
    with pytest.raises(ValueError):
        lut_preview.apply_lut(np.zeros((2, 2, 3)), np.zeros((1, 1, 1, 3)))


def test_cache_hit_skips_rebake(monkeypatch):
    calls = []

    def fake_bake(state, resolution):
        calls.append(resolution)
        return object()

    monkeypatch.setattr(lut_preview, "_bake_bundle", fake_bake)

    from spektrafilm_service.session import SessionState

    state = SessionState().gui_state
    cache = lut_preview.PreviewLutCache(resolution=5)
    first = cache.get(state)
    second = cache.get(state)

    assert first is second
    assert len(calls) == 1


def test_cache_key_ignores_outside_axes(monkeypatch):
    calls = []

    def fake_bake(state, resolution):
        calls.append(resolution)
        return object()

    monkeypatch.setattr(lut_preview, "_bake_bundle", fake_bake)

    from spektrafilm_gui.state import clone_gui_state
    from spektrafilm_service.session import SessionState

    state = SessionState().gui_state
    moved = clone_gui_state(state)
    moved.camera.exposure_compensation_ev = 1.0
    moved.simulation.enlarger.print_exposure = 0.8
    moved.simulation.enlarger.print_exposure_compensation = not (
        state.simulation.enlarger.print_exposure_compensation
    )

    cache = lut_preview.PreviewLutCache(resolution=5)
    cache.get(state)
    cache.get(moved)

    assert len(calls) == 1


def test_bake_bundle_has_four_finite_tables():
    from spektrafilm_service.session import SessionState

    bundle = lut_preview._bake_bundle(SessionState().gui_state, 9)

    assert len(bundle.tables) == 4
    assert len(bundle.wires) == 6
    for table in bundle.tables:
        assert table.shape == (9, 9, 9, 3)
        assert table.dtype == np.float32
        assert np.isfinite(table).all()


def test_predict_chain_is_finite_with_offsets():
    from spektrafilm_service.session import SessionState

    bundle = lut_preview._bake_bundle(SessionState().gui_state, 9)
    source = np.full((8, 8, 3), 0.18, dtype=np.float32)

    out = bundle.predict(
        source,
        auto_ev=-0.5,
        exposure_ev=0.5,
        print_exposure=0.9,
        compensate=True,
    )

    assert out.shape == (8, 8, 3)
    assert out.dtype == np.float32
    assert np.isfinite(out).all()


def test_fast_preview_endpoint(tmp_path):
    import time
    from pathlib import Path

    from spektrafilm.utils.io import save_image_oiio
    from spektrafilm_service.server import Api

    rng = np.random.default_rng(0)
    image = (rng.random((48, 64, 3)) * 0.6).astype(np.float32)
    source = tmp_path / 'input.png'
    save_image_oiio(str(source), image, bit_depth=16, color_space='sRGB', cctf_encoding=True)

    api = Api()
    api.session.open_photo(str(source))

    def wait(job_id):
        deadline = time.time() + 120.0
        while time.time() < deadline:
            job = api.queue.get(job_id)
            if job is not None and job.state in {'done', 'failed', 'cancelled'}:
                return job
            time.sleep(0.05)
        raise TimeoutError(job_id)

    status, payload = api.handle('POST', '/v1/preview/fast', {'scale': 0.5})
    assert status == 200
    job = wait(payload['job_id'])
    assert job.state == 'done', job.error
    assert job.result['predicted'] is True
    assert Path(job.result['image_path']).is_file()
    assert (job.result['width'], job.result['height']) == (32, 24)

    status, again = api.handle('POST', '/v1/preview/fast', {'scale': 0.5})
    assert status == 200
    cached = wait(again['job_id'])
    assert cached.state == 'done', cached.error
    assert cached.result['image_path'] == job.result['image_path']

def _open_small(api, tmp_path):
    from spektrafilm.utils.io import save_image_oiio

    rng = np.random.default_rng(0)
    image = (rng.random((48, 64, 3)) * 0.6).astype(np.float32)
    source = tmp_path / 'input.png'
    save_image_oiio(str(source), image, bit_depth=16, color_space='sRGB', cctf_encoding=True)
    api.session.open_photo(str(source))


def _wait(api, job_id, timeout=120.0):
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        job = api.queue.get(job_id)
        if job is not None and job.state in {'done', 'failed', 'cancelled'}:
            return job
        time.sleep(0.05)
    raise TimeoutError(job_id)


def test_preflight_endpoint(tmp_path):
    from spektrafilm_service.server import Api

    api = Api()
    _open_small(api, tmp_path)

    status, payload = api.handle('POST', '/v1/preview/preflight', {'edge': 64})
    assert status == 200
    assert payload['edge'] == 64
    assert set(payload['model']) == {'max', 'p99', 'mean'}
    assert set(payload['effects']) == {'max', 'p99', 'mean'}
    assert payload['thresholds'] == {'max': 2.0, 'p99': 1.0}
    assert isinstance(payload['ok'], bool)
    assert payload['model']['p99'] >= 0.0


def test_fast_preview_force_precise(tmp_path):
    from spektrafilm_service.server import Api

    api = Api()
    _open_small(api, tmp_path)

    status, payload = api.handle(
        'POST', '/v1/preview/fast', {'scale': 0.5, 'force_precise': True}
    )
    assert status == 200
    job = _wait(api, payload['job_id'])
    assert job.state == 'done', job.error
    assert job.result['predicted'] is False