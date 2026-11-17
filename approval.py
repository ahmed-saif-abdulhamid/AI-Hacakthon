"""Re-exports proveit.approval for convenience."""

from proveit import approval as _m
from proveit.approval import *  # noqa: F401,F403

globals().update({k: getattr(_m, k) for k in dir(_m) if not k.startswith("__")})
