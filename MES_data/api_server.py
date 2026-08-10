"""Compatibility entry point.

Preferred command:
    python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
"""

from backend.main import app


__all__ = ["app"]
