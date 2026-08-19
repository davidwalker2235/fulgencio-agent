from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

sys.argv = [
    "litellm",
    "--config",
    str(ROOT / "litellm_config.yaml"),
    "--host",
    os.getenv("LITELLM_HOST", "127.0.0.1"),
    "--port",
    os.getenv("LITELLM_PORT", "4000"),
]

from litellm import run_server

run_server()
