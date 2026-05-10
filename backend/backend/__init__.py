"""Compatibility package for Render deployments rooted at backend/.

When Render's Root Directory is set to `backend`, a start command like
`uvicorn backend.app:app` normally fails because Python looks for a nested
`backend` package. This package extends its search path to the parent backend
directory so `backend.app`, `backend.database`, and other imports still resolve.
"""

from pathlib import Path

_parent_backend_dir = Path(__file__).resolve().parents[1]
__path__.insert(0, str(_parent_backend_dir))
