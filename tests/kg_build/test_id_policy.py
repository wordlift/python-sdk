from __future__ import annotations

from wordlift_sdk.kg_build.id_policy import DEFAULT_ID_POLICY, type_name_to_container


def test_type_name_to_container_pluralization_rules() -> None:
    assert type_name_to_container("Class") == "classes"
    assert type_name_to_container("Category") == "categories"
    assert type_name_to_container("WebPage") == "web-pages"


def test_default_policy_dependency_and_root_helpers() -> None:
    assert DEFAULT_ID_POLICY.normalize_type_name("FinancialProduct") == "Product"
    assert DEFAULT_ID_POLICY.container_for_type("Thing") == "things"
    assert DEFAULT_ID_POLICY.dependency_rule_for("Offer") is not None
    assert DEFAULT_ID_POLICY.is_dependent("Offer") is True
    assert DEFAULT_ID_POLICY.is_page_root_type("WebPage") is True
    assert DEFAULT_ID_POLICY.is_entity_root_type("Product") is True
    assert DEFAULT_ID_POLICY.preferred_type({"Thing", "WebPage"}) == "WebPage"
    assert DEFAULT_ID_POLICY.preferred_type(set()) == "Thing"
