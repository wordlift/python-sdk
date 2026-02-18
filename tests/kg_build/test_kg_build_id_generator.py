from __future__ import annotations

from rdflib import Graph, Literal, RDF, URIRef

from wordlift_sdk.kg_build.id_generator import CanonicalIdGenerator
from wordlift_sdk.kg_build.id_policy import DEFAULT_ID_POLICY, IdPolicy

SCHEMA = "http://schema.org/"
DATASET = "https://data.example.com"


def test_entity_centric_product_service_rewrites_all_offers_and_price_specs() -> None:
    graph = Graph()
    root = URIRef("https://example.com/p/sku-1")
    graph.add((root, RDF.type, URIRef(f"{SCHEMA}Service")))
    graph.add((root, RDF.type, URIRef(f"{SCHEMA}Product")))
    graph.add((root, URIRef(f"{SCHEMA}name"), Literal("Deluxe Plan")))
    graph.add((root, URIRef(f"{SCHEMA}url"), Literal("https://example.com/p/sku-1")))

    offer_1 = URIRef("https://example.com/offers/a")
    offer_2 = URIRef("https://example.com/offers/b")
    graph.add((root, URIRef(f"{SCHEMA}offers"), offer_1))
    graph.add((root, URIRef(f"{SCHEMA}offers"), offer_2))

    ps_1 = URIRef("https://example.com/prices/1")
    ps_2 = URIRef("https://example.com/prices/2")
    ps_3 = URIRef("https://example.com/prices/3")
    graph.add((offer_1, URIRef(f"{SCHEMA}priceSpecification"), ps_1))
    graph.add((offer_1, URIRef(f"{SCHEMA}priceSpecification"), ps_2))
    graph.add((offer_2, URIRef(f"{SCHEMA}priceSpecification"), ps_3))

    generator = CanonicalIdGenerator()
    output = generator.apply(graph, DATASET)

    root_hash = generator._url_hash("https://example.com/p/sku-1")
    root_iri = URIRef(f"{DATASET}/products/deluxe-plan-{root_hash}")
    assert (
        root_iri,
        URIRef(f"{SCHEMA}url"),
        Literal("https://example.com/p/sku-1"),
    ) in output
    assert (
        root_iri,
        URIRef(f"{SCHEMA}offers"),
        URIRef(f"{root_iri}/offers/offer-1"),
    ) in output
    assert (
        root_iri,
        URIRef(f"{SCHEMA}offers"),
        URIRef(f"{root_iri}/offers/offer-2"),
    ) in output
    assert len(list(output.objects(root_iri, URIRef(f"{SCHEMA}offers")))) == 2

    offer_1_iri = URIRef(f"{root_iri}/offers/offer-1")
    offer_2_iri = URIRef(f"{root_iri}/offers/offer-2")
    assert (
        len(list(output.objects(offer_1_iri, URIRef(f"{SCHEMA}priceSpecification"))))
        == 2
    )
    assert (
        len(list(output.objects(offer_2_iri, URIRef(f"{SCHEMA}priceSpecification"))))
        == 1
    )


def test_page_centric_rewrite_does_not_treat_non_page_url_subject_as_page() -> None:
    graph = Graph()
    page = URIRef("https://example.com/page")
    product = URIRef("https://example.com/product")
    graph.add((page, RDF.type, URIRef(f"{SCHEMA}WebPage")))
    graph.add((page, URIRef(f"{SCHEMA}url"), Literal("https://example.com/page")))
    graph.add((page, URIRef(f"{SCHEMA}mentions"), product))
    graph.add((product, RDF.type, URIRef(f"{SCHEMA}Product")))
    graph.add((product, URIRef(f"{SCHEMA}url"), Literal("https://example.com/product")))

    output = CanonicalIdGenerator().apply(graph, DATASET)

    rewritten_pages = [s for s in output.subjects(RDF.type, URIRef(f"{SCHEMA}WebPage"))]
    assert len(rewritten_pages) == 1
    rewritten_page = rewritten_pages[0]
    assert str(rewritten_page).startswith(f"{DATASET}/web-pages/")

    rewritten_products = [
        s for s in output.subjects(RDF.type, URIRef(f"{SCHEMA}Product"))
    ]
    assert len(rewritten_products) == 1
    rewritten_product = rewritten_products[0]
    assert not str(rewritten_product).startswith(str(rewritten_page))
    assert str(rewritten_product).startswith(f"{DATASET}/products/")


def test_untyped_image_reference_does_not_corrupt_schema_url() -> None:
    graph = Graph()
    page = URIRef("https://example.com/page")
    external = URIRef("https://cdn.example.com/a.png")
    graph.add((page, RDF.type, URIRef(f"{SCHEMA}WebPage")))
    graph.add((page, URIRef(f"{SCHEMA}url"), external))
    graph.add((page, URIRef(f"{SCHEMA}image"), external))

    output = CanonicalIdGenerator().apply(graph, DATASET)

    rewritten_pages = [s for s in output.subjects(RDF.type, URIRef(f"{SCHEMA}WebPage"))]
    assert len(rewritten_pages) == 1
    rewritten_page = rewritten_pages[0]
    assert (rewritten_page, URIRef(f"{SCHEMA}url"), external) in output
    assert (rewritten_page, URIRef(f"{SCHEMA}image"), external) in output


def test_deterministic_type_precedence_for_multi_typed_root() -> None:
    graph = Graph()
    root = URIRef("https://example.com/item")
    graph.add((root, RDF.type, URIRef(f"{SCHEMA}Service")))
    graph.add((root, RDF.type, URIRef(f"{SCHEMA}Product")))
    graph.add((root, URIRef(f"{SCHEMA}name"), Literal("Combo")))

    output = CanonicalIdGenerator().apply(graph, DATASET)
    subjects = list(output.subjects(RDF.type, URIRef(f"{SCHEMA}Product")))
    assert len(subjects) == 1
    assert str(subjects[0]).startswith(f"{DATASET}/products/")


def test_custom_policy_can_prefer_service_container() -> None:
    graph = Graph()
    root = URIRef("https://example.com/item")
    graph.add((root, RDF.type, URIRef(f"{SCHEMA}Service")))
    graph.add((root, RDF.type, URIRef(f"{SCHEMA}Product")))
    graph.add((root, URIRef(f"{SCHEMA}name"), Literal("Combo")))

    policy = IdPolicy(
        dependent_rules=DEFAULT_ID_POLICY.dependent_rules,
        type_aliases=DEFAULT_ID_POLICY.type_aliases,
        container_overrides=DEFAULT_ID_POLICY.container_overrides,
        page_root_types=DEFAULT_ID_POLICY.page_root_types,
        entity_root_types=DEFAULT_ID_POLICY.entity_root_types,
        root_type_precedence=("Service", "Product", "WebPage", "Thing"),
    )

    output = CanonicalIdGenerator(policy=policy).apply(graph, DATASET)
    subjects = list(output.subjects(RDF.type, URIRef(f"{SCHEMA}Service")))
    assert len(subjects) == 1
    assert str(subjects[0]).startswith(f"{DATASET}/services/")
