"""Checkout (MOCKED): test purchase to delivery. Implemented in ``proveit/commerce/checkout.py``.

This root module is an alias of that module (same object), so ``import checkout`` works from the repository root.
"""

import sys

from proveit.commerce import checkout

sys.modules[__name__] = checkout
