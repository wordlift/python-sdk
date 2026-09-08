from pathlib import Path

from rdflib import URIRef

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


def test_scopes_listitem_under_breadcrumb_list(tmp_path: Path) -> None:
    feature = FeatureData(
        url="https://example.com",
        types={
            "BreadcrumbList": {"required": {"itemListElement"}, "recommended": set()},
            "ListItem": {
                "required": {"position", "name", "item"},
                "recommended": set(),
            },
        },
    )

    content = _read_output(tmp_path, feature)

    assert "sh:targetClass schema:BreadcrumbList" in content
    assert "sh:targetClass schema:ListItem" not in content
    assert "sh:path schema:itemListElement" in content
    assert "sh:node [" in content
    assert "sh:class schema:ListItem" in content
    assert "sh:path schema:position" in content


def test_scopes_question_under_qapage(tmp_path: Path) -> None:
    feature = FeatureData(
        url="https://example.com",
        types={
            "QAPage": {"required": {"mainEntity"}, "recommended": set()},
            "Question": {
                "required": {"acceptedAnswer", "suggestedAnswer"},
                "recommended": {"comment"},
            },
            "Answer": {"required": {"text"}, "recommended": {"comment"}},
            "Comment": {"required": {"text"}, "recommended": set()},
        },
    )

    content = _read_output(tmp_path, feature)

    assert "sh:targetClass schema:QAPage" in content
    assert "sh:targetClass schema:Question" not in content
    assert "sh:targetClass schema:Answer" not in content
    assert "sh:targetClass schema:Comment" not in content
    assert "sh:path schema:mainEntity" in content
    assert "sh:class schema:Question" in content
    assert "sh:path schema:acceptedAnswer" in content
    assert "sh:class schema:Answer" in content
    assert "sh:path schema:comment" in content
    assert "sh:class schema:Comment" in content


def test_scopes_question_under_faqpage(tmp_path: Path) -> None:
    feature = FeatureData(
        url="https://example.com",
        types={
            "FAQPage": {"required": {"mainEntity"}, "recommended": set()},
            "Question": {"required": {"acceptedAnswer", "name"}, "recommended": set()},
            "Answer": {"required": {"text"}, "recommended": set()},
        },
    )

    content = _read_output(tmp_path, feature)

    assert "sh:targetClass schema:FAQPage" in content
    assert "sh:targetClass schema:Question" not in content
    assert "sh:targetClass schema:Answer" not in content
    assert "sh:path schema:mainEntity" in content
    assert "sh:class schema:Question" in content
    assert "sh:path schema:acceptedAnswer" in content
    assert "sh:class schema:Answer" in content


def test_scopes_question_under_quiz(tmp_path: Path) -> None:
    feature = FeatureData(
        url="https://example.com",
        types={
            "Quiz": {"required": {"hasPart"}, "recommended": set()},
            "Question": {
                "required": {"acceptedAnswer", "eduQuestionType", "text"},
                "recommended": set(),
            },
        },
    )

    content = _read_output(tmp_path, feature)

    assert "sh:targetClass schema:Quiz" in content
    assert "sh:targetClass schema:Question" not in content
    assert "sh:path schema:hasPart" in content
    assert "sh:class schema:Question" in content


def test_scopes_offer_under_product(tmp_path: Path) -> None:
    feature = FeatureData(
        url="https://example.com",
        types={
            "Product": {"required": {"offers"}, "recommended": set()},
            "Offer": {"required": {"price"}, "recommended": set()},
            "AggregateOffer": {"required": {"lowPrice"}, "recommended": set()},
        },
    )

    content = _read_output(tmp_path, feature)

    assert "sh:targetClass schema:Product" in content
    assert "sh:targetClass schema:Offer" not in content
    assert "sh:targetClass schema:AggregateOffer" not in content
    assert "sh:path schema:offers" in content
    assert "sh:or (" in content
    assert "sh:class schema:Offer" in content
    assert "sh:class schema:AggregateOffer" in content


def test_scopes_howtostep_under_recipe(tmp_path: Path) -> None:
    feature = FeatureData(
        url="https://example.com",
        types={
            "Recipe": {"required": {"recipeInstructions"}, "recommended": set()},
            "HowToStep": {"required": {"text"}, "recommended": set()},
        },
    )

    content = _read_output(tmp_path, feature)

    assert "sh:targetClass schema:Recipe" in content
    assert "sh:targetClass schema:HowToStep" not in content
    assert "sh:path schema:recipeInstructions" in content
    assert "sh:class schema:HowToStep" in content


def test_scopes_profilepage_mainentity_person_or_org(tmp_path: Path) -> None:
    feature = FeatureData(
        url="https://example.com",
        types={
            "ProfilePage": {"required": {"mainEntity"}, "recommended": set()},
            "Person": {"required": {"name"}, "recommended": set()},
            "Organization": {"required": {"name"}, "recommended": set()},
        },
    )

    content = _read_output(tmp_path, feature)

    assert "sh:targetClass schema:ProfilePage" in content
    assert "sh:targetClass schema:Person" not in content
    assert "sh:targetClass schema:Organization" not in content
    assert "sh:path schema:mainEntity" in content
    assert "sh:or (" in content
    assert "sh:class schema:Person" in content
    assert "sh:class schema:Organization" in content


def test_scopes_course_parts(tmp_path: Path) -> None:
    feature = FeatureData(
        url="https://example.com",
        types={
            "Course": {"required": {"provider", "hasPart"}, "recommended": set()},
            "Organization": {"required": {"name"}, "recommended": set()},
            "CreativeWork": {"required": {"name"}, "recommended": set()},
        },
    )

    content = _read_output(tmp_path, feature)

    assert "sh:targetClass schema:Course" in content
    assert "sh:targetClass schema:Organization" not in content
    assert "sh:targetClass schema:CreativeWork" not in content
    assert "sh:path schema:provider" in content
    assert "sh:class schema:Organization" in content
    assert "sh:path schema:hasPart" in content
    assert "sh:class schema:CreativeWork" in content


def test_scopes_rating_under_review(tmp_path: Path) -> None:
    feature = FeatureData(
        url="https://example.com",
        types={
            "Review": {
                "required": {"reviewRating", "aggregateRating"},
                "recommended": set(),
            },
            "Rating": {"required": {"ratingValue"}, "recommended": set()},
            "AggregateRating": {"required": {"ratingValue"}, "recommended": set()},
        },
    )

    content = _read_output(tmp_path, feature)

    assert "sh:targetClass schema:Review" in content
    assert "sh:targetClass schema:Rating" not in content
    assert "sh:targetClass schema:AggregateRating" not in content
    assert "sh:path schema:reviewRating" in content
    assert "sh:class schema:Rating" in content
    assert "sh:path schema:aggregateRating" in content
    assert "sh:class schema:AggregateRating" in content


def test_emits_one_of_group_for_product(tmp_path: Path) -> None:
    feature = FeatureData(
        url="https://example.com",
        types={
            "Product": {"required": {"name"}, "recommended": set()},
            "Offer": {"required": {"price"}, "recommended": set()},
        },
        one_of={"Product": [{"review", "aggregateRating", "offers"}]},
    )

    content = _read_output(tmp_path, feature)

    assert "sh:targetClass schema:Product" in content
    assert "sh:or (" in content
    assert "sh:path schema:review" in content
    assert "sh:path schema:aggregateRating" in content
    assert "sh:path schema:offers" in content


def test_emits_fallback_alternative_one_of_group(tmp_path: Path) -> None:
    feature = FeatureData(
        url="https://example.com",
        types={"ImageObject": {"required": set(), "recommended": set()}},
        one_of={"ImageObject": [{"contentUrl", "url"}]},
    )

    content = _read_output(tmp_path, feature)

    assert "sh:targetClass schema:ImageObject" in content
    assert "sh:or (" in content
    assert "sh:path schema:contentUrl" in content
    assert "sh:path schema:url" in content


def test_scopes_review_under_product_with_notes(tmp_path: Path) -> None:
    feature = FeatureData(
        url="https://example.com",
        types={
            "Product": {"required": {"review"}, "recommended": set()},
            "Review": {
                "required": {"reviewRating", "positiveNotes"},
                "recommended": set(),
            },
            "Rating": {"required": {"ratingValue"}, "recommended": set()},
            "ItemList": {"required": {"itemListElement"}, "recommended": set()},
            "ListItem": {"required": {"name"}, "recommended": set()},
        },
    )

    content = _read_output(tmp_path, feature)

    assert "sh:targetClass schema:Product" in content
    assert "sh:targetClass schema:Review" not in content
    assert "sh:class schema:Review" in content
    assert "sh:class schema:ItemList" in content
    assert "sh:class schema:ListItem" in content


def test_emits_option_branches_for_required_property_sets(tmp_path: Path) -> None:
    feature = FeatureData(
        url="https://example.com",
        types={
            "MerchantReturnPolicy": {
                "required": set(),
                "recommended": set(),
            }
        },
        one_of_option_groups={
            "MerchantReturnPolicy": [
                [
                    {"applicableCountry", "returnPolicyCategory"},
                    {"merchantReturnLink"},
                ]
            ]
        },
    )

    content = _read_output(tmp_path, feature)

    assert "sh:targetClass schema:MerchantReturnPolicy" in content
    assert "sh:path schema:applicableCountry" in content
    assert "sh:path schema:returnPolicyCategory" in content
    assert "sh:path schema:merchantReturnLink" in content


def test_schemaorg_range_allows_literals(tmp_path: Path) -> None:
    from wordlift_sdk.validation.generator import _render_property_shape

    lines = _render_property_shape(
        URIRef("http://schema.org/item"), [URIRef("http://schema.org/Thing")]
    )
    content = "\n".join(lines)

    assert "sh:datatype <http://www.w3.org/2001/XMLSchema#anyURI>" in content
    assert "sh:datatype <http://www.w3.org/2001/XMLSchema#string>" in content
    assert (
        "sh:datatype <http://www.w3.org/1999/02/22-rdf-syntax-ns#langString>" in content
    )


def test_schemaorg_range_accepts_untyped_thing_references(tmp_path: Path) -> None:
    from wordlift_sdk.validation.generator import _render_property_shape

    lines = _render_property_shape(
        URIRef("http://schema.org/item"), [URIRef("http://schema.org/Thing")]
    )
    content = "\n".join(lines)

    assert "sh:nodeKind sh:BlankNodeOrIRI" in content
    assert "sh:class schema:Thing" not in content


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


def test_breadcrumb_listitem_item_is_exempted_for_one_entry(tmp_path: Path) -> None:
    feature = FeatureData(
        url="https://example.com",
        types={
            "BreadcrumbList": {"required": {"itemListElement"}, "recommended": set()},
            "ListItem": {
                "required": {"position", "name", "item"},
                "recommended": set(),
            },
        },
    )

    content = _read_output(tmp_path, feature)

    assert "sh:qualifiedMaxCount 1 ;" in content
    assert "sh:not [" in content
    node_shape = content.split("sh:qualifiedValueShape")[0]
    assert "sh:path schema:item ;\n        sh:minCount 1 ;" not in node_shape


def test_itemlist_listitem_item_stays_unconditional(tmp_path: Path) -> None:
    feature = FeatureData(
        url="https://example.com",
        types={
            "ItemList": {"required": {"itemListElement"}, "recommended": set()},
            "ListItem": {"required": {"position", "item"}, "recommended": set()},
        },
    )

    content = _read_output(tmp_path, feature)

    assert "sh:qualifiedMaxCount" not in content
    assert "sh:path schema:item ;\n        sh:minCount 1 ;" in content
