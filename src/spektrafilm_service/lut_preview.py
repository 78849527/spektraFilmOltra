"""Fast LUT preview: 4-stage bake, cache and lookup (P2).

The full preview pipeline is split into four deterministic per-pixel stages
so that exposure sliders do not invalidate the baked tables:

    source -> [l1] -> log_e_film -> [l2] -> cmy_film
           -> [l3] -> log_e_print -> [l4] -> linear ProPhoto

Camera exposure, print exposure and the print-exposure compensation factor
are applied between stages as exact log-domain offsets.  Filtration, preflash
and the remaining per-pixel settings stay in the bake key.

Spatial and stochastic effects (grain, halation, USM, lens blur, glare)
cannot be represented by a static 3D LUT and are disabled.
"""

from __future__ import annotations

import json
from functools import lru_cache

import numpy as np
from numba import njit, prange

__all__ = [
    "apply_lut",
    "PreviewLutBundle",
    "PreviewLutCache",
    "measure_auto_ev",
    "warmup",
]


@njit(cache=True, inline="always")
def _shaped_index(v, lo, span, inv_span, ev_offset):
    if v < 1e-10:
        v = 1e-10
    e = np.log2(v) + ev_offset - lo
    if e < 0.0:
        e = 0.0
    elif e > span:
        e = span
    return e * inv_span


@njit(cache=True, inline="always")
def _lerp_cube(lut, i0, i1, j0, j1, k0, k1, fr, fg, fb, out, y, x):
    w00 = (np.float32(1.0) - fr) * (np.float32(1.0) - fg)
    w01 = (np.float32(1.0) - fr) * fg
    w10 = fr * (np.float32(1.0) - fg)
    w11 = fr * fg
    w000 = w00 * (np.float32(1.0) - fb)
    w001 = w00 * fb
    w010 = w01 * (np.float32(1.0) - fb)
    w011 = w01 * fb
    w100 = w10 * (np.float32(1.0) - fb)
    w101 = w10 * fb
    w110 = w11 * (np.float32(1.0) - fb)
    w111 = w11 * fb
    for c in range(3):
        out[y, x, c] = (
            w000 * lut[i0, j0, k0, c]
            + w001 * lut[i0, j0, k1, c]
            + w010 * lut[i0, j1, k0, c]
            + w011 * lut[i0, j1, k1, c]
            + w100 * lut[i1, j0, k0, c]
            + w101 * lut[i1, j0, k1, c]
            + w110 * lut[i1, j1, k0, c]
            + w111 * lut[i1, j1, k1, c]
        )


@njit(cache=True, inline="always")
def _cube_indices(value, scale, last):
    f = value * scale
    i0 = int(f)
    if i0 > last:
        i0 = last
    f = np.float32(f - i0)
    return i0, i0 + 1, f


@njit(cache=True, parallel=True, nogil=True)
def _trilinear_shaped(image, lut, out, lo, span, inv_span, ev_offset):
    height = image.shape[0]
    width = image.shape[1]
    n = lut.shape[0]
    scale = np.float32(n - 1)
    last = n - 2
    for y in prange(height):
        for x in range(width):
            r = _shaped_index(image[y, x, 0], lo, span, inv_span, ev_offset)
            g = _shaped_index(image[y, x, 1], lo, span, inv_span, ev_offset)
            b = _shaped_index(image[y, x, 2], lo, span, inv_span, ev_offset)
            i0, i1, fr = _cube_indices(r, scale, last)
            j0, j1, fg = _cube_indices(g, scale, last)
            k0, k1, fb = _cube_indices(b, scale, last)
            _lerp_cube(lut, i0, i1, j0, j1, k0, k1, fr, fg, fb, out, y, x)


@njit(cache=True, parallel=True, nogil=True)
def _trilinear(image, lut, out):
    height = image.shape[0]
    width = image.shape[1]
    n = lut.shape[0]
    scale = np.float32(n - 1)
    last = n - 2
    for y in prange(height):
        for x in range(width):
            r = image[y, x, 0]
            g = image[y, x, 1]
            b = image[y, x, 2]
            if r < 0.0:
                r = 0.0
            elif r > 1.0:
                r = 1.0
            if g < 0.0:
                g = 0.0
            elif g > 1.0:
                g = 1.0
            if b < 0.0:
                b = 0.0
            elif b > 1.0:
                b = 1.0
            i0, i1, fr = _cube_indices(r, scale, last)
            j0, j1, fg = _cube_indices(g, scale, last)
            k0, k1, fb = _cube_indices(b, scale, last)
            _lerp_cube(lut, i0, i1, j0, j1, k0, k1, fr, fg, fb, out, y, x)


def _check_shapes(image, lut):
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("image must have shape (H, W, 3)")
    if lut.ndim != 4 or lut.shape[3] != 3 or lut.shape[0] != lut.shape[1] or lut.shape[0] != lut.shape[2]:
        raise ValueError("lut must have shape (N, N, N, 3)")
    if lut.shape[0] < 2:
        raise ValueError("lut needs at least 2 samples per axis")


def apply_lut(image, lut):
    """Apply a 3D LUT indexed by ``[r, g, b]`` to a ``[0, 1]`` RGB image."""
    image = np.ascontiguousarray(np.asarray(image)[..., :3], dtype=np.float32)
    lut = np.ascontiguousarray(np.asarray(lut)[..., :3], dtype=np.float32)
    _check_shapes(image, lut)
    out = np.empty((image.shape[0], image.shape[1], 3), dtype=np.float32)
    _trilinear(image, lut, out)
    return out


def _apply_lut_shaped(image, lut, ev_offset=0.0):
    """Fused shaper-encode + trilinear lookup (one pass)."""
    image = np.ascontiguousarray(np.asarray(image)[..., :3], dtype=np.float32)
    lut = np.ascontiguousarray(np.asarray(lut)[..., :3], dtype=np.float32)
    _check_shapes(image, lut)
    out = np.empty((image.shape[0], image.shape[1], 3), dtype=np.float32)
    span = float(SHAPER_HI_EV - SHAPER_LO_EV)
    _trilinear_shaped(
        image, lut, out,
        np.float32(SHAPER_LO_EV), np.float32(span), np.float32(1.0 / span),
        np.float32(ev_offset),
    )
    return out

# ---------------------------------------------------------------------------
# Baking
# ---------------------------------------------------------------------------

SHAPER_LO_EV = -8.0
SHAPER_HI_EV = 6.0
DEFAULT_RESOLUTION = 45
PROPHOTO = "ProPhoto RGB"
EV_HEADROOM = 5.0
ENCODED_MAX = 2.0


@njit(cache=True, parallel=True, nogil=True)
def _shaper_kernel(image, out, lo, span):
    height = image.shape[0]
    width = image.shape[1]
    for y in prange(height):
        for x in range(width):
            for c in range(3):
                out[y, x, c] = _shaped_index(
                    image[y, x, c], lo, span, np.float32(1.0) / span, np.float32(0.0)
                )


def shaper_encode(image):
    """Map linear RGB (possibly > 1) into ``[0, 1]`` by log2 EV."""
    data = np.ascontiguousarray(image, dtype=np.float32)
    out = np.empty_like(data)
    span = np.float32(SHAPER_HI_EV - SHAPER_LO_EV)
    _shaper_kernel(data, out, np.float32(SHAPER_LO_EV), span)
    return out


def _to_table(values, resolution):
    table = np.asarray(values, dtype=np.float32).reshape(
        resolution, resolution, resolution, 3
    )
    # cube_grid is R-fastest, so C-order reshape yields [b, g, r].
    return np.ascontiguousarray(table.transpose(2, 1, 0, 3))


def _margin(lo, hi, *, pad=0.0, rel=0.02):
    span = hi - lo
    extra = span * rel + pad
    return lo - extra, hi + extra


def _bake_params(state):
    """Deterministic params with neutralised continuous axes.

    Camera EV, print exposure and print compensation are applied outside the
    tables, so they must be neutral while baking.
    """
    from spektrafilm_gui.params_mapper import build_params_from_state
    from spektrafilm.runtime.api import digest_params

    params = build_params_from_state(state)
    params.camera.auto_exposure = False
    params.camera.exposure_compensation_ev = 0.0
    params.debug.deactivate_spatial_effects = True
    params.debug.deactivate_stochastic_effects = True
    params.film_render.halation.boost_ev = 0.0
    params.scanner.white_correction = False
    params.scanner.black_correction = False
    params.scanner.unsharp_mask = (0.0, 0.0)
    params.enlarger.print_exposure = 1.0
    params.enlarger.print_exposure_compensation = False
    params.io.crop = False
    params.io.upscale_factor = 1.0
    params.io.output_color_space = PROPHOTO
    params.io.output_cctf_encoding = False
    return digest_params(params)


def _comp_params(state):
    """Params with print compensation enabled, used only to measure factors."""
    from spektrafilm_gui.params_mapper import build_params_from_state
    from spektrafilm.runtime.api import digest_params

    params = build_params_from_state(state)
    params.camera.auto_exposure = False
    params.camera.exposure_compensation_ev = 0.0
    params.debug.deactivate_spatial_effects = True
    params.debug.deactivate_stochastic_effects = True
    params.film_render.halation.boost_ev = 0.0
    params.scanner.white_correction = False
    params.scanner.black_correction = False
    params.scanner.unsharp_mask = (0.0, 0.0)
    params.enlarger.print_exposure = 1.0
    params.enlarger.print_exposure_compensation = True
    params.io.crop = False
    params.io.upscale_factor = 1.0
    params.io.output_color_space = PROPHOTO
    params.io.output_cctf_encoding = False
    return digest_params(params)


def _exposure_factor(pipe):
    from spektrafilm.model.illuminants import standard_illuminant

    sensitivity = 10 ** pipe.print.data.log_sensitivity
    illuminant = standard_illuminant(pipe.enlarger.illuminant)
    print_illuminant = pipe._enlarger_service.enlarger_filtered_illuminant(illuminant)
    value = pipe._printing_stage._compute_exposure_factor_midgray(
        sensitivity, print_illuminant
    )
    return float(np.asarray(value).reshape(-1)[0])


def _comp_factor(pipe, ev):
    """Print-exposure factor for ``ev`` with compensation enabled."""
    filming = pipe._filming_stage
    old = pipe.camera.exposure_compensation_ev
    pipe.camera.exposure_compensation_ev = float(ev)
    midgray, midgray_comp = filming._compute_density_spectral_midgray_to_balance_print()
    pipe._enlarger_service.density_spectral_midgray = midgray
    pipe._enlarger_service.density_spectral_midgray_comp = midgray_comp
    pipe.camera.exposure_compensation_ev = old
    return _exposure_factor(pipe)


def _bake_bundle(state, resolution=DEFAULT_RESOLUTION):
    from spektrafilm.runtime.pipeline import SimulationPipeline
    from spektrafilm_lut_creator.grid import cube_grid, grid_as_image

    params = _bake_params(state)
    encoded_input = bool(params.io.input_cctf_decoding)
    pipe = SimulationPipeline(params)

    grid = cube_grid(resolution)
    if encoded_input:
        l1_input = grid * ENCODED_MAX
    else:
        l1_input = np.exp2(
            SHAPER_LO_EV + grid * (SHAPER_HI_EV - SHAPER_LO_EV)
        )
    o1 = np.asarray(
        pipe.process(grid_as_image(l1_input, resolution), inject="rgb_in",
                     collect="log_e_film"),
        dtype=np.float32,
    )
    log_pad = EV_HEADROOM * np.log10(2.0)
    lo1, hi1 = _margin(float(o1.min()), float(o1.max()), pad=log_pad)
    t1 = _to_table((o1 - lo1) / (hi1 - lo1), resolution)

    log_grid = lo1 + grid * (hi1 - lo1)
    o2 = np.asarray(
        pipe.process(grid_as_image(log_grid, resolution), inject="log_e_film",
                     collect="cmy_film"),
        dtype=np.float32,
    )
    lo2, hi2 = _margin(float(o2.min()), float(o2.max()))
    t2 = _to_table((o2 - lo2) / (hi2 - lo2), resolution)

    density_grid = lo2 + grid * (hi2 - lo2)
    o3 = np.asarray(
        pipe.process(grid_as_image(density_grid, resolution), inject="cmy_film",
                     collect="log_e_print"),
        dtype=np.float32,
    )
    lo3, hi3 = _margin(float(o3.min()), float(o3.max()))
    t3 = _to_table((o3 - lo3) / (hi3 - lo3), resolution)

    print_grid = lo3 + grid * (hi3 - lo3)
    o4 = pipe.process(grid_as_image(print_grid, resolution), inject="log_e_print",
                      collect="rgb_out")
    t4 = _to_table(o4, resolution)

    compensate = bool(state.simulation.enlarger.print_exposure_compensation)
    comp_pipe = SimulationPipeline(_comp_params(state)) if compensate else None
    baked_factor = _exposure_factor(pipe)

    return PreviewLutBundle(
        tables=(t1, t2, t3, t4),
        wires=(lo1, hi1, lo2, hi2, lo3, hi3),
        encoded_input=encoded_input,
        baked_factor=baked_factor,
        comp_pipe=comp_pipe,
    )

# ---------------------------------------------------------------------------
# Runtime chain
# ---------------------------------------------------------------------------

class PreviewLutBundle:
    """Four baked tables plus the wires needed to walk them."""

    __slots__ = ("tables", "wires", "encoded_input", "_baked_factor",
                 "_comp_pipe", "_ratios")

    def __init__(self, tables, wires, encoded_input, baked_factor, comp_pipe):
        self.tables = tables
        self.wires = wires
        self.encoded_input = bool(encoded_input)
        self._baked_factor = float(baked_factor)
        self._comp_pipe = comp_pipe
        self._ratios = {}

    def comp_ratio(self, ev):
        if self._comp_pipe is None:
            return 1.0
        key = round(float(ev), 4)
        ratio = self._ratios.get(key)
        if ratio is None:
            ratio = _comp_factor(self._comp_pipe, key) / self._baked_factor
            self._ratios[key] = ratio
        return ratio

    def predict(self, source, *, auto_ev=0.0, exposure_ev=0.0,
                print_exposure=1.0, compensate=False):
        """Run the chain on a source image.

        ``auto_ev`` is the auto-exposure gain measured on the source;
        ``exposure_ev`` is the camera exposure slider.  Both are exact:
        linear sources receive them as log-domain offsets after stage 1,
        encoded sources receive auto exposure before stage 1 (it happens
        before CCTF decoding in the live pipeline).
        """
        t1, t2, t3, t4 = self.tables
        lo1, hi1, lo2, hi2, lo3, hi3 = self.wires
        data = np.asarray(source, dtype=np.float32)

        if self.encoded_input:
            scale = np.float32((2.0 ** float(auto_ev)) / ENCODED_MAX)
            data = np.ascontiguousarray(data * scale, dtype=np.float32)
            v = apply_lut(data, t1)
            log_offset = float(exposure_ev) * np.log10(2.0)
        else:
            v = _apply_lut_shaped(data, t1)
            log_offset = (float(auto_ev) + float(exposure_ev)) * np.log10(2.0)

        v = np.clip(lo1 + v * (hi1 - lo1) + log_offset, lo1, hi1)
        v = apply_lut((v - lo1) / (hi1 - lo1), t2)

        v = np.clip(lo2 + v * (hi2 - lo2), lo2, hi2)
        v = apply_lut((v - lo2) / (hi2 - lo2), t3)

        offset = np.log10(float(print_exposure))
        if compensate:
            offset += np.log10(self.comp_ratio(exposure_ev))
        v = np.clip(lo3 + v * (hi3 - lo3) + offset, lo3, hi3)
        return apply_lut((v - lo3) / (hi3 - lo3), t4)


def _state_key(state):
    import hashlib

    from spektrafilm_gui.persistence import gui_state_to_dict

    data = gui_state_to_dict(state)
    camera = data.get("camera")
    if isinstance(camera, dict):
        camera["exposure_compensation_ev"] = 0.0
        camera["auto_exposure"] = False
    simulation = data.get("simulation")
    if isinstance(simulation, dict):
        simulation["print_exposure"] = 1.0
        simulation["print_exposure_compensation"] = False
    return hashlib.sha1(
        json.dumps(data, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


class PreviewLutCache:
    """Bounded LRU cache of preview LUT bundles keyed by the bake state."""

    def __init__(self, resolution=DEFAULT_RESOLUTION, limit=3):
        self.resolution = int(resolution)
        self.limit = int(limit)
        self._items = {}
        self._order = []

    def get(self, state):
        key = _state_key(state)
        hit = self._items.get(key)
        if hit is not None:
            self._order.remove(key)
            self._order.append(key)
            return hit
        bundle = _bake_bundle(state, self.resolution)
        self._items[key] = bundle
        self._order.append(key)
        while len(self._order) > self.limit:
            oldest = self._order.pop(0)
            self._items.pop(oldest, None)
        return bundle


def measure_auto_ev(source, color_space, cctf_decoding, method="center_weighted"):
    """Mirror ``FilmingStage.auto_exposure`` on the preview source."""
    from skimage.transform import rescale
    from spektrafilm.utils.autoexposure import measure_autoexposure_ev

    image = np.asarray(source, dtype=np.float64)
    long_edge = max(image.shape[0], image.shape[1])
    if long_edge > 256:
        image = rescale(image, 256.0 / long_edge, channel_axis=2, order=0)
    return float(measure_autoexposure_ev(
        image,
        color_space=color_space,
        apply_cctf_decoding=cctf_decoding,
        method=method,
    ))


def warmup():
    """Compile the lookup kernels so the first frame does not pay JIT."""
    lut = np.zeros((2, 2, 2, 3), dtype=np.float32)
    image = np.zeros((2, 2, 3), dtype=np.float32)
    apply_lut(image, lut)
    _apply_lut_shaped(image, lut)
    to_display_rgb8(np.zeros((2, 2, 3), dtype=np.float32))

# ---------------------------------------------------------------------------
# Display transform
# ---------------------------------------------------------------------------

@njit(cache=True, inline="always")
def _srgb_encode_one(v):
    if v <= 0.0:
        return np.float32(0.0)
    if v <= np.float32(0.0031308):
        return v * np.float32(12.92)
    return np.float32(1.055) * np.power(v, np.float32(1.0 / 2.4)) - np.float32(0.055)


@njit(cache=True, parallel=True, nogil=True)
def _display_kernel(image, matrix, out):
    height = image.shape[0]
    width = image.shape[1]
    for y in prange(height):
        for x in range(width):
            r = image[y, x, 0]
            g = image[y, x, 1]
            b = image[y, x, 2]
            sr = matrix[0, 0] * r + matrix[0, 1] * g + matrix[0, 2] * b
            sg = matrix[1, 0] * r + matrix[1, 1] * g + matrix[1, 2] * b
            sb = matrix[2, 0] * r + matrix[2, 1] * g + matrix[2, 2] * b
            for c, v in ((0, sr), (1, sg), (2, sb)):
                e = _srgb_encode_one(v)
                if e < 0.0:
                    e = 0.0
                elif e > 1.0:
                    e = 1.0
                out[y, x, c] = np.uint8(e * np.float32(255.0) + np.float32(0.5))


@lru_cache(maxsize=1)
def _prophoto_to_srgb_matrix():
    import colour

    return np.asarray(
        colour.matrix_RGB_to_RGB("ProPhoto RGB", "sRGB"), dtype=np.float32
    )


def to_display_rgb8(linear_prophoto):
    """Linear ProPhoto float -> 8-bit sRGB display values."""
    image = np.ascontiguousarray(np.asarray(linear_prophoto)[..., :3], dtype=np.float32)
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("image must have shape (H, W, 3)")
    out = np.empty((image.shape[0], image.shape[1], 3), dtype=np.uint8)
    _display_kernel(image, _prophoto_to_srgb_matrix(), out)
    return out
