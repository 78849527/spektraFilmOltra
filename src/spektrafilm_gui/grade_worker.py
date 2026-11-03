"""调色预览线程：渲染在 QThreadPool 里跑，结果按 generation 丢弃过期帧。"""

from __future__ import annotations

import numpy as np
from qtpy import QtCore

from spektrafilm_gui.grade_engine import (
    load_handoff_image,
    prepare_source,
    render,
)
from spektrafilm_gui.grade_recipe import GradeRecipe

Signal = QtCore.Signal


class GradeRenderSignals(QtCore.QObject):
    finished = Signal(int, object, object)
    failed = Signal(int, str)


class GradeRenderTask(QtCore.QRunnable):
    def __init__(
        self,
        generation: int,
        source: np.ndarray,
        recipe: GradeRecipe,
        *,
        analyze: bool = True,
    ):
        super().__init__()
        self.signals = GradeRenderSignals()
        self._generation = int(generation)
        self._source = np.asarray(source, dtype=np.float32)
        self._recipe = recipe.clone()
        self._analyze = bool(analyze)

    @property
    def generation(self) -> int:
        return self._generation

    @QtCore.Slot()
    def run(self) -> None:
        try:
            image, analysis = render(
                self._source,
                self._recipe,
                analyze=self._analyze,
            )
        except Exception as exc:  # noqa: BLE001 - 线程边界必须兜住
            self.signals.failed.emit(self._generation, str(exc))
            return
        self.signals.finished.emit(self._generation, image, analysis)


class GradeFileRenderTask(QtCore.QRunnable):
    """全尺寸导出：线程内重新读取交接图，避免大图常驻内存。"""

    def __init__(self, generation: int, path: str, recipe: GradeRecipe):
        super().__init__()
        self.signals = GradeRenderSignals()
        self._generation = int(generation)
        self._path = str(path)
        self._recipe = recipe.clone()

    @property
    def generation(self) -> int:
        return self._generation

    @QtCore.Slot()
    def run(self) -> None:
        try:
            source = prepare_source(load_handoff_image(self._path))
            image, analysis = render(source, self._recipe, analyze=True)
        except Exception as exc:  # noqa: BLE001 - 线程边界必须兜住
            self.signals.failed.emit(self._generation, str(exc))
            return
        self.signals.finished.emit(self._generation, image, analysis)


__all__ = ['GradeFileRenderTask', 'GradeRenderSignals', 'GradeRenderTask']
