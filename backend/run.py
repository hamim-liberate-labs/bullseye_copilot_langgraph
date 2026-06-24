"""Dev entry point: `python run.py`.

Adds src/ to the path (so no install is needed for local dev) and runs uvicorn
on 127.0.0.1:8000 to match the frontend's Vite dev proxy. For a packaged run,
`pip install -e .` then `uvicorn bullseye_copilot.main:app --port 8000`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import uvicorn  # noqa: E402

from bullseye_copilot.core.config import HOST, PORT  # noqa: E402

if __name__ == "__main__":
    uvicorn.run("bullseye_copilot.main:app", host=HOST, port=PORT, reload=True,
                reload_dirs=[str(Path(__file__).resolve().parent / "src")])
