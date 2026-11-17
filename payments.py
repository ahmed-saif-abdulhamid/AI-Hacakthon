"""Payments (MOCKED provider). Implemented in ``proveit/commerce/payments.py``.

This root module is an alias of that module (same object), so ``import payments`` works from the repository root.
"""

import sys

from proveit.commerce import payments

sys.modules[__name__] = payments
