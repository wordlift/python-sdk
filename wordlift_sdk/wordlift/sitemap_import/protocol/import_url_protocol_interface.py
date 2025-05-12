from abc import abstractmethod
from dataclasses import dataclass
from typing import Protocol

from .protocol_context import ProtocolContext


@dataclass
class ImportUrlInput:
    url_list: list[str]


class ImportUrlProtocolInterface(Protocol):
    context: ProtocolContext

    def __init__(self, context: ProtocolContext):
        self.context = context

    @abstractmethod
    async def import_url(self, import_url_input: ImportUrlInput) -> None:
        ...
