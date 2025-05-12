from dataclasses import dataclass

from wordlift_client import Configuration


@dataclass
class ProtocolContext:
    configuration: Configuration
    types: list[str]
