"""Vercel serverless entrypoint.

Vercel's Python runtime detects the WSGI `app` object exported from this file
and routes every request to it (see ../vercel.json rewrites). The original
request path (e.g. /api/health) is preserved, so Flask routing works as-is.
"""

import os
import sys

# Ensure the project root (which contains the `app` package) is importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402

app = create_app()
