from __future__ import annotations

import pytest

import wordlift_sdk.kg_build as kg_build


def test_lazy_exports_and_missing_attr() -> None:
    assert kg_build.CloudWorkflowConfig is not None
    assert kg_build.validate_yarrrml_text is not None
    with pytest.raises(AttributeError):
        _ = kg_build.DOES_NOT_EXIST
