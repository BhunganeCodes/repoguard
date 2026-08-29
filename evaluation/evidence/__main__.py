"""Entry point for ``python -m evaluation.evidence``."""

from __future__ import annotations

import sys

from evaluation.evidence.cli import main

if __name__ == "__main__":
    sys.exit(main())
