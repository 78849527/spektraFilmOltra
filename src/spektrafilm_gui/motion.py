"""过渡动画：把 oflim 的阻尼曲线搬到 Qt。

oflim 用的是三档曲线：
- ``DS.easeQuick``  cubic-bezier(0.16, 1, 0.3, 1) 180ms —— 悬浮、选中这类高频反馈
- ``DS.easeOutExpo`` cubic-bezier(0.16, 1, 0.3, 1) 280ms —— 面板进出
- ``DS.snappy``      spring(response 0.34, damping 0.82) —— 布局位移
- Renderer 的缩放平移用指数跟随 ``alpha = 1 - exp(-dt * k)``

Qt 侧用 QVariantAnimation 复现前两档，用 QTimer 复现指数跟随。
所有动画都挂在控件自己身上，控件销毁时动画随之停止，不需要手工回收。
"""

from __future__ import annotations

import math

from qtpy import QtCore, QtGui, QtWidgets

# 时长（毫秒）与曲线
DURATION_QUICK = 170
DURATION_BASE = 260
DURATION_SLOW = 340

CURVE_OUT_EXPO = QtCore.QEasingCurve.Type.OutExpo
CURVE_SPRING = QtCore.QEasingCurve.Type.OutBack


def _make_curve(kind: QtCore.QEasingCurve.Type) -> QtCore.QEasingCurve:
    curve = QtCore.QEasingCurve(kind)
    if kind == CURVE_SPRING:
        curve.setOvershoot(1.06)
    return curve


def ease_progress(t: float) -> float:
    """OutExpo 的纯函数版本，供自绘控件按帧计算。"""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return 1.0 - math.pow(2.0, -10.0 * t)


class _Animation(QtCore.QVariantAnimation):
    """生命周期跟随 target 的动画，避免控件销毁后回调野指针。"""

    def __init__(self, target: QtCore.QObject, duration: int, curve: QtCore.QEasingCurve.Type):
        super().__init__(target)
        self.setDuration(max(1, int(duration)))
        self.setEasingCurve(_make_curve(curve))
        self.setStartValue(0.0)
        self.setEndValue(1.0)


def animate_progress(
    target: QtCore.QObject,
    on_frame,
    *,
    duration: int = DURATION_BASE,
    curve: QtCore.QEasingCurve.Type = CURVE_OUT_EXPO,
    on_finished=None,
) -> QtCore.QVariantAnimation:
    """在 duration 内把 0→1 的进度交给 on_frame，曲线默认 OutExpo。"""
    animation = _Animation(target, duration, curve)

    def _frame(value) -> None:
        try:
            on_frame(float(value))
        except RuntimeError:
            animation.stop()

    animation.valueChanged.connect(_frame)
    if on_finished is not None:
        animation.finished.connect(on_finished)
    animation.start()
    return animation


def animate_color(
    target: QtCore.QObject,
    start: QtGui.QColor,
    end: QtGui.QColor,
    on_frame,
    *,
    duration: int = DURATION_QUICK,
    curve: QtCore.QEasingCurve.Type = CURVE_OUT_EXPO,
) -> QtCore.QVariantAnimation:
    """颜色插值。on_frame 收到 QColor。"""
    animation = _Animation(target, duration, curve)
    animation.setStartValue(start)
    animation.setEndValue(end)
    animation.valueChanged.connect(lambda value: on_frame(value))  # noqa: ARG005
    animation.start()
    return animation


class FollowValue(QtCore.QObject):
    """指数跟随，等价于 oflim Renderer 的 ``1 - exp(-dt * rate)``。

    用于滑条填充、缩放这类"跟手"的连续量：目标一变就朝它收敛，
    不会像定时动画那样在连续拖动时反复重启。
    """

    valueChanged = QtCore.Signal(float)

    def __init__(self, parent: QtCore.QObject | None = None, *, rate: float = 14.0, interval_ms: int = 16):
        super().__init__(parent)
        self._value = 0.0
        self._target = 0.0
        self._rate = max(1.0, float(rate))
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(max(8, int(interval_ms)))
        self._timer.timeout.connect(self._tick)
        self._last = QtCore.QElapsedTimer()
        self._last.start()

    @property
    def value(self) -> float:
        return self._value

    def set_value(self, value: float) -> None:
        self._value = float(value)
        self._target = float(value)

    def move_to(self, target: float) -> None:
        self._target = float(target)
        if not self._timer.isActive():
            self._last.restart()
            self._timer.start()

    def snap_to(self, target: float) -> None:
        self._target = float(target)
        self._value = float(target)
        self._timer.stop()
        self.valueChanged.emit(self._value)

    def _tick(self) -> None:
        dt = min(0.05, max(0.001, self._last.restart() / 1000.0))
        delta = self._target - self._value
        if abs(delta) < 0.0008:
            self._value = self._target
            self._timer.stop()
            self.valueChanged.emit(self._value)
            return
        self._value += delta * (1.0 - math.exp(-dt * self._rate))
        self.valueChanged.emit(self._value)


def fade_in(widget: QtWidgets.QWidget, *, duration: int = DURATION_BASE, start: float = 0.0) -> None:
    """淡入。使用 QGraphicsOpacityEffect，结束后自动摘掉以免影响子控件绘制。"""
    if widget is None:
        return
    effect = QtWidgets.QGraphicsOpacityEffect(widget)
    effect.setOpacity(start)
    widget.setGraphicsEffect(effect)

    def _frame(progress: float) -> None:
        if not _alive(widget):
            return
        effect.setOpacity(start + (1.0 - start) * progress)

    def _done() -> None:
        if _alive(widget):
            widget.setGraphicsEffect(None)

    animate_progress(widget, _frame, duration=duration, on_finished=_done)


def slide_fade(
    widget: QtWidgets.QWidget,
    *,
    dx: int = 0,
    dy: int = 10,
    duration: int = DURATION_BASE,
) -> None:
    """从偏移位置滑入并淡入：面板切换的默认手感。"""
    if widget is None:
        return
    origin = widget.pos()
    start = QtCore.QPoint(origin.x() + dx, origin.y() + dy)
    widget.move(start)
    fade_in(widget, duration=duration, start=0.0)

    def _frame(progress: float) -> None:
        if not _alive(widget):
            return
        widget.move(
            QtCore.QPoint(
                round(start.x() + (origin.x() - start.x()) * progress),
                round(start.y() + (origin.y() - start.y()) * progress),
            ),
        )

    animate_progress(widget, _frame, duration=duration)


def pulse(widget: QtWidgets.QWidget, *, scale: float = 0.97, duration: int = DURATION_QUICK) -> None:
    """按压缩放反馈：等价于 oflim 的 PressableStyle。"""
    if widget is None or not _alive(widget):
        return
    base = widget.geometry()
    shrunk = QtCore.QRect(base)
    shrunk.setWidth(max(1, round(base.width() * scale)))
    shrunk.setHeight(max(1, round(base.height() * scale)))
    shrunk.moveCenter(base.center())

    def _down(progress: float) -> None:
        if not _alive(widget):
            return
        rect = QtCore.QRect(base)
        rect.setWidth(round(base.width() + (shrunk.width() - base.width()) * progress))
        rect.setHeight(round(base.height() + (shrunk.height() - base.height()) * progress))
        rect.moveCenter(base.center())
        widget.setGeometry(rect)

    def _up(_=None) -> None:
        if not _alive(widget):
            return
        animate_progress(widget, lambda p: _restore(p), duration=duration)

    def _restore(progress: float) -> None:
        if not _alive(widget):
            return
        rect = QtCore.QRect(shrunk)
        rect.setWidth(round(shrunk.width() + (base.width() - shrunk.width()) * progress))
        rect.setHeight(round(shrunk.height() + (base.height() - shrunk.height()) * progress))
        rect.moveCenter(base.center())
        widget.setGeometry(rect)

    animate_progress(widget, _down, duration=max(60, duration // 3), on_finished=_up)


def _alive(widget: QtWidgets.QWidget | None) -> bool:
    if widget is None:
        return False
    try:
        widget.isVisible()
    except RuntimeError:
        return False
    return True
