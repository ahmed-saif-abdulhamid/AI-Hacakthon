"""Re-exports proveit.approval for convenience."""
from proveit.approval import *  # noqa: F401,F403
from proveit import approval as _m

globals().update({k: getattr(_m, k) for k in dir(_m) if not k.startswith("__")})
