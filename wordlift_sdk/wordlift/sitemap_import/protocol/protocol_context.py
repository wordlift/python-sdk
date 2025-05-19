from dataclasses import dataclass

from wordlift_client import Configuration

from wordlift_sdk.graph import GraphQueue


@dataclass
class ProtocolContext:
    configuration: Configuration
    types: list[str]
    graph_queue: GraphQueue = GraphQueue()
