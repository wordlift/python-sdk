from dataclasses import dataclass

from wordlift_client import AccountInfo
from wordlift_client import Configuration

from ....id_generator.id_generator_interface import IdGeneratorInterface
from ....protocol.graph import GraphQueue


@dataclass
class ProtocolContext:
    account: AccountInfo
    configuration: Configuration
    id_generator: IdGeneratorInterface
    types: list[str]
    graph_queue: GraphQueue
