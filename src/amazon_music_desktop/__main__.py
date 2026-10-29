"""Entry point."""

from __future__ import annotations

import os
import sys

# Ensure src layout importable when running as script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .app import main

if __name__ == "__main__":
    raise SystemExit(main())
