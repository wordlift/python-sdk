from __future__ import annotations

from rdflib import URIRef

from wordlift_sdk.validation import shacl

SCHEMA = "http://schema.org/"


def test_schemaorg_subclasses_is_transitive_and_includes_the_class() -> None:
    actions = shacl.schemaorg_subclasses(URIRef(f"{SCHEMA}Action"))

    assert URIRef(f"{SCHEMA}Action") in actions
    assert URIRef(f"{SCHEMA}TradeAction") in actions
    assert URIRef(f"{SCHEMA}BuyAction") in actions  # via TradeAction
    assert URIRef(f"{SCHEMA}ReserveAction") in actions  # three levels down
    assert URIRef(f"{SCHEMA}Offer") not in actions
    assert URIRef(f"{SCHEMA}Thing") not in actions


def test_schemaorg_subclasses_normalizes_https_schema_uris() -> None:
    assert shacl.schemaorg_subclasses(
        URIRef("https://schema.org/Action")
    ) == shacl.schemaorg_subclasses(URIRef(f"{SCHEMA}Action"))


def test_schemaorg_subclasses_of_a_leaf_is_only_itself() -> None:
    buy = URIRef(f"{SCHEMA}BuyAction")

    assert shacl.schemaorg_subclasses(buy) == frozenset({buy})
