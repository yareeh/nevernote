from pathlib import Path

import pytest
from sample import build_sample


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return build_sample(tmp_path)
