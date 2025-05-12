from abc import abstractmethod
from dataclasses import dataclass
from typing import Protocol

from pandas import Series
from wordlift_client import EntityPatchRequest

from .protocol_context import ProtocolContext


@dataclass
class ParseHtmlInput:
    entity_id: str
    entity_url: str
    html: str
    row: Series


class ParseHtmlProtocolInterface(Protocol):
    context: ProtocolContext

    def __init__(self, context: ProtocolContext):
        self.context = context

    @abstractmethod
    async def parse_html(self, parse_html_input: ParseHtmlInput) -> list[EntityPatchRequest]:
        ...
