"""Qt 侧渲染任务的线程包装。

纯像素处理已抽到 :mod:`spektrafilm_gui.display_pixels`，这里只负责把请求
丢进 Qt 线程池并把进度转成信号。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
from qtpy import QtCore

from spektrafilm_gui.display_pixels import (  # noqa: F401 - re-exported for existing callers
    DISPLAY_PREVIEW_COLOR_SPACE,
    DISPLAY_PROFILE_DIRS,
    apply_display_transform,
    apply_white_padding,
    display_profile_available,
    display_profile_details,
    display_profile_name,
    display_transform_status_message,
    normalized_image_data,
    padding_pixels_for_image,
    prepare_input_color_preview_image,
    prepare_output_display_image,
)

QObject = getattr(QtCore, 'QObject')
QRunnable = getattr(QtCore, 'QRunnable')
Signal = getattr(QtCore, 'Signal')


@dataclass(slots=True)
class SimulationRequest:
    mode_label: str
    image: np.ndarray
    params: object
    output_color_space: str
    use_display_transform: bool
    progress_callback: Callable[[str, int, int], None] | None = None


@dataclass(slots=True)
class SimulationResult:
    mode_label: str
    display_image: np.ndarray
    float_image: np.ndarray
    output_color_space: str
    use_display_transform: bool
    status_message: str


class SimulationWorkerSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)
    progress = Signal(str, int, int)


class SimulationWorker(QRunnable):
    def __init__(self, request: SimulationRequest, *, execute_request: Callable[..., SimulationResult]):
        super().__init__()
        self._request = request
        self._execute_request = execute_request
        self.signals = SimulationWorkerSignals()

    def run(self) -> None:
        try:
            result = self._execute_request(
                self._request,
                progress_callback=self.signals.progress.emit,
            )
        except (AttributeError, LookupError, OSError, RuntimeError, TypeError, ValueError) as exc:
            self.signals.failed.emit(f'{type(exc).__name__}: {exc}')
            return
        self.signals.finished.emit(result)


def execute_simulation_request(
    request: SimulationRequest,
    *,
    run_simulation_fn: Callable[..., np.ndarray],
    prepare_output_display_image_fn: Callable[..., tuple[np.ndarray, str]],
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> SimulationResult:
    scan = run_simulation_fn(
        request.image,
        request.params,
        progress_callback=progress_callback,
    )
    scan_display, display_status = prepare_output_display_image_fn(
        scan,
        output_color_space=request.output_color_space,
        use_display_transform=request.use_display_transform,
    )
    return SimulationResult(
        mode_label=request.mode_label,
        display_image=scan_display,
        float_image=np.asarray(scan),
        output_color_space=request.output_color_space,
        use_display_transform=request.use_display_transform,
        status_message=display_status,
    )
