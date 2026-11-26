"""Run the API on port 8001 with every outgoing httpx request logged (C2).

The wrapper patches httpx's async transport before the app is imported, so
the log shows exactly what leaves the host: method, URL, headers (values of
Authorization/apikey masked). Used to show that Pwned Passwords receives only
the first five hex characters of the SHA-1 hash and the Add-Padding header.

    uv run python scripts/verification/wire_logged_api.py <log.jsonl> [--block-pwned]

--block-pwned makes api.pwnedpasswords.com unreachable (connect error) to show
the documented fail-open behaviour after the 3 s timeout.
"""

import json
import os
import sys
import time
from pathlib import Path

import httpx

LOG = Path(sys.argv[1])
BLOCK = "--block-pwned" in sys.argv
_orig = httpx.AsyncHTTPTransport.handle_async_request


async def _logged(self, request: httpx.Request):
    rec = {"t": time.time(), "method": request.method, "url": str(request.url), "host": request.url.host,
           "headers": {k: ("<masked>" if k.lower() in ("authorization", "apikey") else v) for k, v in request.headers.items()}}
    t0 = time.perf_counter()
    try:
        if BLOCK and request.url.host == "api.pwnedpasswords.com":
            raise httpx.ConnectError("blocked by wire_logged_api --block-pwned", request=request)
        resp = await _orig(self, request)
        rec["status"] = resp.status_code
        return resp
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {e}"
        raise
    finally:
        rec["seconds"] = round(time.perf_counter() - t0, 3)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")


httpx.AsyncHTTPTransport.handle_async_request = _logged

os.environ["CRON_SECRET"] = ""
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
os.chdir(Path(__file__).resolve().parents[2] / "backend")

import uvicorn  # noqa: E402

from app.main import app  # noqa: E402

uvicorn.run(app, host="127.0.0.1", port=8001, log_level="info")
