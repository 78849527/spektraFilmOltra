"""照片库缩略图：磁盘缓存 + 后台生成。

RAW 优先读取相机内嵌的 JPEG 预览（快），没有预览才走半尺寸显影；
普通图片用 QImageReader 直接缩放解码。所有解码都在线程池里做，
主线程只接收 QImage 信号。
"""

from __future__ import annotations

import io
import time
from collections import OrderedDict
from pathlib import Path

from qtpy import QtCore, QtGui

from spektrafilm_gui.library_store import LibraryItem, LibraryStore, is_raw_image

QImage = QtGui.QImage
QImageReader = QtGui.QImageReader
QPixmap = QtGui.QPixmap
QThreadPool = getattr(QtCore, 'QThreadPool')
QRunnable = getattr(QtCore, 'QRunnable')
Signal = QtCore.Signal
QObject = QtCore.QObject

THUMB_MAX_SIZE = 320
THUMB_QUALITY = 88


def _pil_image_to_qimage(pil_image) -> QImage:
    from PIL import Image as PILImage

    image = pil_image.convert('RGB')
    buffer = io.BytesIO()
    image.save(buffer, format='JPEG', quality=92)
    return QImage.fromData(buffer.getvalue(), 'JPG')


def _numpy_to_qimage(array) -> QImage:
    import numpy as np

    data = np.asarray(array)
    if data.ndim == 2:
        data = np.repeat(data[..., None], 3, axis=2)
    data = data[..., :3]
    if data.dtype != np.uint8:
        data = np.clip(data, 0.0, 1.0) * 255.0 if data.max(initial=0.0) <= 1.0 else np.clip(data, 0, 255)
        data = data.astype(np.uint8)
    data = np.ascontiguousarray(data)
    height, width = data.shape[:2]
    return QImage(data.data, width, height, 3 * width, QtGui.QImage.Format_RGB888).copy()


def _apply_raw_flip(pil_image, flip: int):
    from PIL import Image as PILImage

    if flip == 3:
        return pil_image.rotate(180, expand=True)
    if flip == 5:
        return pil_image.transpose(PILImage.Transpose.FLIP_LEFT_RIGHT).rotate(90, expand=True)
    if flip == 6:
        return pil_image.rotate(270, expand=True)
    return pil_image


def _read_raw(path: Path) -> tuple[QImage, int, int]:
    import rawpy
    from PIL import Image as PILImage, ImageOps

    with rawpy.imread(str(path)) as raw:
        width = int(getattr(raw.sizes, 'width', 0) or 0)
        height = int(getattr(raw.sizes, 'height', 0) or 0)
        try:
            thumb = raw.extract_thumb()
        except (rawpy.LibRawNoThumbnailError, rawpy.LibRawUnsupportedThumbnailError, AttributeError):
            thumb = None
        if thumb is not None:
            image = PILImage.open(io.BytesIO(thumb.data))
            image = ImageOps.exif_transpose(image)
            if width and height:
                return _pil_image_to_qimage(image), width, height
            return _pil_image_to_qimage(image), image.width, image.height

        array = raw.postprocess(half_size=True, use_camera_wb=True, no_auto_bright=False)
        flip = int(getattr(raw.sizes, 'flip', 0) or 0)
        image = PILImage.fromarray(array)
        image = _apply_raw_flip(image, flip)
        if not width or not height:
            width, height = image.width, image.height
        return _pil_image_to_qimage(image), int(width), int(height)


def _read_rgb(path: Path) -> tuple[QImage, int, int]:
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid() and size.width() > 0 and size.height() > 0:
        scaled = size.scaled(THUMB_MAX_SIZE, THUMB_MAX_SIZE, QtCore.Qt.KeepAspectRatio)
        reader.setScaledSize(scaled)
        image = reader.read()
        if not image.isNull():
            return image, int(size.width()), int(size.height())

    # QImageReader 读不了的格式（例如 EXR）交给 OIIO
    from spektrafilm.utils.io import load_image_oiio

    array = load_image_oiio(str(path))[..., :3]
    if getattr(array, 'dtype', None) is not None and array.dtype.kind == 'f':
        array = array ** (1.0 / 2.2)
    image = _numpy_to_qimage(array)
    width, height = int(image.width()), int(image.height())
    if max(width, height) > THUMB_MAX_SIZE:
        image = image.scaled(
            THUMB_MAX_SIZE,
            THUMB_MAX_SIZE,
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation,
        )
    return image, width, height


def generate_thumbnail(path: str | Path) -> tuple[QImage, int, int]:
    image_path = Path(path)
    if is_raw_image(image_path):
        image, width, height = _read_raw(image_path)
    else:
        image, width, height = _read_rgb(image_path)
    if max(image.width(), image.height()) > THUMB_MAX_SIZE:
        image = image.scaled(
            THUMB_MAX_SIZE,
            THUMB_MAX_SIZE,
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation,
        )
    return image, width, height


class _ThumbnailSignals(QObject):
    finished = Signal(str, QImage, int, int)
    failed = Signal(str, str)


class _ThumbnailTask(QRunnable):
    def __init__(self, item_id: str, path: str, thumbnail_path: str):
        super().__init__()
        self.item_id = item_id
        self.path = path
        self.thumbnail_path = thumbnail_path
        self.signals = _ThumbnailSignals()

    def run(self) -> None:
        try:
            image, width, height = generate_thumbnail(self.path)
            if image.isNull():
                raise ValueError('无法解码这张图片')
            target = Path(self.thumbnail_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            image.save(str(target), 'JPG', THUMB_QUALITY)
            try:
                self.signals.finished.emit(self.item_id, image, width, height)
            except RuntimeError:
                return
        except Exception as exc:  # noqa: BLE001 - 后台任务必须兜住所有解码异常
            try:
                self.signals.failed.emit(self.item_id, str(exc))
            except RuntimeError:
                return


class ThumbnailService(QObject):
    """按需生成缩略图；同一张图不会重复排队。"""

    thumbnail_ready = Signal(str, QImage)
    metadata_ready = Signal(str, int, int)
    thumbnail_failed = Signal(str, str)

    def __init__(self, store: LibraryStore, *, parent: QObject | None = None, max_threads: int = 3):
        super().__init__(parent)
        self._store = store
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(max(1, int(max_threads)))
        self._requested: set[str] = set()
        self._cache: OrderedDict[str, QImage] = OrderedDict()
        self._cache_limit = 300

    def cached(self, item_id: str) -> QImage | None:
        image = self._cache.get(item_id)
        if image is not None:
            self._cache.move_to_end(item_id)
        return image

    def _remember(self, item_id: str, image: QImage) -> None:
        self._cache[item_id] = image
        self._cache.move_to_end(item_id)
        while len(self._cache) > self._cache_limit:
            self._cache.popitem(last=False)

    def request(self, item: LibraryItem) -> QImage | None:
        cached = self.cached(item.id)
        if cached is not None and not cached.isNull():
            return cached
        if item.id in self._requested:
            return None

        thumb_path = self._store.thumbnail_path(item)
        if thumb_path.exists() and self._store.has_fresh_thumbnail(item):
            image = QImage(str(thumb_path))
            if not image.isNull():
                self._remember(item.id, image)
                return image

        self._requested.add(item.id)
        task = _ThumbnailTask(item.id, item.path, str(thumb_path))
        task.signals.finished.connect(self._on_finished)
        task.signals.failed.connect(self._on_failed)
        self._pool.start(task)
        return None

    def invalidate(self, item_id: str) -> None:
        self._cache.pop(item_id, None)

    def _on_finished(self, item_id: str, image: QImage, width: int, height: int) -> None:
        self._requested.discard(item_id)
        self._remember(item_id, image)
        self.thumbnail_ready.emit(item_id, image)
        if width > 0 and height > 0:
            self.metadata_ready.emit(item_id, width, height)

    def _on_failed(self, item_id: str, message: str) -> None:
        self._requested.discard(item_id)
        self.thumbnail_failed.emit(item_id, message)

    def wait_for_idle(self, timeout_ms: int = 5000) -> bool:
        return self._pool.waitForDone(int(timeout_ms))


def format_file_size(size: int) -> str:
    value = float(max(int(size), 0))
    for unit in ('B', 'KB', 'MB', 'GB'):
        if value < 1024.0 or unit == 'GB':
            if unit == 'B':
                return f'{int(value)} {unit}'
            return f'{value:.1f} {unit}'
        value /= 1024.0
    return f'{value:.1f} GB'


def format_time(timestamp: float) -> str:
    if not timestamp:
        return ''
    return time.strftime('%Y-%m-%d %H:%M', time.localtime(timestamp))
