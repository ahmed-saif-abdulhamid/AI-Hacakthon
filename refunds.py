"""Refunds, always founder-approved. Implemented in ``proveit/commerce/refunds.py``.

This root module is an alias of that module (same object), so ``import refunds`` works from the repository root.
"""

import sys

from proveit.commerce import refunds

sys.modules[__name__] = refunds
