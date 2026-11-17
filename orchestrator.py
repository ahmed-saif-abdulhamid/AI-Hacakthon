"""Re-exports proveit.orchestrator for convenience."""

from proveit import orchestrator as _m
from proveit.orchestrator import *  # noqa: F401,F403

globals().update({k: getattr(_m, k) for k in dir(_m) if not k.startswith("__")})
