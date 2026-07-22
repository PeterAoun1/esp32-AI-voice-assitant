"""
Simple launcher so you can still run:
  python src/server.py

Preferred:
  python -m backend.app
"""

import sys
from pathlib import Path

# Make sure the project root is on the Python path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app import app  # noqa: E402
from backend import config  # noqa: E402

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=config.HOST, port=config.PORT)
