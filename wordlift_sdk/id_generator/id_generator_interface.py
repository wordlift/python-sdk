from abc import ABC, abstractmethod


class IdGeneratorInterface(ABC):

    @abstractmethod
    def create(self, *args):
        pass
