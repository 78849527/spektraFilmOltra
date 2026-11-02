from __future__ import annotations

import numpy as np

from spektrafilm.runtime.api import digest_params, init_params
from spektrafilm.runtime.process import Simulator


def test_pipeline_reports_stage_progress() -> None:
    params = digest_params(init_params())
    events: list[tuple[str, int, int]] = []

    def progress(label: str, completed: int, total: int) -> None:
        events.append((label, completed, total))

    Simulator(params).process(
        np.full((8, 8, 3), 0.5, dtype=np.float64),
        progress_callback=progress,
    )

    assert events
    labels = [event[0] for event in events]
    assert labels[0] == 'preprocess'
    assert labels[-1] in {'scanning.scan_print', 'scanning.scan_film'}
    assert all(0 < completed <= total for _, completed, total in events)
    assert events[-1][1] == events[-1][2]
    assert len(events) == events[0][2]
