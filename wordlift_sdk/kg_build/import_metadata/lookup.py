from __future__ import annotations

import logging
from collections.abc import Collection
from typing import Any, Protocol

from gql import gql
from rdflib import Graph

from wordlift_sdk.graphql.client import GqlClientProvider
from wordlift_sdk.protocol.errors import summarize_error
from wordlift_sdk.protocol.retry_policy import retry_transient

from .hashing import set_import_hash
from .subjects import import_subjects

logger = logging.getLogger(__name__)

IMPORT_HASH_LOOKUP_EXTENSION = "kg_build.import_hash_lookup"

_BATCH_SIZE = 100


class ImportHashLookup(Protocol):
    """Read the ``seovoc:importHash`` stored on graph entities."""

    async def import_hashes(self, iris: Collection[str]) -> dict[str, str]:
        """Map each IRI that has a stored hash to it; IRIs without one are left out."""
        ...


class GraphQlImportHashLookup:
    """Read stored import hashes through the GraphQL ``resource`` field.

    ``iriConstraint`` compares IRIs as literals and matches nothing, so each
    IRI is looked up by ``resource(iri:)``, many to one aliased query.
    ``seovoc:`` is private: the provider sends ``X-include-Private``.
    """

    def __init__(self, client_provider: GqlClientProvider) -> None:
        self._client_provider = client_provider

    @retry_transient(logger)
    async def import_hashes(self, iris: Collection[str]) -> dict[str, str]:
        ordered = sorted(set(iris))
        if not ordered:
            return {}
        hashes: dict[str, str] = {}
        async with self._client_provider.create() as session:
            for start in range(0, len(ordered), _BATCH_SIZE):
                batch = ordered[start : start + _BATCH_SIZE]
                hashes.update(await self._batch(session, batch))
        return hashes

    @staticmethod
    async def _batch(session: Any, iris: list[str]) -> dict[str, str]:
        params = ", ".join(f"$i{n}: Ref!" for n in range(len(iris)))
        fields = " ".join(
            f'e{n}: resource(iri: $i{n}) {{ hash: string(name: "seovoc:importHash") }}'
            for n in range(len(iris))
        )
        query = gql(f"query storedImportHashes({params}) {{ {fields} }}")
        variables = {f"i{n}": iri for n, iri in enumerate(iris)}
        response = await session.execute(query, variable_values=variables)
        return {
            iri: str(entry["hash"])
            for n, iri in enumerate(iris)
            if (entry := response.get(f"e{n}")) and entry.get("hash")
        }


async def restore_stored_import_hash(
    graph: Graph, dataset_uri: str, lookup: ImportHashLookup
) -> bool:
    """Put back on *graph* the import hash its entities already store.

    For graphs with no URL to look their hash up by, such as static templates.
    The hash is restored only when every import subject stores the same one,
    the hash a previous write stamped on all of them. Returns whether it was.
    """
    roots = import_subjects(graph, dataset_uri)
    if not roots:
        return False
    try:
        stored = await lookup.import_hashes([str(subject) for subject in roots])
    except Exception as exc:  # noqa: BLE001 - a failed lookup must not block the write
        logger.warning(
            "Stored import hash lookup failed; writing the graph: %s",
            summarize_error(exc),
        )
        return False
    hashes = {stored.get(str(subject)) for subject in roots}
    if len(hashes) != 1 or None in hashes:
        return False
    (stored_hash,) = hashes
    for subject in roots:
        set_import_hash(graph, subject, stored_hash)
    return True
