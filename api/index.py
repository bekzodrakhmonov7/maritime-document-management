"""The Vercel Python function: the whole FastAPI app (ADR 0003).

`vercel.json` rewrites every `/api/*` request here. The app keeps the original
path, so its routes under `/api` match unchanged. The app's package lives in
`backend/`, which local runs put on the path with `--app-dir backend`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.main import app  # noqa: E402

__all__ = ["app"]
