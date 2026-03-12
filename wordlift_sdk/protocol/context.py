from dataclasses import dataclass, field
from typing import Any

from wordlift_client import AccountInfo, Configuration

from .entity_patch import EntityPatchQueue
from .graph import GraphQueue
from ..configuration import ConfigurationProvider
from ..id_generator import IdGenerator


@dataclass
class Context:
    account: AccountInfo
    client_configuration: Configuration
    id_generator: IdGenerator

    configuration_provider: ConfigurationProvider

    # Queues where clients can append data to be written to the graph.
    graph_queue: GraphQueue
    entity_patch_queue: EntityPatchQueue
    extensions: dict[str, Any] = field(default_factory=dict)

    # Adaptive concurrency settings for entity patching.
    patch_concurrency: int = 10
    patch_concurrency_max: int = 20
