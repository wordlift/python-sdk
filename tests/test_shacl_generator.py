from pathlib import Path

from wordlift_sdk.validation.generator import FeatureData, _write_feature


def _read_output(tmp_path: Path, feature: FeatureData) -> str:
    output_path = tmp_path / "google-carousel.ttl"
    assert _write_feature(feature, output_path, overwrite=True)
    return output_path.read_text(encoding="utf-8")


def test_scopes_listitem_under_itemlist(tmp_path: Path) -> None:
    feature = FeatureData(
        url="https://example.com",
        types={
            "ItemList": {"required": {"itemListElement"}, "recommended": set()},
            "ListItem": {
                "required": {"position", "url", "name", "item"},
                "recommended": set(),
            },
        },
    )

    content = _read_output(tmp_path, feature)

    assert "sh:targetClass schema:ItemList" in content
    assert "sh:targetClass schema:ListItem" not in content
    assert "sh:path schema:itemListElement" in content
    assert "sh:node [" in content
    assert "sh:class schema:ListItem" in content
    assert "sh:path schema:url" in content


def test_keeps_listitem_shape_without_itemlist(tmp_path: Path) -> None:
    feature = FeatureData(
        url="https://example.com",
        types={
            "ListItem": {
                "required": {"position", "url"},
                "recommended": set(),
            }
        },
    )

    content = _read_output(tmp_path, feature)

    assert "sh:targetClass schema:ListItem" in content
