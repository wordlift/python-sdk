from __future__ import annotations

from rdflib import URIRef

SEOVOC_IMPORT_HASH = URIRef("https://w3id.org/seovoc/importHash")
SEOVOC_DATE_IMPORTED = URIRef("https://w3id.org/seovoc/dateImported")
# Write bookkeeping, not content: neither one feeds the import hash.
IMPORT_METADATA_PREDICATES = frozenset({SEOVOC_IMPORT_HASH, SEOVOC_DATE_IMPORTED})
