"""Gates: pre-registered thresholds and deterministic decisions. Implemented in ``proveit/gates.py``.

This root module is an alias of that module (same object), so ``import gates`` works from the repository root.
"""

import sys

from proveit import gates

sys.modules[__name__] = gates
