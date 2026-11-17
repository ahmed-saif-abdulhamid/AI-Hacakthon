"""Re-exports proveit.gates for convenience."""

from proveit import gates as _m
from proveit.gates import *  # noqa: F401,F403

globals().update({k: getattr(_m, k) for k in dir(_m) if not k.startswith("__")})
