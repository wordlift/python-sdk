from __future__ import annotations

from rdflib import Graph, Literal, RDF, URIRef
from rdflib.namespace import XSD

from wordlift_sdk.kg_build.postprocessors.processors.id_generator import (
    CanonicalIdGenerator,
)
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


def test_should_rewrite_subject_requires_full_canonical_shape() -> None:
    generator = CanonicalIdGenerator()

    assert (
        generator._should_rewrite_subject(
            URIRef(f"{DATASET}/services/https://example.com/page"),
            DATASET,
        )
        is True
    )
    assert (
        generator._should_rewrite_subject(
            URIRef(f"{DATASET}/services/service-123"),
            DATASET,
        )
        is False
    )


def test_rewrites_bad_service_root_and_child_ids_and_is_idempotent() -> None:
    graph = Graph()
    bad_service = URIRef(f"{DATASET}/services/https://example.com/page")
    bad_rating = URIRef(f"{bad_service}/aggregate-rating/trustpilot")
    graph.add((bad_service, RDF.type, URIRef(f"{SCHEMA}Service")))
    graph.add((bad_service, URIRef(f"{SCHEMA}name"), Literal("Managed VPS")))
    graph.add(
        (bad_service, URIRef(f"{SCHEMA}url"), Literal("https://example.com/page"))
    )
    graph.add((bad_service, URIRef(f"{SCHEMA}aggregateRating"), bad_rating))
    graph.add((bad_rating, RDF.type, URIRef(f"{SCHEMA}AggregateRating")))
    graph.add((bad_rating, URIRef(f"{SCHEMA}name"), Literal("Trustpilot")))

    generator = CanonicalIdGenerator()
    output = generator.apply(graph, DATASET)

    service_hash = generator._url_hash("https://example.com/page")
    canonical_service = URIRef(f"{DATASET}/services/managed-vps-{service_hash}")
    canonical_rating = URIRef(f"{canonical_service}/aggregate-rating/trustpilot")

    assert (bad_service, RDF.type, URIRef(f"{SCHEMA}Service")) not in output
    assert (bad_rating, RDF.type, URIRef(f"{SCHEMA}AggregateRating")) not in output
    assert (canonical_service, RDF.type, URIRef(f"{SCHEMA}Service")) in output
    assert (
        canonical_service,
        URIRef(f"{SCHEMA}aggregateRating"),
        canonical_rating,
    ) in output
    assert (canonical_rating, RDF.type, URIRef(f"{SCHEMA}AggregateRating")) in output
    assert (
        canonical_service,
        URIRef(f"{SCHEMA}url"),
        Literal("https://example.com/page"),
    ) in output

    first_pass = set(output)
    second_pass = generator.apply(output, DATASET)
    assert set(second_pass) == first_pass


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


def test_review_linked_faqpage_is_nested_not_flat() -> None:
    """FAQPage linked via Review -> subjectOf -> FAQPage must be canonicalized
    under the Review IRI, not as a dataset-root /faq-pages/faqpage."""
    graph = Graph()
    review = URIRef("https://example.com/review/product-x")
    faq = URIRef("https://example.com/faq-pages/product-x-faq")
    question = URIRef("https://example.com/questions/is-auto-approve-legit")
    answer = URIRef("https://example.com/answers/answer-1")
    rating = URIRef("https://example.com/ratings/rating-1")

    graph.add((review, RDF.type, URIRef(f"{SCHEMA}Review")))
    graph.add((review, URIRef(f"{SCHEMA}name"), Literal("Product X Review")))
    graph.add((review, URIRef(f"{SCHEMA}subjectOf"), faq))
    graph.add((review, URIRef(f"{SCHEMA}reviewRating"), rating))

    graph.add((faq, RDF.type, URIRef(f"{SCHEMA}FAQPage")))
    graph.add((faq, URIRef(f"{SCHEMA}about"), review))
    graph.add((faq, URIRef(f"{SCHEMA}mainEntity"), question))

    graph.add((question, RDF.type, URIRef(f"{SCHEMA}Question")))
    graph.add((question, URIRef(f"{SCHEMA}name"), Literal("Is auto-approve legit?")))
    graph.add((question, URIRef(f"{SCHEMA}acceptedAnswer"), answer))

    graph.add((answer, RDF.type, URIRef(f"{SCHEMA}Answer")))
    graph.add((answer, URIRef(f"{SCHEMA}text"), Literal("Yes.")))

    graph.add((rating, RDF.type, URIRef(f"{SCHEMA}Rating")))
    graph.add((rating, URIRef(f"{SCHEMA}ratingValue"), Literal("4.5")))

    output = CanonicalIdGenerator().apply(graph, DATASET)

    reviews = list(output.subjects(RDF.type, URIRef(f"{SCHEMA}Review")))
    assert len(reviews) == 1
    review_iri = reviews[0]
    assert str(review_iri).startswith(f"{DATASET}/reviews/"), review_iri

    # FAQPage must be nested under the review, not at dataset root
    faqs = list(output.subjects(RDF.type, URIRef(f"{SCHEMA}FAQPage")))
    assert len(faqs) == 1
    faq_iri = faqs[0]
    assert str(faq_iri).startswith(str(review_iri)), (
        f"FAQPage {faq_iri} not nested under Review {review_iri}"
    )
    assert "/faq-pages/" in str(faq_iri)

    # Question must be nested under the FAQPage
    questions = list(output.subjects(RDF.type, URIRef(f"{SCHEMA}Question")))
    assert len(questions) == 1
    question_iri = questions[0]
    assert str(question_iri).startswith(str(faq_iri)), (
        f"Question {question_iri} not nested under FAQPage {faq_iri}"
    )

    # Answer must be nested under the Question
    answers = list(output.subjects(RDF.type, URIRef(f"{SCHEMA}Answer")))
    assert len(answers) == 1
    answer_iri = answers[0]
    assert str(answer_iri).startswith(str(question_iri)), (
        f"Answer {answer_iri} not nested under Question {question_iri}"
    )

    # Rating must be nested under the Review
    ratings = list(output.subjects(RDF.type, URIRef(f"{SCHEMA}Rating")))
    assert len(ratings) == 1
    rating_iri = ratings[0]
    assert str(rating_iri).startswith(str(review_iri)), (
        f"Rating {rating_iri} not nested under Review {review_iri}"
    )
    assert "/ratings/" in str(rating_iri)

    # No dataset-root flat IRIs should be produced for these node types
    all_subjects = {str(s) for s in output.subjects() if isinstance(s, URIRef)}
    assert not any(s == f"{DATASET}/faq-pages/faqpage" for s in all_subjects)
    assert not any(s.startswith(f"{DATASET}/questions/") for s in all_subjects)
    assert not any(s.startswith(f"{DATASET}/answers/") for s in all_subjects)
    assert not any(s.startswith(f"{DATASET}/ratings/") for s in all_subjects)


def test_article_linked_faqpage_via_subject_of_is_nested() -> None:
    """FAQPage linked via Article -> subjectOf -> FAQPage must be nested under
    the Article IRI (same pattern as Review but with Article type)."""
    graph = Graph()
    article = URIRef("https://example.com/blog/article-1")
    faq = URIRef("https://example.com/faq-pages/article-1-faq")
    question = URIRef("https://example.com/questions/what-is-this")
    answer = URIRef("https://example.com/answers/answer-1")

    graph.add((article, RDF.type, URIRef(f"{SCHEMA}Article")))
    graph.add((article, URIRef(f"{SCHEMA}name"), Literal("Article 1")))
    graph.add((article, URIRef(f"{SCHEMA}subjectOf"), faq))

    graph.add((faq, RDF.type, URIRef(f"{SCHEMA}FAQPage")))
    graph.add((faq, URIRef(f"{SCHEMA}about"), article))
    graph.add((faq, URIRef(f"{SCHEMA}mainEntity"), question))

    graph.add((question, RDF.type, URIRef(f"{SCHEMA}Question")))
    graph.add((question, URIRef(f"{SCHEMA}name"), Literal("What is this?")))
    graph.add((question, URIRef(f"{SCHEMA}acceptedAnswer"), answer))

    graph.add((answer, RDF.type, URIRef(f"{SCHEMA}Answer")))
    graph.add((answer, URIRef(f"{SCHEMA}text"), Literal("It is an article.")))

    output = CanonicalIdGenerator().apply(graph, DATASET)

    articles = list(output.subjects(RDF.type, URIRef(f"{SCHEMA}Article")))
    assert len(articles) == 1
    article_iri = articles[0]
    assert str(article_iri).startswith(f"{DATASET}/articles/")

    faqs = list(output.subjects(RDF.type, URIRef(f"{SCHEMA}FAQPage")))
    assert len(faqs) == 1
    faq_iri = faqs[0]
    assert str(faq_iri).startswith(str(article_iri)), (
        f"FAQPage {faq_iri} not nested under Article {article_iri}"
    )

    questions = list(output.subjects(RDF.type, URIRef(f"{SCHEMA}Question")))
    assert len(questions) == 1
    question_iri = questions[0]
    assert str(question_iri).startswith(str(faq_iri))

    answers = list(output.subjects(RDF.type, URIRef(f"{SCHEMA}Answer")))
    assert len(answers) == 1
    answer_iri = answers[0]
    assert str(answer_iri).startswith(str(question_iri))


def test_review_linked_faqpage_canonicalization_is_idempotent() -> None:
    """Applying canonicalization twice must yield the same graph."""
    graph = Graph()
    review = URIRef("https://example.com/review/product-y")
    faq = URIRef("https://example.com/faq-pages/product-y-faq")
    question = URIRef("https://example.com/questions/is-it-good")
    answer = URIRef("https://example.com/answers/answer-1")
    rating = URIRef("https://example.com/ratings/rating-1")

    graph.add((review, RDF.type, URIRef(f"{SCHEMA}Review")))
    graph.add((review, URIRef(f"{SCHEMA}name"), Literal("Product Y Review")))
    graph.add((review, URIRef(f"{SCHEMA}subjectOf"), faq))
    graph.add((review, URIRef(f"{SCHEMA}reviewRating"), rating))

    graph.add((faq, RDF.type, URIRef(f"{SCHEMA}FAQPage")))
    graph.add((faq, URIRef(f"{SCHEMA}about"), review))
    graph.add((faq, URIRef(f"{SCHEMA}mainEntity"), question))

    graph.add((question, RDF.type, URIRef(f"{SCHEMA}Question")))
    graph.add((question, URIRef(f"{SCHEMA}name"), Literal("Is it good?")))
    graph.add((question, URIRef(f"{SCHEMA}acceptedAnswer"), answer))

    graph.add((answer, RDF.type, URIRef(f"{SCHEMA}Answer")))
    graph.add((answer, URIRef(f"{SCHEMA}text"), Literal("Yes.")))

    graph.add((rating, RDF.type, URIRef(f"{SCHEMA}Rating")))
    graph.add((rating, URIRef(f"{SCHEMA}ratingValue"), Literal("5")))

    generator = CanonicalIdGenerator()
    first_pass = generator.apply(graph, DATASET)
    first_triples = set(first_pass)
    second_pass = generator.apply(first_pass, DATASET)
    assert set(second_pass) == first_triples


def test_review_with_faq_and_rating_real_world_graph() -> None:
    """Regression test using a realistic production-shaped graph.

    Verifies that FAQPage/Question/Answer/Rating nodes are all canonicalized
    as nested IRIs under the owning Review — never as dataset-root flat paths.

    Forbidden flat IRIs that must NOT appear:
      .../faq-pages/faqpage
      .../questions/is-auto-approve-legit
      .../answers/answer
      .../ratings/rating
    """
    DATASET = "https://data.wordlift.io/example"

    g = Graph()
    review = URIRef(f"{DATASET}/reviews/review-seed")
    product = URIRef(f"{DATASET}/products/product-seed")
    faq = URIRef(f"{DATASET}/faq-pages/auto-approve-da7741d47cf8756e")
    question = URIRef(f"{faq}/questions/question-b7a1b63ec70f217e")
    answer = URIRef(f"{question}/answers/answer-1")
    rating = URIRef(
        f"{DATASET}/reviews/auto-approve-da7741d47cf8756e/ratings/review-rating-da7741d47cf8"
    )

    g.add((review, RDF.type, URIRef(f"{SCHEMA}Review")))
    g.add(
        (
            review,
            URIRef(f"{SCHEMA}url"),
            Literal(
                "https://www.example.com/auto/reviews/auto-approve/",
                datatype=XSD.string,
            ),
        )
    )
    g.add(
        (review, URIRef(f"{SCHEMA}name"), Literal("2026 Auto Approve Auto Loan Review"))
    )
    g.add(
        (
            review,
            URIRef(f"{SCHEMA}headline"),
            Literal("2026 Auto Approve Auto Loan Review"),
        )
    )
    g.add((review, URIRef(f"{SCHEMA}itemReviewed"), product))
    g.add((review, URIRef(f"{SCHEMA}subjectOf"), faq))
    g.add((review, URIRef(f"{SCHEMA}reviewRating"), rating))

    g.add((product, RDF.type, URIRef(f"{SCHEMA}Product")))
    g.add((product, URIRef(f"{SCHEMA}name"), Literal("Auto Approve")))

    g.add((faq, RDF.type, URIRef(f"{SCHEMA}FAQPage")))
    g.add((faq, URIRef(f"{SCHEMA}about"), review))
    g.add((faq, URIRef(f"{SCHEMA}mainEntity"), question))

    g.add((question, RDF.type, URIRef(f"{SCHEMA}Question")))
    g.add(
        (
            question,
            URIRef(f"{SCHEMA}name"),
            Literal("Is Auto Approve legit?", datatype=XSD.string),
        )
    )
    g.add((question, URIRef(f"{SCHEMA}acceptedAnswer"), answer))

    g.add((answer, RDF.type, URIRef(f"{SCHEMA}Answer")))
    g.add((answer, URIRef(f"{SCHEMA}text"), Literal("Yes.", datatype=XSD.string)))

    g.add((rating, RDF.type, URIRef(f"{SCHEMA}Rating")))
    g.add(
        (rating, URIRef(f"{SCHEMA}ratingValue"), Literal("4.79", datatype=XSD.decimal))
    )

    out = CanonicalIdGenerator().apply(g, DATASET)

    def one(type_name: str) -> str:
        subjects = list(out.subjects(RDF.type, URIRef(f"{SCHEMA}{type_name}")))
        assert len(subjects) == 1, f"Expected 1 {type_name}, got {subjects}"
        return str(subjects[0])

    review_iri = one("Review")
    product_iri = one("Product")
    faq_iri = one("FAQPage")
    question_iri = one("Question")
    answer_iri = one("Answer")
    rating_iri = one("Rating")

    # Review and Product get dataset-root canonical paths
    assert review_iri.startswith(f"{DATASET}/reviews/"), review_iri
    assert product_iri.startswith(f"{DATASET}/products/"), product_iri

    # FAQPage must be nested under the review, not at dataset root
    assert faq_iri.startswith(review_iri + "/faq-pages/"), (
        f"FAQPage not nested under Review:\n  FAQ:    {faq_iri}\n  Review: {review_iri}"
    )
    # Question must be nested under the FAQPage
    assert question_iri.startswith(faq_iri + "/questions/"), (
        f"Question not nested under FAQPage:\n  Q:   {question_iri}\n  FAQ: {faq_iri}"
    )
    # Answer must be nested under the Question
    assert answer_iri.startswith(question_iri + "/answers/"), (
        f"Answer not nested under Question:\n  A: {answer_iri}\n  Q: {question_iri}"
    )
    # Rating must be nested under the Review
    assert rating_iri.startswith(review_iri + "/ratings/"), (
        f"Rating not nested under Review:\n  Rating: {rating_iri}\n  Review: {review_iri}"
    )

    # None of the known bad flat paths may appear
    all_subjects = {str(s) for s in out.subjects() if isinstance(s, URIRef)}
    forbidden = [
        f"{DATASET}/faq-pages/faqpage",
        f"{DATASET}/questions/is-auto-approve-legit",
        f"{DATASET}/answers/answer",
        f"{DATASET}/ratings/rating",
    ]
    for bad in forbidden:
        assert bad not in all_subjects, f"Forbidden flat IRI produced: {bad}"


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


# ---------------------------------------------------------------------------
# dependency_graph strategy tests
# ---------------------------------------------------------------------------


def test_dependency_graph_strategy_reparents_faq_under_article_typed_as_faqpage() -> (
    None
):
    """Article+FAQPage root: Questions/Answers are reparented generically.

    The Article is typed both ``schema:Article`` and ``schema:FAQPage`` — no
    intermediate FAQPage node.  The dependency_graph strategy must walk the
    ``Question -> FAQPage -> mainEntity`` rule (matching because FAQPage is in
    the root's type set) and reparent the Question (and its Answer) under the
    newly canonical Article IRI.

    Expected transformation:
      old root  : .../articles/article-1
      new root  : .../articles/article-1-<hash>
      question  : .../articles/<new>/questions/<q-slug>
      answer    : .../articles/<new>/questions/<q-slug>/answers/answer
    """
    graph = Graph()
    article = URIRef("https://example.com/articles/article-1")
    question = URIRef("https://example.com/articles/article-1/questions/question-abc")
    answer = URIRef(
        "https://example.com/articles/article-1/questions/question-abc/answers/answer-1"
    )

    graph.add((article, RDF.type, URIRef(f"{SCHEMA}Article")))
    graph.add((article, RDF.type, URIRef(f"{SCHEMA}FAQPage")))
    graph.add(
        (
            article,
            URIRef(f"{SCHEMA}name"),
            Literal("Credit Card Debt Relief Freedom Debt Relief"),
        )
    )
    graph.add(
        (
            article,
            URIRef(f"{SCHEMA}url"),
            Literal("https://example.com/articles/article-1"),
        )
    )
    graph.add((article, URIRef(f"{SCHEMA}mainEntity"), question))

    graph.add((question, RDF.type, URIRef(f"{SCHEMA}Question")))
    graph.add((question, URIRef(f"{SCHEMA}name"), Literal("What is debt relief?")))
    graph.add((question, URIRef(f"{SCHEMA}acceptedAnswer"), answer))

    graph.add((answer, RDF.type, URIRef(f"{SCHEMA}Answer")))
    graph.add((answer, URIRef(f"{SCHEMA}text"), Literal("Debt relief reduces debt.")))

    generator = CanonicalIdGenerator(strategy="dependency_graph")
    output = generator.apply(graph, DATASET)

    articles = list(output.subjects(RDF.type, URIRef(f"{SCHEMA}Article")))
    assert len(articles) == 1
    article_iri = str(articles[0])
    url_hash = generator._url_hash("https://example.com/articles/article-1")
    assert (
        article_iri
        == f"{DATASET}/articles/credit-card-debt-relief-freedom-debt-relief-{url_hash}"
    ), article_iri

    questions = list(output.subjects(RDF.type, URIRef(f"{SCHEMA}Question")))
    assert len(questions) == 1
    question_iri = str(questions[0])
    assert question_iri.startswith(f"{article_iri}/questions/"), question_iri

    answers = list(output.subjects(RDF.type, URIRef(f"{SCHEMA}Answer")))
    assert len(answers) == 1
    answer_iri = str(answers[0])
    assert answer_iri.startswith(f"{question_iri}/answers/"), answer_iri

    # No stale external article path may remain anywhere in the graph
    all_iris = {str(s) for s in output.subjects() if isinstance(s, URIRef)}
    assert not any(iri.startswith("https://example.com/") for iri in all_iris), all_iris


def test_dependency_graph_strategy_is_generic_product_offer_pricespec() -> None:
    """Non-FAQ case: Product → Offer → PriceSpecification reparented generically.

    Verifies that the dependency_graph strategy is truly generic and not limited
    to FAQ hierarchies.
    """
    graph = Graph()
    product = URIRef("https://example.com/products/widget")
    offer_a = URIRef("https://example.com/offers/a")
    offer_b = URIRef("https://example.com/offers/b")
    price_1 = URIRef("https://example.com/prices/1")
    price_2 = URIRef("https://example.com/prices/2")

    graph.add((product, RDF.type, URIRef(f"{SCHEMA}Product")))
    graph.add((product, URIRef(f"{SCHEMA}name"), Literal("Widget Pro")))
    graph.add(
        (
            product,
            URIRef(f"{SCHEMA}url"),
            Literal("https://example.com/products/widget"),
        )
    )
    graph.add((product, URIRef(f"{SCHEMA}offers"), offer_a))
    graph.add((product, URIRef(f"{SCHEMA}offers"), offer_b))

    graph.add((offer_a, RDF.type, URIRef(f"{SCHEMA}Offer")))
    graph.add((offer_a, URIRef(f"{SCHEMA}priceSpecification"), price_1))
    graph.add((offer_b, RDF.type, URIRef(f"{SCHEMA}Offer")))
    graph.add((offer_b, URIRef(f"{SCHEMA}priceSpecification"), price_2))

    graph.add((price_1, RDF.type, URIRef(f"{SCHEMA}PriceSpecification")))
    graph.add((price_1, URIRef(f"{SCHEMA}price"), Literal("9.99")))
    graph.add((price_2, RDF.type, URIRef(f"{SCHEMA}PriceSpecification")))
    graph.add((price_2, URIRef(f"{SCHEMA}price"), Literal("19.99")))

    generator = CanonicalIdGenerator(strategy="dependency_graph")
    output = generator.apply(graph, DATASET)

    products = list(output.subjects(RDF.type, URIRef(f"{SCHEMA}Product")))
    assert len(products) == 1
    product_iri = str(products[0])
    assert product_iri.startswith(f"{DATASET}/products/")

    offers = sorted(output.subjects(RDF.type, URIRef(f"{SCHEMA}Offer")), key=str)
    assert len(offers) == 2
    for offer_iri in offers:
        assert str(offer_iri).startswith(f"{product_iri}/offers/"), offer_iri

    price_specs = sorted(
        output.subjects(RDF.type, URIRef(f"{SCHEMA}PriceSpecification")), key=str
    )
    assert len(price_specs) == 2
    for ps_iri in price_specs:
        # Each PriceSpecification must be nested under its parent Offer
        parent_offers = list(
            output.subjects(URIRef(f"{SCHEMA}priceSpecification"), ps_iri)
        )
        assert len(parent_offers) == 1
        assert str(ps_iri).startswith(
            str(parent_offers[0]) + "/price-specifications/"
        ), ps_iri

    # No stale flat price/offer paths
    all_iris = {str(s) for s in output.subjects() if isinstance(s, URIRef)}
    assert not any(s.startswith("https://example.com/") for s in all_iris), all_iris


def test_dependency_graph_strategy_default_is_legacy() -> None:
    """Default strategy must remain 'legacy' — no regression for existing callers."""
    graph = Graph()
    review = URIRef("https://example.com/review/x")
    faq = URIRef("https://example.com/faq/x")
    question = URIRef("https://example.com/questions/q1")
    answer = URIRef("https://example.com/answers/a1")
    rating = URIRef("https://example.com/ratings/r1")

    graph.add((review, RDF.type, URIRef(f"{SCHEMA}Review")))
    graph.add((review, URIRef(f"{SCHEMA}name"), Literal("Review X")))
    graph.add((review, URIRef(f"{SCHEMA}subjectOf"), faq))
    graph.add((review, URIRef(f"{SCHEMA}reviewRating"), rating))

    graph.add((faq, RDF.type, URIRef(f"{SCHEMA}FAQPage")))
    graph.add((faq, URIRef(f"{SCHEMA}about"), review))
    graph.add((faq, URIRef(f"{SCHEMA}mainEntity"), question))

    graph.add((question, RDF.type, URIRef(f"{SCHEMA}Question")))
    graph.add((question, URIRef(f"{SCHEMA}name"), Literal("Is it good?")))
    graph.add((question, URIRef(f"{SCHEMA}acceptedAnswer"), answer))

    graph.add((answer, RDF.type, URIRef(f"{SCHEMA}Answer")))
    graph.add((answer, URIRef(f"{SCHEMA}text"), Literal("Yes.")))

    graph.add((rating, RDF.type, URIRef(f"{SCHEMA}Rating")))
    graph.add((rating, URIRef(f"{SCHEMA}ratingValue"), Literal("5")))

    # Default (no strategy arg) must behave identically to strategy="legacy"
    out_default = CanonicalIdGenerator().apply(graph, DATASET)
    out_legacy = CanonicalIdGenerator(strategy="legacy").apply(graph, DATASET)
    assert set(out_default) == set(out_legacy)

    # FAQ/Question/Answer/Rating must be nested under the Review in both cases
    reviews = list(out_default.subjects(RDF.type, URIRef(f"{SCHEMA}Review")))
    assert len(reviews) == 1
    review_iri = str(reviews[0])
    assert review_iri.startswith(f"{DATASET}/reviews/")

    faqs = list(out_default.subjects(RDF.type, URIRef(f"{SCHEMA}FAQPage")))
    assert str(faqs[0]).startswith(review_iri)

    ratings = list(out_default.subjects(RDF.type, URIRef(f"{SCHEMA}Rating")))
    assert str(ratings[0]).startswith(review_iri)
