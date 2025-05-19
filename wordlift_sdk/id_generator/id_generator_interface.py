from abc import ABC, abstractmethod


class IdGeneratorInterface(ABC):

    @abstractmethod
    def create(self, base_uri: str, *args):
        pass
