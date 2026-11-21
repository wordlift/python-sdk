"""Decide which subject owns each looked-up IRI (#62).

A page's URL belongs on its main entity only. When a lookup matches several
subjects (for example an ``Article`` and a ``Review`` that both carry the page
URL), exactly one of them owns the looked-up IRI and the others are reported,
so the mapping can be fixed.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from rdflib import Graph, URIRef

from ...iri_lookup import IriLookup

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LookupOwnership:
    """``owners`` and ``losers`` both map a subject to its looked-up IRI."""

    owners: dict[URIRef, URIRef]
    losers: dict[URIRef, URIRef]


def resolve_lookup_ownership(
    graph: Graph,
    iri_lookup: IriLookup | None,
    *,
    is_candidate: Callable[[URIRef], bool],
    rank: Callable[[URIRef], Any],
) -> LookupOwnership:
    """Give each looked-up IRI to the lowest-``rank`` candidate subject."""
    if iri_lookup is None:
        return LookupOwnership(owners={}, losers={})
    candidates: defaultdict[URIRef, list[URIRef]] = defaultdict(list)
    for subject in sorted(
        {s for s in graph.subjects() if isinstance(s, URIRef)}, key=str
    ):
        if not is_candidate(subject):
            continue
        value = str(iri_lookup.iri_for_subject(graph, subject) or "").strip()
        if value:
            candidates[URIRef(value)].append(subject)

    owners: dict[URIRef, URIRef] = {}
    losers: dict[URIRef, URIRef] = {}
    for iri, subjects in candidates.items():
        owner = min(subjects, key=rank)
        owners[owner] = iri
        others = [subject for subject in subjects if subject != owner]
        losers.update(dict.fromkeys(others, iri))
        if others:
            logger.warning(
                "canonical_ids: %d subjects match lookup IRI %s; %s keeps it, "
                "nesting %s under it. Put the page URL on the main entity only.",
                len(subjects),
                iri,
                owner,
                ", ".join(str(other) for other in others),
            )
    return LookupOwnership(owners=owners, losers=losers)
