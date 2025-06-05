from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import AsyncGenerator


@dataclass
class Url:
    value: str
    iri: str | None = None
    date_modified: datetime | None = None


class UrlSource(ABC):
    @abstractmethod
    async def urls(self) -> AsyncGenerator[Url, None]:
        """Asynchronously yields Url objects."""
        pass
