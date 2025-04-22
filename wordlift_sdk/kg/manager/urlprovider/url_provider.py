from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncGenerator


@dataclass
class Url:
    value: str


class UrlProvider(ABC):
    @abstractmethod
    async def urls(self) -> AsyncGenerator[Url, None]:
        """Asynchronously yields Url objects."""
        pass
