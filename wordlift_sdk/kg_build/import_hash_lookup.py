from __future__ import annotations

from collections.abc import Collection
from typing import Protocol

from gql import gql

from ..graphql.client import GqlClientProvider

IMPORT_HASH_LOOKUP_EXTENSION = "kg_build.import_hash_lookup"

_BATCH_SIZE = 100


class ImportHashLookup(Protocol):
    """Read the ``seovoc:importHash`` stored on graph entities."""

    async def import_hashes(self, iris: Collection[str]) -> dict[str, str]:
        """Map each IRI that has a stored hash to it; IRIs without one are left out."""
        ...


class GraphQlImportHashLookup:
    """Read stored import hashes through the GraphQL ``resource`` field.

    The ``iriConstraint`` filter compares IRIs as literals and matches nothing,
    so each IRI is looked up by ``resource(iri:)``, many to one aliased query.
    ``seovoc:`` is a private namespace: the provider sends ``X-include-Private``.
    """

    def __init__(self, client_provider: GqlClientProvider) -> None:
        self._client_provider = client_provider

    async def import_hashes(self, iris: Collection[str]) -> dict[str, str]:
        ordered = sorted(set(iris))
        hashes: dict[str, str] = {}
        for start in range(0, len(ordered), _BATCH_SIZE):
            hashes.update(await self._batch(ordered[start : start + _BATCH_SIZE]))
        return hashes

    async def _batch(self, iris: list[str]) -> dict[str, str]:
        params = ", ".join(f"$i{n}: Ref!" for n in range(len(iris)))
        fields = " ".join(
            f'e{n}: resource(iri: $i{n}) {{ hash: string(name: "seovoc:importHash") }}'
            for n in range(len(iris))
        )
        query = gql(f"query storedImportHashes({params}) {{ {fields} }}")
        variables = {f"i{n}": iri for n, iri in enumerate(iris)}
        async with self._client_provider.create() as session:
            response = await session.execute(query, variable_values=variables)
        return {
            iri: str(entry["hash"])
            for n, iri in enumerate(iris)
            if (entry := response.get(f"e{n}")) and entry.get("hash")
        }
