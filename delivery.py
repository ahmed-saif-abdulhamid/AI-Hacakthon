"""Delivery: signed download tokens, revoked by a refund. Implemented in ``proveit/commerce/delivery.py``.

This root module is an alias of that module (same object), so ``import delivery`` works from the repository root.
"""

import sys

from proveit.commerce import delivery

sys.modules[__name__] = delivery
