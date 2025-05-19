from dataclasses import dataclass

from wordlift_client import AccountInfo
from wordlift_client import Configuration

from wordlift_sdk.graph import GraphQueue
from wordlift_sdk.id_generator.id_generator_interface import IdGeneratorInterface


@dataclass
class ProtocolContext:
    account: AccountInfo
    configuration: Configuration
    id_generator: IdGeneratorInterface
    types: list[str]
    graph_queue: GraphQueue
