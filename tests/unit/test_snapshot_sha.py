"""SHA validation tests."""

from __future__ import annotations

import pytest

from evaluation.snapshot.commits import is_full_sha, normalize_sha
from evaluation.snapshot.errors import InvalidShaError

VALID = "e80360834b59dd4c8bfd45344ad1478ab9f86565"


def test_accepts_full_lowercase() -> None:
    assert is_full_sha(VALID)
    assert normalize_sha(VALID) == VALID


def test_accepts_uppercase_and_normalizes() -> None:
    assert normalize_sha(VALID.upper()) == VALID


def test_strips_surrounding_whitespace() -> None:
    assert normalize_sha(f"  {VALID}\n") == VALID


@pytest.mark.parametrize(
    "value",
    [
        "",
        "e80360834b59dd4c8bfd45344ad1478ab9f8656",  # too short
        "e80360834b59dd4c8bfd45344ad1478ab9f865655",  # too long
        "zzzzzz34b59dd4c8bfd45344ad1478ab9f86565zz",  # non-hex
        "e8036083-4b59-dd4c-8bfd-45344ad1478ab9",  # wrong shape
    ],
)
def test_is_full_sha_rejects_invalid(value: str) -> None:
    assert not is_full_sha(value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "abc",  # short SHA never accepted
        "not-a-sha-40-chars",
        "e80360834b59dd4c8bfd45344ad1478ab9f8656g",  # 'g' is not hex
    ],
)
def test_normalize_sha_rejects_invalid(value: str) -> None:
    with pytest.raises(InvalidShaError):
        normalize_sha(value)
