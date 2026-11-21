"""Decide which subjects take each looked-up IRI (#62).

A page's URL belongs on its main entity only. The lookup maps that URL to the
IRI the page already has in the KG.

- Subjects nothing links to ("roots") that match the lookup keep it, as before.
- When no root matches, for example because the page root is linked from its
  own ``FAQPage.about``, the best-ranked matching subject takes it instead of
  the IRI being dropped and the root re-minted.
- When several subjects match the same lookup, a warning names them so the
  mapping can be fixed.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable, Set
from typing import Any

from rdflib import Graph, URIRef

from ...iri_lookup import IriLookup

logger = logging.getLogger(__name__)


def resolve_lookup_owners(
    graph: Graph,
    iri_lookup: IriLookup | None,
    *,
    roots: Set[URIRef],
    is_candidate: Callable[[URIRef], bool],
    rank: Callable[[URIRef, URIRef], Any],
) -> dict[URIRef, URIRef]:
    """Map each subject that takes a looked-up IRI to that IRI.

    ``rank(subject, iri)`` orders non-root candidates, lowest first; it is only
    used when no root matches the lookup.
    """
    if iri_lookup is None:
        return {}
    matches: defaultdict[URIRef, list[URIRef]] = defaultdict(list)
    for subject in sorted(
        {s for s in graph.subjects() if isinstance(s, URIRef)}, key=str
    ):
        if not is_candidate(subject):
            continue
        value = str(iri_lookup.iri_for_subject(graph, subject) or "").strip()
        if value:
            matches[URIRef(value)].append(subject)

    owners: dict[URIRef, URIRef] = {}
    for iri, subjects in matches.items():
        chosen = [subject for subject in subjects if subject in roots] or [
            min(subjects, key=lambda subject: rank(subject, iri))
        ]
        owners.update(dict.fromkeys(chosen, iri))
        if len(subjects) > 1:
            logger.warning(
                "canonical_ids: %d subjects match lookup IRI %s (%s); %s keep it. "
                "Put the page URL on the main entity only.",
                len(subjects),
                iri,
                ", ".join(str(subject) for subject in subjects),
                ", ".join(str(subject) for subject in chosen),
            )
    return owners
