from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
async def _clean(clean_runtime: dict[str, Any]) -> dict[str, Any]:
    return clean_runtime
