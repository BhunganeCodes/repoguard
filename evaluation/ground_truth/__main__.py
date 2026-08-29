"""Entry point for ``python -m evaluation.ground_truth``."""

from __future__ import annotations

import sys

from evaluation.ground_truth.cli import main

if __name__ == "__main__":
    sys.exit(main())
