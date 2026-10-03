"""Shared fixtures.

The 30 MB corpus is not in git, so every test that reads it asks for the
``trials`` fixture and is skipped, with the command that fixes it, when the
file is absent. Everything else (parser, label file) runs on a fresh clone.
"""

from __future__ import annotations

import pytest

from trialmatch import corpus


@pytest.fixture(scope="session")
def trials() -> tuple[corpus.Trial, ...]:
    if not corpus.available():
        pytest.skip(
            f"needs {corpus.trials_path()}: run `python scripts/fetch_trials.py` "
            f"or set {corpus.DATA_ENV}"
        )
    return corpus.load()
