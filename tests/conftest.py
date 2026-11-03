# SPDX-License-Identifier: Apache-2.0
import pytest

from master_library.settings import Settings


@pytest.fixture
def settings(tmp_path):
    """Settings in a temporary folder, never the user's own."""
    return Settings(tmp_path / "settings")
