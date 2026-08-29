"""Entry point for ``python -m evaluation.scoring``."""

from __future__ import annotations

import sys

from evaluation.scoring.cli import main

if __name__ == "__main__":
    sys.exit(main())
