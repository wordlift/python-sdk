from __future__ import annotations

from dataclasses import dataclass
import re


def type_name_to_container(type_name: str) -> str:
    """Convert a Schema.org type name to dashed plural container."""
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1-\2", type_name)
    dashed = re.sub("([a-z0-9])([A-Z])", r"\1-\2", s1).lower()
    if dashed.endswith("s"):
        return f"{dashed}es"
    if dashed.endswith("y") and len(dashed) > 1 and dashed[-2] not in "aeiou":
        return f"{dashed[:-1]}ies"
    return f"{dashed}s"


@dataclass(frozen=True)
class DependentRule:
    child_type: str
    parent_type: str
    parent_predicates: tuple[str, ...]


@dataclass(frozen=True)
class IdPolicy:
    dependent_rules: tuple[DependentRule, ...]
    type_aliases: dict[str, str]
    container_overrides: dict[str, str]
    page_root_types: tuple[str, ...]
    entity_root_types: tuple[str, ...]
    root_type_precedence: tuple[str, ...]

    def normalize_type_name(self, type_name: str) -> str:
        return self.type_aliases.get(type_name, type_name)

    def container_for_type(self, type_name: str) -> str:
        normalized = self.normalize_type_name(type_name)
        return self.container_overrides.get(
            normalized, type_name_to_container(normalized)
        )

    def dependency_rule_for(self, child_type: str) -> DependentRule | None:
        normalized = self.normalize_type_name(child_type)
        for rule in self.dependent_rules:
            if rule.child_type == normalized:
                return rule
        return None

    def is_dependent(self, type_name: str) -> bool:
        return self.dependency_rule_for(type_name) is not None

    def is_page_root_type(self, type_name: str) -> bool:
        normalized = self.normalize_type_name(type_name)
        return normalized in self.page_root_types

    def is_entity_root_type(self, type_name: str) -> bool:
        normalized = self.normalize_type_name(type_name)
        return normalized in self.entity_root_types

    def preferred_type(self, type_names: set[str]) -> str:
        normalized = {self.normalize_type_name(name) for name in type_names}
        for candidate in self.root_type_precedence:
            if candidate in normalized:
                return candidate
        return sorted(normalized)[0] if normalized else "Thing"


DEFAULT_ID_POLICY = IdPolicy(
    dependent_rules=(
        DependentRule(
            child_type="Offer",
            parent_type="Product",
            parent_predicates=("offers",),
        ),
        DependentRule(
            child_type="PriceSpecification",
            parent_type="Offer",
            parent_predicates=("priceSpecification",),
        ),
        DependentRule(
            child_type="FAQPage",
            parent_type="WebPage",
            # subjectOf covers the pattern MainEntity -> subjectOf -> FAQPage
            parent_predicates=("hasPart", "mainEntity", "subjectOf"),
        ),
        DependentRule(
            child_type="Question",
            parent_type="FAQPage",
            parent_predicates=("mainEntity",),
        ),
        DependentRule(
            child_type="Answer",
            parent_type="Question",
            parent_predicates=("acceptedAnswer",),
        ),
        DependentRule(
            child_type="Rating",
            parent_type="Review",
            parent_predicates=("reviewRating",),
        ),
        DependentRule(
            child_type="HowTo",
            parent_type="WebPage",
            parent_predicates=("mainEntity", "mentions"),
        ),
        DependentRule(
            child_type="HowToStep",
            parent_type="HowTo",
            parent_predicates=("step",),
        ),
        DependentRule(
            child_type="ImageObject",
            parent_type="WebPage",
            parent_predicates=("image",),
        ),
        DependentRule(
            child_type="VideoObject",
            parent_type="WebPage",
            parent_predicates=("video",),
        ),
    ),
    # FinancialProduct follows Product ID rules by default.
    type_aliases={"FinancialProduct": "Product"},
    container_overrides={"Thing": "things"},
    page_root_types=("WebPage",),
    entity_root_types=("Product", "Service", "Brand"),
    root_type_precedence=(
        "WebPage",
        "Product",
        "Service",
        "Brand",
        "Offer",
        "Thing",
    ),
)
