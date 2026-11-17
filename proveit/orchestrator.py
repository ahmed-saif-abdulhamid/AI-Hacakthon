"""The six-phase pipeline's public entry points. No agent framework: a hand-written state machine.

The model has no tools: agents return data, and only code calls functions. Every run writes to
runs/<run_id>/ only; ``promote`` is the only writer of outputs/.

Stages (``advance`` runs until a stage needs the founder):
  intake -> phase1 -> gate1 -> phase2 -> [approve publish_landing_page] -> gate2 -> [founder override]
  -> phase3 -> phase4 -> [founder gate 4] -> phase5 -> [approve open_store] -> payment_test
  -> [approve refund] -> refund -> phase6 -> done

The implementation lives in ``proveit.pipeline``: ``run`` (the persisted run), ``engine`` (the loop),
``research`` (Phase 1 evidence), ``copy_guard`` (outward copy) and one module per phase in ``stages``.
"""

from .pipeline.engine import advance, friendly_error, retry, run_pipeline, start
from .pipeline.run import PHASE_NAMES, WAITING, Run, Stage, Status, list_runs, load

__all__ = [
    "PHASE_NAMES",
    "WAITING",
    "Run",
    "Stage",
    "Status",
    "advance",
    "friendly_error",
    "list_runs",
    "load",
    "retry",
    "run_pipeline",
    "start",
]
