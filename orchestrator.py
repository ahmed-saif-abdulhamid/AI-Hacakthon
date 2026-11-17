"""The six-phase pipeline state machine. Implemented in ``proveit/orchestrator.py``.

This root module is an alias of that module (same object), so ``import orchestrator`` works from the repository root.
"""

import sys

from proveit import orchestrator

sys.modules[__name__] = orchestrator
