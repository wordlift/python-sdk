from __future__ import annotations

from rdflib import Graph, Literal, RDF, URIRef

from wordlift_sdk.kg_build.id_generator import CanonicalIdGenerator
from wordlift_sdk.kg_build.iri_lookup import IriLookup
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


def test_rewrites_non_canonical_dataset_subject_prefix() -> None:
    graph = Graph()
    subject = URIRef(
        "https://kg.smallpdf.com/smallpdf/articles/"
        "https://smallpdf.com/blog/how-to-delete-pages-from-a-pdf/"
        "actions/convert-pdf-to-word"
    )
    graph.add((subject, RDF.type, URIRef(f"{SCHEMA}Article")))
    graph.add(
        (
            subject,
            URIRef(f"{SCHEMA}url"),
            Literal("https://smallpdf.com/blog/how-to-delete-pages-from-a-pdf"),
        )
    )

    output = CanonicalIdGenerator().apply(graph, "https://kg.smallpdf.com")

    assert (subject, RDF.type, URIRef(f"{SCHEMA}Article")) not in output
    rewritten_articles = list(output.subjects(RDF.type, URIRef(f"{SCHEMA}Article")))
    assert len(rewritten_articles) == 1
    assert str(rewritten_articles[0]).startswith("https://kg.smallpdf.com/articles/")


def test_keeps_subject_with_canonical_root_prefix() -> None:
    graph = Graph()
    subject = URIRef("https://data.example.com/products/alpha/offers/offer-1")
    graph.add((subject, RDF.type, URIRef(f"{SCHEMA}Offer")))

    output = CanonicalIdGenerator().apply(graph, DATASET)

    assert (subject, RDF.type, URIRef(f"{SCHEMA}Offer")) in output


def test_rewrites_action_subject_as_nested_dependent_entity() -> None:
    graph = Graph()
    article = URIRef(
        "https://kg.smallpdf.com/smallpdf/articles/"
        "https://smallpdf.com/blog/how-to-print-secured-pdf"
    )
    action = URIRef(
        "https://kg.smallpdf.com/smallpdf/articles/"
        "https://smallpdf.com/blog/how-to-print-secured-pdf/"
        "actions/convert-pdf-to-word"
    )
    graph.add((article, RDF.type, URIRef(f"{SCHEMA}Article")))
    graph.add(
        (
            article,
            URIRef(f"{SCHEMA}url"),
            Literal("https://smallpdf.com/blog/how-to-print-secured-pdf"),
        )
    )
    graph.add((article, URIRef(f"{SCHEMA}potentialAction"), action))
    graph.add((action, RDF.type, URIRef(f"{SCHEMA}Action")))
    graph.add((action, URIRef(f"{SCHEMA}name"), Literal("Convert PDF to Word")))

    output = CanonicalIdGenerator().apply(graph, "https://kg.smallpdf.com")

    rewritten_articles = list(output.subjects(RDF.type, URIRef(f"{SCHEMA}Article")))
    assert len(rewritten_articles) == 1
    rewritten_article = rewritten_articles[0]
    nested_actions = list(
        output.objects(rewritten_article, URIRef(f"{SCHEMA}potentialAction"))
    )
    assert len(nested_actions) == 1
    nested_action = nested_actions[0]
    assert str(nested_action).startswith(f"{rewritten_article}/actions/")
    assert (nested_action, RDF.type, URIRef(f"{SCHEMA}Action")) in output


class _DictLookup(IriLookup):
    def __init__(self, mapping: dict[str, str]) -> None:
        self._mapping = mapping

    def iri_for_subject(self, graph: Graph, subject: URIRef) -> str | None:
        value = graph.value(subject, URIRef(f"{SCHEMA}url"))
        if value is None:
            return None
        return self._mapping.get(str(value))


def test_lookup_rewrites_only_root_subjects_not_dependent_nodes() -> None:
    graph = Graph()
    root = URIRef("https://example.com/product")
    offer = URIRef("https://example.com/product#offer")
    graph.add((root, RDF.type, URIRef(f"{SCHEMA}Product")))
    graph.add((root, URIRef(f"{SCHEMA}url"), Literal("https://example.com/product")))
    graph.add((root, URIRef(f"{SCHEMA}offers"), offer))
    graph.add((offer, RDF.type, URIRef(f"{SCHEMA}Offer")))
    graph.add((offer, URIRef(f"{SCHEMA}url"), Literal("https://example.com/product")))

    lookup = _DictLookup(
        {"https://example.com/product": "https://kg.example.com/products/from-lookup"}
    )
    output = CanonicalIdGenerator().apply(graph, DATASET, iri_lookup=lookup)

    root_iri = URIRef("https://kg.example.com/products/from-lookup")
    assert (root_iri, RDF.type, URIRef(f"{SCHEMA}Product")) in output
    # Offer remains canonically nested under the root and is not directly replaced
    # with the same lookup IRI as the parent.
    nested_offers = list(output.objects(root_iri, URIRef(f"{SCHEMA}offers")))
    assert len(nested_offers) == 1
    assert str(nested_offers[0]).startswith(f"{root_iri}/offers/")


def test_lookup_miss_falls_back_to_default_generation() -> None:
    graph = Graph()
    root = URIRef("https://example.com/article")
    graph.add((root, RDF.type, URIRef(f"{SCHEMA}Article")))
    graph.add((root, URIRef(f"{SCHEMA}url"), Literal("https://example.com/article")))

    output = CanonicalIdGenerator().apply(
        graph, DATASET, iri_lookup=_DictLookup(mapping={})
    )

    rewritten_articles = list(output.subjects(RDF.type, URIRef(f"{SCHEMA}Article")))
    assert len(rewritten_articles) == 1
    assert str(rewritten_articles[0]).startswith(f"{DATASET}/articles/")
