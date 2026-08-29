"""Error types for the baseline evaluator.

The baseline fails closed: any problem (input, provider, parsing, or
validation) surfaces as an exception or a recorded failure result rather
than a coerced score.
"""

from __future__ import annotations


class BaselineError(Exception):
    """Failure in the baseline evaluator pipeline."""


class ProviderError(BaselineError):
    """The LLM provider raised or returned unusable content."""


class MalformedResponse(ProviderError):
    """The provider response could not be parsed into a structured assessment."""
