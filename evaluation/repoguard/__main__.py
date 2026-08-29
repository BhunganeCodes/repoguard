"""Entry point for ``python -m evaluation.repoguard``."""

from __future__ import annotations

import sys

from evaluation.repoguard.cli import main

if __name__ == "__main__":
    sys.exit(main())
