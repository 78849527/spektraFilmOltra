"""前端侧的计算互斥锁。

Numba 的 workqueue 线程层不是线程安全的：后台预热与用户触发的预览
如果同时调用 ``Simulator.process``，会直接让进程崩溃。这里只做一件事——
让「预热」和「真实预览/扫描」排队，不改变任何计算内容。
"""

from __future__ import annotations

from threading import Lock

SIMULATION_LOCK = Lock()
