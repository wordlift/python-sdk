from dataclasses import dataclass
from wordlift_client import EntityPatchRequest


@dataclass
class EntityPatch:
    iri: str
    requests: list[EntityPatchRequest]
