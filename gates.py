"""Re-exports proveit.gates for convenience."""
from proveit.gates import *  # noqa: F401,F403
from proveit import gates as _m

globals().update({k: getattr(_m, k) for k in dir(_m) if not k.startswith("__")})
