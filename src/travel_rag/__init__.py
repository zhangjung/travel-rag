"""Multi-Agent travel planning with local RAG."""

import os

# Disable optional third-party telemetry before importing retrieval libraries.
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("DO_NOT_TRACK", "1")

__version__ = "0.1.0"
