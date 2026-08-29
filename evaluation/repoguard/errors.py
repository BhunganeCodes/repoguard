"""Error types for the RepoGuard structured assessment subsystem.

RepoGuard fails closed: any problem (input, provider, parsing, planning,
cross-check, or scoring validation) surfaces as an exception or a recorded
failure result rather than a coerced score. Parsing and provider failures
reuse the baseline's error types so both systems share one provider contract.
"""

from __future__ import annotations

from evaluation.baseline.errors import MalformedResponse, ProviderError

__all__ = ["RepoGuardError", "ProviderError", "MalformedResponse"]


class RepoGuardError(Exception):
    """Failure in the RepoGuard assessment workflow."""
