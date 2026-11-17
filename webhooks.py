"""Signed, idempotent payment webhooks. Implemented in ``proveit/commerce/webhooks.py``.

This root module is an alias of that module (same object), so ``import webhooks`` works from the repository root.
"""

import sys

from proveit.commerce import webhooks

sys.modules[__name__] = webhooks
