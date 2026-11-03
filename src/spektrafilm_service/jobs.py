"""单工作线程的渲染作业队列。

与 Qt 版行为对齐：同一时间只跑一个模拟；预览可被更新的预览取代；
导出必须排队，当前任务结束后自动执行，不丢请求。
"""

from __future__ import annotations

import itertools
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from typing import Callable


class JobCancelled(Exception):
    """任务在排队阶段被更新的同类任务取代。"""


@dataclass
class Job:
    id: str
    kind: str
    created_at: float
    state: str = 'queued'
    progress: dict[str, object] = field(default_factory=lambda: {'label': '排队中', 'index': 0, 'total': 1})
    result: dict[str, object] | None = None
    error: str | None = None
    cancelled: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            'id': self.id,
            'kind': self.kind,
            'state': self.state,
            'progress': dict(self.progress),
            'result': self.result,
            'error': self.error,
        }


class JobQueue:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._queue: deque[tuple[Job, Callable[[Job], dict[str, object] | None]]] = deque()
        self._worker = threading.Thread(target=self._run, name='spektrafilm-worker', daemon=True)
        self._seq = itertools.count(1)
        self._wake = threading.Condition(self._lock)
        self._worker.start()

    def submit(
        self,
        kind: str,
        run: Callable[[Job], dict[str, object] | None],
        *,
        supersede_kind: str | None = None,
    ) -> Job:
        job = Job(id=f'j_{next(self._seq)}', kind=kind, created_at=time.time())
        with self._lock:
            if supersede_kind:
                for queued_job, _ in list(self._queue):
                    if queued_job.kind == supersede_kind:
                        queued_job.state = 'cancelled'
                        queued_job.cancelled = True
                self._queue = deque(item for item in self._queue if not item[0].cancelled)
            self._jobs[job.id] = job
            self._prune()
            self._queue.append((job, run))
            self._wake.notify()
        return job

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            if job.state == 'queued':
                job.state = 'cancelled'
                job.cancelled = True
                self._queue = deque(item for item in self._queue if not item[0].cancelled)
                return True
            # 运行中的任务没有安全的打断点（核心管线吞掉回调异常），
            # 只标记结果作废，等它跑完自然丢弃。
            job.cancelled = True
            return True

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update_progress(self, job: Job, label: str, index: int, total: int) -> None:
        with self._lock:
            job.progress = {'label': label, 'index': int(index), 'total': int(total)}

    def mark_running(self, job: Job) -> None:
        with self._lock:
            job.state = 'running'

    def is_cancelled(self, job: Job) -> bool:
        with self._lock:
            return job.cancelled

    def finish(self, job: Job, result: dict[str, object] | None, error: str | None) -> None:
        with self._lock:
            if job.cancelled:
                job.state = 'cancelled'
                return
            if error is not None:
                job.state = 'failed'
                job.error = error
            else:
                job.state = 'done'
                job.result = result

    def _prune(self) -> None:
        if len(self._jobs) <= 200:
            return
        for job_id in list(self._jobs)[:-160]:
            job = self._jobs[job_id]
            if job.state in {'done', 'failed', 'cancelled'}:
                del self._jobs[job_id]

    def _run(self) -> None:
        while True:
            with self._lock:
                while not self._queue:
                    self._wake.wait()
                job, run = self._queue.popleft()
            with self._lock:
                if job.cancelled:
                    continue
                job.state = 'running'
            try:
                result = run(job)
            except Exception as exc:  # noqa: BLE001 - 作业失败要回报给前端
                self.finish(job, None, f'{type(exc).__name__}: {exc}')
            else:
                self.finish(job, result, None)


__all__ = ['Job', 'JobCancelled', 'JobQueue']
