from abc import abstractmethod, ABC
from typing import AsyncGenerator

from .graph_bag import GraphBag


class GraphProvider(ABC):

    @abstractmethod
    async def graphs(self) -> AsyncGenerator[GraphBag, None]:
        pass
