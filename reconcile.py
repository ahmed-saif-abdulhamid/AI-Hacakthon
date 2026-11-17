"""Reconciliation of orders, payments, fees and payouts. Implemented in ``proveit/commerce/reconcile.py``.

This root module is an alias of that module (same object), so ``import reconcile`` works from the repository root.
"""

import sys

from proveit.commerce import reconcile

sys.modules[__name__] = reconcile
