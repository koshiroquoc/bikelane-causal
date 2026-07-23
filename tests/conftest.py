from __future__ import annotations

import pytest

from bikelane_causal.pipeline import load_config


@pytest.fixture(scope="session")
def config():
    return load_config()
