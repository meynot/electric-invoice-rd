"""Run the DGII e-CF issuer API.

Usage:
    uvicorn main:app --reload
"""

from app.api import app

__all__ = ["app"]
