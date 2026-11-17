"""Founder approval: hash-locked, enforced in code. Implemented in ``proveit/approval.py``.

This root module is an alias of that module (same object), so ``import approval`` works from the repository root.
"""

import sys

from proveit import approval

sys.modules[__name__] = approval
