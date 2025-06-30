from dataclasses import dataclass

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
