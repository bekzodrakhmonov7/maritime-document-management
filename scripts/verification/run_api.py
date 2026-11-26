"""Start the API for the black-box checks: one uvicorn worker on 127.0.0.1:8000,
daily check off (CRON_SECRET empty), uvicorn defaults otherwise (it trusts
X-Forwarded-For from 127.0.0.1). Log to stdout.

    uv run python scripts/verification/run_api.py [--port 8000]
"""

import os
import sys
from pathlib import Path

os.environ["CRON_SECRET"] = ""
backend = Path(__file__).resolve().parents[2] / "backend"
os.chdir(backend)
sys.path.insert(0, str(backend))

import uvicorn  # noqa: E402

port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8000
uvicorn.run("app.main:app", host="127.0.0.1", port=port, workers=1, log_level="info")
